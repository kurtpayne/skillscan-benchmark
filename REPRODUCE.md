# Reproduce

The method and harness are public; the corpus is private (anti-gaming). You can reproduce the
*pipeline* on the shipped example corpus, or point it at your own (see CORPUS_FORMAT.md).

**Source:** everything here lives in one repo —
[github.com/kurtpayne/skillscan-benchmark](https://github.com/kurtpayne/skillscan-benchmark):
the harness (`scoreboard/`), the site generator (`scripts/build_site.py`), this methodology, the
example corpus, and the board JSON the site is rendered from. Clone it and the commands below run as-is.

## Pinned versions (this board run · 2026-06-17 · corpus v1.1)
| component | pin |
|---|---|
| SkillSpector | git `cff7ecc` (static layer) |
| Cisco AI Defense skill-scanner | git `ff708ea` (static layer) |
| Snyk Agent Scan | `0.5.10` (cloud) |
| SkillGate | git `c0324161` (pure-static; graded full-corpus) |
| LLM baseline (in-set) | `Qwen/Qwen2.5-72B-Instruct-AWQ`, temp 0, generic prompt |
| LLM baseline (disjoint control) | `microsoft/phi-4`, temp 0, generic prompt |
| Frontier baselines | `gpt-4o`, `gpt-4o-mini`, `claude-sonnet-4-6`, `claude-haiku-4-5` (raw read, temp 0 — cloud, ±1/84 reproducible); `claude-opus-4-8` (raw read, **default temp** — Opus 4.x rejects temp-0) |

## Scanner staging (required for the real scanners)
The graded scanners are run from their published source, cloned into a **staging dir** with each tool's
own venv (binaries at `<staging>/<tool>/.venv/bin/<tool>`). Point the harness at it:
```bash
export SCOREBOARD_STAGING=/path/to/_scoreboard_staging   # else auto-resolves to ./_scoreboard_staging
                                                         # or ~/skillscan-family/_scoreboard_staging
```
If a scanner binary is missing the harness now **errors out** rather than silently scoring every sample
`ERROR` (= a false 0% board). Static scanners (`--no-llm`) need no API key.

## Run the pipeline on the example corpus (offline, static scanners)
```bash
SKILLSCAN_CORPUS=example_corpus python3 -m scoreboard.run_board --no-baseline --benign-cap 0 \
    --out board.json
python3 scripts/build_site.py --board board.json     # renders docs/
```

## Run on your own corpus
Put your corpus in the layout in `CORPUS_FORMAT.md`, then:
```bash
python3 -m scoreboard.run_board --corpus /path/to/your/corpus --snyk --out board.json
```
Flags: `--scanner-llm` (+llm via an OpenAI-compatible endpoint), `--frontier-model <id>` (separate
frontier board), `--k N` (repeats for stochastic scanners), `--workers N`.

## Data sources (the parts of the corpus we did *not* author)

Our corpus is private (anti-gaming), but the non-generated parts come from public, independent sources —
linked here so the provenance is checkable. (What we *did* generate is disclosed separately: organic
malicious via `gpt-4o` / `claude` / `deepseek`, defanged-synthetic malicious via open-weight models — see
[Methodology §2.6](methodology.html). Those are ours and are *not* in this list.)

| Set (provenance) | n | Source (external, not ours) | License |
|---|---|---|---|
| `published_independent` — the headline | 84 | **Skill-Inject** — [github.com/aisa-group/skill-inject](https://github.com/aisa-group/skill-inject) · [arXiv:2602.20156](https://arxiv.org/abs/2602.20156) | verify (reconstructed locally, not redistributed) |
| `dual_use` FP-bait (the X-axis) | 1588 | **MaliciousAgentSkillsBench** — [github.com/protectskills/MaliciousAgentSkillsBench](https://github.com/protectskills/MaliciousAgentSkillsBench) (mas-bench "suspicious"-recovered) | MIT |
| `benign` control | 500 | real public GitHub skills (harvested; the [openclaw/skills](https://github.com/openclaw/skills) archive is the canonical public index — per-repo provenance is encoded in each sample id) | upstream repo licenses |
| `wild_verbatim` real malicious | 5 | real disclosed skills — **content hashes in [`WILD_PROVENANCE.md`](https://github.com/kurtpayne/skillscan-benchmark/blob/main/WILD_PROVENANCE.md)** (de-identified; source URLs held privately, shared with affected owners / researchers on request) | as published |

Threat-prevalence grounding (cited, not a corpus input): **Liu et al.**, *USENIX Security 2026* —
[arXiv:2602.06547](https://arxiv.org/abs/2602.06547) (157 malicious in 98,380 skills). Scanner sources +
licenses are in [Notices](notices.html).

## What's reproducible vs not
- **Reproducible by anyone:** the full pipeline + analysis (recall/FP/Wilson CIs/BH-FDR/cross-family/
  generalization-gap/balance score) on *any* corpus in the documented format — run it on the example
  or your own.
- **Not bit-for-bit public:** our exact corpus (private, anti-gaming). We publish aggregate results +
  per-sample provenance metadata + this method + the example corpus — reproduce the pipeline on your own.
- **Cloud-scanner / frontier numbers** depend on vendor backends that change over time; we pin dates
  and re-run on a cadence. Open-weight + static runs are deterministic (temp 0, local). Frontier **cloud**
  reads at temp-0 reproduce within **±1/84** run-to-run (cloud temp-0 isn't bit-exact — two sonnet runs
  gave 68/84 and 69/84); claude-opus-4.8 additionally rejects temp-0 and runs at the provider default.

## Code
Harness, adapters, analysis, and methodology are in this repo. Tests: `pytest -q` (40 tests).
