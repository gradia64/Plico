"""Edits of the outline, as functions from one bookmark list to the next.

The outline is a flat list in reading order, each entry with its level: a
tree drawn by indentation, as PDF stores it. An entry's *subtree* is the
entry and the deeper ones right after it. Every function returns a new list
and leaves the one it was given alone, so the window can hand both to
``SetOutline`` and undo is a matter of putting the old one back.
"""

from __future__ import annotations

from dataclasses import replace

from .document import Bookmark


def subtree_end(outline: list[Bookmark], index: int) -> int:
    """Where the subtree of *index* ends (exclusive)."""
    level = outline[index].level
    end = index + 1
    while end < len(outline) and outline[end].level > level:
        end += 1
    return end


def insertion_point(outline: list[Bookmark], positions: list[int | None], page: int) -> int:
    """Where a bookmark for the page at *page* goes, keeping reading order.

    *positions* is, for every bookmark, the position of its page in the
    document (None for a deleted page). The new one goes after the last
    top-level subtree that starts on that page or before it.
    """
    point = 0
    index = 0
    while index < len(outline):
        end = subtree_end(outline, index)
        position = positions[index]
        if position is not None and position > page:
            break
        point = end
        index = end
    return point


def add(outline: list[Bookmark], index: int, bookmark: Bookmark) -> list[Bookmark]:
    """*bookmark* inserted at *index*, at the first level."""
    result = list(outline)
    result.insert(index, replace(bookmark, level=1))
    return result


def rename(outline: list[Bookmark], index: int, title: str) -> list[Bookmark]:
    result = list(outline)
    result[index] = replace(result[index], title=title)
    return result


def remove(outline: list[Bookmark], index: int) -> list[Bookmark]:
    """The outline without the entry at *index* and the entries under it."""
    return outline[:index] + outline[subtree_end(outline, index) :]


def _previous_sibling(outline: list[Bookmark], index: int) -> int | None:
    level = outline[index].level
    for before in range(index - 1, -1, -1):
        if outline[before].level < level:
            return None
        if outline[before].level == level:
            return before
    return None


def move_up(outline: list[Bookmark], index: int) -> list[Bookmark] | None:
    """The subtree at *index* swapped with the previous sibling's (None: none)."""
    before = _previous_sibling(outline, index)
    if before is None:
        return None
    end = subtree_end(outline, index)
    return outline[:before] + outline[index:end] + outline[before:index] + outline[end:]


def move_down(outline: list[Bookmark], index: int) -> list[Bookmark] | None:
    """The subtree at *index* swapped with the next sibling's (None: none)."""
    end = subtree_end(outline, index)
    if end >= len(outline) or outline[end].level != outline[index].level:
        return None
    after_end = subtree_end(outline, end)
    return outline[:index] + outline[end:after_end] + outline[index:end] + outline[after_end:]


def _shift(outline: list[Bookmark], index: int, delta: int) -> list[Bookmark]:
    end = subtree_end(outline, index)
    moved = [replace(entry, level=entry.level + delta) for entry in outline[index:end]]
    return outline[:index] + moved + outline[end:]


def indent(outline: list[Bookmark], index: int) -> list[Bookmark] | None:
    """The subtree at *index* one level deeper, under the entry before it."""
    if _previous_sibling(outline, index) is None:
        return None
    return _shift(outline, index, 1)


def outdent(outline: list[Bookmark], index: int) -> list[Bookmark] | None:
    """The subtree at *index* one level up (None at the first level).

    Its later siblings stay where they are and become its children: that is
    what moving up a level means in a list drawn by indentation.
    """
    if outline[index].level <= 1:
        return None
    return _shift(outline, index, -1)
