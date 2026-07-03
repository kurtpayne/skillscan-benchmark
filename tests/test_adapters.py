import subprocess

import pytest

from scoreboard.adapters import (
    CiscoSkillScannerAdapter,
    LLMBaselineAdapter,
    SkillSpectorAdapter,
    SnykAgentScanAdapter,
)
from scoreboard.adapters.llm_baseline import assert_open_weight, parse_verdict
from scoreboard.model import Verdict


def test_parse_verdict_robust_to_preamble():
    assert parse_verdict("MALICIOUS") == Verdict.MALICIOUS
    assert parse_verdict("BENIGN\n\nThe skill...") == Verdict.BENIGN
    # verbose preamble before the verdict (the phi-4 failure mode at max_tokens=8)
    assert parse_verdict("Based on the provided information, the skill is BENIGN") == Verdict.BENIGN
    # first keyword wins
    assert parse_verdict("MALICIOUS — though some BENIGN traits") == Verdict.MALICIOUS
    assert parse_verdict("I think this is BENIGN, not MALICIOUS") == Verdict.BENIGN
    assert parse_verdict("I cannot determine") is None
    assert parse_verdict("") is None


def _proc(stdout="", stderr="", rc=0):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr=stderr)


def test_cisco_parse_malicious_and_benign():
    a = CiscoSkillScannerAdapter(binary="x", version="t")
    mal = a._parse(
        "s", _proc(stdout='{"is_safe": false, "max_severity": "CRITICAL", "findings": [{"category": "rce"}]}')
    )
    assert mal.verdict == Verdict.MALICIOUS and "rce" in mal.categories
    ben = a._parse("s", _proc(stdout='{"is_safe": true, "max_severity": "LOW", "findings": []}'))
    assert ben.verdict == Verdict.BENIGN


def test_cisco_parse_garbage_is_error():
    a = CiscoSkillScannerAdapter(binary="x")
    r = a._parse("s", _proc(stdout="not json", stderr="boom"))
    assert r.verdict == Verdict.ERROR and "boom" in r.error


def test_skillspector_proprietary_unaffected_but_baseline_guard():
    # Principle 2: LLM baseline must refuse proprietary models on the malicious corpus
    with pytest.raises(ValueError):
        assert_open_weight("openai/gpt-4o-mini")
    with pytest.raises(ValueError):
        assert_open_weight("anthropic/claude-sonnet-4")
    # open-weight passes
    assert_open_weight("meta-llama/llama-3.3-70b-instruct")
    assert_open_weight("qwen/qwen-2.5-72b-instruct")


def test_llm_baseline_disabled_returns_error_not_call():
    a = LLMBaselineAdapter(model="meta-llama/llama-3.3-70b-instruct", enabled=False)
    r = a.scan("s", "/tmp/whatever")
    assert r.verdict == Verdict.ERROR and "not enabled" in r.error


def test_skillspector_constructs():
    a = SkillSpectorAdapter(binary="x")
    assert a.name == "skillspector"


def test_snyk_parse_high_is_malicious():
    a = SnykAgentScanAdapter(binary="x")
    out = (
        '{"/p": {"issues": [{"code": "W007", "extra_data": '
        '{"severity": "high", "title": "Insecure credential handling"}}], "error": "None"}}'
    )
    r = a._parse("s", _proc(stdout=out))
    assert r.verdict == Verdict.MALICIOUS and r.severity == "HIGH"
    assert any("w007" in c or "insecure" in c for c in r.categories)


def test_snyk_parse_no_issues_is_benign():
    a = SnykAgentScanAdapter(binary="x")
    r = a._parse("s", _proc(stdout='{"/p": {"issues": [], "error": "None"}}'))
    assert r.verdict == Verdict.BENIGN


def test_snyk_parse_error_when_no_issues_and_error():
    a = SnykAgentScanAdapter(binary="x")
    r = a._parse("s", _proc(stdout='{"/p": {"issues": [], "error": "auth failed"}}'))
    assert r.verdict == Verdict.ERROR and "auth failed" in r.error
