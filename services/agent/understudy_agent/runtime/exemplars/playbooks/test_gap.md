Goal: find source files that keep changing without a test, in the repository the worker named. The history is read by code, so you only ever receive counts.
Work in four steps and no more.
1. Call git_log with file id gitlog. Code reads the history and saves a structured copy in the workspace.
2. Call write_workspace with file id script and template id test_gap. This writes the vetted gap finder.
3. Call run_python with file id script. It lists files changed at least three times in commits that touched no test, then writes the result file.
4. Call emit_result with file id result. Code recounts the history itself and compares.
If a step fails, stop and let the worker see the failure rather than guessing.
