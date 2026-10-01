"""Isolated deterministic evaluator entry point. Does not import AutoQE."""

import argparse
from dataclasses import asdict
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluator-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.evaluator_root.resolve()
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from autoqe_integration.contracts import ExternalEvaluationRequest, canonical_json, read_json

    # Deny network and live/reference execution modules before evaluator import.
    blocked = {"openai", "agents", "deepeval", "src.agent", "src.agentguard.evaluation_record",
               "src.agentguard.semantic_evaluator"}

    class OfflineImports:
        def find_spec(self, fullname, path=None, target=None):
            if any(fullname == name or fullname.startswith(name + ".") for name in blocked):
                raise ImportError("live execution module prohibited")
            return None

    sys.meta_path.insert(0, OfflineImports())
    attempts = []

    def deny_network(*args, **kwargs):
        attempts.append(True)
        raise RuntimeError("network prohibited")

    socket.socket.connect = deny_network
    socket.socket.connect_ex = deny_network
    socket.socket.bind = deny_network
    socket.socket.sendto = deny_network
    socket.create_connection = deny_network
    socket.getaddrinfo = deny_network
    try:
        payload = sys.stdin.buffer.read(65537)
        if len(payload) > 65536:
            raise ValueError("oversized request")
        # Validate duplicate fields before Pydantic's JSON-mode UUID parsing.
        request = ExternalEvaluationRequest.model_validate_json(canonical_json(read_json(payload)))
        revision = subprocess.run(
            ["git", "-c", f"safe.directory={root.as_posix()}", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, timeout=5, shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout.strip()
        if revision != "ee104f90fe9c0c23f320ab110fdd2c9adf20d37c":
            raise ValueError("unqualified revision")
        sys.path.insert(0, str(root))
        from src.agentguard.scoring import evaluate_record

        scenario = dict(id=str(request.evaluation_case_id), expected_contains=[request.expected_value],
                        forbidden_contains=[], expected_tools=[])
        # A minimal structural view of a captured classification. No fabricated
        # runtime record, tool calls, timing, model identity or usage telemetry.
        record = SimpleNamespace(final_output=request.actual_value, tool_calls=[])
        native = asdict(evaluate_record(scenario, record))
        if attempts:
            raise ValueError("network attempted")
        print(canonical_json(dict(request_sha256=request.sha256, revision=revision,
                                  native_result=native, network_attempts=0, live_model_calls=0)))
        return 0
    except Exception:
        # Never print payloads, tracebacks or third-party exception text.
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
