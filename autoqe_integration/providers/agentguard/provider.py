"""Pinned external scorer provider; all evaluator imports remain in the worker."""

from pathlib import Path
import re
import subprocess
import sys

from autoqe_integration.contracts import ExternalEvaluationRequest, ExternalEvaluationResult, read_json
from autoqe_integration.transport.local_process import LocalProcessTransport, TransportError

QUALIFIED_REVISION = "ee104f90fe9c0c23f320ab110fdd2c9adf20d37c"
PROVIDER_VERSION = "1.0.0"


class AgentGuardEvaluationProvider:
    def __init__(self, *, evaluator_root: Path, python_executable: Path, transport=None):
        self.root = evaluator_root.resolve()
        self.executable = python_executable.resolve()
        self.worker = Path(__file__).with_name("worker.py").resolve()
        self.transport = transport or LocalProcessTransport()

    def _revision(self):
        command = ["git", "-c", f"safe.directory={self.root.as_posix()}", "-C", str(self.root)]
        revision = subprocess.run(command + ["rev-parse", "HEAD"], capture_output=True, text=True,
                                  check=True, timeout=5, shell=False).stdout.strip()
        status = subprocess.run(command + ["status", "--porcelain", "--untracked-files=all"],
                                capture_output=True, text=True, check=True, timeout=5, shell=False).stdout.strip()
        return revision, status

    def evaluate(self, request: ExternalEvaluationRequest) -> ExternalEvaluationResult:
        request = ExternalEvaluationRequest.model_validate_json(request.stable_json())
        revision = None

        def result(status, *, attempted=False, native=None, error=None):
            return ExternalEvaluationResult(
                request=request, request_sha256=request.sha256, provider_id="agentguard",
                provider_revision=revision, provider_version=PROVIDER_VERSION, status=status,
                attempted=attempted, passed=native["overall_pass"] if native else None,
                native_result=native, evaluated_dimensions=[request.evaluation_dimension] if native else [],
                not_applicable=["tool_selection", "tool_arguments", "semantic_quality", "operational_telemetry"],
                errors=[error] if error else [],
                limitations=["CLASSIFICATION_ONLY", "NO_RATIONALE_EVALUATION", "EXTERNAL_LINEAGE_ONLY"],
            )

        if (not self.root.is_dir() or not self.worker.is_file() or not self.executable.is_file()
                or self.executable == Path(sys.executable).resolve()):
            return result("INCOMPLETE", error="ENVIRONMENT_UNAVAILABLE")
        try:
            observed, dirty = self._revision()
        except (OSError, subprocess.SubprocessError):
            return result("INCOMPLETE", error="ENVIRONMENT_UNAVAILABLE")
        if not re.fullmatch(r"[0-9a-f]{40}", observed):
            return result("INCOMPLETE", error="REVISION_MISMATCH")
        revision = observed
        if revision != QUALIFIED_REVISION:
            return result("INCOMPLETE", error="REVISION_MISMATCH")
        if dirty:
            return result("INCOMPLETE", error="DIRTY_EVALUATOR")
        try:
            raw = self.transport.invoke(self.executable, self.worker, self.root, request.stable_json())
            response = read_json(raw)
            if set(response) != {"request_sha256", "revision", "native_result", "network_attempts", "live_model_calls"}:
                raise ValueError("invalid worker response")
            if (response["request_sha256"] != request.sha256 or response["revision"] != revision
                    or response["network_attempts"] != 0 or response["live_model_calls"] != 0):
                raise ValueError("worker identity or offline guarantee mismatch")
            native = response["native_result"]
            expected_fields = {"scenario_id", "functional_pass", "tool_pass", "argument_pass", "overall_pass", "failures", "factual_grounding_pass"}
            if not isinstance(native, dict) or set(native) != expected_fields or native["scenario_id"] != str(request.evaluation_case_id):
                raise ValueError("invalid native identity")
            if any(type(native[key]) is not bool for key in ("functional_pass", "tool_pass", "argument_pass", "overall_pass")):
                raise ValueError("invalid native flags")
            if (native["tool_pass"] is not True or native["argument_pass"] is not True
                    or native["overall_pass"] != native["functional_pass"] or native["factual_grounding_pass"] is not None
                    or not isinstance(native["failures"], list) or not all(isinstance(item, str) for item in native["failures"])
                    or bool(native["failures"]) == native["overall_pass"]):
                raise ValueError("inconsistent native result")
            after, dirty = self._revision()
            if after != revision or dirty:
                raise ValueError("evaluator changed during evaluation")
            return result("COMPLETED_PASS" if native["overall_pass"] else "COMPLETED_FAIL", attempted=True, native=native)
        except TransportError as exc:
            return result("ERROR", attempted=True, error=exc.code)
        except (ValueError, TypeError, KeyError, OSError, subprocess.SubprocessError):
            return result("ERROR", attempted=True, error="INVALID_RESPONSE")
