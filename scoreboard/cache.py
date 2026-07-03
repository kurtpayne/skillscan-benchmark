"""Content-hash cache: (scanner, scanner_version, skill_sha256) → ScanResult.

Unchanged cells never re-run (scoreboard-v1-plan.md cost section). Errored results are NOT
cached (mirrors trace's "errored traces are not cached" rule — a refusal/timeout may be
transient, so we retry it next run rather than freezing a bad verdict).
"""

from __future__ import annotations

import json
import os

from .model import ScanResult, Verdict


class ResultCache:
    def __init__(self, path: str):
        self.path = path
        self._d: dict[str, dict] = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self._d = json.load(f)

    @staticmethod
    def key(scanner: str, version: str, skill_sha: str, k: int = 0, mode: str = "static") -> str:
        # k>0 namespaces a stochastic run-index so K repeats don't collapse to one cached
        # result. mode!="static" namespaces a scanner's +llm pass separately from its static
        # pass. k=0 + static mode keep the original key for back-compat (static cache intact).
        base = f"{scanner}@{version}:{skill_sha}"
        if mode and mode != "static":
            base = f"{base}~{mode}"
        return f"{base}#k{k}" if k else base

    def get(
        self, scanner: str, version: str, skill_sha: str, k: int = 0, mode: str = "static"
    ) -> ScanResult | None:
        d = self._d.get(self.key(scanner, version, skill_sha, k, mode))
        if not d:
            return None
        return ScanResult(
            sample_id=d["sample_id"],
            scanner=d["scanner"],
            scanner_version=d["scanner_version"],
            verdict=Verdict(d["verdict"]),
            severity=d.get("severity", ""),
            categories=d.get("categories", []),
            duration_s=d.get("duration_s", 0.0),
            error=d.get("error", ""),
            raw=d.get("raw", {}),
        )

    def put(self, skill_sha: str, r: ScanResult, k: int = 0, mode: str = "static") -> None:
        if r.verdict == Verdict.ERROR:
            return  # never cache refusals/errors — retry them next run
        self._d[self.key(r.scanner, r.scanner_version, skill_sha, k, mode)] = {
            "sample_id": r.sample_id,
            "scanner": r.scanner,
            "scanner_version": r.scanner_version,
            "verdict": r.verdict.value,
            "severity": r.severity,
            "categories": r.categories,
            "duration_s": r.duration_s,
            "raw": r.raw,
        }

    def save(self) -> None:
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._d, f, indent=0)
        os.replace(tmp, self.path)
