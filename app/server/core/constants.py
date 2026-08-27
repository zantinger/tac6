"""
Constants for JSONL file processing and field flattening.

This module defines the delimiter constants used for flattening nested JSON objects
and arrays into flat column names suitable for SQLite tables. These two constants are
the single source of truth: changing them here changes every generated column name
with no other code edit.

Delimiter System:
- NESTED_DELIMITER: Used to separate nested object keys (e.g., "user__profile__name")
- LIST_INDEX_DELIMITER: Used to separate list indices (e.g., "items_0", "items_1")

Emission Contract (every case the flattener can produce):
- Nested object {"user": {"profile": {"name": "John"}}} becomes "user__profile__name"
- Array field {"items": ["a", "b"]} becomes "items_0" and "items_1"
- Array of objects {"tags": [{"name": "tag1"}, {"name": "tag2"}]} becomes
  "tags_0__name", "tags_1__name"
- Primitive leaves (string, number, boolean, null) map to the value itself
- Empty collections {"a": [], "b": {}} become a single NULL leaf each ("a" -> None,
  "b" -> None) so a field whose value is always empty is never silently erased
- Top-level primitives/arrays are NOT valid JSONL records: every JSONL line must be a
  JSON object, otherwise conversion fails with a line-numbered error

Known ambiguity: a literal key "a__b" is indistinguishable from nested {"a": {"b": ...}},
and a literal key "items_0" collides with index 0 of an "items" list. Collisions are
de-duplicated by `clean_column_names` rather than escaped, keeping column names readable
for the common case.
"""

# Delimiter for nested object fields
NESTED_DELIMITER = "__"

# Delimiter for list/array indices
LIST_INDEX_DELIMITER = "_"
