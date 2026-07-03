# Vendor responses & corrections

The site's **Responses & corrections** page (`responses.html`) is composed automatically from this
directory — **one markdown file per vendor per reply**. To publish a response, drop a file and rebuild
(`python3 scripts/build_site.py`); no code changes.

## Layout (one dir per vendor, one file per reply)

```
responses/
  README.md            ← this file (ignored by the builder)
  _TEMPLATE.md         ← copy this; underscore-prefixed files are ignored
  cisco/2026-07-01.md
  nvidia/2026-07-03.md
  skillscan/2026-07-05.md   ← our own corrections go under a self-named dir too
```

The builder globs `responses/*/*.md`, skips any file whose name starts with `_`, and renders newest-first
(by the `date` field). Vendor text is published **verbatim** — nothing is edited inside the body.

## File format

A YAML-ish frontmatter block, then the verbatim reply as markdown:

```markdown
---
vendor: Cisco AI Defense skill-scanner
date: 2026-07-01
kind: response          # "response" (a vendor reply) or "correction" (a fix we made)
---
<the vendor's reply, pasted verbatim — or, for a correction, what we changed and why>
```

- `kind: response` renders with a green "Vendor response" tag.
- `kind: correction` renders with an amber "Correction" tag — use this to log a factual/method fix
  (what changed, when, why) so the corrections posture is auditable.

If the directory has no reply files, the page shows a clear empty state — that's expected at launch.
