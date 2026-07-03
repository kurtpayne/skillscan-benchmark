"""NVIDIA SkillSpector adapter.

Verified shape (2026-06-14): `skillspector scan <path> --no-llm --format json -o <file>`.
JSON top keys: skill, risk_assessment{score,severity,recommendation}, components, issues[],
metadata. Exit 1 on block, 0 on safe. We run --no-llm (static only): no LLM spend, and keeps
malicious content off any commercial model (Principle 2).
"""

from __future__ import annotations

import json
import subprocess

from ..model import ScanResult, Verdict
from .base import ScannerAdapter

_MAL_SEVERITIES = {"CRITICAL", "HIGH"}


class SkillSpectorAdapter(ScannerAdapter):
    name = "skillspector"

    def __init__(
        self,
        binary: str,
        version: str = "2.1.4",
        timeout_s: int = 120,
        llm: bool = False,
        llm_model: str | None = None,
        llm_base_url: str | None = None,
        llm_api_key: str | None = None,
        llm_label: str = "",
    ):
        # +llm mode: drive SkillSpector's LLM analyzers via an OpenAI-compatible endpoint
        # (open-weight Modal by default → Principle 2). Static mode keeps --no-llm.
        self.llm = llm
        if llm:
            version = f"{version}+llm-{llm_label}" if llm_label else f"{version}+llm"
        super().__init__(binary, version, timeout_s)
        self._outfile = None
        if llm:
            self.mode = "llm"
            self.stochastic = True
            self.env = {
                "SKILLSPECTOR_PROVIDER": "openai",
                "OPENAI_BASE_URL": llm_base_url or "",
                "OPENAI_API_KEY": llm_api_key or "",
            }
            if llm_model:
                self.env["SKILLSPECTOR_MODEL"] = llm_model

    def _argv(self, skill_path: str) -> list[str]:
        # JSON to STDOUT (no -o): the previous `-o self._outfile` stored the path on the shared
        # adapter instance, which RACES under the parallel ThreadPool (concurrent scans clobber each
        # other's filename → spurious ERRORs / undercounted n). stdout is per-process and race-free.
        base = [self.binary, "scan", skill_path, "--format", "json"]
        if not self.llm:
            base.insert(3, "--no-llm")
        return base

    def _parse(self, sample_id: str, proc: subprocess.CompletedProcess) -> ScanResult:
        try:
            s = proc.stdout
            d = json.loads(s) if s.lstrip().startswith("{") else json.loads(s[s.find("{") : s.rfind("}") + 1])
        except Exception as e:  # noqa: BLE001
            return ScanResult(
                sample_id,
                self.name,
                self.version,
                Verdict.ERROR,
                error=f"no/invalid json: {str(e)[:120]}; stderr={proc.stderr[:120]}",
            )
        ra = d.get("risk_assessment", {}) or {}
        sev = (ra.get("severity") or "").upper()
        rec = (ra.get("recommendation") or "").upper()
        mal = rec == "DO_NOT_INSTALL" or sev in _MAL_SEVERITIES
        cats = sorted({(i.get("category") or "").lower() for i in d.get("issues", []) if i.get("category")})
        return ScanResult(
            sample_id,
            self.name,
            self.version,
            Verdict.MALICIOUS if mal else Verdict.BENIGN,
            severity=sev,
            categories=cats,
            raw={"score": ra.get("score"), "recommendation": rec},
        )
