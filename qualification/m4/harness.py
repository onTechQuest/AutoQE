"""External controller. Only normal artifact paths cross into fresh worker processes."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = json.loads(Path(__file__).with_name("profiles.json").read_text(encoding="utf-8"))
REVISION = MANIFEST["revision"]


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root), *args],
        text=True, stderr=subprocess.PIPE,
    ).strip()


def listeners() -> list[dict[str, object]]:
    result = []
    for line in subprocess.check_output(["netstat", "-ano"], text=True).splitlines():
        fields = line.split()
        if len(fields) >= 5 and fields[0] == "TCP" and fields[3] == "LISTENING" and fields[1].rsplit(":", 1)[-1] in {"3000", "3001"}:
            result.append({"address": fields[1], "pid": int(fields[4])})
    return result


def worker_environment(reference: Path) -> dict[str, str]:
    allowed = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP", "USERPROFILE",
               "LOCALAPPDATA", "APPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "HOMEDRIVE", "HOMEPATH",
               "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE"}
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="safe.directory", GIT_CONFIG_VALUE_0=reference.as_posix(), PYTHONDONTWRITEBYTECODE="1")
    return env


def seed_password(reference: Path) -> str:
    value = os.environ.get("RWA_TEST_PASSWORD")
    if not value:
        match = re.search(r"^SEED_DEFAULT_USER_PASSWORD\s*=\s*(.+?)\s*$", (reference / ".env").read_text(), re.M)
        if not match:
            raise RuntimeError("Runtime seed credential unavailable")
        value = match.group(1).strip().strip('"').strip("'")
    return value


class IsolatedTarget:
    def __init__(self, reference: Path, parent: Path, yarn: Path):
        self.reference = reference.resolve()
        self.parent = parent.resolve()
        self.path = self.parent / uuid4().hex
        self.yarn = yarn
        self.active = False
        self.created = False
        self.process = None
        self.observed_listeners: list[dict[str, object]] = []

    def __enter__(self):
        if git(self.reference, "rev-parse", "HEAD") != REVISION or git(self.reference, "status", "--porcelain"):
            raise RuntimeError("Canonical reference must be clean and pinned")
        self.parent.mkdir(parents=True, exist_ok=True)
        try:
            git(self.reference, "worktree", "add", "--detach", str(self.path), REVISION)
            self.created = True
            subprocess.run(["cmd", "/c", "mklink", "/J", str(self.path / "node_modules"), str(self.reference / "node_modules")],
                           check=True, capture_output=True)
            return self
        except Exception:
            self.close()
            raise

    def apply(self, profile: dict[str, str]) -> None:
        if self.active or self.process is not None:
            raise RuntimeError("Only one product patch may be activated before startup")
        if profile not in MANIFEST["profiles"]:
            raise ValueError("Unregistered controlled profile")
        target = (self.path / profile["file"]).resolve()
        if not target.is_relative_to(self.path.resolve()):
            raise ValueError("Patch escaped isolated target")
        text = target.read_text(encoding="utf-8")
        if text.count(profile["before"]) != 1:
            raise RuntimeError("Pinned patch point was not unique")
        target.write_text(text.replace(profile["before"], profile["after"], 1), encoding="utf-8")
        self.active = True

    def start(self) -> None:
        if listeners():
            raise RuntimeError("Reference ports already occupied")
        env = worker_environment(self.reference)
        env.update(NODE_OPTIONS=f"--require={ROOT / 'scripts/force_loopback_bind.cjs'}", BROWSER="none")
        self.process = subprocess.Popen(["node", str(self.yarn), "start"], cwd=self.path, env=env,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        creationflags=subprocess.CREATE_NO_WINDOW)
        for attempt in range(120):
            running = listeners()
            if any(item["address"].rsplit(":", 1)[0] not in {"127.0.0.1", "[::1]"} for item in running):
                raise RuntimeError("Non-loopback listener detected")
            try:
                with httpx.Client(timeout=2, trust_env=False) as client:
                    ready = all(client.get(url).status_code == 200 for url in ("http://localhost:3000/", "http://localhost:3001/"))
                if ready and {item["address"].rsplit(":", 1)[-1] for item in running} == {"3000", "3001"}:
                    self.observed_listeners = running
                    return
            except httpx.HTTPError:
                pass
            if self.process.poll() is not None:
                raise RuntimeError("Isolated target exited before readiness")
            if attempt % 10 == 0:
                print("Waiting for isolated loopback target readiness.", flush=True)
            time.sleep(1)
        raise RuntimeError("Isolated target readiness timeout")

    def close(self) -> None:
        # Validate every removal target, and unlink the junction before Git cleanup.
        if self.path.parent != self.parent or not re.fullmatch(r"[0-9a-f]{32}", self.path.name) or self.path == self.reference:
            raise RuntimeError("Unsafe cleanup target")
        if self.process is not None:
            subprocess.run(["taskkill", "/PID", str(self.process.pid), "/T", "/F"], capture_output=True)
            self.process.wait(timeout=20)
            self.process = None
            for _ in range(30):
                if not listeners():
                    break
                time.sleep(0.5)
            if listeners():
                raise RuntimeError("Target listeners remained after shutdown")
        junction = self.path / "node_modules"
        if junction.is_junction():
            junction.rmdir()
        if self.created:
            git(self.reference, "worktree", "remove", "--force", str(self.path))
            self.created = False
        if self.path.exists():
            raise RuntimeError("Isolated target was not removed")

    def __exit__(self, *_):
        self.close()


def run_triage(profile: Path, spec: Path, execution: Path, output: Path, reference: Path) -> dict:
    result = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/triage_execution.py"),
                             "--project-profile", str(profile), "--test-spec", str(spec),
                             "--execution-record", str(execution), "--output", str(output)],
                            cwd=ROOT, env=worker_environment(reference), capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError("Triage worker failed")
    return json.loads(output.read_text())


def execute(reference: Path, runtime: Path, spec: Path, output: Path) -> dict:
    destination = output / "runtime" / uuid4().hex
    destination.mkdir(parents=True)
    env = worker_environment(reference)
    password = seed_password(reference)
    env["RWA_TEST_PASSWORD"] = password
    profile = ROOT / "examples/rwa/project-profile.json"
    command = [sys.executable, "-B", str(ROOT / "scripts/execute_testspec.py"),
               "--project-profile", str(profile), "--test-spec", str(spec), "--provider", "api",
               "--rwa-root", str(runtime), "--reference-root", str(reference),
               "--output", str(destination), "--evidence-output", str(destination / "evidence")]
    process = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, timeout=180)
    env.pop("RWA_TEST_PASSWORD")
    if process.returncode not in {0, 1}:
        raise RuntimeError("Execution worker failed without a normalized record")
    result = json.loads(process.stdout)
    execution = Path(result["artifact"])
    record = json.loads(execution.read_text())
    triage_path = destination / (uuid4().hex + ".json")
    triage = run_triage(profile, spec, execution, triage_path, reference)
    audit_runtime(destination, password)
    return {"status": record["status"], "classification": triage["classification"],
            "testspec_sha256": hashlib.sha256(spec.read_bytes()).hexdigest(),
            "execution": str(execution.relative_to(ROOT)), "triage": str(triage_path.relative_to(ROOT)),
            "duration_ms": record["duration_ms"]}


def audit_runtime(directory: Path, password: str) -> None:
    forbidden = {"password", "cookie", "cookies", "headers", "request_body", "response_body", "access_token", "secret"}
    def inspect(value):
        if isinstance(value, dict):
            if forbidden.intersection(key.lower() for key in value):
                raise RuntimeError("Private evidence key detected")
            for child in value.values():
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        content = path.read_bytes()
        if password.encode() in content:
            raise RuntimeError("Credential appeared in runtime evidence")
        if path.suffix == ".json":
            text = content.decode("utf-8")
            if any(profile["id"] in text for profile in MANIFEST["profiles"]):
                raise RuntimeError("Controller identity appeared in runtime artifacts")
            inspect(json.loads(text))


def qualify(reference: Path, yarn: Path, output: Path) -> dict:
    reference = reference.resolve()
    output = output.resolve()
    if not output.is_relative_to(ROOT / "reports") or output.exists():
        raise ValueError("Qualification requires a fresh ignored reports directory")
    output.mkdir(parents=True)
    report = {"products": [], "non_product": [], "live_model_calls": 0, "listeners": [], "result": "FAIL"}
    targets = output / "targets"
    try:
        if listeners() or git(reference, "status", "--porcelain") or git(reference, "rev-parse", "HEAD") != REVISION:
            raise RuntimeError("Reference preflight failed")
        for profile in MANIFEST["profiles"]:
            spec = ROOT / profile["test_spec"]
            pair = {"profile": profile["id"], "expected_classification": profile["expected_classification"]}
            for phase in ("healthy", "faulty"):
                with IsolatedTarget(reference, targets, yarn) as target:
                    if phase == "faulty":
                        target.apply(profile)
                    target.start()
                    report["listeners"].extend(target.observed_listeners)
                    pair[phase] = execute(reference, target.path, spec, output)
                print(json.dumps({"experiment": profile["id"], "phase": phase, **pair[phase]}), flush=True)
            pair["same_testspec"] = pair["healthy"]["testspec_sha256"] == pair["faulty"]["testspec_sha256"]
            pair["passed"] = pair["same_testspec"] and pair["healthy"]["status"] == "PASSED" and pair["faulty"]["status"] == "FAILED" and pair["faulty"]["classification"] == profile["expected_classification"]
            report["products"].append(pair)
            if not pair["passed"]:
                raise RuntimeError("Healthy/faulty product comparison failed")
        spec = ROOT / "examples/rwa/execution/invalid-payment.json"
        environment = execute(reference, reference, spec, output)
        report["non_product"].append({"expected": "ENVIRONMENT_FAILURE", **environment})
        with IsolatedTarget(reference, targets, yarn) as target:
            # A seed fingerprint mismatch is data preparation evidence, not a product patch.
            seed = target.path / "data/database-seed.json"
            seed.write_bytes(seed.read_bytes() + b"\n")
            target.start()
            report["listeners"].extend(target.observed_listeners)
            data = execute(reference, target.path, spec, output)
        report["non_product"].append({"expected": "DATA_FAILURE", **data})
        inputs = output / "runtime" / uuid4().hex
        inputs.mkdir()
        unsupported = json.loads(spec.read_text())
        unsupported["steps"][-1]["target"] = "unregistered account operation"
        input_path = inputs / (uuid4().hex + ".json")
        input_path.write_text(json.dumps(unsupported))
        report["non_product"].append({"expected": "UNSUPPORTED_BEHAVIOR", **execute(reference, reference, input_path, output)})
        healthy_record = json.loads((ROOT / report["products"][0]["healthy"]["execution"]).read_text())
        for expected in ("UNKNOWN", "TEST_DEFECT"):
            fixture = json.loads(json.dumps(healthy_record))
            fixture.update(producer="autoqe-evidence-fixture", limitations=["Synthetic evidence fixture; not an observed target failure."],
                           status="INCOMPLETE", failure_category="UNKNOWN", environment_identity={})
            if expected == "UNKNOWN":
                fixture["assertion_results"] = []
            else:
                fixture["assertion_results"][0]["expected"] = "An incompatible test-side assertion definition."
            fixture_path, triage_path = inputs / (uuid4().hex + ".json"), inputs / (uuid4().hex + ".json")
            fixture_path.write_text(json.dumps(fixture))
            triage = run_triage(ROOT / "examples/rwa/project-profile.json", spec, fixture_path, triage_path, reference)
            report["non_product"].append({"expected": expected, "classification": triage["classification"], "kind": "synthetic-evidence-fixture"})
        audit_runtime(output / "runtime", seed_password(reference))
        report["counts"] = {
            "product_faults_attempted": len(report["products"]),
            "product_faults_detected": sum(pair["faulty"]["status"] != "PASSED" for pair in report["products"]),
            "healthy_baselines_passed": sum(pair["healthy"]["status"] == "PASSED" for pair in report["products"]),
            "faulty_runs_incorrectly_passed": sum(pair["faulty"]["status"] == "PASSED" for pair in report["products"]),
        }
        if all(case["expected"] == case["classification"] for case in report["non_product"]):
            report["result"] = "PASS"
    except Exception as exc:
        report["exception_type"] = type(exc).__name__
        print("Qualification stopped: " + type(exc).__name__, flush=True)
    finally:
        report["final_listeners"] = listeners()
        report["canonical_status"] = git(reference, "status", "--porcelain")
        report["canonical_revision"] = git(reference, "rev-parse", "HEAD")
        report["temporary_targets_remaining"] = [str(path) for path in targets.iterdir()] if targets.exists() else []
        if report["final_listeners"] or report["canonical_status"] or report["temporary_targets_remaining"]:
            report["result"] = "FAIL"
        (output / "qualification.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"result": report["result"], "report": str(output / "qualification.json")}), flush=True)
    return report
