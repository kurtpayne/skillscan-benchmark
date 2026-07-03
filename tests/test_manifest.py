from scoreboard.manifest import (
    ensure_skill_frontmatter,
    strip_label_frontmatter,
    validate_manifest,
)
from scoreboard.model import Sample


def _has(fm_text, key):
    block = fm_text.split("---", 2)[1]
    return any(ln.strip().lower().startswith(key + ":") for ln in block.splitlines())


def test_ensure_frontmatter_added_when_missing():
    # no frontmatter at all (defanged synthetic) → both name+description injected
    out = ensure_skill_frontmatter("# Cool Skill\n\nThis does telemetry things.\n", "syn_1")
    assert out.startswith("---\n")
    assert _has(out, "name") and _has(out, "description")
    assert "Cool Skill" in out  # name derived from the H1
    assert "telemetry things" in out  # description derived from first prose line
    assert out.endswith("# Cool Skill\n\nThis does telemetry things.\n")  # body preserved


def test_ensure_frontmatter_preserved_when_present():
    src = "---\nname: real\ndescription: a real one\nlabel: malicious\n---\nbody\n"
    assert ensure_skill_frontmatter(src, "fallback") == src  # untouched + idempotent


def test_ensure_frontmatter_fills_only_missing_key():
    src = "---\nname: only-name\n---\nbody text here\n"
    out = ensure_skill_frontmatter(src, "fb")
    assert _has(out, "name") and _has(out, "description")
    assert "only-name" in out  # existing name kept
    assert ensure_skill_frontmatter(out, "fb") == out  # idempotent


def _s(**kw):
    base = dict(
        id="x",
        cls="rce",
        tier="overt",
        label="malicious",
        source="t",
        source_ref="",
        license="MIT",
        confidence="wild-confirmed",
        content_path="/x",
    )
    base.update(kw)
    return Sample(**base)


def test_validate_catches_bad_rows():
    bad = [
        _s(id="a", label="malicious", cls=""),  # malicious needs a class
        _s(id="b", label="benign", tier="overt"),  # benign must be a control tier
        _s(id="c", tier="nope"),  # bad tier
        _s(id="d", confidence="made-up"),  # bad confidence
        _s(id="e", label="malicious", tier="benign"),  # malicious can't be in control tier
    ]
    errs = validate_manifest(bad)
    assert len(errs) >= 5


def test_validate_duplicate_ids():
    errs = validate_manifest([_s(id="dup"), _s(id="dup")])
    assert any("duplicate" in e for e in errs)


def test_valid_rows_pass():
    good = [
        _s(id="m", label="malicious", cls="cred-exfil", tier="obfuscated"),
        _s(id="b", label="benign", cls="", tier="dual-use-fp-bait"),
    ]
    assert validate_manifest(good) == []


def test_strip_label_frontmatter_removes_labels_keeps_name():
    text = (
        "---\n"
        "name: my-skill\n"
        "description: does things\n"
        "label: malicious\n"
        "attack_labels: [rce]\n"
        "confidence: 0.9\n"
        "---\n"
        "# Body\nstuff\n"
    )
    out = strip_label_frontmatter(text)
    assert "label:" not in out and "attack_labels" not in out and "confidence:" not in out
    assert "name: my-skill" in out and "description: does things" in out
    # frontmatter must still be well-formed: opens and closes with --- on their own lines
    assert out.startswith("---\n")
    assert "\n---" in out
    assert "# Body" in out


def test_strip_no_frontmatter_is_noop():
    text = "# Just a heading\nno frontmatter"
    assert strip_label_frontmatter(text) == text
