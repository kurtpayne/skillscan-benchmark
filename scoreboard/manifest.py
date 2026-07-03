"""Manifest = the external label store (JSONL, one Sample per line).

Labels/tiers live HERE, never in the skill files (Decision 1: strip in-file labels →
no leakage). The harness reads the manifest, scanners read only the stripped content.
"""

from __future__ import annotations

import json
import re

from .model import Sample

# YAML frontmatter label fields that must be stripped from content before a scanner sees it
# (mirrors skillscan-corpus _strip_label_fields; prevents the scanner from reading the answer).
LABEL_FIELDS = (
    "label",
    "labels",
    "attack_labels",
    "attack_type",
    "classification",
    "confidence",
    "malicious",
    "is_malicious",
    "verdict",
    "severity",
    "tier",
    "ground_truth",
)


def load_manifest(path: str) -> list[Sample]:
    samples = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            d = json.loads(line)
            samples.append(
                Sample(
                    id=d["id"],
                    cls=d.get("cls", d.get("class", "")),
                    tier=d["tier"],
                    label=d["label"],
                    source=d["source"],
                    source_ref=d.get("source_ref", ""),
                    license=d.get("license", "verify"),
                    confidence=d["confidence"],
                    content_path=d.get("content_path"),
                    sha256=d.get("sha256"),
                    notes=d.get("notes", ""),
                )
            )
    return samples


def validate_manifest(samples: list[Sample]) -> list[str]:
    errs = []
    seen = set()
    for s in samples:
        if s.id in seen:
            errs.append(f"duplicate id {s.id!r}")
        seen.add(s.id)
        errs.extend(s.validate())
    return errs


def strip_label_frontmatter(text: str) -> str:
    """Remove label-bearing keys from a leading YAML frontmatter block. Leaves the rest
    (name/description) intact so the skill still looks like a real skill to the scanner."""
    if not text.startswith("---"):
        return text
    parts = text.split("---", 2)
    if len(parts) != 3:
        return text
    _, fm, body = parts
    nonempty = [ln for ln in fm.splitlines() if ln.strip()]
    kept = [ln for ln in nonempty if ln.split(":", 1)[0].strip().lower().lstrip("- ") not in LABEL_FIELDS]
    if len(kept) == len(nonempty):
        return text  # no label field present → byte-identical no-op (preserves cache sha)
    # Rebuild a well-formed frontmatter block (newline before the closing delimiter, or the
    # next parser can't find `name:`). body keeps its own leading newline.
    return "---\n" + "\n".join(kept) + "\n---" + body


def _derive_name_desc(body: str, fallback: str) -> tuple[str, str]:
    """Best-effort name/description from a skill body: first H1 → name, first prose line →
    description. Uniform, content-derived, label-free — so no scanner is penalized for a
    missing-metadata precondition rather than for detection."""
    name, desc = fallback, "AI agent skill."
    lines = body.splitlines()
    for ln in lines:
        s = ln.strip()
        if s.startswith("#"):
            name = s.lstrip("#").strip()[:80] or fallback
            break
    for ln in lines:
        s = ln.strip()
        if s and not s.startswith(("#", "=", "-", "*", "|", "```", "<")):
            desc = s[:160]
            break
    # YAML-safe (single line, no stray colons breaking the block)
    return name.replace("\n", " "), desc.replace("\n", " ").replace(":", " -")


def ensure_skill_frontmatter(text: str, fallback_name: str) -> str:
    """Guarantee a leading YAML frontmatter block with BOTH name and description, so every
    sample is a well-formed skill that all scanners can parse (Cisco rejects skills missing
    name/description — defanged/harvested samples often have no frontmatter at all). Existing
    name/description are preserved; only missing keys are filled. Idempotent."""
    has_fm = text.startswith("---") and len(text.split("---", 2)) == 3
    if has_fm:
        _, fm, body = text.split("---", 2)
        keys = {ln.split(":", 1)[0].strip().lower().lstrip("- ") for ln in fm.splitlines() if ":" in ln}
        if "name" in keys and "description" in keys:
            return text
        nm, desc = _derive_name_desc(body, fallback_name)
        add = []
        if "name" not in keys:
            add.append(f"name: {nm}")
        if "description" not in keys:
            add.append(f"description: {desc}")
        return "---\n" + "\n".join(add) + "\n" + fm.strip("\n") + "\n---" + body
    nm, desc = _derive_name_desc(text, fallback_name)
    return f"---\nname: {nm}\ndescription: {desc}\n---\n" + text


_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def is_index_only(s: Sample) -> bool:
    """A sample with no on-disk content (e.g. mas-bench rows whose payloads weren't fetched).
    Scored as 'coverage gap', never silently dropped (scoreboard-v1-plan.md: honest gaps)."""
    return not s.content_path
