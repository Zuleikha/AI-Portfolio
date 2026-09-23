"""Tests for vector storage and similarity search.

Covers ranking, pre-filtering, persistence, and the guards that exist because
their failure mode is *silent*: an index built by a different model, or one
holding duplicate chunks, produces confident nonsense rather than an error.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from app.knowledge.models import DocumentMetadata
from app.rag.models import Chunk, EmbeddedChunk
from app.rag.vectorstore import (
    CHUNKS_FILENAME,
    MANIFEST_FILENAME,
    IncompatibleIndexError,
    IndexNotFoundError,
    InMemoryVectorStore,
    UnknownFilterFieldError,
    VectorStore,
    VectorStoreError,
)

DIMENSION = 4


def unit(*values: float) -> tuple[float, ...]:
    """Return the L2-normalised form of ``values``."""
    vector = np.array(values, dtype=np.float32)
    return tuple(float(v) for v in vector / np.linalg.norm(vector))


def make_chunk(
    chunk_id: str,
    domain: str = "atm",
    component: str = "TransactionSwitch",
    doc_type: str = "reference",
) -> Chunk:
    """Build a Chunk with controllable metadata."""
    document_id = chunk_id.split("#")[0]
    return Chunk(
        chunk_id=chunk_id,
        document_id=document_id,
        ordinal=int(chunk_id.split("#")[1]),
        heading="Section",
        content=f"Content of {chunk_id}.",
        metadata=DocumentMetadata(
            document_id=document_id,
            title=f"Title {document_id}",
            domain=domain,
            component=component,
            version="4.2",
            doc_type=doc_type,
        ),
        source_path=f"{domain}/{document_id}.md",
        token_count=10,
    )


def embedded(chunk: Chunk, vector: tuple[float, ...]) -> EmbeddedChunk:
    """Pair a chunk with a vector."""
    return EmbeddedChunk(chunk=chunk, embedding=vector)


@pytest.fixture
def store() -> InMemoryVectorStore:
    """An empty store."""
    return InMemoryVectorStore(model_id="test-model", dimension=DIMENSION)


@pytest.fixture
def populated(store: InMemoryVectorStore) -> InMemoryVectorStore:
    """A store holding four chunks on distinct axes, across three domains."""
    store.add(
        [
            embedded(make_chunk("doc-a#0", domain="atm"), unit(1, 0, 0, 0)),
            embedded(make_chunk("doc-b#0", domain="cards"), unit(0, 1, 0, 0)),
            embedded(make_chunk("doc-c#0", domain="payments"), unit(0, 0, 1, 0)),
            embedded(make_chunk("doc-c#1", domain="payments"), unit(0, 0, 0.9, 0.1)),
        ]
    )
    return store


# --------------------------------------------------------------------------
# Protocol and basics
# --------------------------------------------------------------------------


def test_in_memory_store_satisfies_the_protocol(store):
    assert isinstance(store, VectorStore)


def test_a_new_store_is_empty(store):
    assert len(store) == 0
    assert store.count() == 0


def test_adding_chunks_grows_the_index(populated):
    assert len(populated) == 4
    assert populated.count() == 4


def test_adding_an_empty_batch_is_a_no_op(store):
    store.add([])
    assert len(store) == 0


def test_clear_empties_the_index(populated):
    populated.clear()
    assert len(populated) == 0
    assert populated.search(np.array(unit(1, 0, 0, 0), dtype=np.float32)) == ()


def test_dimension_must_be_positive():
    with pytest.raises(ValueError, match="positive"):
        InMemoryVectorStore(model_id="m", dimension=0)


# --------------------------------------------------------------------------
# Search and ranking
# --------------------------------------------------------------------------


def test_search_returns_the_nearest_chunk_first(populated):
    results = populated.search(np.array(unit(1, 0, 0, 0), dtype=np.float32), k=4)
    assert results[0].chunk.chunk_id == "doc-a#0"


def test_results_are_ordered_by_descending_score(populated):
    results = populated.search(np.array(unit(0, 0, 1, 0), dtype=np.float32), k=4)
    scores = [result.score for result in results]
    assert scores == sorted(scores, reverse=True)


def test_an_identical_vector_scores_one(populated):
    results = populated.search(np.array(unit(1, 0, 0, 0), dtype=np.float32), k=1)
    assert results[0].score == pytest.approx(1.0, abs=1e-5)


def test_an_orthogonal_vector_scores_zero(populated):
    results = populated.search(np.array(unit(0, 1, 0, 0), dtype=np.float32), k=4)
    by_id = {result.chunk.chunk_id: result.score for result in results}
    assert by_id["doc-a#0"] == pytest.approx(0.0, abs=1e-5)


def test_k_limits_the_number_of_results(populated):
    assert len(populated.search(np.array(unit(1, 0, 0, 0), dtype=np.float32), k=2)) == 2


def test_k_larger_than_the_index_returns_everything(populated):
    assert (
        len(populated.search(np.array(unit(1, 0, 0, 0), dtype=np.float32), k=99)) == 4
    )


def test_scores_stay_within_the_valid_cosine_range(populated):
    for result in populated.search(np.array(unit(1, 1, 1, 1), dtype=np.float32), k=4):
        assert -1.0 <= result.score <= 1.0


def test_searching_an_empty_store_returns_nothing(store):
    assert store.search(np.array(unit(1, 0, 0, 0), dtype=np.float32)) == ()


def test_k_must_be_positive(populated):
    with pytest.raises(ValueError, match="k must be positive"):
        populated.search(np.array(unit(1, 0, 0, 0), dtype=np.float32), k=0)


def test_a_wrongly_shaped_query_vector_is_rejected(populated):
    with pytest.raises(ValueError, match="expects"):
        populated.search(np.array([1.0, 0.0], dtype=np.float32))


# --------------------------------------------------------------------------
# Filtering — applied before scoring, not after
# --------------------------------------------------------------------------


def test_a_filter_restricts_results_to_the_matching_domain(populated):
    results = populated.search(
        np.array(unit(1, 0, 0, 0), dtype=np.float32),
        k=4,
        filters={"domain": "payments"},
    )
    assert {result.chunk.metadata.domain for result in results} == {"payments"}


def test_filtering_happens_before_scoring_not_after(populated):
    # doc-a is the nearest chunk by a wide margin. A post-filter on top-1 would
    # return nothing for the payments domain; a pre-filter returns the best
    # payments chunk, which is the behaviour retrieval actually needs.
    results = populated.search(
        np.array(unit(1, 0, 0, 0), dtype=np.float32),
        k=1,
        filters={"domain": "payments"},
    )
    assert len(results) == 1
    assert results[0].chunk.metadata.domain == "payments"


def test_a_filter_accepts_several_allowed_values(populated):
    results = populated.search(
        np.array(unit(1, 1, 0, 0), dtype=np.float32),
        k=4,
        filters={"domain": ["atm", "cards"]},
    )
    assert {result.chunk.metadata.domain for result in results} == {"atm", "cards"}


def test_filters_combine_conjunctively(populated):
    results = populated.search(
        np.array(unit(1, 0, 0, 0), dtype=np.float32),
        k=4,
        filters={"domain": "atm", "component": "TransactionSwitch"},
    )
    assert len(results) == 1


def test_a_filter_matching_nothing_returns_nothing(populated):
    assert (
        populated.search(
            np.array(unit(1, 0, 0, 0), dtype=np.float32),
            filters={"domain": "cards", "component": "Nope"},
        )
        == ()
    )


def test_filtering_on_document_id_is_supported(populated):
    results = populated.search(
        np.array(unit(0, 0, 1, 0), dtype=np.float32),
        k=4,
        filters={"document_id": "doc-c"},
    )
    assert len(results) == 2


def test_count_respects_filters(populated):
    assert populated.count({"domain": "payments"}) == 2
    assert populated.count() == 4


def test_an_unknown_filter_field_fails_loudly(populated):
    # A typo would otherwise match nothing and look like "no documented answer".
    with pytest.raises(UnknownFilterFieldError, match="Unknown filter field"):
        populated.search(
            np.array(unit(1, 0, 0, 0), dtype=np.float32), filters={"damain": "atm"}
        )


# --------------------------------------------------------------------------
# Integrity guards
# --------------------------------------------------------------------------


def test_a_wrongly_sized_vector_is_rejected_on_add(store):
    with pytest.raises(VectorStoreError, match="expects 4"):
        store.add([embedded(make_chunk("doc-a#0"), (1.0, 0.0))])


def test_a_duplicate_chunk_id_is_rejected(store):
    store.add([embedded(make_chunk("doc-a#0"), unit(1, 0, 0, 0))])
    with pytest.raises(VectorStoreError, match="already indexed"):
        store.add([embedded(make_chunk("doc-a#0"), unit(0, 1, 0, 0))])


def test_duplicates_within_one_batch_are_rejected(store):
    with pytest.raises(VectorStoreError, match="already indexed"):
        store.add(
            [
                embedded(make_chunk("doc-a#0"), unit(1, 0, 0, 0)),
                embedded(make_chunk("doc-a#0"), unit(0, 1, 0, 0)),
            ]
        )


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------


def test_a_saved_index_reloads_identically(populated, tmp_path):
    populated.save(tmp_path / "index", corpus_fingerprint="abc123")
    loaded, fingerprint = InMemoryVectorStore.load(
        tmp_path / "index", model_id="test-model", dimension=DIMENSION
    )
    assert len(loaded) == len(populated)
    assert fingerprint == "abc123"


def test_search_results_survive_a_save_and_load(populated, tmp_path):
    query = np.array(unit(0, 0, 1, 0), dtype=np.float32)
    before = populated.search(query, k=4)

    populated.save(tmp_path / "index", corpus_fingerprint="abc123")
    loaded, _ = InMemoryVectorStore.load(
        tmp_path / "index", model_id="test-model", dimension=DIMENSION
    )
    after = loaded.search(query, k=4)

    assert [r.chunk.chunk_id for r in before] == [r.chunk.chunk_id for r in after]
    assert [r.score for r in before] == pytest.approx(
        [r.score for r in after], abs=1e-6
    )


def test_chunk_metadata_survives_a_round_trip(populated, tmp_path):
    populated.save(tmp_path / "index", corpus_fingerprint="abc123")
    loaded, _ = InMemoryVectorStore.load(
        tmp_path / "index", model_id="test-model", dimension=DIMENSION
    )
    chunk = loaded.search(np.array(unit(1, 0, 0, 0), dtype=np.float32), k=1)[0].chunk
    assert chunk.metadata.component == "TransactionSwitch"
    assert chunk.metadata.version == "4.2"
    assert chunk.source_path == "atm/doc-a.md"


def test_the_manifest_records_what_built_the_index(populated, tmp_path):
    populated.save(tmp_path / "index", corpus_fingerprint="abc123")
    manifest = json.loads((tmp_path / "index" / MANIFEST_FILENAME).read_text())
    assert manifest["model_id"] == "test-model"
    assert manifest["dimension"] == DIMENSION
    assert manifest["chunk_count"] == 4
    assert manifest["corpus_fingerprint"] == "abc123"
    assert manifest["built_at"]


def test_loading_a_missing_index_fails_loudly(tmp_path):
    with pytest.raises(IndexNotFoundError, match="No vector index"):
        InMemoryVectorStore.load(
            tmp_path / "nope", model_id="test-model", dimension=DIMENSION
        )


def test_an_index_built_by_another_model_is_refused(populated, tmp_path):
    # The critical guard: vectors from two models are not comparable, and
    # searching across them returns plausible-looking nonsense rather than
    # failing, so it has to be caught here.
    populated.save(tmp_path / "index", corpus_fingerprint="abc123")
    with pytest.raises(IncompatibleIndexError, match="not comparable"):
        InMemoryVectorStore.load(
            tmp_path / "index", model_id="a-different-model", dimension=DIMENSION
        )


def test_an_index_with_a_different_vector_width_is_refused(populated, tmp_path):
    populated.save(tmp_path / "index", corpus_fingerprint="abc123")
    with pytest.raises(IncompatibleIndexError, match="dimension"):
        InMemoryVectorStore.load(tmp_path / "index", model_id="test-model", dimension=8)


def test_an_index_in_an_older_format_is_refused(populated, tmp_path):
    populated.save(tmp_path / "index", corpus_fingerprint="abc123")
    path = tmp_path / "index" / MANIFEST_FILENAME
    manifest = json.loads(path.read_text())
    manifest["format_version"] = 0
    path.write_text(json.dumps(manifest))
    with pytest.raises(IncompatibleIndexError, match="format version"):
        InMemoryVectorStore.load(
            tmp_path / "index", model_id="test-model", dimension=DIMENSION
        )


def test_an_index_missing_its_vectors_fails_loudly(populated, tmp_path):
    populated.save(tmp_path / "index", corpus_fingerprint="abc123")
    (tmp_path / "index" / "vectors.npy").unlink()
    with pytest.raises(IndexNotFoundError, match="missing"):
        InMemoryVectorStore.load(
            tmp_path / "index", model_id="test-model", dimension=DIMENSION
        )


def test_vectors_and_chunks_disagreeing_fails_loudly(populated, tmp_path):
    populated.save(tmp_path / "index", corpus_fingerprint="abc123")
    path = tmp_path / "index" / CHUNKS_FILENAME
    chunks = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(chunks[:2]), encoding="utf-8")
    with pytest.raises(VectorStoreError, match="inconsistent"):
        InMemoryVectorStore.load(
            tmp_path / "index", model_id="test-model", dimension=DIMENSION
        )
