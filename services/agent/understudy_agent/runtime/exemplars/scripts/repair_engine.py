"""Vetted template: a small, crash-safe program-repair engine (mutation search guided by fault localisation). Runs in the sandbox.

control.json names ONE phase per run:
  {"phase": "diagnose"}                       run every test with line tracing; rank the lines of calc/ by how much more the
                                              failing tests touch them than the passing ones (Ochiai)
  {"phase": "try", "class": "<class>"}        for the top-ranked lines, try the single-token mutations of that class, one at a
                                              time, and keep a mutation only if it strictly lowers the number of failing tests
  {"phase": "final"}                          run everything once more and write result.json

Classes: compare_boundary (< <= > >=), arith_operator (+ - * /), bool_operator (and or), off_by_one (integer literal +1 / -1).
It edits only files under calc/; it never touches tests. State lives in state.json and is written after every change, with a
journal entry (the original text) before a trial, so a run killed half way is rolled back at the next start. After each run it
writes status.json: typed numbers only. input/fault.json {"crash_on_call": k} crashes the k-th call once (failure injection).
"""
import glob
import io
import json
import math
import os
import sys
import tokenize
import unittest

STATE, STATUS = "state.json", "status.json"
CLASSES = {
    "compare_boundary": {"<": ["<="], "<=": ["<"], ">": [">="], ">=": [">"]},
    "arith_operator": {"+": ["-"], "-": ["+"], "*": ["/"], "/": ["*"]},
    "bool_operator": {"and": ["or"], "or": ["and"]},
}
MAX_LINES = 8
sys.dont_write_bytecode = True


def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE))
    return {"calls": 0, "crashed": False, "phase_log": [], "suspects": [], "failing": None, "total": None, "fixes": [],
            "classes_tried": [], "backtracks": 0, "failing_before": None, "pending": None}


def save_state(st):
    tmp = STATE + ".tmp"
    json.dump(st, open(tmp, "w"))
    os.replace(tmp, STATE)


def rollback(st):
    p = st.get("pending")
    if p:
        open(p["file"], "w", encoding="utf-8").write(p["orig"])
        st["pending"] = None
        save_state(st)


def purge():
    for m in list(sys.modules):
        if m == "calc" or m.startswith("calc.") or m == "tests" or m.startswith("tests."):
            del sys.modules[m]


def cases(suite):
    for t in suite:
        if isinstance(t, unittest.TestSuite):
            yield from cases(t)
        else:
            yield t


def run_tests(trace=False):
    """Returns (total, failing_ids, coverage {test id: set((file, line))}). Fresh imports every time."""
    purge()
    sys.path.insert(0, os.getcwd())
    cov = {}
    cur = [None]
    root = os.path.join(os.getcwd(), "calc")

    def tracer(frame, event, arg):
        fn = frame.f_code.co_filename
        if not fn.startswith(root):
            return None
        rel = os.path.relpath(fn)

        def local(fr, ev, ag):
            if ev == "line" and cur[0] is not None:
                cov[cur[0]].add((rel, fr.f_lineno))
            return local
        if cur[0] is not None:
            cov[cur[0]].add((rel, frame.f_lineno))
        return local

    suite = unittest.defaultTestLoader.discover("tests", top_level_dir=os.getcwd())
    failing, total = [], 0
    for case in cases(suite):
        total += 1
        tid = case.id()
        cov[tid] = set()
        res = unittest.TestResult()
        cur[0] = tid
        if trace:
            sys.settrace(tracer)
        try:
            case.run(res)
        finally:
            sys.settrace(None)
            cur[0] = None
        if res.failures or res.errors:
            failing.append(tid)
    sys.path.pop(0)
    return total, failing, cov


def rank_lines(failing, cov, total):
    fset = set(failing)
    pf = len(fset)
    scores = {}
    lines = {l for c in cov.values() for l in c}
    for line in lines:
        ef = sum(1 for t in fset if line in cov.get(t, ()))
        ep = sum(1 for t, c in cov.items() if t not in fset and line in c)
        if ef == 0:
            continue
        scores[line] = ef / math.sqrt(pf * (ef + ep)) if pf else 0.0
    out = [{"file": f, "line": n, "score": round(s, 4)} for (f, n), s in scores.items()]
    return sorted(out, key=lambda d: (-d["score"], d["file"], d["line"]))[:12]


def candidates(text, line_no, cls):
    """Single-token mutations of line `line_no` (1-based): [(start (row, col), end col, new text, old text)]."""
    out = []
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError):
        return out
    for t in toks:
        if t.start[0] != line_no:
            continue
        if cls == "off_by_one":
            if t.type == tokenize.NUMBER and t.string.isdigit():
                n = int(t.string)
                for new in (n + 1, n - 1):
                    if new >= 0:
                        out.append((t.start, t.end[1], str(new), t.string))
        else:
            table = CLASSES[cls]
            if t.string in table and t.type in (tokenize.OP, tokenize.NAME):
                for new in table[t.string]:
                    out.append((t.start, t.end[1], new, t.string))
    return out


def apply(text, cand):
    (row, col), end, new, _ = cand
    lines = text.splitlines(keepends=True)
    lines[row - 1] = lines[row - 1][:col] + new + lines[row - 1][end:]
    return "".join(lines)


def refresh(st):
    total, failing, cov = run_tests(trace=True)
    st["total"], st["failing"] = total, len(failing)
    st["suspects"] = rank_lines(failing, cov, total) if failing else []
    return failing


def write_status(st, **extra):
    sig = {"tests_total": st["total"] or 0, "tests_failing": st["failing"] if st["failing"] is not None else 0,
           "suspects_left": len(st["suspects"]), "classes_tried": len(st["classes_tried"]), "fixes_kept": len(st["fixes"]),
           "backtracks": st["backtracks"], "phases_done": len(st["phase_log"]), **extra}
    json.dump({"signals": sig}, open(STATUS, "w"))


def main():
    st = load_state()
    st["calls"] += 1
    fault = json.load(open("input/fault.json")) if os.path.exists("input/fault.json") else {}
    if fault.get("crash_on_call") == st["calls"] and not st["crashed"]:
        st["crashed"] = True
        save_state(st)
        raise RuntimeError("injected fault")
    rollback(st)
    ctl = json.load(open("control.json"))
    phase = ctl["phase"]
    if phase == "diagnose":
        failing = refresh(st)
        st["failing_before"] = st["failing"] if st["failing_before"] is None else st["failing_before"]
    elif phase == "try":
        cls = ctl["class"]
        if st["failing"] is None:
            refresh(st)
        for sus in list(st["suspects"])[:MAX_LINES]:
            if st["failing"] == 0:
                break
            path = sus["file"]
            if not path.startswith("calc" + os.sep) and not path.startswith("calc/"):
                continue
            orig = open(path, encoding="utf-8").read()
            for cand in candidates(orig, sus["line"], cls):
                new_text = apply(orig, cand)
                try:
                    compile(new_text, path, "exec")
                except SyntaxError:
                    continue
                st["pending"] = {"file": path, "orig": orig}
                save_state(st)
                open(path, "w", encoding="utf-8").write(new_text)
                total, failing, _ = run_tests()
                if len(failing) < st["failing"]:
                    st["fixes"].append({"file": path, "line": sus["line"], "class": cls, "from": cand[3], "to": cand[2]})
                    st["failing"] = len(failing)
                    st["pending"] = None
                    save_state(st)
                    orig = new_text
                    break
                open(path, "w", encoding="utf-8").write(orig)
                st["backtracks"] += 1
                st["pending"] = None
                save_state(st)
        st["classes_tried"].append(cls)
        refresh(st)
    elif phase == "final":
        refresh(st)
        os.makedirs("out", exist_ok=True)
        result = {"tests_total": st["total"], "failing_before": st["failing_before"] or 0, "failing_after": st["failing"],
                  "fixes": st["fixes"][:12], "classes_tried": st["classes_tried"], "backtracks": st["backtracks"]}
        json.dump(result, open("result.json", "w"))
        json.dump(result, open("out/repair_notes.json", "w"), indent=1)
    else:
        raise SystemExit("unknown phase")
    st["phase_log"].append(phase + (":" + ctl.get("class", "") if ctl.get("class") else ""))
    save_state(st)
    write_status(st)
    print("phase", phase, "failing", st["failing"])


main()
