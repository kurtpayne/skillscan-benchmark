"""Reproducibility diff: compare a fresh Profile-A run against the committed board.

Quantifies (a) temp-0 frontier run-to-run drift on the 84 independent Skill-Inject cases
(per-model pooled hits + how many individual verdicts flipped), and (b) static-board exactness
(recall k/n + FP per scanner cell). Static should match by construction (commit-pinned); any
delta there is a real regression. Frontier deltas of ±1-2/84 empirically justify the K=1 disclosure.

    python3 scripts/repro_diff.py
"""

from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(p):
    fp = os.path.join(HERE, p)
    return json.load(open(fp, encoding="utf-8")) if os.path.exists(fp) else None


def frontier_diff():
    pairs = [
        ("gpt-4o", "skillinject_llm.json", "_repro/repro_gpt-4o.json"),
        ("gpt-4o-mini", "skillinject_llm_gpt-4o-mini.json", "_repro/repro_gpt-4o-mini.json"),
        ("claude-sonnet-4.6", "skillinject_llm_claude-sonnet.json", "_repro/repro_claude-sonnet.json"),
        ("claude-haiku-4.5", "skillinject_llm_claude-haiku.json", "_repro/repro_claude-haiku.json"),
    ]
    print("=== FRONTIER (independent Skill-Inject, n=84) — committed vs fresh ===")
    print(f"{'model':<20} {'committed':>10} {'fresh':>10} {'Δpooled':>8} {'verdicts flipped':>18}")
    worst = 0
    for name, old_p, new_p in pairs:
        old, new = _load(old_p), _load(new_p)
        if not old or not new:
            print(f"{name:<20} {'MISSING' if not old else '':>10} {'MISSING' if not new else '':>10}")
            continue
        oh, on = old["pooled"]["hits"], old["pooled"]["n"]
        nh, nn = new["pooled"]["hits"], new["pooled"]["n"]
        ov = {r["id"]: r["verdict"] for r in old["results"]}
        nv = {r["id"]: r["verdict"] for r in new["results"]}
        flipped = sum(1 for k in ov if k in nv and ov[k] != nv[k])
        worst = max(worst, flipped)
        print(f"{name:<20} {f'{oh}/{on}':>10} {f'{nh}/{nn}':>10} {nh - oh:>+8} {flipped:>18}")
    print(f"\nworst per-model verdict drift: {worst}/84 "
          f"({'within K=1 tolerance' if worst <= 3 else 'INVESTIGATE — exceeds ±3'})")


def static_diff():
    old, new = _load("board_v11_static.json"), _load("_repro/board_static_repro.json")
    print("\n=== STATIC BOARD — committed vs fresh (should match exactly) ===")
    if not new:
        print("  fresh static board not present yet")
        return
    mismatches = 0
    for sc in old.get("recall", {}):
        for mode in old["recall"][sc]:
            for arch, prov_map in old["recall"][sc][mode].items():
                for prov, cell in prov_map.items():
                    ow = (cell or {}).get("wilson") or {}
                    nw = (((new.get("recall", {}).get(sc, {}).get(mode, {}) or {}).get(arch, {}) or {}).get(prov, {}) or {}).get("wilson") or {}
                    if ow.get("k") != nw.get("k") or ow.get("n") != nw.get("n"):
                        mismatches += 1
                        print(f"  MISMATCH {sc}/{mode}/{arch}/{prov}: "
                              f"committed {ow.get('k')}/{ow.get('n')} vs fresh {nw.get('k')}/{nw.get('n')}")
    oc = old.get("consensus", {})
    nc = new.get("consensus", {})
    print(f"  consensus n: committed {oc.get('n')} vs fresh {nc.get('n')}")
    print(f"  corpus n: committed {old.get('corpus', {}).get('n')} vs fresh {new.get('corpus', {}).get('n')}")
    print(f"\nstatic recall-cell mismatches: {mismatches} "
          f"({'EXACT MATCH ✓' if mismatches == 0 else 'INVESTIGATE — static must be deterministic'})")


if __name__ == "__main__":
    frontier_diff()
    static_diff()
