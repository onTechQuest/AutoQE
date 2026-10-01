"""Bounded JSON subprocess transport. Never inherits model credentials."""

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess


class TransportError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class LocalProcessTransport:
    timeout_seconds: float = 20
    max_bytes: int = 65536

    def __post_init__(self):
        if not 0 < self.timeout_seconds <= 60 or not 0 < self.max_bytes <= 1048576:
            raise ValueError("invalid transport bounds")

    def invoke(self, executable: Path, worker: Path, evaluator_root: Path, payload: str) -> bytes:
        if len(payload.encode()) > self.max_bytes:
            raise TransportError("INVOCATION_FAILED")
        # Only OS/runtime essentials; no PYTHONPATH, .env loading, provider keys,
        # proxy settings, inherited model configuration or reference credentials.
        environment = {key: value for key, value in os.environ.items()
                       if key.upper() in {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH", "PATHEXT"}}
        environment.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
        try:
            completed = subprocess.run(
                [str(executable), "-I", "-B", str(worker), "--evaluator-root", str(evaluator_root)],
                input=payload.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=str(evaluator_root), env=environment, timeout=self.timeout_seconds,
                shell=False, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired:
            raise TransportError("TIMEOUT") from None
        except OSError:
            raise TransportError("INVOCATION_FAILED") from None
        if len(completed.stdout) > self.max_bytes or len(completed.stderr) > self.max_bytes:
            raise TransportError("INVALID_RESPONSE")
        if completed.returncode != 0:
            raise TransportError("EVALUATOR_ERROR")
        if completed.stderr:
            raise TransportError("INVALID_RESPONSE")
        return completed.stdout
