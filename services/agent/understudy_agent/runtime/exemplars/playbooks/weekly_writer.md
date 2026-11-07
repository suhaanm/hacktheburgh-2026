Goal: draft a short weekly write-up from the digest records the worker supplied. The records are already in the workspace under the file id input. They hold fixed categories and sizes and an id each.
Work in three steps and no more.
1. Call write_workspace with file id script and template id weekly_summary. This writes the vetted drafting script.
2. Call run_python with file id script. It groups the records by category and writes a draft that cites record ids only, then writes the result file.
3. Call emit_result with file id result. Code checks that every id in the draft is one of the supplied ids and that every count is right.
If a step fails, stop and let the worker see the failure rather than guessing.
