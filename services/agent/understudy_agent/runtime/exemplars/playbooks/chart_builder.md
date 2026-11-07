Goal: draw one bar chart of the table the worker named. The table is already in the workspace under the file id input.
Work in three steps and no more.
1. Call write_workspace with file id script and template id chart_csv. This writes the vetted chart script.
2. Call run_python with file id script. The script picks the category column and the value column, sums the values per category, saves the picture and writes the result file.
3. Call emit_result with file id result. Code checks the picture and recounts every bar from the table.
If a step fails, stop and let the worker see the failure rather than guessing. You only ever receive codes and counts about the table, never its contents.
