"""Frontier LLM-read baselines — cross-model comparison (user-requested).

Runs frontier models as RAW-READ baselines (same generic, un-primed prompt as the open-weight
baseline) directly against the corpus, and reports per-model recall / false-positive / REFUSAL rate.
Two axes the user asked for: provider (OpenAI vs Anthropic) and size (4o vs 4o-mini, Sonnet vs Haiku).

Why baselines not product-wrappers: clean apples-to-apples with the phi/Qwen baselines, and it
sidesteps OpenRouter's gateway + Cisco's json_schema. Frontier models are FULLY DISJOINT from our six
open-weight generators (none wrote the synthetic set) → synthetic recall is 100% cross-family-clean.

Principle-2 exception (user-approved): malicious corpus → direct commercial APIs, K=1, refusals are
DATA (a model that won't classify is a finding), stop a provider if it hard-errors/abuse-signals.

Run: infisical run -- python3 scripts/frontier_baselines.py --limit 60   # slice; omit --limit for full
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import random
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)  # make the scoreboard package importable when run as a loose script

from scoreboard.adapters.llm_baseline import PROMPT, parse_verdict  # noqa: E402
from scoreboard.manifest import strip_label_frontmatter  # noqa: E402

CORPUS = os.environ.get("SKILLSCAN_CORPUS") or os.path.abspath(
    os.path.join(ROOT, "..", "skillscan-corpus", "corpus")
)

# (label, model, provider). Anthropic IDs per current family; OpenAI big-vs-small.
MODELS = [
    ("gpt-4o", "gpt-4o", "openai"),
    ("gpt-4o-mini", "gpt-4o-mini", "openai"),
    ("claude-sonnet-4.6", "claude-sonnet-4-6", "anthropic"),
    ("claude-haiku-4.5", "claude-haiku-4-5-20251001", "anthropic"),
    ("claude-opus-4.8", "claude-opus-4-8", "anthropic"),
]


def _anthropic_key():
    return os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("BACKUP_ANTHROPIC_API_KEY", "")


def call(provider, model, text, timeout=60):
    """Return 'malicious' | 'benign' | ('refused', reason) | ('error', reason)."""
    body_msgs = [{"role": "user", "content": text[:8000]}]
    try:
        if provider == "openai":
            url = "https://api.openai.com/v1/chat/completions"
            data = json.dumps(
                {
                    "model": model,
                    "temperature": 0,
                    "max_tokens": 64,
                    "messages": [{"role": "system", "content": PROMPT}] + body_msgs,
                }
            ).encode()
            hdr = {
                "Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', '')}",
                "Content-Type": "application/json",
            }
            req = urllib.request.Request(url, data=data, headers=hdr)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.load(r)
            ch = (d.get("choices") or [{}])[0]
            if ch.get("finish_reason") == "content_filter":
                return ("refused", "content_filter")
            ans = (ch.get("message") or {}).get("content") or ""
        else:  # anthropic messages API
            url = "https://api.anthropic.com/v1/messages"
            abody = {"model": model, "max_tokens": 64, "system": PROMPT, "messages": body_msgs}
            # Opus 4.x rejects temperature=0 (reasoning-tier); omit it (API default) like the
            # independent-set run did. Sonnet/Haiku keep temp 0 for determinism.
            if "opus" not in model:
                abody["temperature"] = 0
            data = json.dumps(abody).encode()
            hdr = {
                "x-api-key": _anthropic_key(),
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
            req = urllib.request.Request(url, data=data, headers=hdr)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                d = json.load(r)
            if d.get("stop_reason") == "refusal":
                return ("refused", "stop_reason:refusal")
            ans = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "replace")[:200]
        # moderation/abuse blocks vs transient
        if e.code in (400, 403) and any(
            w in msg.lower() for w in ("policy", "moderation", "refus", "flag", "abuse")
        ):
            return ("refused", f"HTTP{e.code}:{msg[:80]}")
        return ("error", f"HTTP{e.code}:{msg[:80]}")
    except Exception as e:  # noqa: BLE001
        return ("error", str(e)[:80])
    v = parse_verdict(ans)
    if v is None:
        return ("refused", f"unparseable:{ans[:60]!r}")  # a non-answer = effective refusal
    return "malicious" if v.name == "MALICIOUS" else "benign"


def _load(globpat, want, n, rng):
    rows = []
    for mp in glob.glob(os.path.join(CORPUS, globpat)):
        for ln in open(mp, encoding="utf-8"):
            d = json.loads(ln)
            if want(d):
                p = os.path.join(CORPUS, d["content_path"])
                if os.path.exists(p):
                    rows.append(strip_label_frontmatter(open(p, encoding="utf-8", errors="replace").read()))
    rng.shuffle(rows)
    return rows[: n or len(rows)]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="samples per group (0=all)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--only", default="", help="run only this model label (merge into existing results)")
    args = ap.parse_args(argv)
    rng = random.Random(13)
    half = (args.limit // 2) or 0
    groups = {
        "malicious_organic": _load("manifest.organic.jsonl", lambda d: d["label"] == "malicious", half, rng),
        "malicious_synth": _load("manifest.synthetic.jsonl", lambda d: d["label"] == "malicious", half, rng),
        "benign": _load("manifest.benign.jsonl", lambda d: d["label"] == "benign", half, rng),
        "dual_use": _load("manifest.dualuse_recovered.jsonl", lambda d: d["label"] == "benign", half, rng),
    }
    print({k: len(v) for k, v in groups.items()}, flush=True)
    results = {}
    for label, model, provider in MODELS:
        if args.only and label != args.only:
            continue
        if provider == "anthropic" and not _anthropic_key():
            print(f"skip {label}: no anthropic key", flush=True)
            continue
        if provider == "openai" and not os.environ.get("OPENAI_API_KEY"):
            print(f"skip {label}: no openai key", flush=True)
            continue
        per = {}
        for gname, texts in groups.items():
            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                outs = [
                    f.result() for f in as_completed([ex.submit(call, provider, model, t) for t in texts])
                ]
            mal = sum(1 for o in outs if o == "malicious")
            ben = sum(1 for o in outs if o == "benign")
            ref = sum(1 for o in outs if isinstance(o, tuple) and o[0] == "refused")
            err = sum(1 for o in outs if isinstance(o, tuple) and o[0] == "error")
            per[gname] = {"n": len(texts), "malicious": mal, "benign": ben, "refused": ref, "error": err}
        results[label] = per
        # live line: recall (malicious groups) + FP (benign groups) + refusal
        mtot = per["malicious_organic"]["malicious"] + per["malicious_synth"]["malicious"]
        mn = (per["malicious_organic"]["n"] + per["malicious_synth"]["n"]) - (
            per["malicious_organic"]["refused"]
            + per["malicious_organic"]["error"]
            + per["malicious_synth"]["refused"]
            + per["malicious_synth"]["error"]
        )
        refrate = (per["malicious_organic"]["refused"] + per["malicious_synth"]["refused"]) / max(
            1, per["malicious_organic"]["n"] + per["malicious_synth"]["n"]
        )
        du = per["dual_use"]
        print(
            f"  {label:20} recall(mal)={mtot}/{max(1, mn)}={mtot / max(1, mn) * 100:.0f}% "
            f"refusal(mal)={refrate * 100:.0f}% FP(dual)={du['malicious']}/{du['n']}",
            flush=True,
        )
    # Merge into the committed repo-root file so a single-model (--only) run preserves the others.
    out_path = os.path.join(ROOT, "frontier_baselines.json")
    merged = {}
    if os.path.exists(out_path):
        merged = json.load(open(out_path, encoding="utf-8"))
    merged.update(results)
    json.dump(merged, open(out_path, "w"), indent=2)
    json.dump(merged, open(os.path.join(ROOT, "_staging", "frontier_baselines.json"), "w"), indent=2)
    print(f"wrote frontier_baselines.json (merged {list(results)} into {list(merged)})", flush=True)


if __name__ == "__main__":
    main()
