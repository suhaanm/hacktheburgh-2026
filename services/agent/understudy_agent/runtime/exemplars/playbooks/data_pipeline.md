Goal: clean, join and total a larger table of order lines for the worker, and check the total against the ledger before trusting it. This is a long task of about twenty steps, so keep to the order below and read the counts you receive.
The pipeline engine is a vetted script. It runs one phase per run, named in the control file. After every run you receive typed counts, for example rows in, duplicate lines found, lines priced in pence, quantity outliers found, rows out, the gap to the ledger and whether it reconciled.
Order of work:
1. Call write_workspace with file id script and template id pipeline_engine. Do this once.
2. Profile: call write_workspace with file id control and template id ctl_profile, then run_python with file id script.
3. Clean, only the problems the profile counted: ctl_dedupe when duplicate lines were found, ctl_units when lines priced in pence were found, ctl_outliers when quantity outliers were found. Each is write_workspace with file id control and that template id, then run_python with file id script.
4. Then in this order: ctl_join, ctl_aggregate, ctl_chart, ctl_reconcile, each the same two calls.
5. Read the reconcile counts. The total may be trusted only when it reconciled. Then ctl_final and emit_result with file id result.
If a run fails because the script crashed, run it again without changing the control file: the engine resumes from its saved state. Never invent ids; use only the ids in the menus.
