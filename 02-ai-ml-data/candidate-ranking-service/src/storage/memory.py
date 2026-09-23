"""In-memory candidate storage.

Deliberately not a database. The service ranks a working set inside one
session; it is not a system of record for applicant data, and keeping
candidate details out of persistent storage is the point rather than a
shortcut — see ``docs/SECURITY.md``.

Two consequences follow, and both are enforced rather than assumed:

1. **Contents are lost on restart.** Nothing here survives the process.
2. **Capacity is bounded.** Beyond ``max_size`` an upload is rejected with an
   error. The alternative — silently evicting the oldest entry — would drop a
   candidate from a ranking without anyone being told.
"""

from __future__ import annotations

import threading

from src.models.domain import Candidate


class CandidateStoreFull(RuntimeError):
    """Raised when an upload would exceed the store's capacity."""


class InMemoryCandidateStore:
    """A bounded, thread-safe dictionary of candidates keyed by candidate id."""

    def __init__(self, max_size: int = 1000) -> None:
        """Create the store.

        Args:
            max_size: Maximum number of distinct candidates held at once.

        Raises:
            ValueError: If ``max_size`` is not positive.
        """
        if max_size < 1:
            raise ValueError(f"max_size must be at least 1, got {max_size}")
        self.max_size = max_size
        self._candidates: dict[str, Candidate] = {}
        self._lock = threading.Lock()

    def add(self, candidate: Candidate) -> bool:
        """Store a candidate, replacing any entry with the same id.

        Args:
            candidate: The candidate to store.

        Returns:
            True if this created a new entry, False if it replaced one.

        Raises:
            CandidateStoreFull: If storing a *new* candidate would exceed
                capacity. Replacing an existing id never does.
        """
        with self._lock:
            is_new = candidate.candidate_id not in self._candidates
            if is_new and len(self._candidates) >= self.max_size:
                raise CandidateStoreFull(
                    f"Candidate store holds its maximum of {self.max_size} entries"
                )
            self._candidates[candidate.candidate_id] = candidate
            return is_new

    def get(self, candidate_id: str) -> Candidate | None:
        """Return a candidate by id, or None if absent."""
        with self._lock:
            return self._candidates.get(candidate_id)

    def delete(self, candidate_id: str) -> bool:
        """Remove a candidate. Returns True if one was removed."""
        with self._lock:
            return self._candidates.pop(candidate_id, None) is not None

    def list_ids(self) -> list[str]:
        """Return the stored candidate ids, sorted for a stable response."""
        with self._lock:
            return sorted(self._candidates)

    def all(self) -> list[Candidate]:
        """Return every stored candidate, ordered by id."""
        with self._lock:
            return [self._candidates[key] for key in sorted(self._candidates)]

    def clear(self) -> None:
        """Drop every stored candidate."""
        with self._lock:
            self._candidates.clear()

    @property
    def remaining_capacity(self) -> int:
        """How many further new candidates fit."""
        with self._lock:
            return self.max_size - len(self._candidates)

    def __len__(self) -> int:
        with self._lock:
            return len(self._candidates)
