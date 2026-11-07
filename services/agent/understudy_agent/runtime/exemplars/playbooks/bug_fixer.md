Goal: make the failing tests of the repository the worker named succeed by repairing the code, never the tests. You work in a private copy and the result is a patch draft; nothing is applied or pushed. This is a long task of about fourteen steps, so keep to the order below and read the counts you receive.
The repair engine is a vetted script. It runs one phase per run, named in the control file. After every run you receive typed counts: tests total, tests failing, suspect lines left, classes tried, fixes kept and backtracks.
Order of work:
1. Call write_workspace with file id script and template id repair_engine. Do this once.
2. Diagnose: call write_workspace with file id control and template id ctl_diagnose, then run_python with file id script.
3. Repair: for each repair class in turn, call write_workspace with file id control and the template id for that class (ctl_compare_boundary, ctl_bool_operator, ctl_arith_operator, ctl_off_by_one), then run_python with file id script. After each run read the failing count: when it reaches zero, stop trying classes. A class that fixes nothing is rolled back by the engine; that is normal, move to the next class.
4. Finish: write_workspace with file id control and template id ctl_final, run_python with file id script, then emit_result with file id result.
If a run fails because the script crashed, run it again without changing the control file: the engine resumes from its saved state. Never invent ids; use only the ids in the menus.
