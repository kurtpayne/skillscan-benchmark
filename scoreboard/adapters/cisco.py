"""Cisco AI Defense skill-scanner adapter.

Verified shape (2026-06-14): `skill-scanner scan <path> --format json` → stdout JSON with
is_safe (bool), max_severity, findings_count, findings[]{category,rule_id,severity}, ...
Exit code is always 0 (use is_safe, not the exit code). Run without --use-llm/--use-behavioral
to stay static-only (no LLM spend / Principle 2).
"""

from __future__ import annotations

import json
import subprocess

from ..model import ScanResult, Verdict
from .base import ScannerAdapter


class CiscoSkillScannerAdapter(ScannerAdapter):
    name = "cisco-skill-scanner"

    def __init__(
        self,
        binary: str,
        version: str = "unknown",
        timeout_s: int = 120,
        llm: bool = False,
        llm_model: str | None = None,
        llm_base_url: str | None = None,
        llm_api_key: str | None = None,
        llm_label: str = "",
    ):
        # +llm mode: --use-llm via LiteLLM openai-compatible endpoint (open-weight Modal by
        # default → Principle 2). We do our own K-fold, so --llm-consensus-runs 1.
        self.llm = llm
        if llm:
            version = f"{version}+llm-{llm_label}" if llm_label else f"{version}+llm"
        super().__init__(binary, version, timeout_s)
        if llm:
            self.mode = "llm"
            self.stochastic = True
            self.env = {
                "SKILL_SCANNER_LLM_PROVIDER": "openai-compatible",
                "SKILL_SCANNER_LLM_BASE_URL": llm_base_url or "",
                "SKILL_SCANNER_LLM_API_KEY": llm_api_key or "",
            }
            if llm_model:
                self.env["SKILL_SCANNER_LLM_MODEL"] = llm_model

    def _argv(self, skill_path: str) -> list[str]:
        base = [self.binary, "scan", skill_path, "--format", "json"]
        if self.llm:
            base += [
                "--use-llm",
                "--llm-provider",
                "openai-compatible",
                "--llm-consensus-runs",
                "1",
                "--llm-max-tokens",
                "512",
            ]
        return base

    def _parse(self, sample_id: str, proc: subprocess.CompletedProcess) -> ScanResult:
        try:
            d = json.loads(proc.stdout)
        except Exception as e:  # noqa: BLE001
            return ScanResult(
                sample_id,
                self.name,
                self.version,
                Verdict.ERROR,
                error=f"no/invalid json: {str(e)[:120]}; stderr={proc.stderr[:120]}",
            )
        is_safe = d.get("is_safe")
        if is_safe is None:
            return ScanResult(sample_id, self.name, self.version, Verdict.ERROR, error="missing is_safe")
        cats = sorted(
            {(fi.get("category") or "").lower() for fi in d.get("findings", []) if fi.get("category")}
        )
        return ScanResult(
            sample_id,
            self.name,
            self.version,
            Verdict.BENIGN if is_safe else Verdict.MALICIOUS,
            severity=(d.get("max_severity") or "").upper(),
            categories=cats,
            raw={"findings_count": d.get("findings_count"), "analyzers_used": d.get("analyzers_used")},
        )
