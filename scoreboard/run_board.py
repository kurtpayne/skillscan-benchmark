"""Run the full board: corpus manifest × scanners × modes → flat results → analyze → board.json.

Scanners: SkillSpector + Cisco (static, and +llm via OpenAI-compatible endpoint), Snyk (cloud),
and two LLM baselines (Qwen in-set on Modal, phi-4 disjoint on OpenRouter). The +llm pass points
the products at our OPEN-WEIGHT Modal Qwen (Principle 2); the optional frontier pass (--frontier-model)
uses OpenRouter and writes a SEPARATE board. Every sample is normalized to a well-formed skill
(name+description frontmatter) so all scanners can parse it. Caches by (scanner@ver, sha, k, mode);
stochastic scanners run K times and are majority-voted.

Usage:
  # open-weight board (static + products' +llm on Modal + Snyk + baselines)
  infisical run --env=dev -- python3 -m scoreboard.run_board --scanner-llm --snyk --k 3 \
     --corpus ../skillscan-corpus/corpus --out board_v1.json
  # frontier pass (separate board)
  infisical run --env=dev -- python3 -m scoreboard.run_board --no-baseline \
     --frontier-model openai/gpt-4o --out board_v1_frontier.json
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import random
import shutil
import subprocess
import tempfile
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import analyze
from .adapters import (
    CiscoSkillScannerAdapter,
    LLMBaselineAdapter,
    SkillSpectorAdapter,
    SnykAgentScanAdapter,
)
from .adapters.skillgate import SkillGateAdapter
from .adapters.skillscan import SkillscanAdapter
from .cache import ResultCache
from .manifest import ensure_skill_frontmatter, strip_label_frontmatter
from .model import Verdict, sha256_of_path


def _resolve_staging() -> str:
    """Locate the cloned-scanner staging dir. Order: $SCOREBOARD_STAGING, the in-repo
    `_scoreboard_staging`, then the sibling `~/skillscan-family/_scoreboard_staging`. Returns the
    first that exists; else the in-repo default (startup validation will then fail loudly rather
    than silently scoring every sample ERROR — the repro footgun the e2e check caught)."""
    env = os.environ.get("SCOREBOARD_STAGING")
    if env:
        return env
    for cand in ("_scoreboard_staging", os.path.expanduser("~/skillscan-family/_scoreboard_staging")):
        if os.path.isdir(cand):
            return cand
    return "_scoreboard_staging"


STG = _resolve_staging()


def load_corpus(corpus_dir, benign_cap):
    rows = []
    for mp in glob.glob(os.path.join(corpus_dir, "manifest.*.jsonl")) + [
        os.path.join(corpus_dir, "manifest.jsonl")
    ]:
        if os.path.exists(mp):
            for ln in open(mp, encoding="utf-8"):
                ln = ln.strip()
                if ln and not ln.startswith("#"):
                    rows.append(json.loads(ln))
    # dedup by id
    seen, uniq = set(), []
    for r in rows:
        if r["id"] not in seen and r.get("content_path"):
            seen.add(r["id"])
            uniq.append(r)
    # cap benign for runtime — but NEVER cap the generated-benign control (it's a fixed, small,
    # purpose-built tier; capping it would defeat the comparison).
    mal = [r for r in uniq if r["label"] == "malicious"]
    random.seed(13)
    # generated_benign control (small, fixed) — never capped.
    gen_ben = [r for r in uniq if r["label"] == "benign" and r.get("tier") == "generated_benign"]
    # dual_use control — sampled to a tight-CI size (the recovered set is ~1.6k; no need to scan all,
    # and it keeps the Snyk-cloud / LLM cost bounded). Full set stays in the corpus manifests.
    dual = [r for r in uniq if r["label"] == "benign" and r.get("tier") == "dual_use"]
    if len(dual) > 300:
        dual = random.sample(dual, 300)
    _ctrl_tiers = ("generated_benign", "dual_use")
    ben = [r for r in uniq if r["label"] == "benign" and r.get("tier") not in _ctrl_tiers]
    if benign_cap and len(ben) > benign_cap:
        ben = random.sample(ben, benign_cap)
    return mal + ben + gen_ben + dual


_OPENROUTER = "https://openrouter.ai/api/v1/chat/completions"
_OPENROUTER_V1 = "https://openrouter.ai/api/v1"
_SS_BIN = f"{STG}/skillspector/.venv/bin/skillspector"
_CISCO_BIN = f"{STG}/cisco-skill-scanner/.venv/bin/skill-scanner"
_SS_VER = "cff7ecc"
_CISCO_VER = "ff708ea"


def _modal_v1():
    """The Modal vLLM /v1 root (strip the /chat/completions suffix from SCOREBOARD_LLM_URL)."""
    url = os.environ.get("SCOREBOARD_LLM_URL", "")
    return url.rsplit("/chat/completions", 1)[0] if url else ""


_SNYK_BIN = f"{STG}/snyk-agent-scan/.venv/bin/snyk-agent-scan"
_SNYK_VER = "0.5.10"


def build_adapters(
    enable_baseline,
    disjoint_model="microsoft/phi-4",
    scanner_llm=False,
    frontier_model="",
    llm_timeout=300,
    enable_snyk=False,
    llm_products=("skillspector", "cisco"),
):
    # which products get a +llm pass. Cisco +llm requires OpenAI json_schema structured output,
    # which our open-weight vLLM AWQ endpoint HTTP500s on — so the open-weight pass is SkillSpector
    # only; Cisco's +llm is evaluated in the frontier pass (json_schema-capable).
    lp = set(llm_products)
    a = [
        SkillSpectorAdapter(binary=_SS_BIN, version=_SS_VER),
        CiscoSkillScannerAdapter(binary=_CISCO_BIN, version=_CISCO_VER),
    ]
    if enable_snyk:
        # Snyk Agent Scan = cloud product (its own LLM); SNYK_TOKEN mapped from Infisical SNYK_API_KEY.
        snyk = SnykAgentScanAdapter(binary=_SNYK_BIN, version=_SNYK_VER, timeout_s=180)
        snyk.env = {"SNYK_TOKEN": os.environ.get("SNYK_API_KEY", "") or os.environ.get("SNYK_TOKEN", "")}
        a.append(snyk)
    if scanner_llm:
        # T4 fair board: run each product with its +LLM analysis on our OPEN-WEIGHT Modal Qwen
        # (Principle 2 — malicious corpus stays off commercial endpoints).
        url, key, model = (
            _modal_v1(),
            os.environ.get("SCOREBOARD_LLM_KEY", ""),
            "Qwen/Qwen2.5-72B-Instruct-AWQ",
        )
        if "skillspector" in lp:
            a.append(
                SkillSpectorAdapter(
                    _SS_BIN,
                    _SS_VER,
                    llm_timeout,
                    llm=True,
                    llm_model=model,
                    llm_base_url=url,
                    llm_api_key=key,
                    llm_label="qwen",
                )
            )
        if "cisco" in lp:
            a.append(
                CiscoSkillScannerAdapter(
                    _CISCO_BIN,
                    _CISCO_VER,
                    llm_timeout,
                    llm=True,
                    llm_model=model,
                    llm_base_url=url,
                    llm_api_key=key,
                    llm_label="qwen",
                )
            )
    if frontier_model:
        # T4 frontier pass (user-approved exception): products + a FRONTIER brain. OpenAI models route
        # DIRECT to api.openai.com (OpenRouter's gateway blocks ~100% of skill-content requests);
        # everything else via OpenRouter. K=1; refusals captured as ERROR (separate board).
        if frontier_model.startswith(("gpt-", "openai/", "o1", "o3", "o4")):
            fbase, fkey = "https://api.openai.com/v1", os.environ.get("OPENAI_API_KEY", "")
            flabel = "frontier-openai-direct"
        else:
            fbase, fkey = _OPENROUTER_V1, os.environ.get("OPENROUTER_API_KEY", "")
            flabel = "frontier"
        fa = []
        if "skillspector" in lp:
            fa.append(
                SkillSpectorAdapter(
                    _SS_BIN,
                    _SS_VER,
                    llm_timeout,
                    llm=True,
                    llm_model=frontier_model,
                    llm_base_url=fbase,
                    llm_api_key=fkey,
                    llm_label=flabel,
                )
            )
        if "cisco" in lp:
            fa.append(
                CiscoSkillScannerAdapter(
                    _CISCO_BIN,
                    _CISCO_VER,
                    llm_timeout,
                    llm=True,
                    llm_model=frontier_model,
                    llm_base_url=fbase,
                    llm_api_key=fkey,
                    llm_label=flabel,
                )
            )
        a += fa
    if enable_baseline:
        # In-set baseline: Modal-served Qwen (open-weight; endpoint+key from SCOREBOARD_LLM_URL/KEY
        # env, Principle 2). Qwen IS in the generator set → analyze scores it CROSS-FAMILY.
        a.append(
            LLMBaselineAdapter(
                model="Qwen/Qwen2.5-72B-Instruct-AWQ", version="qwen-72b-modal", enabled=True, timeout_s=120
            )
        )
        # T2 canonical control: a baseline DISJOINT from every generator family (phi ∉
        # {qwen,llama,deepseek,mistral,gemma,hermes}). Open-weight via OpenRouter. Its synthetic
        # recall is contamination-free by construction → the headline LLM number.
        if disjoint_model:
            a.append(
                LLMBaselineAdapter(
                    model=disjoint_model,
                    name="llm-baseline-disjoint",
                    version=f"{disjoint_model.split('/')[-1]}-openrouter",
                    enabled=True,
                    timeout_s=120,
                    endpoint=_OPENROUTER,
                    key_env="OPENROUTER_API_KEY",
                )
            )
    return a


def adapter_models(adapters):
    """scanner name → model id (for LLM scanners) so analyze can score cross-family."""
    return {a.name: getattr(a, "model", None) for a in adapters}


def fold_repeats(raw):
    """Fold K stochastic repeats → ONE verdict per (sample, scanner, mode) by MAJORITY vote,
    so K runs don't pseudo-replicate into the recall denominators (Wilson n must = #samples,
    not #samples×K). Ties break MALICIOUS (conservative for a security scanner). Returns
    (results, stability) where stability[scanner] = mean fraction of repeats agreeing with the
    chosen verdict — a stochasticity readout. Errors are dropped before voting; an all-error
    cell stays ERROR."""
    groups = defaultdict(list)  # (sample, scanner, mode) -> [verdicts]
    for r in raw:
        groups[(r["sample_id"], r["scanner"], r["mode"])].append(r["verdict"])
    results, agree = [], defaultdict(list)
    for (sid, sc, mode), verdicts in groups.items():
        non_err = [v for v in verdicts if v != "error"]
        if not non_err:
            results.append({"sample_id": sid, "scanner": sc, "mode": mode, "verdict": "error"})
            continue
        cnt = Counter(non_err)
        mal, ben = cnt.get("malicious", 0), cnt.get("benign", 0)
        chosen = "malicious" if mal >= ben else "benign"
        results.append({"sample_id": sid, "scanner": sc, "mode": mode, "verdict": chosen})
        if len(non_err) > 1:
            agree[sc].append(cnt[chosen] / len(non_err))
    stability = {sc: round(sum(a) / len(a), 4) for sc, a in agree.items() if a}
    return results, stability


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--corpus",
        default=os.environ.get("SKILLSCAN_CORPUS", "../skillscan-corpus/corpus"),
        help="corpus dir (default: $SKILLSCAN_CORPUS or the private sibling repo; see example_corpus/)",
    )
    ap.add_argument("--benign-cap", type=int, default=120)
    ap.add_argument("--out", default="board.json")
    ap.add_argument("--no-baseline", action="store_true")
    ap.add_argument(
        "--disjoint-model",
        default="microsoft/phi-4",
        help='T2 canonical baseline model, disjoint from generators ("" to skip)',
    )
    ap.add_argument("--limit", type=int, default=0, help="cap total samples (validation)")
    ap.add_argument("--cache", default="_staging/board_cache.json")
    ap.add_argument("--k", type=int, default=1, help="repeats for stochastic scanners (majority-voted)")
    ap.add_argument("--workers", type=int, default=8, help="parallel scan workers")
    ap.add_argument("--scanner-llm", action="store_true", help="add products' +llm (open-weight Modal) pass")
    ap.add_argument(
        "--frontier-model", default="", help="add products' +llm frontier pass (OpenRouter); separate board"
    )
    ap.add_argument("--llm-timeout", type=int, default=300, help="timeout for product +llm scans")
    ap.add_argument("--snyk", action="store_true", help="add Snyk Agent Scan (cloud product)")
    ap.add_argument(
        "--llm-products", default="skillspector,cisco", help="which products get a +llm pass (comma list)"
    )
    ap.add_argument(
        "--skillscan",
        action="store_true",
        help="run ONLY the author's own retired skillscan (static rules) as a non-graded "
        "reference self-entry; ignores all other scanner flags",
    )
    ap.add_argument(
        "--skillscan-ml",
        action="store_true",
        help="with --skillscan, also run the local ML mode (--ml-detect, v4 Qwen2.5-1.5B GGUF)",
    )
    ap.add_argument(
        "--only-skillgate",
        action="store_true",
        help="run ONLY SkillGate (full-corpus pass for its master-table row); run inside an isolated "
        "container (docker --network none) since it's untrusted; ignores other scanner flags",
    )
    ap.add_argument("--skillgate-bin", default="skillgate", help="SkillGate executable (on PATH in the image)")
    ap.add_argument("--skillgate-version", default="c0324161", help="SkillGate pinned version label")
    ap.add_argument("--skillgate-profile", default="audit",
                    help="SkillGate policy profile (audit=most discriminating; preinstall/strict block ~everything)")
    args = ap.parse_args(argv)

    manifest = load_corpus(args.corpus, args.benign_cap)
    if args.limit:
        random.seed(13)
        manifest = random.sample(manifest, min(args.limit, len(manifest)))
    print(
        f"corpus: {len(manifest)} samples "
        f"({sum(r['label'] == 'malicious' for r in manifest)} mal / "
        f"{sum(r['label'] == 'benign' for r in manifest)} ben)",
        flush=True,
    )
    if args.only_skillgate:
        # SkillGate ONLY — full-corpus pass for its master-table row. Untrusted day-old code, so this
        # is meant to run inside `docker run --network none` (or the Fly sandbox); set
        # SCOREBOARD_SKILLGATE_NETCUT=0 when the container already isolates the network. Generate the
        # preinstall gate policy first (the deployable-screening verdict; see adapters/skillgate.py).
        prof = args.skillgate_profile
        pol = os.environ.get("SKILLGATE_POLICY", os.path.join(os.getcwd(), f"skillgate.{prof}.yaml"))
        if not os.path.exists(pol):
            subprocess.run(
                [args.skillgate_bin, "policy", "init", "--profile", prof, "-o", pol],
                check=True, capture_output=True, text=True, timeout=60,
            )
        adapters = [SkillGateAdapter(binary=args.skillgate_bin, version=args.skillgate_version,
                                     timeout_s=90, policy=pol)]
    elif args.skillscan:
        # Author's own retired scanner, included ONLY as a labeled non-graded reference.
        # static rules (+ optional local ML via --skillscan-ml: --ml-detect, v4 Qwen2.5-1.5B GGUF).
        adapters = [SkillscanAdapter(ml=False)]
        if args.skillscan_ml:
            # Score the ML mode CROSS-FAMILY vs qwen-generated synthetic (its detector is a qwen) —
            # same rule as the Qwen baseline, the conservative (non-flattering) choice.
            ml = SkillscanAdapter(ml=True)
            ml.model = "Qwen/Qwen2.5-1.5B-Instruct"
            adapters.append(ml)
    else:
        adapters = build_adapters(
            not args.no_baseline,
            disjoint_model=args.disjoint_model or "",
            scanner_llm=args.scanner_llm,
            frontier_model=args.frontier_model,
            llm_timeout=args.llm_timeout,
            enable_snyk=args.snyk,
            llm_products=tuple(p.strip() for p in args.llm_products.split(",") if p.strip()),
        )
    # Fail LOUDLY if a binary-based scanner's executable is missing — otherwise every scan returns
    # ERROR and the board silently reports 0% recall (the repro footgun the e2e check caught: STG
    # defaulted to a relative path that didn't exist). LLM/endpoint adapters have no local binary.
    # A binary-based scanner's executable lives under `.venv/bin/` or is an absolute path; an LLM
    # baseline's `binary` is a model id (e.g. "Qwen/Qwen2.5-72B-Instruct-AWQ") — never a local file.
    def _is_local_binary(b: str) -> bool:
        b = str(b)
        return "://" not in b and (".venv/bin/" in b or "/bin/" in b or os.path.isabs(b))

    missing = [
        (a.name, a.binary)
        for a in adapters
        if getattr(a, "binary", "") and _is_local_binary(a.binary) and not os.path.exists(a.binary)
    ]
    if missing:
        lines = "\n".join(f"  - {n}: {b}" for n, b in missing)
        raise SystemExit(
            f"scanner binary not found (would silently score every sample ERROR):\n{lines}\n"
            f"Set SCOREBOARD_STAGING to your cloned-scanner dir "
            f"(currently resolved to '{STG}'). See REPRODUCE.md."
        )
    os.makedirs(os.path.dirname(args.cache) or ".", exist_ok=True)
    cache = ResultCache(args.cache)

    # 1. Pre-stage one SKILL.md dir per sample. Normalize to a well-formed skill (ensure
    #    name+description frontmatter) so EVERY scanner can parse it — Cisco rejects skills
    #    missing those, and ~60% of the corpus (defanged synthetic, harvested wild/benign) has
    #    no frontmatter. Cache sha is computed on the NORMALIZED content the scanners see.
    staged = []  # (sample, sha, tmpdir)
    for s in manifest:
        cp = os.path.join(args.corpus, s["content_path"])
        if not os.path.exists(cp):
            continue
        tmp = tempfile.mkdtemp(prefix="sb_")
        if os.path.isdir(cp):
            # multi-file skill (e.g. Skill-Inject: SKILL.md + scripts/ + references/) — copy the
            # whole tree so scanners see the full skill (the payload often lives in scripts/), then
            # normalize the SKILL.md frontmatter in place. sha over the normalized tree.
            shutil.copytree(cp, tmp, dirs_exist_ok=True)
            skillmd = os.path.join(tmp, "SKILL.md")
            if os.path.exists(skillmd):
                with open(skillmd, encoding="utf-8", errors="replace") as fh:
                    c = ensure_skill_frontmatter(strip_label_frontmatter(fh.read()), s["id"])
                with open(skillmd, "w", encoding="utf-8") as fh:
                    fh.write(c)
            sha = sha256_of_path(tmp)
        else:
            with open(cp, encoding="utf-8", errors="replace") as fh:
                # strip any label-bearing frontmatter for ALL scanners (not just LLM baselines), then
                # guarantee name+description. No-op (cache-preserving) on the label-free corpus, but
                # enforces the no-leakage invariant for external datasets.
                content = ensure_skill_frontmatter(strip_label_frontmatter(fh.read()), s["id"])
            sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
            with open(os.path.join(tmp, "SKILL.md"), "w", encoding="utf-8") as fh:
                fh.write(content)
        staged.append((s, sha, tmp))

    # 2. Worklist: (sample, sha, dir, adapter, k). Stochastic adapters run K times (namespaced
    #    cache slots); deterministic ones run once.
    work = []
    for s, sha, tmp in staged:
        for a in adapters:
            kruns = args.k if a.stochastic else 1
            for k in range(kruns):
                work.append((s, sha, tmp, a, k))

    lock = threading.Lock()
    raw = []
    done = 0

    def run_one(item):
        s, sha, tmp, a, k = item
        with lock:
            cached = cache.get(a.name, a.version, sha, k, a.mode)
        r = cached or a.scan(s["id"], tmp)
        if not cached:
            with lock:
                cache.put(sha, r, k, a.mode)
        return {
            "sample_id": s["id"],
            "scanner": a.name,
            "mode": a.mode,
            "k": k,
            "verdict": r.verdict.value if isinstance(r.verdict, Verdict) else r.verdict,
        }

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(run_one, it) for it in work]
        for f in as_completed(futs):
            raw.append(f.result())
            done += 1
            if done % 100 == 0:
                print(f"  scanned {done}/{len(work)}", flush=True)
                with lock:
                    cache.save()
    with lock:
        cache.save()
    for _s, _sha, tmp in staged:
        shutil.rmtree(tmp, ignore_errors=True)

    # 3. Fold K stochastic repeats → one verdict/sample (no pseudo-replication), then analyze.
    results, stability = fold_repeats(raw)
    board = analyze.compute(manifest, results, scanner_models=adapter_models(adapters))
    board["k"] = args.k
    board["stochastic_stability"] = stability
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(board, f, indent=2)
    print(
        f"\nwrote {args.out} | scanners={board['scanners']} | "
        f"consensus={board['consensus']} | stability={stability}"
    )


if __name__ == "__main__":
    main()
