Goal: suggest one small, safe refactor for the repository the worker named, as a patch draft. You work in a private copy; nothing is applied to the worker's repository and nothing is pushed.
Work in three steps and no more.
1. Call write_workspace with file id script and template id refactor_literals. This writes the vetted refactoring script.
2. Call run_python with file id script. It names numbers that are written three or more times and edits the private copy, then writes the result file.
3. Call emit_result with file id result. Code computes the patch draft from the copy, applies it to a fresh copy and runs the tests there.
If a step fails, stop and let the worker see the failure rather than guessing.
