"""Analysis layer (METHODOLOGY §4-6): turn scan results into the board with Wilson CIs,
the Generalization Gap, McNemar significance, per-generator fingerprint check, and consensus.

Inputs:
  manifest: list[dict] — {id, label, provenance, archetype, tier, dual_use, generator_model}
  results:  list[dict] — {sample_id, scanner, mode, verdict}  (verdict: malicious|benign|error)
"""

from __future__ import annotations

import json
from collections import defaultdict

from .stats import benjamini_hochberg, mcnemar_exact, newcombe_diff, two_proportion_p, wilson

KNOWN = ("wild_verbatim", "organic_authored")  # public/known-IOC → memorizable
NOVEL = "synthetic_novel"

# scanner → kind, so the board artifact itself (not just the site prose) distinguishes products
# from open-weight control baselines (panel: don't let a reader put a static-only product number in
# the same undifferentiated column as a cloud product / an LLM baseline).
SCANNER_TYPE = {
    "skillspector": "static-rules",
    "cisco-skill-scanner": "static-rules",
    "snyk-agent-scan": "cloud-llm-product",
    "llm-baseline": "llm-baseline-control",
    "llm-baseline-disjoint": "llm-baseline-control",
}

# T2 defense — generator families. A synthetic sample's generator and an LLM scanner's
# own model may share a family; a same-family score risks "grading its own homework"
# (recognizing generator style, not malice). Map both generator_model ids AND scanner
# model ids onto a shared family token so cross-family scoring can exclude the overlap.
# hermes-3 is a Llama-3.1 fine-tune → same family as llama for contamination safety.
_FAMILY_HINTS = (
    ("qwen", "qwen"),
    ("hermes", "llama"),  # Nous Hermes 3 is a Llama fine-tune
    ("llama", "llama"),
    ("deepseek", "deepseek"),
    ("mixtral", "mistral"),
    ("mistral", "mistral"),
    ("gemma", "gemma"),
    ("phi", "phi"),
    ("command-r", "cohere"),
    ("command", "cohere"),
    ("cohere", "cohere"),
    ("yi-", "yi"),
    ("01-ai", "yi"),
    ("olmo", "olmo"),
)


def model_family(model_id: str | None) -> str | None:
    """Map a generator_model or scanner model id → coarse family token (or None)."""
    if not model_id:
        return None
    m = model_id.lower()
    for hint, fam in _FAMILY_HINTS:
        if hint in m:
            return fam
    return None


def load_manifest(path: str) -> list[dict]:
    out = []
    for ln in open(path, encoding="utf-8"):
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            out.append(json.loads(ln))
    return out


def _idx(manifest):
    return {s["id"]: s for s in manifest}


def _rate(results, samples, keyfn, want_malicious):
    """Generic: for each key, count verdict outcomes over the relevant label."""
    agg = defaultdict(lambda: {"k": 0, "n": 0, "err": 0, "total": 0})
    for r in results:
        s = samples.get(r["sample_id"])
        if not s:
            continue
        is_mal = s["label"] == "malicious"
        if want_malicious != is_mal:
            continue
        cell = agg[keyfn(r, s)]
        cell["total"] += 1
        if r["verdict"] == "error":
            cell["err"] += 1
            continue
        cell["n"] += 1
        # recall: malicious flagged; FP: benign flagged malicious
        if r["verdict"] == "malicious":
            cell["k"] += 1
    return agg


def compute(manifest: list[dict], results: list[dict], scanner_models: dict | None = None) -> dict:
    """scanner_models maps scanner name → the model id it ran (for LLM scanners), so the
    Generalization Gap can score each LLM scanner CROSS-FAMILY (excluding synthetic generated
    by its own model family). Static tools have no model → no exclusion (cross-family == pooled)."""
    samples = _idx(manifest)
    scanners = sorted({r["scanner"] for r in results})
    modes = sorted({r["mode"] for r in results})
    scanner_models = scanner_models or {}
    scanner_fam = {sc: model_family(scanner_models.get(sc)) for sc in scanners}

    # --- recall by scanner × mode × archetype × provenance (Wilson CI) ---
    rec = _rate(
        results, samples, lambda r, s: (r["scanner"], r["mode"], s["archetype"], s["provenance"]), True
    )
    recall = {}
    for (sc, mode, arch, prov), c in rec.items():
        recall.setdefault(sc, {}).setdefault(mode, {}).setdefault(arch, {})[prov] = {
            "wilson": wilson(c["k"], c["n"]),
            "refusal": round(c["err"] / c["total"], 4) if c["total"] else None,
        }

    # --- false-positive by scanner × mode × benign-tier (Wilson CI) ---
    def _fp_bucket(s):
        # generated-benign control (T2): benign skills from the same generators+defang as the
        # malicious synthetic — its own bucket so we can compare FP(generated) vs FP(real benign).
        if s.get("provenance") == "synthetic_benign" or s.get("tier") == "generated_benign":
            return "generated_benign"
        if s.get("dual_use") or s.get("tier") == "dual_use":
            return "dual_use"
        return "benign"

    fp = _rate(results, samples, lambda r, s: (r["scanner"], r["mode"], _fp_bucket(s)), False)
    fprate = {}
    for (sc, mode, tier), c in fp.items():
        fprate.setdefault(sc, {}).setdefault(mode, {})[tier] = {"wilson": wilson(c["k"], c["n"])}

    # --- GENERALIZATION GAP: recall(known) vs recall(synthetic), per scanner×mode×archetype ---
    def recall_kn(sc, mode, arch, provset):
        k = n = 0
        for r in results:
            s = samples.get(r["sample_id"])
            if not s or s["label"] != "malicious" or r["scanner"] != sc or r["mode"] != mode:
                continue
            if s["archetype"] != arch or s["provenance"] not in provset or r["verdict"] == "error":
                continue
            n += 1
            k += r["verdict"] == "malicious"
        return k, n

    def synth_by_generator(sc, mode, arch):
        """Per-generator (k,n) for synthetic — to balance out single-model fingerprint/quality."""
        per = defaultdict(lambda: [0, 0])
        for r in results:
            s = samples.get(r["sample_id"])
            if (
                not s
                or s["label"] != "malicious"
                or r["scanner"] != sc
                or r["mode"] != mode
                or s["archetype"] != arch
                or s["provenance"] != NOVEL
                or r["verdict"] == "error"
            ):
                continue
            g = s.get("generator_model", "?")
            per[g][1] += 1
            per[g][0] += r["verdict"] == "malicious"
        return per

    def synth_crossfamily(sc, mode, arch, own_fam):
        """(k,n) for synthetic EXCLUDING samples whose generator shares the scanner's family.
        T2 defense: a Qwen scanner is not credited for catching Qwen-generated synthetic."""
        k = n = 0
        for r in results:
            s = samples.get(r["sample_id"])
            if (
                not s
                or s["label"] != "malicious"
                or r["scanner"] != sc
                or r["mode"] != mode
                or s["archetype"] != arch
                or s["provenance"] != NOVEL
                or r["verdict"] == "error"
            ):
                continue
            if own_fam and model_family(s.get("generator_model")) == own_fam:
                continue
            n += 1
            k += r["verdict"] == "malicious"
        return k, n

    gengap = {}
    archetypes = sorted({s["archetype"] for s in manifest if s["label"] == "malicious"})
    for sc in scanners:
        for mode in modes:
            for arch in archetypes:
                kk, nk = recall_kn(sc, mode, arch, KNOWN)
                ks, ns = recall_kn(sc, mode, arch, {NOVEL})
                if not (nk and ns):
                    continue
                # generator-BALANCED synthetic recall = mean of per-generator rates (equal weight),
                # so the gap isn't dominated by whichever model emitted more/easier samples.
                pg = synth_by_generator(sc, mode, arch)
                rates = [k / n for k, n in pg.values() if n]
                bal = sum(rates) / len(rates) if rates else None
                spread = (max(rates) - min(rates)) if len(rates) > 1 else 0.0
                # T2: cross-family synthetic recall (exclude scanner's own generator family) is the
                # HEADLINE; pooled kept only for transparency. CI, p-value, and FDR all derive from
                # the SAME (cross-family) quantity so the significance columns can't contradict.
                own_fam = scanner_fam.get(sc)
                kx, nx = synth_crossfamily(sc, mode, arch, own_fam)
                if not nx:  # no cross-family samples → fall back to pooled
                    kx, nx = ks, ns
                cell = {
                    "recall_known": wilson(kk, nk),
                    "recall_synthetic": wilson(kx, nx),  # HEADLINE = cross-family
                    "recall_synthetic_pooled": wilson(ks, ns),  # all generators (transparency)
                    "recall_synthetic_balanced": round(bal, 4) if bal is not None else None,
                    "generator_spread": round(spread, 4),
                    "gap_ci": newcombe_diff(kk, nk, kx, nx),  # cross-family
                    "gap_ci_pooled": newcombe_diff(kk, nk, ks, ns),
                    "p_value": two_proportion_p(kk, nk, kx, nx),  # cross-family → feeds BH-FDR
                    "scanner_family": own_fam,
                    "samefamily_excluded": (own_fam if own_fam and nx != ns else None),
                }
                # keep the old key name too (site/back-compat reads recall_synthetic_crossfamily)
                cell["recall_synthetic_crossfamily"] = cell["recall_synthetic"]
                cell["gap_ci_crossfamily"] = cell["gap_ci"]
                gengap.setdefault(sc, {}).setdefault(mode, {})[arch] = cell

    # --- WILD-ONLY recall (T1/T2 clean number: real samples, no generator style to detect) ---
    # Pooled across archetypes, per scanner×mode, over provenance == wild_verbatim malicious.
    wild_samples = {sid: s for sid, s in samples.items() if s.get("provenance") == "wild_verbatim"}
    wildonly = _rate(results, wild_samples, lambda r, s: (r["scanner"], r["mode"]), True)
    wild_recall = {}
    for (sc, mode), c in wildonly.items():
        wild_recall.setdefault(sc, {})[mode] = {"wilson": wilson(c["k"], c["n"])}

    # --- per-generator-model recall (fingerprint check: should be ~invariant) ---
    fpr = _rate(results, samples, lambda r, s: (r["scanner"], r["mode"], s.get("generator_model", "?")), True)
    by_gen = {}
    for (sc, mode, gen), c in fpr.items():
        if gen and gen != "?":
            by_gen.setdefault(sc, {}).setdefault(mode, {})[gen] = wilson(c["k"], c["n"])

    # --- McNemar: static vs +llm (paired on malicious samples) ---
    mcnemar = {}
    if "static" in modes and "llm" in modes:
        per = defaultdict(lambda: {"b": 0, "c": 0})  # b: static right/llm wrong; c: opposite
        v = defaultdict(dict)
        for r in results:
            s = samples.get(r["sample_id"])
            if s and s["label"] == "malicious" and r["verdict"] != "error":
                v[(r["scanner"], r["sample_id"])][r["mode"]] = r["verdict"] == "malicious"
        for (sc, _sid), mv in v.items():
            if "static" in mv and "llm" in mv:
                if mv["static"] and not mv["llm"]:
                    per[sc]["b"] += 1
                elif not mv["static"] and mv["llm"]:
                    per[sc]["c"] += 1
        mcnemar = {sc: mcnemar_exact(d["b"], d["c"]) for sc, d in per.items()}

    # --- cross-scanner consensus on malicious (static mode) ---
    flags = defaultdict(list)
    for r in results:
        s = samples.get(r["sample_id"])
        if (
            s
            and s["label"] == "malicious"
            and r["mode"] == ("static" if "static" in modes else modes[0])
            and r["verdict"] != "error"
        ):
            flags[r["sample_id"]].append(r["verdict"] == "malicious")
    considered = [f for f in flags.values() if len(f) >= 2]
    full = sum(1 for f in considered if all(f))
    consensus = {
        "n": len(considered),
        "full_consensus_rate": round(full / len(considered), 4) if considered else None,
    }

    # --- BH-FDR across the WHOLE family of comparisons (T5: control false discovery, not just
    # per-cell CIs). Pool every gen-gap p-value + every McNemar p-value, correct at q=0.05, and
    # write significant_fdr back onto each cell so the board never over-claims significance. ---
    q = 0.05
    pslots = []  # cells carrying a p_value, in a flat list to FDR-correct together
    for mm in gengap.values():
        for am in mm.values():
            for cell in am.values():
                if cell.get("p_value") is not None:
                    pslots.append(cell)
    for d in mcnemar.values():
        if d.get("discordant", 0) > 0:
            pslots.append(d)
    flags_fdr = benjamini_hochberg([s["p_value"] for s in pslots], q=q)
    for slot, sig in zip(pslots, flags_fdr, strict=True):
        slot["significant_fdr"] = bool(sig)
    fdr = {"q": q, "n_comparisons": len(pslots), "n_significant": sum(flags_fdr)}

    return {
        "scanners": scanners,
        "modes": modes,
        "corpus": {
            "n": len(manifest),
            "by_provenance": dict(_count(manifest, "provenance")),
            # malicious-only provenance: the honest count (by_provenance includes benign wild scrape,
            # so wild_verbatim there is ~125 but malicious wild is only a handful — surface both).
            "by_provenance_malicious": dict(
                _count([s for s in manifest if s["label"] == "malicious"], "provenance")
            ),
            # explicit benign split too, so a reader reconciles e.g. wild_verbatim(all)=malicious+benign
            # and never mistakes the all-provenance count for a malicious count.
            "by_provenance_benign": dict(
                _count([s for s in manifest if s["label"] == "benign"], "provenance")
            ),
            "by_archetype": dict(_count([s for s in manifest if s["label"] == "malicious"], "archetype")),
            # wild malicious per archetype (exposes that some archetypes have ZERO real samples)
            "wild_malicious_by_archetype": dict(
                _count(
                    [
                        s
                        for s in manifest
                        if s["label"] == "malicious" and s.get("provenance") == "wild_verbatim"
                    ],
                    "archetype",
                )
            ),
        },
        "recall": recall,
        "wild_recall": wild_recall,
        "scanner_models": {sc: scanner_models.get(sc) for sc in scanners},
        "scanner_type": {sc: SCANNER_TYPE.get(sc, "unknown") for sc in scanners},
        "scanner_family": scanner_fam,
        "false_positive": fprate,
        "generalization_gap": gengap,
        "per_generator_recall": by_gen,
        "mcnemar_static_vs_llm": mcnemar,
        "consensus": consensus,
        "fdr": fdr,
    }


def _count(rows, key):
    c = defaultdict(int)
    for r in rows:
        c[r.get(key, "?")] += 1
    return c
