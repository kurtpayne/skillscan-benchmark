#!/bin/bash
# Profile-A re-run (the 90-day cadence job): re-score the headline slice and check it still
# reproduces the committed board. Profile A = static board (SkillSpector + Cisco) + the 4-model
# independent Skill-Inject set. ~$5 API, ~10-15 min. Cheap, deterministic-ish, and exactly what
# the site leads with.
#
# Run MANUALLY (owner keeps a phone reminder; intentionally NOT scheduled — no cron/launchd).
# The full quarterly playbook (research new engines / shipped updates → decide → run → republish)
# is the `skillscan-benchmark-update` skill in skillscan-private/skills/. This script is its run step.
#
# SAFE BY DEFAULT: re-runs into _repro/, diffs vs the committed board, prints PASS/INVESTIGATE,
# and STOPS. It does NOT touch committed board JSON, rebuild the site, or push. Pass --apply to
# promote the fresh results into the committed board + rebuild the site (still no auto-push; a
# human reviews `git diff` and pushes). Modal/open-weight is NOT run here — per decision, that
# only re-runs when a new free frontier open-weight model ships.
#
#   ops/rerun_profile_a.sh           # check reproducibility, report, stop
#   ops/rerun_profile_a.sh --apply   # also promote + rebuild (review git diff, then push)
set -euo pipefail
cd "$(dirname "$0")/.."
export SCOREBOARD_STAGING="${SCOREBOARD_STAGING:-$HOME/skillscan-family/_scoreboard_staging}"
export SKILLSCAN_CORPUS="${SKILLSCAN_CORPUS:-../skillscan-corpus/corpus}"
APPLY="${1:-}"
mkdir -p _repro
echo "== Profile A re-run @ $(date -u +%Y-%m-%dT%H:%MZ) | staging=$SCOREBOARD_STAGING =="

echo "-- static board (SkillSpector + Cisco) --"
infisical run --env=dev -- python3 -m scoreboard.run_board \
  --no-baseline --benign-cap 120 \
  --out _repro/board_static_fresh.json --cache _repro/rerun_static_cache.json --workers 8

echo "-- independent Skill-Inject (4 frontier models) --"
for spec in gpt-4o:repro_gpt-4o gpt-4o-mini:repro_gpt-4o-mini \
            claude-sonnet-4-6:repro_claude-sonnet claude-haiku-4-5-20251001:repro_claude-haiku; do
  m="${spec%%:*}"; o="${spec##*:}"
  infisical run --env=dev -- python3 scripts/score_skillinject_llm.py --model "$m" --workers 6 --out "_repro/$o.json"
done

echo "-- reproducibility diff vs committed board --"
python3 scripts/repro_diff.py

if [ "$APPLY" = "--apply" ]; then
  echo "-- --apply: promoting fresh results into committed board + rebuilding site --"
  cp _repro/board_static_fresh.json board_v11_static.json
  cp _repro/repro_gpt-4o.json skillinject_llm.json
  cp _repro/repro_gpt-4o-mini.json skillinject_llm_gpt-4o-mini.json
  cp _repro/repro_claude-sonnet.json skillinject_llm_claude-sonnet.json
  cp _repro/repro_claude-haiku.json skillinject_llm_claude-haiku.json
  python3 scripts/build_site.py
  echo "DONE. Review 'git diff', then commit + push to deploy. (Numbers are dated/directional;"
  echo "      bump the corpus/run-date stamp in build_site.py + REPRODUCE.md if they moved.)"
else
  echo "CHECK COMPLETE (no files changed). Re-run with --apply to promote, or investigate deltas above."
fi
