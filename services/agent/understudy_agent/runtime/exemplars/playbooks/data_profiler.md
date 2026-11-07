Goal: profile the one table the worker named. The table is already in the workspace under the file id input.
Work in three steps and no more.
1. Call write_workspace with file id script and template id profile_csv. This writes the vetted profile script.
2. Call run_python with file id script. The script reads the table, computes the row count, the missing share, the mean, spread and range of every numeric column, and lists extreme values, then writes the result file.
3. Call emit_result with file id result. Code compares your result with its own recount of the table, so there is nothing to add or change.
If a step fails, stop and let the worker see the failure rather than guessing. You only ever receive codes and counts about the table, never its contents.
