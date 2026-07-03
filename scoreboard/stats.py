"""Statistics for the scoreboard (METHODOLOGY §5). Stdlib only.

- Wilson score interval for proportions (recall/FP) — valid at small n, unlike Wald.
- McNemar exact test for PAIRED binary comparisons (scanner A vs B, static vs +llm, on same items).
- Newcombe difference CI for two independent proportions (the generalization gap).
- Benjamini-Hochberg FDR for many comparisons.
"""

from __future__ import annotations

import math
from math import comb


def wilson(k: int, n: int, z: float = 1.96) -> dict | None:
    """95% Wilson score interval. Returns {point, lo, hi, k, n} or None if n==0."""
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    center = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return {
        "point": round(p, 4),
        "lo": round(max(0.0, center - half), 4),
        "hi": round(min(1.0, center + half), 4),
        "k": k,
        "n": n,
    }


def mcnemar_exact(b: int, c: int) -> dict:
    """Paired binary test. b = #(A right, B wrong), c = #(A wrong, B right).
    Two-sided exact binomial p-value on the discordant pairs."""
    n = b + c
    if n == 0:
        return {"p_value": 1.0, "b": b, "c": c, "discordant": 0}
    k = min(b, c)
    tail = sum(comb(n, i) for i in range(k + 1)) / (2**n)
    return {"p_value": round(min(1.0, 2 * tail), 5), "b": b, "c": c, "discordant": n}


def newcombe_diff(k1: int, n1: int, k2: int, n2: int, z: float = 1.96) -> dict | None:
    """95% CI for the difference of two independent proportions p1 - p2 (Newcombe method 10).
    Used for the generalization gap: recall(known) - recall(synthetic)."""
    if n1 == 0 or n2 == 0:
        return None
    w1, w2 = wilson(k1, n1, z), wilson(k2, n2, z)
    p1, p2 = k1 / n1, k2 / n2
    diff = p1 - p2
    lo = diff - math.sqrt((p1 - w1["lo"]) ** 2 + (w2["hi"] - p2) ** 2)
    hi = diff + math.sqrt((w1["hi"] - p1) ** 2 + (p2 - w2["lo"]) ** 2)
    return {"diff": round(diff, 4), "lo": round(lo, 4), "hi": round(hi, 4), "significant": lo > 0 or hi < 0}


def _normal_sf(x: float) -> float:
    """Survival function of the standard normal (1 - CDF), via erf."""
    return 0.5 * math.erfc(x / math.sqrt(2))


def two_proportion_p(k1: int, n1: int, k2: int, n2: int) -> float | None:
    """Two-sided p-value for H0: p1 == p2 (pooled two-proportion z-test). Returns None if a
    denominator is 0. Used to get a p-value per generalization-gap cell so the family of gap
    comparisons can be FDR-corrected (the Newcombe CI gives the interval; this gives the p)."""
    if n1 == 0 or n2 == 0:
        return None
    p = (k1 + k2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return 1.0
    z = (k1 / n1 - k2 / n2) / se
    return round(min(1.0, 2 * _normal_sf(abs(z))), 6)


def benjamini_hochberg(pvals: list[float], q: float = 0.05) -> list[bool]:
    """Return per-test significance under BH FDR control at level q."""
    m = len(pvals)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvals[i])
    sig = [False] * m
    kmax = -1
    for rank, i in enumerate(order, start=1):
        if pvals[i] <= q * rank / m:
            kmax = rank
    for rank, i in enumerate(order, start=1):
        if rank <= kmax:
            sig[i] = True
    return sig
