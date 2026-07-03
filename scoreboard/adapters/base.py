"""Scanner adapter contract.

Each adapter wraps one scanner CLI and normalizes its output to a ScanResult. Adapters
shell out to a scanner installed in its own venv (paths come from config, see run.py).
A scanner that crashes / refuses / times out yields Verdict.ERROR — never a silent miss.
"""

from __future__ import annotations

import abc
import subprocess

from ..model import ScanResult, Verdict


class ScannerAdapter(abc.ABC):
    name: str = "base"
    # the board "mode" this adapter contributes to: "static" (rules only) or "llm" (+LLM pass).
    mode: str = "static"
    # stochastic scanners (LLM-backed +llm modes with temperature > 0) are run K times and
    # majority-voted; deterministic ones (static rules, temp-0 reads) run once (K=1).
    stochastic: bool = False
    # extra env merged into the subprocess (e.g. provider base_url/key for a +llm pass).
    env: dict | None = None

    def __init__(self, binary: str, version: str = "unknown", timeout_s: int = 120):
        self.binary = binary
        self.version = version
        self.timeout_s = timeout_s

    @abc.abstractmethod
    def _argv(self, skill_path: str) -> list[str]: ...

    @abc.abstractmethod
    def _parse(self, sample_id: str, proc: subprocess.CompletedProcess) -> ScanResult: ...

    def scan(self, sample_id: str, skill_path: str) -> ScanResult:
        import os
        import time

        run_env = None
        if self.env:
            run_env = os.environ.copy()
            run_env.update(self.env)
        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                self._argv(skill_path),
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                stdin=subprocess.DEVNULL,
                env=run_env,
            )
        except subprocess.TimeoutExpired:
            return ScanResult(
                sample_id, self.name, self.version, Verdict.ERROR, error="timeout", duration_s=self.timeout_s
            )
        except Exception as e:  # noqa: BLE001 — any launch failure is an ERROR, not a miss
            return ScanResult(sample_id, self.name, self.version, Verdict.ERROR, error=str(e)[:200])
        res = self._parse(sample_id, proc)
        res.duration_s = round(time.monotonic() - t0, 3)
        return res
