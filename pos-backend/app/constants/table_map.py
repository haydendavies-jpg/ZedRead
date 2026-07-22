"""
Constants for table maps & floor service (Android POS Phase 4).

A `table_map_shapes` row's `kind` is either a seatable table shape (gets a
1:1 `dining_tables` row so the POS can carry live occupancy status) or a
decorative shape used only to render the floor plan (zones, bar counter,
entrance marker, walls — never linked to a dining table).

Mirrors the app/constants/pages.py convention of a single source of truth
list other modules validate against, rather than hardcoding string kinds
inline (root CLAUDE.md absolute rule 8).
"""

# Shape kinds that represent an actual seatable table — each gets a 1:1
# DiningTable row created alongside it (see table_map_service.create_shape).
TABLE_SHAPE_KINDS: frozenset[str] = frozenset({"stool", "round", "rect"})

# Decorative, non-seatable shapes used only to render the floor plan's
# backdrop (README-tables-floormap.md's zone/bar-counter/entrance/wall
# elements) — never linked to a DiningTable.
DECOR_SHAPE_KINDS: frozenset[str] = frozenset({"zone", "bar_counter", "entrance", "wall"})

# Every valid table_map_shapes.kind value.
SHAPE_KINDS: frozenset[str] = TABLE_SHAPE_KINDS | DECOR_SHAPE_KINDS

# table_sessions.status values. Deliberately excludes an "open" value — an
# unoccupied table is represented by DiningTable.active_session_id being
# NULL (no session row at all), not a session row carrying a status of
# 'open'. See TableSession's class docstring for the rationale.
TABLE_SESSION_STATUSES: frozenset[str] = frozenset({"seated", "ordered", "bill"})
