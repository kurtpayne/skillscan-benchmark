"""Core data model for the scoreboard.

A Sample is one curated skill (with external label/tier — never in-file, to avoid leakage).
A ScanResult is a scanner's normalized output on one sample. Verdict separates a genuine
BENIGN call from an ERROR/refusal — the refusal column is itself a finding (see EVAL.md:
LLM classifiers get moderation-refused on the very content they must scan).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum


class Verdict(str, Enum):
    MALICIOUS = "malicious"
    BENIGN = "benign"
    ERROR = "error"  # refused / crashed / timed out — NOT a miss, NOT a false positive


# v1 attack classes (scoreboard-v1-plan.md, Decision 2)
CLASSES = ("cred-exfil", "rce", "prompt-injection")
# difficulty / technique tiers + the two non-malicious controls (Decision 1)
TIERS = ("overt", "obfuscated", "indirect", "benign", "dual-use-fp-bait")
LABELS = ("malicious", "benign")
# provenance confidence gradient (scoreboard-corpus-sources.md)
CONFIDENCE = ("wild-confirmed", "vendor-demo", "published-synthetic")


@dataclass(frozen=True)
class Sample:
    id: str
    cls: str  # one of CLASSES (or "" for benign/dual-use rows where class is n/a)
    tier: str  # one of TIERS
    label: str  # one of LABELS
    source: str  # dataset key, e.g. "skill-inject"
    source_ref: str  # citation / URL
    license: str  # e.g. "MIT", "Apache-2.0", "verify"
    confidence: str  # one of CONFIDENCE
    content_path: str | None  # path to label-stripped SKILL dir/file; None = index-only
    sha256: str | None = None  # content hash (None when index-only)
    notes: str = ""

    def validate(self) -> list[str]:
        errs = []
        if self.label not in LABELS:
            errs.append(f"{self.id}: bad label {self.label!r}")
        if self.tier not in TIERS:
            errs.append(f"{self.id}: bad tier {self.tier!r}")
        if self.label == "malicious" and self.cls not in CLASSES:
            errs.append(f"{self.id}: malicious sample needs a class, got {self.cls!r}")
        if self.confidence not in CONFIDENCE:
            errs.append(f"{self.id}: bad confidence {self.confidence!r}")
        if self.label == "malicious" and self.tier in ("benign", "dual-use-fp-bait"):
            errs.append(f"{self.id}: malicious sample cannot be in control tier {self.tier!r}")
        if self.label == "benign" and self.tier not in ("benign", "dual-use-fp-bait"):
            errs.append(f"{self.id}: benign sample must be in a control tier, got {self.tier!r}")
        return errs


@dataclass
class ScanResult:
    sample_id: str
    scanner: str
    scanner_version: str
    verdict: Verdict
    severity: str = ""  # scanner-native severity string, best-effort
    categories: list[str] = field(default_factory=list)  # scanner's flagged categories
    duration_s: float = 0.0
    error: str = ""  # populated when verdict == ERROR
    raw: dict = field(default_factory=dict)


def sha256_of_path(path: str) -> str:
    """Stable content hash of a skill: concat of all files sorted by relative path.
    Works for a single file or a directory tree."""
    import os

    h = hashlib.sha256()
    if os.path.isfile(path):
        with open(path, "rb") as f:
            h.update(f.read())
        return h.hexdigest()
    for root, _dirs, files in sorted(os.walk(path)):
        for name in sorted(files):
            fp = os.path.join(root, name)
            rel = os.path.relpath(fp, path)
            h.update(rel.encode())
            with open(fp, "rb") as f:
                h.update(f.read())
    return h.hexdigest()
