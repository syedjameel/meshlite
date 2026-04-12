"""fzf-style fuzzy subsequence matcher for the command palette.

:func:`score` takes a query and a candidate string and returns a score
(higher = better match) plus the list of matched character indices. Used
by the command palette to rank filtered entries.

Scoring heuristics (loosely inspired by fzf and Sublime Text):

- Exact prefix match → big bonus
- Each matched char → base score
- Consecutive matched chars → streak bonus (grows with streak length)
- Match at word boundary (after ``_``, ``:`` , `` ``) → boundary bonus
- Case-insensitive matching, but case-exact gets a small bonus
"""

from __future__ import annotations

# Tuning constants
_BASE = 10
_CONSECUTIVE_BONUS = 8
_PREFIX_BONUS = 30
_BOUNDARY_BONUS = 15
_CASE_EXACT_BONUS = 3
_UNMATCHED_PENALTY = -1

_BOUNDARY_CHARS = frozenset(" _-:/.")


def score(query: str, text: str) -> tuple[int, list[int]]:
    """Score ``text`` against ``query`` using fuzzy subsequence matching.

    Returns ``(score, matched_indices)``. If ``query`` is not a subsequence
    of ``text``, returns ``(0, [])``.
    """
    if not query:
        return (0, [])

    q_lower = query.lower()
    t_lower = text.lower()

    # Quick reject: every query char must exist in text.
    for ch in q_lower:
        if ch not in t_lower:
            return (0, [])

    # Greedy forward match — find the earliest subsequence.
    indices: list[int] = []
    qi = 0
    for ti in range(len(t_lower)):
        if qi < len(q_lower) and t_lower[ti] == q_lower[qi]:
            indices.append(ti)
            qi += 1
    if qi < len(q_lower):
        return (0, [])

    # Score the match.
    total = 0
    prev_idx = -2
    streak = 0

    for i, idx in enumerate(indices):
        total += _BASE

        # Consecutive chars bonus.
        if idx == prev_idx + 1:
            streak += 1
            total += _CONSECUTIVE_BONUS * streak
        else:
            streak = 0

        # Prefix bonus (match at position 0).
        if idx == 0:
            total += _PREFIX_BONUS

        # Word boundary bonus.
        if idx > 0 and text[idx - 1] in _BOUNDARY_CHARS:
            total += _BOUNDARY_BONUS

        # Case-exact bonus.
        if query[i] == text[idx]:
            total += _CASE_EXACT_BONUS

        prev_idx = idx

    # Penalize long unmatched gaps.
    total += (len(text) - len(indices)) * _UNMATCHED_PENALTY

    return (total, indices)


def filter_and_rank(
    query: str,
    items: list[str],
    *,
    min_score: int = 1,
) -> list[tuple[int, str, list[int]]]:
    """Filter ``items`` by ``query`` and return them sorted by score (desc).

    Each result is ``(score, item, matched_indices)``. Items that don't
    match at all are excluded.
    """
    results: list[tuple[int, str, list[int]]] = []
    for item in items:
        s, indices = score(query, item)
        if s >= min_score:
            results.append((s, item, indices))
    results.sort(key=lambda r: -r[0])
    return results
