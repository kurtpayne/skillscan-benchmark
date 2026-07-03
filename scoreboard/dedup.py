"""Dedup tooling — keep the corpus leakage-free.

Two jobs (scoreboard-v1-plan.md gaps #2):
1. Drop exact duplicates when merging sourced sets (e.g. the openclaw archive overlaps our
   existing held_out_eval benign).
2. Flag samples a scanner's OWN training/fixtures touched, so we never grade a scanner on
   content it has memorized (the home-turf bias).

Exact-dup detection is sha256 of normalized content. (Near-dup / fuzzy is a follow-up.)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .model import sha256_of_path


def hash_corpus(paths: list[str]) -> dict[str, list[str]]:
    """sha256 → [paths] for a list of skill files/dirs."""
    out: dict[str, list[str]] = {}
    for p in paths:
        if not os.path.exists(p):
            continue
        out.setdefault(sha256_of_path(p), []).append(p)
    return out


@dataclass
class DedupReport:
    unique: list[str] = field(default_factory=list)  # one representative per hash
    duplicates: dict[str, list[str]] = field(default_factory=dict)  # hash → dropped paths
    collisions_with_existing: list[str] = field(default_factory=list)  # candidates already in corpus

    @property
    def n_dropped(self) -> int:
        return sum(len(v) for v in self.duplicates.values()) + len(self.collisions_with_existing)


def dedup_against(candidate_paths: list[str], existing_paths: list[str] | None = None) -> DedupReport:
    """Return unique candidates, dropping intra-candidate dups and any that collide with an
    existing corpus (e.g. held_out_eval). Deterministic: representative = sorted-first path."""
    existing_hashes = set(hash_corpus(existing_paths or []).keys())
    rep = DedupReport()
    cand = hash_corpus(candidate_paths)
    for h, paths in sorted(cand.items()):
        paths = sorted(paths)
        if h in existing_hashes:
            rep.collisions_with_existing.extend(paths)
            continue
        rep.unique.append(paths[0])
        if len(paths) > 1:
            rep.duplicates[h] = paths[1:]
    return rep
