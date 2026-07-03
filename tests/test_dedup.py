import os

from scoreboard.dedup import dedup_against, hash_corpus


def _write(d, name, content):
    p = os.path.join(d, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(content)
    return p


def test_intra_candidate_dedup(tmp_path):
    d = str(tmp_path)
    a = _write(d, "a.md", "same content")
    b = _write(d, "b.md", "same content")  # exact dup of a
    c = _write(d, "c.md", "different")
    rep = dedup_against([a, b, c])
    assert len(rep.unique) == 2  # one of {a,b} + c
    assert rep.n_dropped == 1


def test_collision_with_existing(tmp_path):
    d = str(tmp_path)
    existing = _write(d, "existing.md", "in corpus already")
    cand = _write(d, "cand.md", "in corpus already")  # same content
    fresh = _write(d, "fresh.md", "new")
    rep = dedup_against([cand, fresh], existing_paths=[existing])
    assert rep.unique == [fresh]
    assert cand in rep.collisions_with_existing


def test_hash_corpus_groups_by_content(tmp_path):
    d = str(tmp_path)
    a = _write(d, "a.md", "x")
    b = _write(d, "b.md", "x")
    h = hash_corpus([a, b])
    assert len(h) == 1 and len(next(iter(h.values()))) == 2
