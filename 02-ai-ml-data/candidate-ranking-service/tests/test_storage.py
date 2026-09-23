"""Tests for the bounded in-memory candidate store."""

from __future__ import annotations

import pytest

from src.models.domain import Candidate
from src.storage.memory import CandidateStoreFull, InMemoryCandidateStore


def make_candidate(candidate_id: str) -> Candidate:
    return Candidate(candidate_id=candidate_id, resume_text="Python and SQL", skills=["Python"])


def test_add_and_get_roundtrip():
    store = InMemoryCandidateStore()
    store.add(make_candidate("c1"))

    stored = store.get("c1")
    assert stored is not None
    assert stored.candidate_id == "c1"


def test_get_returns_none_for_an_unknown_id():
    assert InMemoryCandidateStore().get("nope") is None


def test_add_reports_whether_it_created_or_replaced():
    store = InMemoryCandidateStore()

    assert store.add(make_candidate("c1")) is True
    assert store.add(make_candidate("c1")) is False
    assert len(store) == 1


def test_store_rejects_new_candidates_at_capacity():
    """Rejecting is the point: silent eviction would drop someone from a ranking."""
    store = InMemoryCandidateStore(max_size=2)
    store.add(make_candidate("c1"))
    store.add(make_candidate("c2"))

    with pytest.raises(CandidateStoreFull, match="maximum of 2"):
        store.add(make_candidate("c3"))

    assert store.list_ids() == ["c1", "c2"]


def test_replacing_an_existing_candidate_works_at_capacity():
    store = InMemoryCandidateStore(max_size=1)
    store.add(make_candidate("c1"))

    replacement = Candidate(candidate_id="c1", resume_text="Rust", skills=["Rust"])
    assert store.add(replacement) is False
    assert store.get("c1").skills == ["Rust"]


def test_capacity_must_be_positive():
    with pytest.raises(ValueError, match="at least 1"):
        InMemoryCandidateStore(max_size=0)


def test_delete_reports_whether_anything_was_removed():
    store = InMemoryCandidateStore()
    store.add(make_candidate("c1"))

    assert store.delete("c1") is True
    assert store.delete("c1") is False
    assert len(store) == 0


def test_ids_are_listed_in_sorted_order():
    store = InMemoryCandidateStore()
    for candidate_id in ("c3", "c1", "c2"):
        store.add(make_candidate(candidate_id))

    assert store.list_ids() == ["c1", "c2", "c3"]


def test_all_returns_candidates_ordered_by_id():
    store = InMemoryCandidateStore()
    for candidate_id in ("z", "a", "m"):
        store.add(make_candidate(candidate_id))

    assert [candidate.candidate_id for candidate in store.all()] == ["a", "m", "z"]


def test_clear_empties_the_store():
    store = InMemoryCandidateStore()
    store.add(make_candidate("c1"))
    store.clear()

    assert len(store) == 0
    assert store.list_ids() == []


def test_remaining_capacity_tracks_occupancy():
    store = InMemoryCandidateStore(max_size=3)
    assert store.remaining_capacity == 3

    store.add(make_candidate("c1"))
    assert store.remaining_capacity == 2


def test_deleting_frees_capacity():
    store = InMemoryCandidateStore(max_size=1)
    store.add(make_candidate("c1"))
    store.delete("c1")

    store.add(make_candidate("c2"))
    assert store.list_ids() == ["c2"]
