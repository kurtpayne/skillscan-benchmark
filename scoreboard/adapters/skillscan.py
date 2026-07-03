"""skillscan — the author's OWN, now-retired scanner — adapter.

Included ONLY as a clearly-labeled, NON-graded REFERENCE self-entry (transparency: the author
does not exempt their own tool from the same test). Two fully-offline modes:
  - static rules            (`--no-ml-detect`)
  - local ML classifier     (`--ml-detect`  → the v4 Qwen2.5-1.5B GGUF detector, offline)
skillscan `scan` has NO frontier/OpenAI mode — scanning is entirely local (that data point is
covered by the frontier baselines). Run at the `strict` policy default (its most generous recall).
JSON report on stdout; native verdict is allow / warn / block → **block == MALICIOUS** (the
deployable gate: `skillscan scan` exits non-zero on BLOCK).
"""

from __future__ import annotations

import json
import subprocess

from ..model import ScanResult, Verdict
from .base import ScannerAdapter


def _loads(s: str):
    """skillscan prints the JSON report to stdout; tolerate any leading log noise by falling
    back to the outermost {...} block."""
    try:
        return json.loads(s)
    except Exception:  # noqa: BLE001
        i, j = s.find("{"), s.rfind("}")
        if i >= 0 and j > i:
            return json.loads(s[i : j + 1])
        raise


class SkillscanAdapter(ScannerAdapter):
    name = "skillscan"

    def __init__(self, binary="skillscan", version="retired", timeout_s=120, ml=False, policy="strict"):
        self.ml = ml
        self.policy = policy
        if ml:
            version = f"{version}+ml"
            timeout_s = max(timeout_s, 300)  # local GGUF load+infer per file
        super().__init__(binary, version, timeout_s)
        # reuse analyze's two mode buckets; the render labels them "static rules" / "local ML".
        self.mode = "llm" if ml else "static"

    def _argv(self, skill_path: str) -> list[str]:
        return [
            self.binary,
            "scan",
            skill_path,
            "--policy-profile",
            self.policy,
            "--ml-detect" if self.ml else "--no-ml-detect",
            "--no-auto-intel",
            "--format",
            "json",
        ]

    def _parse(self, sample_id: str, proc: subprocess.CompletedProcess) -> ScanResult:
        try:
            d = _loads(proc.stdout)
        except Exception as e:  # noqa: BLE001
            return ScanResult(
                sample_id,
                self.name,
                self.version,
                Verdict.ERROR,
                error=f"no/invalid json: {str(e)[:120]}; stderr={proc.stderr[:120]}",
            )
        v = (d.get("verdict") or "").lower()
        mal = v == "block"
        cats = sorted(
            {(f.get("category") or f.get("rule_id") or "").lower() for f in d.get("findings", []) if isinstance(f, dict)}
            - {""}
        )
        return ScanResult(
            sample_id,
            self.name,
            self.version,
            Verdict.MALICIOUS if mal else Verdict.BENIGN,
            severity=v,
            categories=cats,
            raw={"score": d.get("score"), "verdict": v},
        )
