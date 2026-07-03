# Notices & attributions

skillscan.sh is an independent scoreboard. It grades **scanners**, not skills, and is **not a
certification**. Scanner and product names are trademarks of their respective owners, used
**nominatively** to identify what was tested — no affiliation or endorsement is implied or claimed.

## Scanners graded or cited

| Tool | Owner | License | Use here |
|---|---|---|---|
| [SkillSpector](https://github.com/NVIDIA/SkillSpector) | NVIDIA | Apache-2.0 | graded (static + `+llm`), pinned `cff7ecc` |
| AI Defense skill-scanner | [Cisco](https://www.cisco.com) | Apache-2.0 | graded (static + `+llm`), pinned `ff708ea` |
| Agent Scan | [Snyk](https://snyk.io) | proprietary (free self-serve tier) | graded (cloud LLM), `0.5.10` |
| [SkillGate](https://github.com/charliechenye/SkillGate) | charliechenye | MIT | graded on the full corpus — run offline in an isolated sandbox via `check --policy`, pinned `c0324161`; high recall driven by a high benign false-positive rate (see [Methodology §3](methodology.html)) |
| AI Skills Checker | [ESET](https://www.eset.com) | proprietary | cited — web-form only, not scriptable |
| Skillgate | [Mitiga](https://www.mitiga.io) | proprietary | cited — account-gated, no public API |
| SkillSieve | (arXiv:2604.06550) | open-sourced | cited — F1 0.920 on its 390-skill benchmark; not yet integrated into this harness |
| BIV | (arXiv:2605.11770) | published benchmark | cited — corroborating, not re-run |

Apache-2.0 scanners are run from their published source at the pinned commit; no source is
redistributed here. Proprietary tools are exercised only through their owners' free, self-serve
interfaces under normal terms of use.

## Datasets & corpora

| Source | Provenance | License | Use here |
|---|---|---|---|
| Skill-Inject (arXiv:2602.20156 · [repo](https://github.com/aisa-group/skill-inject) · [site](https://www.skill-inject.com/)) | published injection benchmark (36 overt + 48 contextual templates) | MIT — [added 2026-07-01](https://github.com/aisa-group/skill-inject/issues/3) after we asked | injection templates reconstructed into base skills and scored **locally**; **not redistributed** |
| [MaliciousAgentSkillsBench](https://github.com/protectskills/MaliciousAgentSkillsBench) (`ProtectSkills`) | mas-bench "suspicious"-recovered skills (n=1588) | MIT | `dual_use` FP-bait (the FP X-axis); reconstructed/scored locally |
| Liu et al., USENIX Security 2026 (arXiv:2602.06547) | wild-prevalence study (157 / 98,380) | published paper | cited for threat-model grounding + wild scarcity |

Our scoring corpus is **private** (anti-gaming). We publish the method, the harness, aggregate
results, per-sample provenance metadata, and an example corpus — not the full corpus, and not any
third-party dataset content we did not author.

## Models (LLM controls & baselines)

Run via their providers' APIs under normal terms — none are products we grade: OpenAI `gpt-4o` /
`gpt-4o-mini`; Anthropic `claude-sonnet-4-6` / `claude-haiku-4-5` / `claude-opus-4-8`; open-weight `Qwen/Qwen2.5-72B-Instruct`,
`microsoft/phi-4`, and the defanged-synthetic generators (`mixtral-8x22b`, `gemma-2-27b`, `hermes-3`,
`llama-3.3-70b`, `qwen2.5-72b`, `deepseek-v3.1`). Provider/cross-family contamination is disclosed in
[Methodology §2.6](methodology.html).

## Vendor neutrality & corrections

No preferential treatment, no methodology accommodation or score negotiation; vendor responses may be
published verbatim and never alter scoring. Corrections (factual or method errors) are
welcome from anyone — see the corrections policy in [Methodology §7](methodology.html). This is **not
security advice** and carries **no warranty**.

## Responsible disclosure

Reconstructed malicious cases are composed and scored only in disposable, isolated environments and are
**never redistributed**. We do not publish working novel exploit payloads; the `synthetic_novel` set is
defanged and kept private.
