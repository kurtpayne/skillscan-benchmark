from scoreboard import analyze
from scoreboard.stats import (
    benjamini_hochberg,
    mcnemar_exact,
    newcombe_diff,
    two_proportion_p,
    wilson,
)


def test_two_proportion_p():
    # big, clearly-different proportions → tiny p
    assert two_proportion_p(45, 50, 10, 50) < 0.001
    # identical proportions → p ≈ 1
    assert two_proportion_p(25, 50, 25, 50) == 1.0
    assert two_proportion_p(5, 0, 5, 10) is None  # empty denom


def test_fdr_annotates_gengap_and_summary():
    # one strong gap (memorizer) → should survive FDR; build a minimal manifest/results
    manifest = [
        {
            "id": f"k{i}",
            "label": "malicious",
            "provenance": "organic_authored",
            "archetype": "code_execution",
            "tier": "overt",
        }
        for i in range(30)
    ] + [
        {
            "id": f"s{i}",
            "label": "malicious",
            "provenance": "synthetic_novel",
            "archetype": "code_execution",
            "tier": "overt",
            "generator_model": "qwen",
        }
        for i in range(30)
    ]
    results = []
    for i in range(30):
        results.append(
            {
                "sample_id": f"k{i}",
                "scanner": "X",
                "mode": "static",
                "verdict": "malicious" if i < 28 else "benign",
            }
        )
        results.append(
            {
                "sample_id": f"s{i}",
                "scanner": "X",
                "mode": "static",
                "verdict": "malicious" if i < 5 else "benign",
            }
        )
    board = analyze.compute(manifest, results)
    cell = board["generalization_gap"]["X"]["static"]["code_execution"]
    assert cell["p_value"] is not None and cell["p_value"] < 0.05
    assert cell["significant_fdr"] is True
    assert board["fdr"]["n_comparisons"] >= 1 and board["fdr"]["q"] == 0.05


def test_wilson_basic():
    w = wilson(5, 10)
    assert w["point"] == 0.5 and 0 < w["lo"] < 0.5 < w["hi"] < 1
    assert wilson(0, 0) is None
    # tight CI at large n, wide at small n
    assert (wilson(50, 100)["hi"] - wilson(50, 100)["lo"]) < (wilson(5, 10)["hi"] - wilson(5, 10)["lo"])


def test_mcnemar():
    assert mcnemar_exact(0, 0)["p_value"] == 1.0
    # lopsided discordance → significant
    assert mcnemar_exact(10, 0)["p_value"] < 0.05
    assert mcnemar_exact(5, 5)["p_value"] == 1.0


def test_newcombe_gap_significance():
    # 90% vs 30% recall, decent n → gap CI excludes 0
    g = newcombe_diff(45, 50, 15, 50)
    assert g["diff"] > 0 and g["significant"]
    # equal → not significant
    assert not newcombe_diff(25, 50, 25, 50)["significant"]


def test_bh():
    sig = benjamini_hochberg([0.001, 0.04, 0.5, 0.9], q=0.05)
    assert sig[0] is True and sig[3] is False


def test_analyze_gen_gap():
    manifest = (
        [
            {
                "id": f"k{i}",
                "label": "malicious",
                "provenance": "organic_authored",
                "archetype": "code_execution",
                "tier": "overt",
            }
            for i in range(20)
        ]
        + [
            {
                "id": f"s{i}",
                "label": "malicious",
                "provenance": "synthetic_novel",
                "archetype": "code_execution",
                "tier": "overt",
                "generator_model": "qwen",
            }
            for i in range(20)
        ]
        + [
            {
                "id": f"b{i}",
                "label": "benign",
                "provenance": "wild_verbatim",
                "archetype": "n/a",
                "tier": "benign",
            }
            for i in range(20)
        ]
    )
    results = []
    # scanner memorizes known (18/20) but misses novel (4/20) → big gen-gap
    for i in range(20):
        results.append(
            {
                "sample_id": f"k{i}",
                "scanner": "X",
                "mode": "static",
                "verdict": "malicious" if i < 18 else "benign",
            }
        )
        results.append(
            {
                "sample_id": f"s{i}",
                "scanner": "X",
                "mode": "static",
                "verdict": "malicious" if i < 4 else "benign",
            }
        )
        results.append(
            {
                "sample_id": f"b{i}",
                "scanner": "X",
                "mode": "static",
                "verdict": "malicious" if i < 2 else "benign",
            }
        )  # 2 FP
    board = analyze.compute(manifest, results)
    gg = board["generalization_gap"]["X"]["static"]["code_execution"]
    assert gg["recall_known"]["point"] == 0.9 and gg["recall_synthetic"]["point"] == 0.2
    assert gg["gap_ci"]["significant"]  # memorization detected
    fp = board["false_positive"]["X"]["static"]["benign"]["wilson"]
    assert fp["point"] == 0.1


def test_model_family_mapping():
    assert analyze.model_family("Qwen/Qwen2.5-72B-Instruct-AWQ") == "qwen"
    assert analyze.model_family("hermes-3-70b") == "llama"  # Llama fine-tune
    assert analyze.model_family("meta-llama/llama-3.3-70b-instruct") == "llama"
    assert analyze.model_family("mixtral-8x22b") == "mistral"
    assert analyze.model_family("microsoft/phi-4") == "phi"
    assert analyze.model_family(None) is None
    assert analyze.model_family("some-unknown-model") is None


def test_cross_family_excludes_own_generator():
    """T2: a Qwen scanner must NOT be credited for catching Qwen-generated synthetic.
    Build synthetic from two generators (qwen + llama); the Qwen scanner catches all qwen
    samples but no llama samples. Pooled recall is inflated by the qwen self-detection;
    cross-family recall (llama-only) is the honest 0.0."""
    arch = "code_execution"
    manifest = [
        {
            "id": f"k{i}",
            "label": "malicious",
            "provenance": "organic_authored",
            "archetype": arch,
            "tier": "overt",
        }
        for i in range(20)
    ]
    for i in range(10):
        manifest.append(
            {
                "id": f"sq{i}",
                "label": "malicious",
                "provenance": "synthetic_novel",
                "archetype": arch,
                "tier": "overt",
                "generator_model": "qwen2.5-72b",
            }
        )
        manifest.append(
            {
                "id": f"sl{i}",
                "label": "malicious",
                "provenance": "synthetic_novel",
                "archetype": arch,
                "tier": "overt",
                "generator_model": "llama-3.3-70b",
            }
        )
    results = []
    for i in range(20):
        results.append(
            {
                "sample_id": f"k{i}",
                "scanner": "llm-baseline",
                "mode": "static",
                "verdict": "malicious" if i < 18 else "benign",
            }
        )
    for i in range(10):
        # catches every qwen-generated, none of the llama-generated
        results.append(
            {"sample_id": f"sq{i}", "scanner": "llm-baseline", "mode": "static", "verdict": "malicious"}
        )
        results.append(
            {"sample_id": f"sl{i}", "scanner": "llm-baseline", "mode": "static", "verdict": "benign"}
        )

    board = analyze.compute(
        manifest, results, scanner_models={"llm-baseline": "Qwen/Qwen2.5-72B-Instruct-AWQ"}
    )
    gg = board["generalization_gap"]["llm-baseline"]["static"][arch]
    assert gg["scanner_family"] == "qwen"
    assert gg["recall_synthetic_pooled"]["point"] == 0.5  # pooled (10 qwen caught / 20)
    # headline recall_synthetic is now cross-family (llama-only): honest, no self-detection
    assert gg["recall_synthetic"]["point"] == 0.0
    assert gg["recall_synthetic_crossfamily"]["point"] == 0.0
    assert gg["samefamily_excluded"] == "qwen"
    # a disjoint scanner (phi) excludes nothing → cross-family == pooled
    board2 = analyze.compute(manifest, results, scanner_models={"llm-baseline": "microsoft/phi-4"})
    gg2 = board2["generalization_gap"]["llm-baseline"]["static"][arch]
    assert gg2["samefamily_excluded"] is None
    assert gg2["recall_synthetic_crossfamily"]["point"] == gg2["recall_synthetic"]["point"] == 0.5


def test_wild_only_recall():
    arch = "data_exfiltration"
    manifest = [
        {
            "id": f"w{i}",
            "label": "malicious",
            "provenance": "wild_verbatim",
            "archetype": arch,
            "tier": "overt",
        }
        for i in range(8)
    ] + [
        {
            "id": f"s{i}",
            "label": "malicious",
            "provenance": "synthetic_novel",
            "archetype": arch,
            "tier": "overt",
            "generator_model": "qwen2.5-72b",
        }
        for i in range(8)
    ]
    results = []
    for i in range(8):
        results.append(
            {
                "sample_id": f"w{i}",
                "scanner": "Z",
                "mode": "static",
                "verdict": "malicious" if i < 6 else "benign",
            }
        )  # 6/8 wild
        results.append({"sample_id": f"s{i}", "scanner": "Z", "mode": "static", "verdict": "benign"})
    board = analyze.compute(manifest, results)
    assert board["wild_recall"]["Z"]["static"]["wilson"]["point"] == 0.75  # 6/8, synthetic excluded
