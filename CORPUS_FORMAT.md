# Corpus format — bring your own

This harness **grades scanners against a corpus it loads from disk** — the corpus is *not* baked into
the code. That's deliberate:

- **The code is public** (this repo): the harness, analysis, adapters, methodology.
- **Our corpus is private** (a separate repo) — anti-gaming. Publishing the exact samples would let a
  vendor train/tune to them. We publish aggregate results + method, not the samples. (Open-*method*,
  not open-data.)
- **`example_corpus/` (in this repo) shows the required format** so anyone can run the harness on
  *their own* corpus. The example samples are tiny, inert fixtures (defanged: `cdn-sync.invalid`,
  `PLACEHOLDER_SECRET`) — a format demo, not a real benchmark.

## How the harness finds a corpus
Resolution order: `--corpus <dir>` flag → `$SKILLSCAN_CORPUS` → the default private sibling
(`../skillscan-corpus/corpus`). To run on the example:

```bash
SKILLSCAN_CORPUS=example_corpus python3 -m scoreboard.run_board --no-baseline --benign-cap 0 \
    --out board.json
# or: python3 -m scoreboard.run_board --corpus example_corpus --no-baseline ...
```

## Layout
```
<corpus>/
  manifest.*.jsonl         # one or more JSONL manifests (globbed: manifest.benign.jsonl, …)
  samples/…/<id>.md        # one skill per file; content_path is relative to <corpus>
```

## Manifest schema (one JSON object per line)
| field | required | values / notes |
|---|---|---|
| `id` | yes | unique sample id |
| `label` | yes | `malicious` \| `benign` |
| `provenance` | yes | `wild_verbatim` (real, in-the-wild) \| `organic_authored` (authored, real-threat-grounded) \| `synthetic_novel` (LLM-generated, defanged) \| `synthetic_benign` (generated-benign control) |
| `archetype` | yes | `code_execution` \| `data_exfiltration` \| `agent_hijacking` \| `n/a` (benign) |
| `tier` | yes | `overt` \| `obfuscated` \| `indirect` \| `dual_use` \| `benign` \| `generated_benign` |
| `content_path` | yes | path to the `.md`, relative to the corpus dir |
| `sha256` | optional | of the file; the harness recomputes on the normalized content |
| `generator_model` | malicious-synthetic | which model generated it (enables **cross-family** scoring — an LLM scanner is never credited for catching synthetic its own family generated) |
| `source`, `license` | optional | provenance metadata |

## What the labels drive
- **recall** over `malicious`; **false-positive** over `benign` (bucketed `benign` / `dual_use` /
  `generated_benign`).
- **Generalization gap** = recall(known: wild+organic) − recall(novel: synthetic, cross-family).
- **Cross-family scoring** uses `generator_model` (+ the scanner's own model) — see `scoreboard/analyze.py`.
- Every sample is normalized to a well-formed skill (name+description frontmatter injected if missing)
  and label-frontmatter is stripped before any scanner sees it (no leakage).

Bring your own corpus in this shape and the full board (recall/FP/gen-gap/CIs/FDR/balance score)
computes against it.
