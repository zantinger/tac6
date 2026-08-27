# E2E Test: JSONL File Upload

Test JSONL file upload and flattened-column querying in the Natural Language SQL Interface application.

## User Story

As a data analyst working with log, event, and API-export files
I want to upload `.jsonl` files and have their nested fields and lists become queryable columns
So that I can ask natural-language questions about JSONL data without first converting it to CSV

## Test Steps

1. Navigate to the `Application URL`
2. Take a screenshot of the initial state
3. **Verify** the page title is "Natural Language SQL Interface"

4. Click the "Upload Data" button
5. **Verify** the upload modal is visible
6. **Verify** the drop zone text mentions `.jsonl` (expected: "Drag and drop .csv, .json, or .jsonl files here")
7. **Verify** a hint explaining flattened column naming is visible (mentions `user__name` and `items_0`)
8. Take a screenshot of the upload modal

9. Click the "Event Analytics" sample button (serves `public/sample-data/events.jsonl`)
10. **Verify** the success message reads `Table "events" created successfully with 10 rows!`
11. Take a screenshot of the success message

12. **Verify** the Available Tables section lists the `events` table
13. **Verify** the `events` table shows flattened columns, including:
    - at least one nested column named `user__name`
    - at least one list-indexed column named `action__items_0__name`
14. Take a screenshot of the table schema

15. Enter the query: "Show the event id and user name for every event"
16. Click the Query button
17. **Verify** the query results appear
18. **Verify** the generated SQL references a flattened column containing `user__name`
19. **Verify** the results table renders 10 rows
20. Take a screenshot of the results
21. Click "Hide" button to close results

## Success Criteria
- `.jsonl` is advertised in the upload modal drop-zone text
- The flattened column-naming hint is shown in the modal
- The JSONL upload creates exactly one table named `events` with 10 rows
- Nested columns use the `__` delimiter (`user__name`) and list items use the index delimiter (`action__items_0__name`)
- A natural-language query against a flattened column returns 10 rows
- No console errors or UI error messages appear
- 5 screenshots are taken
