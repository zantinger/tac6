# Feature: JSONL File Upload Support

## Metadata
issue_number: `1`
adw_id: `5c700c17`
issue_json: `{"number":1,"title":"Add support for uploading jsonl files.","body":"/feature\n\nBe sure to look through entire jsonl first to get all possible fields. use std lib - no new libraries outside of what we have.\n\nOne jsonl files will create one new table just like our current csv.\n\nconcat nested fields and any possible lists with __ store as updatable delimiter in a constans file.\n\nuse _0 to denote list items (use delimiter and specify by index)\n\nupdate ui to let users know they can upload jsonl files as well then inside codebase in the test dir create a couple jsonl files we can use to test uploads "}`

## Feature Description
Add first-class support for uploading JSON Lines (`.jsonl`) files to the Natural Language SQL Interface. A JSONL file contains one JSON object per line, and objects commonly have nested objects and arrays plus a *ragged* schema (different lines carry different keys).

One uploaded `.jsonl` file produces exactly one SQLite table, exactly like a `.csv` upload does today. Because SQLite tables are flat, every nested structure is flattened into a single column-per-leaf-value layout:

- Nested object keys are joined with the nested delimiter `__` — `{"user": {"profile": {"name": "John"}}}` → `user__profile__name`
- List items are denoted by index using the list-index delimiter `_` — `{"items": ["a","b"]}` → `items_0`, `items_1`
- The two compose for lists of objects — `{"tags": [{"name": "t1"}]}` → `tags_0__name`

Both delimiters live in a dedicated constants module (`app/server/core/constants.py`) so they are updatable in one place instead of being hardcoded across the flattening logic.

Crucially, the whole file is scanned **before** any table is created, so the resulting table's column set is the *union* of every field found on every line. Lines missing a field get `NULL` for that column rather than the upload failing or silently dropping data.

The client UI advertises the new format (drop-zone copy, the file picker's `accept` filter, a JSONL sample-data quick-start button, and a short hint explaining the flattened `parent__child` / `list_0` column naming so users know what to query). Test JSONL fixtures live in the server test assets directory so uploads are covered by automated tests.

Implementation uses only the Python standard library (`json`) plus dependencies already in `app/server/pyproject.toml` (`pandas`, `sqlite3`). No new packages.

## User Story
As a data analyst working with log, event, and API-export files
I want to upload `.jsonl` files and have their nested fields and lists become queryable columns
So that I can ask natural-language questions about JSONL data without first converting it to CSV or hand-flattening it

## Problem Statement
JSONL is the de-facto interchange format for event streams, LLM/ML datasets, and API exports, but the app currently only accepts `.csv` and `.json`:

1. A `.jsonl` file is not a valid JSON document, so `convert_json_to_sqlite()` (which does `json.loads()` on the whole file and requires a top-level array) fails on it outright.
2. Even when JSON records *are* wrapped in an array, `pd.DataFrame(data)` stores nested dicts/lists as Python objects, which land in SQLite as opaque stringified blobs the LLM cannot meaningfully query.
3. Naively taking the columns from the first record (or letting pandas infer per-chunk) silently loses fields that appear only on later lines — a real hazard because JSONL schemas are routinely ragged.
4. Users have no way to know from the UI which formats are accepted or how nested data will be named once flattened.

Today a JSONL user has to leave the app, write a flattening script, and re-upload a CSV — which is exactly the friction this app exists to remove.

## Solution Statement
Add a JSONL ingestion path alongside the existing CSV/JSON paths, following the exact shape of the existing converters so the rest of the system (schema endpoint, insights, SQL generation, table deletion) needs no changes.

1. **Constants module** — `app/server/core/constants.py` owns `NESTED_DELIMITER = "__"` and `LIST_INDEX_DELIMITER = "_"`, documented with examples. All flattening reads these constants; no delimiter literal appears anywhere else.
2. **Pure flattening helper** — `flatten_json_object(obj, prefix="")` recursively walks dicts and lists using those constants and returns a flat `{column_name: primitive}` dict. It is pure and side-effect free, so it unit-tests cheaply.
3. **Two-pass conversion** — pass one (`discover_jsonl_fields`) parses every line and unions all flattened field names, so the column set is complete and stable; pass two builds one record per line, filling absent fields with `None`, then hands a rectangular `DataFrame` to `df.to_sql(..., if_exists='replace')`.
4. **Reuse existing security + response plumbing** — table names go through `sanitize_table_name()`/`validate_identifier()`, and schema/sample/row-count reads go through `execute_query_safely()`, identical to the CSV path. The endpoint keeps returning the same `FileUploadResponse`.
5. **UI + docs** — extend the accepted-extension copy, `accept` attribute, and sample-data quick start; add a hint describing flattened column naming; update `README.md`, which still advertises only `.csv` and `.json`.
6. **Fixtures + tests** — a couple of `.jsonl` files under `app/server/tests/assets/` (flat/ragged, deeply nested, and edge cases) drive unit tests, and a new E2E test drives a real browser upload.

### Current State Audit (read this before starting)
A substantial part of this feature is **already present at HEAD** (commit `39fc11c`) and `uv run pytest` currently reports **67 passed**. This plan is therefore a *gap-closing and hardening* plan, not a greenfield build. Verify-then-extend; do not rewrite what already works.

Already implemented (verify, keep):
- `app/server/core/constants.py` with both delimiters and docstring examples
- `flatten_json_object()`, `discover_jsonl_fields()`, `convert_jsonl_to_sqlite()` in `app/server/core/file_processor.py`
- `POST /api/upload` accepting `.jsonl` and routing to `convert_jsonl_to_sqlite()` (`app/server/server.py`)
- Unit tests in `app/server/tests/core/test_file_processor.py` and fixtures `tests/assets/sample_data.jsonl`, `tests/assets/complex_data.jsonl`
- Client: drop-zone copy "Drag and drop .csv, .json, or .jsonl files here", `accept=".csv,.json,.jsonl"`, "Event Analytics" sample button, `public/sample-data/events.jsonl` (10 records)

Genuine gaps this plan closes:
- **G1 — Non-deterministic column order.** `discover_jsonl_fields()` returns a `set`, and `convert_jsonl_to_sqlite()` iterates that set to build each record, so the table's column order varies between runs (Python randomizes `str` hashing per process). Uploading the same file twice can yield differently ordered columns.
- **G2 — Empty collections erase fields.** `flatten_json_object({"a": [], "b": {}, "c": 1})` returns `{"c": 1}` — verified. A field whose value is `[]`/`{}` on *every* line disappears from the table entirely, and a file of only such fields fails with a misleading "No valid JSON objects found".
- **G3 — Non-object lines produce garbage columns.** A top-level primitive line yields the empty-string column name `""` (verified: `flatten_json_object(5) == {"": 5}`), and a top-level array line yields `_0`, `_1`. Both need a clear, line-numbered error instead.
- **G4 — Column-name collisions.** All three converters do `col.lower().replace(' ','_').replace('-','_')` with no de-duplication, so `{"Name": 1, "name": 2}` produces two `name` columns and `df.to_sql` raises an opaque "duplicate column name" error.
- **G5 — README is stale.** It still says ".csv and .json" in Features, Usage, API Endpoints, and Security.
- **G6 — No E2E coverage** for a JSONL upload.
- **G7 — No UI explanation** of the flattened column naming, so users don't know to query `user__name` rather than `user`.

## Relevant Files
Use these files to implement the feature:

- `README.md` — Project overview, features list, usage instructions, API endpoint list, and security notes. Still advertises only `.csv`/`.json`; must be updated (G5). Per `.claude/commands/conditional_docs.md`, reading this is required because we touch both `app/server` and `app/client`.
- `.claude/commands/conditional_docs.md` — Conditional documentation rules. Matched conditions for this task: operating under `app/server`, operating under `app/client`, and needing the start/stop commands. No `adws/` files change, so `.claude/commands/classify_adw.md` and `adws/README.md` are **not** required.
- `app/server/core/constants.py` — Home of `NESTED_DELIMITER` (`"__"`) and `LIST_INDEX_DELIMITER` (`"_"`). Single source of truth for delimiters; extend its docstring with the empty-collection rule.
- `app/server/core/file_processor.py` — Contains `sanitize_table_name`, `convert_csv_to_sqlite`, `convert_json_to_sqlite`, `flatten_json_object`, `discover_jsonl_fields`, `convert_jsonl_to_sqlite`. All of G1–G4 are fixed here.
- `app/server/core/sql_security.py` — `validate_identifier`, `execute_query_safely`, `check_table_exists`, `SQLSecurityError`. Must be used for every identifier and query in the JSONL path; do not hand-build SQL strings.
- `app/server/server.py` — `POST /api/upload` validates the extension, derives the table name from the filename, and dispatches by extension. Verify the `.jsonl` branch and that the rejection message names all three formats.
- `app/server/core/data_models.py` — `FileUploadResponse` (`table_name`, `table_schema`, `row_count`, `sample_data`, `error`). JSONL reuses it unchanged; no model changes expected.
- `app/server/core/sql_processor.py` / `app/server/core/insights.py` — Downstream consumers of whatever table we create. Read to confirm long flattened column names and `NULL`-heavy columns need no special handling.
- `app/server/tests/core/test_file_processor.py` — Existing CSV/JSON/JSONL unit tests. Note that `test_discover_jsonl_fields_*` assert **set equality** (e.g. `fields == {"name","age","city"}`), so `discover_jsonl_fields` must keep returning a `Set[str]`; add ordering as a separate helper rather than changing that signature.
- `app/server/tests/assets/sample_data.jsonl` — Existing fixture: flat records with a ragged nested `profile` object on later lines.
- `app/server/tests/assets/complex_data.jsonl` — Existing fixture: deeply nested objects, lists of objects, and a `tags` string list.
- `app/server/tests/test_sql_injection.py` — Security regression suite; must stay green (it exercises upload/table-name sanitization).
- `app/server/pyproject.toml` — Dependency list (`pandas`, `fastapi`, …) and pytest config. Confirms no new library is needed; `json` is stdlib.
- `app/client/index.html` — Upload modal: sample-data buttons, drop-zone copy, and the `accept` attribute. G7's naming hint goes here.
- `app/client/src/main.ts` — `initializeFileUpload()`, `handleFileUpload()`, `loadSampleData()` (maps `data-sample="events"` → `events.jsonl`), `displayUploadSuccess()`, `displayTables()`. Verify the JSONL sample path and success messaging.
- `app/client/src/types.d.ts` — Shared client types including `FileUploadResponse`. Check whether anything is format-specific.
- `app/client/src/style.css` — Styles for the upload modal / drop zone; needed if the naming hint requires a new class (per `conditional_docs.md`, read before changing client styles).
- `app/client/public/sample-data/events.jsonl` — Client-served JSONL sample (10 nested event records) used by the "Event Analytics" quick-start button and by the E2E test.
- `scripts/start.sh`, `scripts/stop_apps.sh`, `scripts/reset_db.sh` — Start/stop both services and reset the DB; used to bring the app up for the E2E test and to get a clean table list.
- `.claude/commands/test_e2e.md` — **Read this** to understand how E2E tests are executed (Playwright MCP, screenshot directory convention `agents/<adw_id>/<agent_name>/img/<test_name>/`, required JSON output format).
- `.claude/commands/e2e/test_basic_query.md` — **Read this** as the template for E2E test structure (User Story, numbered Test Steps with `**Verify**` assertions, Success Criteria including screenshot count).
- `.claude/commands/e2e/test_complex_query.md` — Second E2E example showing query-flow assertions; useful for the "query the flattened columns" half of the new test.

### New Files
- `.claude/commands/e2e/test_jsonl_upload.md` — New E2E test: upload a `.jsonl` file through the UI, verify the table appears with flattened `__`/`_0` columns, and run one natural-language query against a flattened column. Modeled on `test_basic_query.md`.
- `app/server/tests/assets/edge_cases.jsonl` — New fixture exercising the hardening work: empty list `[]`, empty object `{}`, explicit `null`, a boolean, a deeply-nested-only record, a field appearing only on the last line, and mixed types for the same field across lines.

## Implementation Plan

### Phase 1: Foundation
Lock down the delimiter contract and the flattening primitive before touching ingestion.

- Confirm `core/constants.py` is the only place delimiter literals live; grep for stray `"__"` / `'_'` string literals in the flattening code path.
- Extend the constants docstring so it documents every case the flattener can emit, including the empty-collection rule added in Phase 2.
- Treat `flatten_json_object()` as the pure, well-tested core: dict → `parent__child`, list → `name_<index>`, primitives → leaf value, empty collections → a single `NULL` leaf so the field is never silently erased.
- Keep the public signatures already covered by tests (`flatten_json_object(obj, prefix="")` and `discover_jsonl_fields(content) -> Set[str]`) so the existing 67 tests keep passing.

### Phase 2: Core Implementation
Harden the two-pass JSONL → SQLite conversion.

- Add an ordered field-discovery helper (e.g. `discover_jsonl_fields_ordered(content) -> List[str]`) that records fields in first-seen order using a `dict` as an ordered set. Re-implement `discover_jsonl_fields()` as `set(discover_jsonl_fields_ordered(content))` so the tested set-returning contract is preserved with no duplicated parsing logic (fixes G1).
- Enforce that each non-blank line parses to a JSON **object**, raising `ValueError(f"Line {n}: JSONL lines must be JSON objects, got <type>")` otherwise (fixes G3). Keep `flatten_json_object`'s primitive behavior unchanged — the check belongs in the line loop, not the flattener, because a test asserts `flatten_json_object("hello") == {"": "hello"}`.
- Emit `result[prefix] = None` for `[]` and `{}` when a prefix exists, so those fields still become columns (fixes G2).
- Extract a shared `clean_column_names(columns) -> List[str]` helper that lowercases, replaces spaces/dashes with `_`, replaces any remaining SQLite-hostile character, guards against empty/leading-digit names, and de-duplicates collisions with a `_2`, `_3`, … suffix. Use it in all three converters so CSV and JSON benefit too (fixes G4).
- Keep line-numbered, actionable error messages for invalid JSON, non-UTF-8 bytes, empty files, and blank-line-only files.
- Keep using `sanitize_table_name()` + `execute_query_safely()` for the table write and the schema/sample/count reads.

### Phase 3: Integration
Wire the hardened core through the API, the UI, the docs, and the tests.

- Verify `POST /api/upload` accepts `.jsonl` (case-insensitively), dispatches to `convert_jsonl_to_sqlite`, and returns the standard `FileUploadResponse`; confirm the rejection message lists `.csv`, `.json`, and `.jsonl`.
- Confirm downstream endpoints (`GET /api/schema`, `POST /api/insights`, `POST /api/query`, `DELETE /api/table/{name}`) work unchanged against a JSONL-derived table with long flattened column names.
- Update the client so JSONL is discoverable: drop-zone copy, `accept` filter, sample button, and a one-line hint explaining `parent__child` / `list_0` naming.
- Update `README.md` everywhere it enumerates supported formats.
- Add the `edge_cases.jsonl` fixture, unit tests for every new behavior, and the new E2E test file; then run the full validation suite.

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

### 1. Read the required documentation and audit the current state
- Read `README.md` (required by `.claude/commands/conditional_docs.md` for both `app/server` and `app/client` work).
- Read `.claude/commands/test_e2e.md` and `.claude/commands/e2e/test_basic_query.md` to learn the E2E test format before writing one.
- Read `app/server/core/constants.py`, `app/server/core/file_processor.py`, `app/server/server.py`, `app/server/tests/core/test_file_processor.py`, `app/client/index.html`, and `app/client/src/main.ts`.
- Run `cd app/server && uv run pytest` and record the baseline (expected: 67 passed). Every later step must keep this suite green.
- Confirm each gap G1–G7 from the *Current State Audit*; skip any that no longer applies and say so in the final summary.

### 2. Create the E2E test file `.claude/commands/e2e/test_jsonl_upload.md`
- Model the structure on `.claude/commands/e2e/test_basic_query.md`: `# E2E Test: ...` title, `## User Story`, numbered `## Test Steps` with `**Verify**` assertions, `## Success Criteria`, and the same JSON `Output Format` expectations that `test_e2e.md` describes.
- Keep it to the minimal set of steps that proves JSONL upload works, with screenshots as evidence:
  1. Navigate to the `Application URL`; screenshot the initial state.
  2. Click "Upload Data"; **Verify** the drop zone text mentions `.jsonl` and screenshot the modal (this is the UI-discoverability assertion).
  3. Click the "Event Analytics" sample button (serves `public/sample-data/events.jsonl`).
  4. **Verify** the success message reads `Table "events" created successfully with 10 rows!`; screenshot it.
  5. **Verify** the Available Tables section lists `events` with flattened columns — at least one nested column (`user__name`) and at least one list-indexed column (`action__items_0__name`); screenshot the table schema.
  6. Enter the query "Show the event id and user name for every event" and click Query.
  7. **Verify** the generated SQL references a flattened column containing `user__name` and that the results table renders 10 rows; screenshot the results.
  8. Click "Hide" to close results.
- Success Criteria: `.jsonl` is advertised in the UI; the upload creates one table with 10 rows; nested and list-indexed columns exist with the `__` / `_0` naming; a natural-language query against a flattened column returns rows; no console/UI errors; 5 screenshots captured.

### 3. Finalize the delimiter constants in `app/server/core/constants.py`
- Keep `NESTED_DELIMITER = "__"` and `LIST_INDEX_DELIMITER = "_"` as the two updatable knobs.
- Extend the module docstring with the full emission contract, including the new empty-collection rule (`{"a": []}` → column `a` with `NULL`) and the rule that JSONL lines must be JSON objects.
- Grep the flattening path to confirm no delimiter literal is hardcoded outside this module.

### 4. Harden `flatten_json_object` in `app/server/core/file_processor.py`
- Emit `result[prefix] = None` when a `dict` or `list` is empty **and** `prefix` is non-empty, so `{"a": [], "b": {}, "c": 1}` yields `{"a": None, "b": None, "c": 1}` (fixes G2).
- Leave the existing dict/list/primitive behavior otherwise byte-for-byte identical; `user__profile__name`, `items_0`, `actions_0__type`, and `flatten_json_object(42) == {"": 42}` must all still hold.
- Keep the function pure — no I/O, no logging, no mutation of the input.

### 5. Add deterministic ordered field discovery
- Add `discover_jsonl_fields_ordered(jsonl_content: bytes) -> List[str]` that walks lines in order and accumulates flattened field names in first-seen order (use a `dict` keyed by field name as an ordered set).
- Enforce per-line object-ness there: skip blank lines, and raise `ValueError` naming the 1-based line number for non-`dict` parses and for `json.JSONDecodeError` (keep the existing `"Invalid JSON on line {n}"` wording so `test_discover_jsonl_fields_invalid_json` still passes).
- Keep the `UnicodeDecodeError` → `"File is not valid UTF-8 encoded text"` translation.
- Redefine `discover_jsonl_fields()` to return `set(discover_jsonl_fields_ordered(...))` so its `Set[str]` contract and the existing set-equality assertions are preserved.

### 6. Add `clean_column_names` and use it in all three converters
- Implement `clean_column_names(columns: List[str]) -> List[str]`: lowercase; replace spaces and dashes with `_`; replace any character outside `[a-z0-9_]` with `_`; substitute `column` for an empty result and prefix `col_` when the name starts with a digit; then de-duplicate by appending `_2`, `_3`, … preserving order (fixes G4).
- Call it from `convert_csv_to_sqlite`, `convert_json_to_sqlite`, and `convert_jsonl_to_sqlite` in place of the inline list comprehensions, so all three formats share one rule.
- Verify the existing `test_convert_csv_to_sqlite_column_cleaning` expectations still hold.

### 7. Rewire `convert_jsonl_to_sqlite` onto the hardened primitives
- Pass one: `ordered_fields = discover_jsonl_fields_ordered(jsonl_content)`; raise `ValueError("No valid JSON objects found in JSONL file")` when empty.
- Pass two: for each non-blank line, parse, `flatten_json_object`, then build a record as `{field: flattened.get(field) for field in ordered_fields}` — iterating the **ordered list**, never the set (fixes G1).
- Build the `DataFrame` with `columns=ordered_fields` so column order is pinned even if pandas would infer otherwise, then apply `clean_column_names`.
- Keep `df.to_sql(table_name, conn, if_exists='replace', index=False)` so re-uploading the same filename overwrites the table, matching documented CSV behavior.
- Keep reading schema, 5-row sample, and row count through `execute_query_safely()` with `identifier_params={'table': table_name}`, and keep returning the same `{'table_name', 'schema', 'row_count', 'sample_data'}` dict.
- Close the SQLite connection on both success and failure paths (`try/finally`) so a mid-file error cannot leak a handle.

### 8. Verify the upload endpoint in `app/server/server.py`
- Confirm the extension guard accepts `.jsonl` and that the 400 message names all three supported formats.
- Make the extension check case-insensitive (`file.filename.lower().endswith(...)`) so `DATA.JSONL` is accepted and routed to the JSONL branch rather than falling through to the JSON branch.
- Confirm the table name derivation (`filename.rsplit('.', 1)[0]`) strips `.jsonl` correctly and that `sanitize_table_name` still guards it.
- Leave logging and the `FileUploadResponse` error-envelope behavior unchanged.

### 9. Add the `edge_cases.jsonl` test fixture
- Create `app/server/tests/assets/edge_cases.jsonl` with one JSON object per line covering: an empty list, an empty object, an explicit `null`, a boolean, a nested-only record, a field that appears only on the final line, and the same field holding different types on different lines.
- Confirm `app/server/tests/assets/sample_data.jsonl` (flat + ragged nested) and `complex_data.jsonl` (deeply nested, lists of objects, string list) already satisfy the issue's "create a couple jsonl files we can use to test uploads" requirement; keep both.
- Do not add trailing-garbage lines — invalid-JSON cases stay as inline byte literals in the tests so the fixtures remain valid, loadable files.

### 10. Extend the unit tests in `app/server/tests/core/test_file_processor.py`
- `flatten_json_object`: empty list → `{"a": None}`; empty object → `{"b": None}`; nested empty collection inside a nested object; and re-assert the existing nested/list/complex/primitive cases as regressions.
- Ordered discovery: same file parsed twice yields the identical field **order**; first-seen order matches the file's field order; ordered list de-duplicates repeated fields.
- Set-returning `discover_jsonl_fields` still returns a `Set[str]` equal to the expected set (no regression).
- Object-ness enforcement: a top-level primitive line and a top-level array line each raise `ValueError` naming the correct line number, and no `""`/`_0` column is ever created.
- Column cleaning: `{"Name": 1, "name": 2}` produces `name` and `name_2` and the upload succeeds; spaces/dashes/`$` are normalized; a digit-leading key is prefixed.
- `convert_jsonl_to_sqlite` against `edge_cases.jsonl`: table created, row count equals the number of non-blank lines, every discovered field is a column, missing values read back as `NULL`.
- `convert_jsonl_to_sqlite` column order determinism: convert the same fixture twice and assert `PRAGMA table_info` returns the same column sequence.
- Re-upload overwrite: converting twice with the same table name leaves one table with the second file's row count (`if_exists='replace'`).
- Keep every existing test passing; do not delete or weaken an assertion to make new code fit.

### 11. Update the client UI to advertise JSONL (`app/client/index.html`, `app/client/src/main.ts`, `app/client/src/style.css`)
- Verify the drop-zone copy reads "Drag and drop .csv, .json, or .jsonl files here" and that `accept=".csv,.json,.jsonl"` is set on `#file-input`.
- Add a short hint under the drop zone explaining flattened naming, e.g. "JSONL: nested fields become `user__name`, list items become `items_0`" — plain, small, muted text. Read `app/client/src/style.css` first (per `conditional_docs.md`) and reuse an existing muted/small class if one exists rather than adding new CSS.
- Verify the "Event Analytics" sample button (`data-sample="events"`) maps to `events.jsonl` in `loadSampleData()` and that its "10 events with nested data" label matches the fixture's 10 records.
- Do not change `handleFileUpload()`'s API contract; JSONL rides the existing `POST /api/upload` multipart path.
- Keep TypeScript strict-clean — `bun tsc --noEmit` must pass.

### 12. Update `README.md`
- Features: "Drag-and-drop file upload (.csv, .json, and .jsonl)".
- Usage step 1: "Or drag and drop your own .csv, .json, or .jsonl files".
- API Endpoints: "`POST /api/upload` - Upload CSV/JSON/JSONL file".
- Security → Additional Security Features: "File upload validation (CSV, JSON, and JSONL only)".
- Add a short "JSONL Support" subsection under Usage documenting the two-pass full-file field discovery, the `__` and `_0` conventions, that missing fields become `NULL`, and that both delimiters are configurable in `app/server/core/constants.py`.

### 13. Run the full validation suite
- Execute every command in `## Validation Commands`, in order, and confirm each exits without error.
- Include the E2E run: read `.claude/commands/test_e2e.md`, then execute `.claude/commands/e2e/test_jsonl_upload.md`.
- Report the final test counts and note explicitly any gap from the audit that turned out not to apply.

## Testing Strategy

### Unit Tests
Extend `app/server/tests/core/test_file_processor.py` (pytest, `Test*` classes, fixtures `test_db` → `':memory:'` and `test_assets_dir` → `tests/assets`):

- **`flatten_json_object`** — nested dicts (`user__profile__name`), lists (`items_0`, `items_1`), lists of objects (`actions_0__type`), scalar/`None`/bool leaves, empty list → single `None` leaf, empty object → single `None` leaf, and delimiters sourced from `constants` (patch `NESTED_DELIMITER` in a test to prove nothing is hardcoded).
- **`discover_jsonl_fields` / `discover_jsonl_fields_ordered`** — union across ragged lines, nested field names, list indices growing with the longest list, blank lines skipped, invalid JSON raising with the right line number, non-object lines raising with the right line number, non-UTF-8 bytes raising the encoding error, and stable first-seen ordering across repeated calls.
- **`clean_column_names`** — lowercasing, space/dash normalization, exotic-character replacement, empty and digit-leading names, and collision de-duplication order.
- **`convert_jsonl_to_sqlite`** — happy path on `sample_data.jsonl`; deep nesting/lists on `complex_data.jsonl`; hardening on `edge_cases.jsonl`; correct `row_count`; `sample_data` capped at 5 rows; `schema` keys matching `PRAGMA table_info`; ragged records filled with `NULL`; deterministic column order across two conversions; `if_exists='replace'` overwrite semantics; sanitized table names for hostile filenames; and clear failures on invalid JSON, empty content, and blank-line-only content.
- **Regression** — the existing CSV and JSON tests must pass unchanged after `clean_column_names` is shared, and `tests/test_sql_injection.py` must stay green.

### Edge Cases
- Empty file, whitespace-only file, blank-line-only file → clear `ValueError`, no table created.
- No trailing newline on the last line (true of `public/sample-data/events.jsonl`) → last record still ingested.
- Trailing newline and interior blank lines → skipped, not counted as rows.
- CRLF (`\r\n`) line endings → records parse without a stray `\r` in values or field names.
- Invalid JSON on line N → error names line N; no partial table left behind.
- Non-UTF-8 bytes → "File is not valid UTF-8 encoded text".
- Line that is a JSON array or a bare scalar → explicit "lines must be JSON objects" error, never a `""` or `_0` column.
- Ragged schema where a field appears only on the very last line → still a column, `NULL` on all earlier rows.
- Lists of different lengths across lines → column count driven by the longest list; shorter rows `NULL`.
- Empty list / empty object / explicit `null` values → column exists, value `NULL`.
- Same field with different types across lines (int then string) → pandas widens to `TEXT`/object without crashing.
- Deeply nested structures (4+ levels) and lists of objects containing lists → long but valid column names.
- Key collisions after cleaning (`"Name"`/`"name"`, `"a b"`/`"a-b"`) → de-duplicated, no "duplicate column name" error.
- Keys containing the delimiters themselves (a literal `"a__b"` key, or a literal `"items_0"` key alongside an `items` list) → documented ambiguity; must not crash the upload.
- Filename edge cases: `.JSONL` uppercase, spaces, and characters requiring `sanitize_table_name`.
- Re-uploading the same filename → table replaced, not duplicated or appended.
- Wide file (hundreds of discovered columns) → upload completes; verify SQLite's column limit is not the failure mode at realistic sizes.

## Acceptance Criteria
1. Uploading a `.jsonl` file through the UI creates exactly one SQLite table named after the file, with `row_count` equal to the number of non-blank lines.
2. The entire file is scanned before the table is created: a field present only on the last line is still a column, and rows lacking it hold `NULL`.
3. Nested object fields are flattened with `__` (`{"user":{"profile":{"name":"John"}}}` → `user__profile__name`).
4. List items are flattened with the list-index delimiter and their index (`{"items":["a","b"]}` → `items_0`, `items_1`), and lists of objects compose both delimiters (`tags_0__name`).
5. Both delimiters are defined only in `app/server/core/constants.py`; changing `NESTED_DELIMITER` there changes the generated column names with no other code edit.
6. No new third-party dependency is added — `app/server/pyproject.toml` is unchanged; parsing uses stdlib `json`.
7. `POST /api/upload` accepts `.csv`, `.json`, and `.jsonl` (case-insensitively) and rejects anything else with a 400 naming all three.
8. Converting the same JSONL file twice produces the same column order (G1 fixed).
9. Fields whose value is `[]` or `{}` still appear as `NULL` columns (G2 fixed).
10. A JSONL line that is not a JSON object fails with a line-numbered error, and no `""` or `_0` column is ever created (G3 fixed).
11. Records whose keys collide after cleaning upload successfully with de-duplicated column names (G4 fixed).
12. The upload modal states that `.jsonl` is accepted, the file picker filters for it, and a hint explains the flattened `parent__child` / `list_0` naming (G7 fixed).
13. `README.md` lists `.jsonl` in Features, Usage, API Endpoints, and Security, and documents the flattening conventions (G5 fixed).
14. `app/server/tests/assets/` contains at least two usable `.jsonl` fixtures (`sample_data.jsonl`, `complex_data.jsonl`) plus `edge_cases.jsonl`, all exercised by tests.
15. `.claude/commands/e2e/test_jsonl_upload.md` exists and passes, capturing 5 screenshots (G6 fixed).
16. A natural-language query against a flattened column (e.g. `user__name`) returns correct rows through `POST /api/query`.
17. `cd app/server && uv run pytest` passes with **at least** the 67 pre-existing tests plus the new ones, and zero failures.
18. `cd app/client && bun tsc --noEmit` and `bun run build` both succeed.

## Validation Commands
Execute every command to validate the feature works correctly with zero regressions.

- `cd app/server && uv run pytest` - Run server tests to validate the feature works with zero regressions (baseline before changes: 67 passed; must end at 67 + new tests, 0 failures)
- `cd app/server && uv run pytest tests/core/test_file_processor.py -v` - Verify every CSV/JSON/JSONL converter test, including all new flattening, ordering, and column-cleaning tests
- `cd app/server && uv run pytest tests/test_sql_injection.py -v` - Verify the SQL injection protections still hold after the shared column-cleaning refactor
- `cd app/server && uv run python -c "from core.file_processor import flatten_json_object; assert flatten_json_object({'user':{'profile':{'name':'John'}}}) == {'user__profile__name':'John'}; assert flatten_json_object({'items':['a','b']}) == {'items_0':'a','items_1':'b'}; assert flatten_json_object({'tags':[{'name':'t1'}]}) == {'tags_0__name':'t1'}; assert flatten_json_object({'a':[],'b':{},'c':1}) == {'a':None,'b':None,'c':1}; print('flattening OK')"` - Prove the `__` / `_0` conventions and the empty-collection rule
- `cd app/server && uv run python -c "from core.file_processor import convert_jsonl_to_sqlite; d=open('tests/assets/complex_data.jsonl','rb').read(); a=convert_jsonl_to_sqlite(d,'t1',':memory:'); b=convert_jsonl_to_sqlite(d,'t1',':memory:'); assert list(a['schema'])==list(b['schema']), 'column order not deterministic'; assert a['row_count']>0; print('deterministic order OK:', list(a['schema'])[:6])"` - Prove deterministic column ordering (G1)
- `cd app/server && uv run python -c "from core.file_processor import convert_jsonl_to_sqlite; r=convert_jsonl_to_sqlite(open('tests/assets/edge_cases.jsonl','rb').read(),'edge',':memory:'); print(r['row_count'], list(r['schema'])); assert '' not in r['schema']; print('edge cases OK')"` - Prove edge-case fixture ingests with no empty column name (G2/G3)
- `./scripts/reset_db.sh` - Start the API-level check from a clean database
- `./scripts/start.sh` - Start backend (http://localhost:8000) and frontend (http://localhost:5173)
- `curl -s -X POST http://localhost:8000/api/upload -F "file=@app/client/public/sample-data/events.jsonl" | python3 -m json.tool` - Verify the end-to-end upload returns `table_name: "events"`, `row_count: 10`, `error: null`, and a schema containing `user__name` and a `_0`-indexed list column
- `curl -s http://localhost:8000/api/schema | python3 -m json.tool` - Verify the `events` table and its flattened columns appear in the schema endpoint
- `curl -s -X POST http://localhost:8000/api/query -H "Content-Type: application/json" -d '{"query":"Show the event id and user name for every event","llm_provider":"anthropic"}' | python3 -m json.tool` - Verify a natural-language query against a flattened column returns 10 rows with no error
- `curl -s -X POST http://localhost:8000/api/insights -H "Content-Type: application/json" -d '{"table_name":"events"}' | python3 -m json.tool` - Verify insights generation works on a JSONL-derived table with `NULL`-heavy flattened columns
- `curl -s -X POST http://localhost:8000/api/upload -F "file=@README.md" | python3 -m json.tool` - Verify an unsupported extension is rejected with an error naming .csv, .json, and .jsonl
- `Read .claude/commands/test_e2e.md`, then read and execute your new E2E `.claude/commands/e2e/test_jsonl_upload.md` test file to validate this functionality works.
- `./scripts/stop_apps.sh` - Stop both services after the API and E2E checks
- `cd app/client && bun tsc --noEmit` - Run frontend tests to validate the feature works with zero regressions
- `cd app/client && bun run build` - Run frontend build to validate the feature works with zero regressions

## Notes

**No new dependencies.** The issue mandates the standard library. JSONL parsing uses stdlib `json` line by line; `pandas` and `sqlite3` are already used by the CSV/JSON converters and are already declared in `app/server/pyproject.toml`. Nothing needs `uv add`.

**This feature is largely already implemented at HEAD.** Commit `39fc11c` already ships `core/constants.py`, the three JSONL functions in `core/file_processor.py`, the `.jsonl` branch in `POST /api/upload`, JSONL unit tests and fixtures, and the client-side `.jsonl` copy/`accept`/sample button — and `uv run pytest` passes 67 tests today. This plan is therefore written as *verify, then close the real gaps* (G1–G7 in the Current State Audit). The implementer should not rewrite working code; where a gap turns out not to apply, say so explicitly in the final summary rather than making a cosmetic change to look busy.

**Delimiter ambiguity worth flagging to the issue author.** The issue says "concat nested fields and any possible lists with `__`" and also "use `_0` to denote list items". The shipped code resolves this as `NESTED_DELIMITER = "__"` for object keys and `LIST_INDEX_DELIMITER = "_"` for list indices, producing `items_0` and `tags_0__name`. The alternative reading (`items__0`) is a one-character change to `LIST_INDEX_DELIMITER` — which is exactly why both are constants. This plan preserves the shipped `items_0` behavior because existing tests, fixtures, and the constants docstring all assert it; if the author intended `items__0`, flip the constant and update the affected test assertions.

**Known, accepted ambiguity in the flattened namespace.** A literal key `"a__b"` is indistinguishable from nested `{"a": {"b": ...}}`, and a literal key `"items_0"` collides with index 0 of an `items` list. Resolving this properly would require escaping the delimiters, which would make column names uglier for the common case. The de-duplication in `clean_column_names` prevents a hard `to_sql` failure; document the ambiguity in the README subsection rather than engineering around it.

**Why lists are indexed rather than exploded.** Indexing keeps the "one file → one table" contract the issue asks for. The cost is that a file whose lists vary wildly in length produces many sparse columns, and that querying "any item" requires touching several columns. A future enhancement could offer an opt-in child-table mode for list-of-object fields (`events__actions` with a foreign key), which would make list queries far more natural — explicitly out of scope here.

**Column-count ceiling.** SQLite's default `SQLITE_MAX_COLUMN` is 2000. A pathological JSONL file (very long lists, very wide unions) can exceed it. Out of scope for this issue, but if it becomes real, the right fix is a friendly pre-flight error naming the discovered column count rather than surfacing a raw SQLite error.

**Memory profile.** Both passes read the whole file into memory (`content.decode()` plus a `records` list plus a `DataFrame`), so peak usage is several times the file size. Acceptable for the interactive upload sizes this app targets; a streaming/chunked ingest would be the follow-up if large-file uploads become a requirement.

**Type inference is pandas'.** Column types come from `pandas` → `to_sql`, so a field that is an int on one line and a string on another becomes `TEXT`. This matches the existing CSV/JSON behavior and keeps the schema endpoint and insights code path unchanged; no per-column type coercion is added.

**Metadata note.** The slash-command argument parsing shifted the variables (it read `issue_number` as `5c700c17` and `adw_id` as a fragment of the issue JSON). The values in `## Metadata` follow `agents/5c700c17/adw_state.json` and the branch name `feature-issue-1-adw-5c700c17-add-jsonl-file-upload`: issue_number `1`, adw_id `5c700c17`. The filename uses the same convention. Worth fixing in `.claude/commands/feature.md`'s `## Variables` block so `issue_number: $1`, `adw_id: $2`, `issue_json: $3` line up with how `adws/` actually invokes it.
