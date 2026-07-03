"""Snyk Agent Scan adapter.

Verified shape (2026-06-14): `snyk-agent-scan scan <path> --json` (needs SNYK_TOKEN in env →
mapped from Infisical SNYK_API_KEY). Output is a dict keyed by the scanned dir; each value has
`issues[]` with `code`, `message`, and `extra_data.{severity, risk_score, title}`. Verdict =
MALICIOUS if any issue is high/critical severity. Sends content to Snyk's cloud (egress required;
acceptable — that's a scanner's job, and the owner OK'd it).
"""

from __future__ import annotations

import json
import subprocess

from ..model import ScanResult, Verdict
from .base import ScannerAdapter

_MAL_SEVERITIES = {"high", "critical"}
_SEV_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "": 0}


class SnykAgentScanAdapter(ScannerAdapter):
    name = "snyk-agent-scan"

    def _argv(self, skill_path: str) -> list[str]:
        return [self.binary, "scan", skill_path, "--json"]

    def _parse(self, sample_id: str, proc: subprocess.CompletedProcess) -> ScanResult:
        try:
            d = json.loads(proc.stdout)
        except Exception as e:  # noqa: BLE001
            return ScanResult(
                sample_id,
                self.name,
                self.version,
                Verdict.ERROR,
                error=f"no/invalid json: {str(e)[:100]}; stderr={proc.stderr[:120]}",
            )
        issues, hard_error = [], None
        for v in d.values() if isinstance(d, dict) else []:
            if not isinstance(v, dict):
                continue
            issues += v.get("issues") or []
            err = v.get("error")
            if err not in (None, "None", ""):
                hard_error = str(err)
        if not issues and hard_error:
            return ScanResult(sample_id, self.name, self.version, Verdict.ERROR, error=hard_error[:160])
        severities = [(i.get("extra_data") or {}).get("severity", "").lower() for i in issues]
        mal = any(s in _MAL_SEVERITIES for s in severities)
        top = max(severities, key=lambda s: _SEV_RANK.get(s, 0), default="")
        cats = sorted(
            {
                (i.get("code") or (i.get("extra_data") or {}).get("title") or "").lower()
                for i in issues
                if i.get("code") or (i.get("extra_data") or {}).get("title")
            }
        )
        return ScanResult(
            sample_id,
            self.name,
            self.version,
            Verdict.MALICIOUS if mal else Verdict.BENIGN,
            severity=top.upper(),
            categories=cats,
            raw={"issue_count": len(issues)},
        )
