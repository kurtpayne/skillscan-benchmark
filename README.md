# skillscan-benchmark

An **independent, FOSS scoreboard** that grades AI-skill **security scanners** — not skills, and not a
certification. Built by a solo white-hat who built a scanner, measured it honestly, and **retired it**;
there's no tool to sell here, so the score can be kept honestly. Live (public draft):
**[skillscan.sh](https://kurtpayne.github.io/skillscan-benchmark/)**.

## The finding: capability is the price

Measured on an **independent benchmark we did not author** (Skill-Inject, arXiv:2602.20156 — 84 published
injection cases), detection recall climbs straight up the model-cost ladder:

| Method | Recall on the independent set (n=84) |
|---|---|
| Static rules (SkillSpector, Cisco) | 13–32% |
| gpt-4o-mini | 23% |
| claude-haiku-4.5 | 26% |
| gpt-4o | 38% |
| **claude-sonnet-4.6** | **81%** |
| claude-opus-4.8 | 81% (ties sonnet; stochastic — rejects temp-0) |

> Recall is measured on the independent Skill-Inject set. The **false-positive rates** these pair with
> (e.g. the flagship's low FP) are measured on the **in-house benign/dual-use set** — Skill-Inject ships
> no benign cases, so no scanner has a recall *and* an FP number from the same independent corpus.

The cheap / local / private bet (static rules, small models) fails; only a **flagship frontier model
reading the skill** clears bar — the exact expensive, cloud-dependent, content-disclosing, token-burning option the
project set out to avoid. "Use an LLM" isn't advice until you name the model. Numbers are **dated and
directional** (the real-wild sample is small and we say so).

## How provenance actually works (read this before trusting any number)

The scoring corpus is **private** (anti-gaming); method, harness, and aggregate results are public.
The malicious corpus is a mix, **disclosed in full** (see [METHODOLOGY](METHODOLOGY.md) §2.6):
- **`published_independent`** — Skill-Inject, a *different group's* published benchmark we authored none
  of. **This is the headline**, because it's free of *our*-authorship contamination.
- **`organic_authored`** — LLM-written via our tooling (gpt-4o / Claude / DeepSeek).
- **`synthetic_novel`** — defanged, open-weight-generated.
- **`wild_verbatim`** — real in-the-wild malicious (n=5, all code-execution; small, disclosed loudly).

Because our in-house sets are LLM-written, an LLM scoring them has a self-recognition edge — so we do
**not** headline the (higher) in-house LLM recall. We lead with the independent set. We do **not** claim
even that is "uncontaminated in the absolute" (residual confounds are flagged: Skill-Inject's authors'
pipeline is unverifiable, and a public arXiv set could enter pretraining). See [NOTICES](NOTICES.md) for
attributions/licenses and [METHODOLOGY](METHODOLOGY.md) for the full method.

## What it measures
Per `scanner × archetype × provenance × difficulty tier`, plus benign/dual-use controls:
**recall**, **false-positive rate**, **refusal/error rate** — three separate columns (a miss and a
refusal are different failures) — each with a **Wilson 95% interval**; never one number. Plus BH-FDR
across cells, McNemar for paired comparisons, a recall-vs-FP frontier, the generalization gap, and the
cross-scanner consensus stat. Labels live in an **external manifest** (no leakage into skill files).

- **Archetypes:** `code_execution`, `data_exfiltration`, `agent_hijacking`
- **Tiers:** `overt` / `indirect` (the independent set carries the tier signal; the in-house set is
  overt-dominated and that's disclosed)

## Scanner roster
- **Graded** (free / self-serve — the access bar): **NVIDIA SkillSpector** (static + `+llm`), **Cisco
  AI Defense skill-scanner** (static + `+llm`), **Snyk Agent Scan** (free tier, cloud LLM), **SkillGate**
  (MIT, pure-static — run offline in an isolated sandbox; the block-all corner: over-blocks at both profiles we tested).
- **Cited, not graded:** ESET (web-form only), Mitiga (account-gated), SkillSieve (open-sourced; not yet integrated),
  BIV (published benchmark). See the access-bar table on the site.
- **LLM controls** (not graded products): gpt-4o, gpt-4o-mini, claude-sonnet-4-6, claude-haiku-4-5
  (direct APIs, temp 0) and claude-opus-4-8 (default temp — rejects temp-0), plus open-weight
  Qwen-72B / phi-4 baselines.

## Run
```bash
export SCOREBOARD_STAGING=~/skillscan-family/_scoreboard_staging   # cloned scanners (each in its own venv)
export SKILLSCAN_CORPUS=../skillscan-corpus/corpus                 # private corpus, or your own (see CORPUS_FORMAT.md)
python3 -m pytest tests/ -q
infisical run --env=dev -- python3 -m scoreboard.run_board --no-baseline --benign-cap 120 --out board.json
python3 scripts/build_site.py --board board.json                  # renders docs/
```
If a scanner binary is missing the harness **fails loudly** rather than silently scoring 0%. Full
reproduce instructions + pinned versions: [REPRODUCE.md](REPRODUCE.md).

## Layout
```
scoreboard/        harness — run_board.py (corpus × scanners × modes → analyze → board.json),
                   analyze.py (Wilson/McNemar/Newcombe/BH-FDR/gen-gap/consensus), adapters/, cache.py
scripts/           build_site.py (renders docs/), score_skillinject_llm.py (independent set),
                   frontier_baselines.py (in-house frontier), repro_diff.py (reproducibility check)
ops/               rerun_profile_a.sh (the ~90-day refresh run step)
docs/              the published static site (GitHub Pages); noindex while in draft
METHODOLOGY.md · ABOUT.md · NOTICES.md · REPRODUCE.md
```

## Maintenance
The board is refreshed **manually, ~every 90 days** (owner-triggered; no cron). The full playbook —
research new scanner engines, detect shipped updates (scanner versions, frontier models, new free
open-weight models, new published benchmarks, pricing), decide what to re-run, check reproducibility,
and decide whether to republish — is the `skillscan-benchmark-update` skill (private). Profile A
(static + independent frontier set) ≈ $5/run; reproducibility validated (static + open-weight exact;
temp-0 frontier *cloud* reads reproduce within ±1/84 — cloud temp-0 isn't bit-exact; opus at default temp).

Corrections (factual or method errors) welcome from anyone. Not a certification; no warranty; not
security advice.
