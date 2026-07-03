from scoreboard.cache import ResultCache
from scoreboard.model import ScanResult, Verdict
from scoreboard.run_board import fold_repeats


def test_cache_key_namespacing():
    # k=0 keeps the legacy key; k>0 namespaces a distinct slot
    assert ResultCache.key("s", "v", "abc") == "s@v:abc"
    assert ResultCache.key("s", "v", "abc", 0) == "s@v:abc"
    assert ResultCache.key("s", "v", "abc", 2) == "s@v:abc#k2"
    assert ResultCache.key("s", "v", "abc", 1) != ResultCache.key("s", "v", "abc", 2)


def test_cache_roundtrip_per_k(tmp_path):
    c = ResultCache(str(tmp_path / "c.json"))
    r0 = ScanResult("m1", "s", "v", Verdict.MALICIOUS)
    r1 = ScanResult("m1", "s", "v", Verdict.BENIGN)
    c.put("sha", r0, 0)
    c.put("sha", r1, 1)
    assert c.get("s", "v", "sha", 0).verdict == Verdict.MALICIOUS
    assert c.get("s", "v", "sha", 1).verdict == Verdict.BENIGN  # distinct slot, not collapsed


def test_fold_majority_vote_no_pseudo_replication():
    # 5 stochastic repeats of one sample → ONE folded row (n must not become 5)
    raw = [
        {
            "sample_id": "m1",
            "scanner": "x",
            "mode": "static",
            "k": k,
            "verdict": "malicious" if k < 3 else "benign",
        }
        for k in range(5)
    ]
    results, stability = fold_repeats(raw)
    assert len(results) == 1
    assert results[0]["verdict"] == "malicious"  # 3/5 majority
    assert stability["x"] == 0.6  # 3 of 5 agree with the chosen verdict


def test_fold_tie_breaks_malicious_and_drops_errors():
    raw = [
        {"sample_id": "m", "scanner": "x", "mode": "static", "k": 0, "verdict": "malicious"},
        {"sample_id": "m", "scanner": "x", "mode": "static", "k": 1, "verdict": "benign"},
        {"sample_id": "m", "scanner": "x", "mode": "static", "k": 2, "verdict": "error"},  # dropped
    ]
    results, _ = fold_repeats(raw)
    assert results[0]["verdict"] == "malicious"  # 1-1 tie → conservative malicious

    all_err = [{"sample_id": "e", "scanner": "x", "mode": "static", "k": 0, "verdict": "error"}]
    res2, _ = fold_repeats(all_err)
    assert res2[0]["verdict"] == "error"  # nothing to vote on → stays error
