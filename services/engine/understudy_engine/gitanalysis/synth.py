"""Synthetic git repositories with PLANTED habits and a truth file (GIT-1, evaluation of the git layer).

``make_repo(spec, dest) -> Path`` writes a REAL git repository (``git init`` plus a ``git fast-import`` stream with
controlled author and committer dates, then a checkout so the working tree exists) and a ``truth.json`` beside it:

    dest/repo/          the repository (working tree checked out, ``git log`` and ``git fsck`` work)
    dest/truth.json     what was planted and what was realised; per-commit labels (never read by the analysis code)

Nobody is real. Authors, customers and messages are scripted; file contents are filler (valid one-line Python
assignments) because only history, sizes, paths and timing matter to the analysis. A habit is planted by changing one rate
of the generator; everything else is drawn from the same baseline for learners and experts, with a little per-person
jitter, so "no habit" is a fair negative and not a different distribution.

Habits (rates; the first value is the expert baseline, the second the planted value at ``strength=1``):

    big_commits         P(a commit is giant: 450 to 2500 lines, 6 to 18 files)             0.03 -> 0.30
    tests_with_changes  P(a feature or fix commit also changes a test file)                0.78 -> 0.12
    fix_after_fix       P(a fix is followed by another fix 4 to 40 minutes later), chained 0.06 -> 0.55
    reverts             P(a feature or fix commit is reverted 10 to 180 minutes later)     0.012 -> 0.12
    vague_messages      P(a message is "wip", "stuff", "update" and the like)              0.04 -> 0.55
    late_night          P(an active day is followed by a 3 to 6 commit burst, 00:15-04:40) 0.025 -> 0.30

Canary variant (``spec.canary=True``): the same history and the same numbers, but names, emails, customer names, ticket
numbers and some file paths carry unique tokens (listed in ``truth["canaries"]``) so leak tests can search outbound
payloads, logs and responses for them. Structure is drawn from a separate random stream, so a canary repo and a plain repo
with the same seed have identical commit times, sizes and test-touch pattern.

Stable API for other tracks: ``RepoSpec``, ``make_repo``, ``make_cohort``, ``learner_specs``, ``expert_specs``.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import shutil
import subprocess
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .vocab import size_bucket

GENERATOR = "git-synth-2"

HABIT_IDS = ("big_commits", "tests_with_changes", "fix_after_fix", "reverts", "vague_messages", "late_night")
BASELINE = {"big_commits": 0.03, "tests_with_changes": 0.78, "fix_after_fix": 0.06, "reverts": 0.012, "vague_messages": 0.04, "late_night": 0.025}
PLANTED = {"big_commits": 0.30, "tests_with_changes": 0.12, "fix_after_fix": 0.55, "reverts": 0.12, "vague_messages": 0.55, "late_night": 0.30}

KIND_WEIGHTS = (("feature", 0.46), ("fix", 0.22), ("refactor", 0.08), ("test", 0.06), ("docs", 0.07), ("chore", 0.11))

MODULES = ["billing", "auth", "parser", "scheduler", "exporter", "search", "cache", "notifier", "importer", "reports", "settings", "api"]
SUBS = ["core", "utils", "models", "views", "handlers", "helpers", "schema", "client"]
THINGS = ["retry logic", "pagination", "csv export", "rate limiting", "audit trail", "user filters", "timezone handling", "bulk import",
          "email templates", "search ranking", "session timeout", "webhook support", "date parsing", "permission checks"]
BUGS = ["off-by-one in pagination", "null handling on empty input", "race in cache refresh", "wrong rounding in totals",
        "duplicate rows on import", "timezone drift in schedules", "crash on empty file", "missing validation for email field"]
DEPS = ["pytest", "requests", "pydantic", "numpy", "httpx", "ruff"]
VAGUE = ["update", "wip", "fix stuff", "changes", "misc", "more work", "asdf", "fixes", ".", "tmp", "stuff", "fix", "ok now", "final",
         "stuff and things", "updated code", "small changes", "it works"]
VAGUE_HARD = ["Another attempt at it", "Trying something else", "One more time please", "Hopefully this works", "Round two of the thing"]
CHAIN_FIX = ["Fix typo from previous change", "Fix test broken by last commit", "Fix lint failure", "Fix missing import", "Fix again after review"]

FEATURE_MSG = ["Add {thing} to {mod}", "Implement {thing} for {mod}", "Support {thing} in {mod}", "Add {thing} handling to {mod}"]
FEATURE_PARA = ["Make {mod} handle {thing}", "Get {thing} working in {mod}", "Teach {mod} about {thing}", "{Mod}: first cut of {thing}"]
FIX_MSG = ["Fix {bug} in {mod}", "Resolve {bug}", "Fix {bug}", "Patch {bug} in {mod}"]
FIX_PARA = ["Correct {bug} in {mod}", "Stop {mod} choking on {thing}", "Squash {bug}", "Handle {bug} in {mod}"]
REFACTOR_MSG = ["Refactor {mod} {sub} module", "Extract {thing} helper from {mod}", "Rename {sub} functions in {mod}", "Clean up {mod} {sub}"]
REFACTOR_PARA = ["Split {mod} into smaller pieces", "Move {thing} out of {mod}", "Untangle {mod} imports"]
TEST_MSG = ["Add tests for {mod} {thing}", "Cover {thing} edge cases in {mod}", "More checks for {mod} {sub}"]
DOCS_MSG = ["Document {thing} in {mod}", "Update README for {thing}", "Explain {thing} in the docs"]
CHORE_MSG = ["Bump {dep} to {ver}", "Update CI cache key", "Pin {dep} version", "Tidy Makefile targets"]

FIRST = ["Marisol", "Tobias", "Ananya", "Callum", "Ingrid", "Rafael", "Wen", "Seren", "Dmitri", "Aisha", "Joaquin", "Freya"]
LAST = ["Okonkwo", "Lindqvist", "Raman", "Fairbairn", "Haddad", "Whitcombe", "Zhao", "Penhale", "Kowalczyk", "Adeyemi", "Moreau", "Strand"]
CUSTOMER_STEM = ["Halvorsen", "Brimstone", "Northgate", "Quillan", "Ashworth", "Delacroix", "Penrose", "Kestrel"]
CUSTOMER_KIND = ["Logistics", "Capital", "Holdings", "Foods", "Energy", "Partners"]


# --------------------------------------------------------------------------------------------- specs
@dataclass
class RepoSpec:
    person: str
    level: str = "expert"                 # "learner" | "expert" (a label for the truth file)
    seed: int = 0
    days: int = 42
    start: str = "2026-09-07"             # a Monday
    planted: tuple[str, ...] = ()         # habit ids from HABIT_IDS
    strength: float = 1.0                 # 0 = baseline, 1 = fully planted (dose-response experiments use 0.25, 0.5)
    canary: bool = False
    tz_min: int = 0                       # the author's UTC offset in minutes
    commits_per_day: float = 3.4
    jitter: float = 1.0                   # scales the between-person spread of the baseline rates (stress experiments use 2.0)
    author_name: str | None = None
    author_email: str | None = None

    def __post_init__(self) -> None:
        bad = [h for h in self.planted if h not in HABIT_IDS]
        if bad:
            raise ValueError(f"unknown habit ids: {bad}; known: {HABIT_IDS}")
        self.planted = tuple(self.planted)


LEARNER_PLAN = (
    ("p_git_learner_1", ("big_commits", "tests_with_changes"), 0),
    ("p_git_learner_2", ("fix_after_fix", "reverts"), 60),
    ("p_git_learner_3", ("late_night", "vague_messages"), -300),
    ("p_git_learner_4", HABIT_IDS, 330),
)
EXPERT_TZ = (0, 0, 60, 60, -300, -480, 120, 330)


def learner_specs(replicate: int = 0, *, canary: bool = False, strength: float = 1.0, days: int = 42, jitter: float = 1.0) -> list[RepoSpec]:
    return [RepoSpec(person=f"{p}" if replicate == 0 else f"{p}_r{replicate}", level="learner", seed=1000 * replicate + i + 1, days=days,
                     planted=planted, strength=strength, canary=canary, tz_min=tz, jitter=jitter)
            for i, (p, planted, tz) in enumerate(LEARNER_PLAN)]


def expert_specs(replicate: int = 0, *, canary: bool = False, days: int = 42, jitter: float = 1.0) -> list[RepoSpec]:
    return [RepoSpec(person=f"p_git_expert_{i + 1}" if replicate == 0 else f"p_git_expert_{i + 1}_r{replicate}", level="expert",
                     seed=1000 * replicate + 100 + i + 1, days=days, planted=(), canary=canary, tz_min=EXPERT_TZ[i % len(EXPERT_TZ)],
                     commits_per_day=2.8 + 0.25 * (i % 5), jitter=jitter)
            for i in range(8)]


# --------------------------------------------------------------------------------------------- canaries
def canary_tokens(spec: RepoSpec) -> dict:
    """Deterministic unique tokens for one repo. ``marker`` is a substring of every token."""
    h = hashlib.sha256(f"{spec.person}:{spec.seed}:canary".encode()).hexdigest()
    marker = "zq" + h[:6]
    r = random.Random(h)
    first, last = r.choice(FIRST), r.choice(LAST)
    customers = [f"{r.choice(CUSTOMER_STEM)}-{marker} {r.choice(CUSTOMER_KIND)}", f"{r.choice(CUSTOMER_STEM)}-{marker}{h[6]} {r.choice(CUSTOMER_KIND)}"]
    return {
        "marker": marker,
        "author_name": f"{first} {last}-{marker}",
        "author_email": f"{first.lower()}.{last.lower()}.{marker}@canary-mail.example",
        "customers": customers,
        "path_stem": f"customer_{marker}",
        "ticket": f"INC-{marker.upper()}",
    }


def canary_list(tok: dict) -> list[str]:
    return [tok["marker"], tok["author_name"], tok["author_email"], *tok["customers"], tok["path_stem"], tok["ticket"]]


# --------------------------------------------------------------------------------------------- simulation
@dataclass
class _Ev:
    local_min: float                  # minutes since local midnight of the start date
    kind: str                         # feature | fix | refactor | test | docs | chore | revert
    giant: bool = False
    with_tests: bool = False
    vague: bool = False
    chain: bool = False               # a follow-up fix
    target: int | None = None         # for reverts: the id of the reverted event
    id: int = 0
    late: bool = False


@dataclass
class _Commit:
    mark: int
    ts: int
    author: str
    message: str
    files: dict[str, str]             # path -> full new content
    kind: str
    realised: dict
    email: str | None = None          # None: the stream's default


def _poisson(r: random.Random, lam: float) -> int:
    lim, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= r.random()
        if p <= lim:
            return k
        k += 1


def _lerp(a: float, b: float, s: float) -> float:
    return a + (b - a) * max(0.0, min(1.0, s))


class _Sim:
    def __init__(self, spec: RepoSpec) -> None:
        self.spec = spec
        self.r = random.Random(spec.seed * 7919 + 13)         # structure
        self.c = random.Random(spec.seed * 104729 + 7)        # canary choices and message paraphrase (never affects structure)
        self.tok = canary_tokens(spec) if spec.canary else None
        self.rates = self._rates()
        self.counter = 0
        self.changelog: dict[int, dict[str, tuple[list[str], list[str]]]] = {}
        self.subjects: dict[int, str] = {}
        self.canary_pair = (MODULES[spec.seed % len(MODULES)], SUBS[spec.seed % len(SUBS)])
        self._next_id = 0
        self.files = {"README.md": ["# Project"], "pyproject.toml": ["[project]", 'name = "demo"'], "src/__init__.py": [],
                      "tests/__init__.py": [], ".github/workflows/ci.yml": ["name: ci", "on: [push]"]}

    # -------------------------------------------------------------- rates
    def _rates(self) -> dict[str, float]:
        rr = random.Random(self.spec.seed * 31 + 5)
        out = {}
        for h in HABIT_IDS:
            if h in self.spec.planted:
                v = _lerp(BASELINE[h], PLANTED[h], self.spec.strength) * rr.uniform(0.9, 1.1)
            elif h == "tests_with_changes":
                v = BASELINE[h] + rr.gauss(0, 0.07 * self.spec.jitter)       # a high rate: additive jitter (a multiplicative one runs past 1)
            else:
                v = BASELINE[h] * rr.lognormvariate(0, 0.25 * self.spec.jitter)
            out[h] = min(0.97, max(0.0, v))
        return out

    # -------------------------------------------------------------- phase 1: schedule
    def _new(self, evs: list[_Ev], t: float, kind: str, **kw) -> _Ev:
        self._next_id += 1
        ev = _Ev(local_min=t, kind=kind, id=self._next_id, **kw)
        evs.append(ev)
        return ev

    def schedule(self) -> list[_Ev]:
        r, rates, spec = self.r, self.rates, self.spec
        evs: list[_Ev] = []
        d0 = date.fromisoformat(spec.start)
        for d in range(spec.days):
            day = d0 + timedelta(days=d)
            if r.random() > (0.9 if day.weekday() < 5 else 0.3):
                continue
            base = d * 1440.0
            n = max(1, _poisson(r, spec.commits_per_day))
            t = base + min(14 * 60, max(7 * 60, r.gauss(9.5 * 60, 50)))
            for k in range(n):
                if k:
                    t += max(6.0, r.lognormvariate(math.log(70), 0.6))
                if t > base + 22.5 * 60:
                    break
                self._emit(evs, t, self._kind())
            if r.random() < rates["late_night"]:
                tt = base + 1440 + 15 + r.uniform(0, 20)
                for _ in range(r.randint(3, 6)):
                    if tt > base + 1440 + 4 * 60 + 40:
                        break
                    self._emit(evs, tt, r.choice(("feature", "fix", "feature")), late=True)
                    tt += r.uniform(5, 35)
        evs.sort(key=lambda e: (e.local_min, e.id))
        return evs

    def _kind(self) -> str:
        x, acc = self.r.random(), 0.0
        for k, w in KIND_WEIGHTS:
            acc += w
            if x < acc:
                return k
        return "feature"

    def _emit(self, evs: list[_Ev], t: float, kind: str, late: bool = False, chain: bool = False) -> _Ev:
        r, rates = self.r, self.rates
        ev = self._new(evs, t, kind, late=late, chain=chain)
        ev.giant = kind in ("feature", "refactor", "fix") and not chain and r.random() < rates["big_commits"]
        ev.with_tests = kind in ("feature", "fix") and r.random() < rates["tests_with_changes"] * (1.0 if kind == "feature" else 0.85)
        ev.vague = kind != "test" and r.random() < rates["vague_messages"]
        if kind == "feature" and r.random() < 0.5 * rates["fix_after_fix"]:
            self._emit(evs, t + r.uniform(4, 40), "fix", chain=True)         # the feature broke something; the fix may chain on
        if kind == "fix":
            t2, cnt = t, 0
            while cnt < 4 and r.random() < rates["fix_after_fix"]:
                t2 += r.uniform(4, 40)
                f = self._new(evs, t2, "fix", chain=True)
                f.with_tests = r.random() < rates["tests_with_changes"] * 0.85
                f.vague = r.random() < rates["vague_messages"]
                cnt += 1
        if kind in ("feature", "fix") and r.random() < rates["reverts"]:
            self._new(evs, t + r.uniform(10, 180), "revert", target=ev.id)
        return ev

    # -------------------------------------------------------------- phase 2: materialise
    def _line(self, kind: str) -> str:
        self.counter += 1
        n = self.counter
        if kind == "test":
            return f"CHECK_{n:06d} = ({n % 97} + {n % 13} == {n % 97 + n % 13})"
        if kind == "docs":
            return f"- note {n:06d}: describes behaviour {n % 31}"
        return f"VALUE_{n:06d} = {n % 1009}"

    def _path(self, mod: str, sub: str, test: bool = False) -> str:
        if (mod, sub) == self.canary_pair and self.tok:
            return f"tests/customers/test_{self.tok['path_stem']}.py" if test else f"src/customers/{self.tok['path_stem']}.py"
        return f"tests/{mod}/test_{sub}.py" if test else f"src/{mod}/{sub}.py"

    def _touch(self, path: str, add: int, dele: int, ev_id: int, kind: str = "src") -> tuple[int, int]:
        lines = self.files.setdefault(path, [])
        removed: list[str] = []
        for _ in range(min(dele, max(0, len(lines) - 1))):
            removed.append(lines.pop(self.r.randrange(len(lines))))
        added = [self._line(kind) for _ in range(add)]
        for ln in added:
            lines.insert(self.r.randint(0, len(lines)), ln)
        self.changelog.setdefault(ev_id, {})[path] = (added, removed)
        return len(added), len(removed)

    def _pairs(self, k: int) -> list[tuple[str, str]]:
        r = self.r
        out: list[tuple[str, str]] = []
        while len(out) < k:
            p = (r.choice(MODULES), r.choice(SUBS))
            if p not in out:
                out.append(p)
        return out

    def _sizes(self, ev: _Ev) -> tuple[int, int]:
        r = self.r
        if ev.giant:
            return int(min(2500, max(450, r.lognormvariate(math.log(700), 0.35)))), r.randint(6, 18)
        med = {"feature": 35, "fix": 8, "refactor": 30, "test": 25, "docs": 12, "chore": 6}[ev.kind]
        hi = {"feature": 180, "fix": 60, "refactor": 120, "test": 100, "docs": 60, "chore": 30}[ev.kind]
        lines = int(min(hi, max(2, r.lognormvariate(math.log(med), 0.8))))
        k = 1 if lines < 12 else min(3, 1 + lines // 40 + (r.random() < 0.3))
        return lines, int(k)

    def _subject(self, ev: _Ev, target_subject: str | None) -> tuple[str, str]:
        """(subject, intended message quality). Canary substitutions never change the words the digest looks at."""
        c = self.c
        mod, sub, thing = c.choice(MODULES), c.choice(SUBS), c.choice(THINGS)
        bug, dep, ver = c.choice(BUGS), c.choice(DEPS), f"{c.randint(1, 9)}.{c.randint(0, 9)}"
        fmt = dict(mod=mod, Mod=mod.capitalize(), sub=sub, thing=thing, bug=bug, dep=dep, ver=ver)
        if ev.kind == "revert":
            return f'Revert "{target_subject or "earlier change"}"', "good"
        if ev.vague:
            pool = VAGUE_HARD if c.random() < 0.15 else VAGUE
            return c.choice(pool), "vague"
        if ev.kind == "fix" and ev.chain:
            return c.choice(CHAIN_FIX), "good"
        paraphrase = c.random() < 0.2
        table = {
            "feature": FEATURE_PARA if paraphrase else FEATURE_MSG, "fix": FIX_PARA if paraphrase else FIX_MSG,
            "refactor": REFACTOR_PARA if paraphrase else REFACTOR_MSG, "test": TEST_MSG, "docs": DOCS_MSG, "chore": CHORE_MSG,
        }[ev.kind]
        subject = c.choice(table).format(**fmt)
        use_customer, cust = c.random() < 0.4, c.randrange(2)       # always drawn, so canary and plain repos stay in step
        if self.tok and use_customer and ev.kind in ("feature", "fix"):
            subject = f"{subject.split(' in ')[0].split(' to ')[0].split(' for ')[0]} for {self.tok['customers'][cust]}"
        return subject, "good"

    def _body(self) -> str:
        roll, cust = self.c.random(), self.c.randrange(2)
        if not self.tok or roll > 0.35:
            return ""
        t = self.tok
        return f"Reported by {t['author_name']} <{t['author_email']}> ({t['ticket']}) for {t['customers'][cust]}."

    def materialise(self, evs: list[_Ev], author: str) -> list[_Commit]:
        spec = self.spec
        epoch0 = (date.fromisoformat(spec.start) - date(1970, 1, 1)).days * 86400
        commits: list[_Commit] = []
        subj_by_ev: dict[int, str] = {}
        # initial commit, the day before the first scheduled day
        init_ts = epoch0 - 86400 + 10 * 3600 - spec.tz_min * 60
        init_files = {p: ("\n".join(v) + "\n" if v else "") for p, v in self.files.items()}
        commits.append(_Commit(1, init_ts, author, "Initial project skeleton with CI config\n", init_files, "chore",
                               {"added": 5, "deleted": 0, "n_files": 5, "touches_tests": True, "lines": 5, "message_quality": "good"}))
        mark = 2
        for ev in evs:
            ts = int(epoch0 + ev.local_min * 60 - spec.tz_min * 60)
            changes: dict[str, list[str]] = {}
            added = deleted = 0
            if ev.kind == "revert":
                tgt_log = self.changelog.get(ev.target, {})
                for path, (adds, dels) in tgt_log.items():
                    cur = self.files.setdefault(path, [])
                    for ln in adds:
                        if ln in cur:
                            cur.remove(ln)
                            deleted += 1
                    for ln in dels:
                        cur.insert(self.r.randint(0, len(cur)), ln)
                        added += 1
                    changes[path] = cur
                if added + deleted == 0:        # everything already changed again: revert one trailing line
                    path = next(iter(tgt_log), "src/api/core.py")
                    self._touch(path, 1, 1, ev.id)
                    added, deleted = 1, 1
                    changes[path] = self.files[path]
                self.changelog[ev.id] = {}
                subject, quality = self._subject(ev, subj_by_ev.get(ev.target))
                body = ""
                self._body()                                  # keep the canary stream in step
            else:
                lines, k = self._sizes(ev)
                if ev.kind == "test":
                    pairs = self._pairs(min(k, 3))
                    per = max(1, lines // len(pairs))
                    for mod, sub in pairs:
                        p = self._path(mod, sub, test=True)
                        a, d = self._touch(p, per, int(per * self.r.uniform(0.0, 0.2)), ev.id, "test")
                        added, deleted = added + a, deleted + d
                        changes[p] = self.files[p]
                elif ev.kind == "docs":
                    p = "README.md" if self.r.random() < 0.5 else f"docs/{self.r.choice(MODULES)}.md"
                    a, d = self._touch(p, lines, int(lines * 0.2), ev.id, "docs")
                    added, deleted = added + a, deleted + d
                    changes[p] = self.files[p]
                elif ev.kind == "chore":
                    p = self.r.choice(["pyproject.toml", ".github/workflows/ci.yml", "Makefile"])
                    a, d = self._touch(p, lines, int(lines * 0.3), ev.id, "docs")
                    added, deleted = added + a, deleted + d
                    changes[p] = self.files[p]
                else:
                    pairs = self._pairs(k)
                    per = max(1, lines // len(pairs))
                    churn = 0.5 if ev.kind == "refactor" else 0.2
                    for mod, sub in pairs:
                        p = self._path(mod, sub)
                        a, d = self._touch(p, per, int(per * self.r.uniform(0.0, churn * 2)), ev.id)
                        added, deleted = added + a, deleted + d
                        changes[p] = self.files[p]
                    if ev.with_tests:
                        for mod, sub in pairs[:2]:
                            p = self._path(mod, sub, test=True)
                            a, d = self._touch(p, max(2, per // 3), 0, ev.id, "test")
                            added, deleted = added + a, deleted + d
                            changes[p] = self.files[p]
                subject, quality = self._subject(ev, None)
                body = self._body()
            subj_by_ev[ev.id] = subject
            msg = subject + ("\n\n" + body if body else "") + "\n"
            touches = any(p.startswith("tests/") for p in changes)
            files = {p: "\n".join(v) + "\n" if v else "" for p, v in ((p, self.files.get(p, [])) for p in changes)}
            commits.append(_Commit(mark, ts, author, msg, files, ev.kind,
                                   {"added": added, "deleted": deleted, "n_files": len(changes), "touches_tests": touches,
                                    "lines": added + deleted, "message_quality": quality, "chain": ev.chain, "giant": ev.giant,
                                    "late": ev.late}))
            mark += 1
        return commits


def _fix_targets(evs: list[_Ev]) -> None:
    """Renumber ids to dense integers and rewrite revert targets accordingly."""
    remap = {e.id: i for i, e in enumerate(evs)}
    for i, e in enumerate(evs):
        if e.target is not None:
            e.target = remap.get(e.target)
    for i, e in enumerate(evs):
        e.id = i


# --------------------------------------------------------------------------------------------- git plumbing
def _git_env(home: Path) -> dict[str, str]:
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(home), "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_TERMINAL_PROMPT": "0"}


def _run(args: list[str], cwd: Path, env: dict, input_bytes: bytes | None = None) -> bytes:
    p = subprocess.run(args, cwd=str(cwd), env=env, input=input_bytes, capture_output=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[1:3])} failed (exit {p.returncode}): {p.stderr.decode('utf-8', 'replace')[:200]}")
    return p.stdout


def _stream(commits: list[_Commit], tz_min: int, author: str, email: str) -> bytes:
    sign = "-" if tz_min < 0 else "+"
    tz = f"{sign}{abs(tz_min) // 60:02d}{abs(tz_min) % 60:02d}"
    out = bytearray()
    for c in commits:
        msg = c.message.encode("utf-8")
        ident = f"{c.author or author} <{c.email or email}> {c.ts} {tz}".encode()
        out += b"commit refs/heads/main\nmark :%d\nauthor %s\ncommitter %s\ndata %d\n" % (c.mark, ident, ident, len(msg))
        out += msg + b"\n"
        for path, content in c.files.items():
            body = content.encode("utf-8")
            out += b"M 100644 inline %s\ndata %d\n%s\n" % (path.encode("utf-8"), len(body), body)
        out += b"\n"
    return bytes(out)


def make_repo(spec: RepoSpec, dest: str | os.PathLike) -> Path:
    """Create the repository for ``spec`` under ``dest`` and return the repository path (``dest/repo``).

    ``dest/truth.json`` is written beside it. Deterministic: the same spec gives the same commit ids. Takes a few tens of
    milliseconds for a 6-week history."""
    dest = Path(dest)
    repo = dest / "repo"
    if repo.exists() and any(repo.iterdir()):
        raise FileExistsError(f"{repo} already exists and is not empty")
    dest.mkdir(parents=True, exist_ok=True)
    repo.mkdir(parents=True, exist_ok=True)

    sim = _Sim(spec)
    tok = sim.tok
    author = (tok["author_name"] if tok else spec.author_name) or spec.person
    email = (tok["author_email"] if tok else spec.author_email) or f"{spec.person}@example.test"
    evs = sim.schedule()
    _fix_targets(evs)
    commits = sim.materialise(evs, author)

    env = _git_env(dest)
    _run(["git", "init", "-q", "--template=", "-b", "main", str(repo)], dest, env)
    marks = dest / ".marks"
    _run(["git", "fast-import", "--quiet", f"--export-marks={marks}"], repo, env, _stream(commits, spec.tz_min, author, email))
    _run(["git", "reset", "-q", "--hard", "main"], repo, env)
    sha_by_mark = {int(ln.split()[0][1:]): ln.split()[1] for ln in marks.read_text().splitlines() if ln.strip()}
    marks.unlink()

    truth_commits = []
    for c in commits:
        lines = c.realised["lines"]
        truth_commits.append({
            "sha": sha_by_mark[c.mark], "t": c.ts, "category": c.kind, "size_bucket": size_bucket(lines), "lines": lines,
            "n_files": c.realised["n_files"], "touches_tests": bool(c.realised["touches_tests"]),
            "message_quality": c.realised.get("message_quality", "good"),
        })
    n = len(commits)
    fixes = [c for c in commits if c.kind == "fix"]
    realised = {
        "n_commits": n,
        "big_commits": sum(1 for t in truth_commits if t["size_bucket"] in ("large", "huge")),
        "reverts": sum(1 for c in commits if c.kind == "revert"),
        "vague_messages": sum(1 for t in truth_commits if t["message_quality"] != "good"),
        "fix_commits": len(fixes),
        "code_commits": sum(1 for c in commits if c.kind in ("feature", "fix")),
        "code_with_tests": sum(1 for c in commits if c.kind in ("feature", "fix") and c.realised["touches_tests"]),
        "late_night_commits": sum(1 for c in commits if 0 <= ((c.ts + spec.tz_min * 60) % 86400) // 3600 < 5),
    }
    truth = {
        "generator": GENERATOR, "person": spec.person, "level": spec.level, "seed": spec.seed, "days": spec.days,
        "start": spec.start, "tz_min": spec.tz_min, "planted": list(spec.planted), "strength": spec.strength, "jitter": spec.jitter,
        "rates": {h: round(v, 4) for h, v in sim.rates.items()}, "baseline": BASELINE, "planted_full": PLANTED,
        "canary": bool(tok), "canaries": canary_list(tok) if tok else [], "realised": realised,
        "note": "scripted developer; nobody is real; file contents are filler",
        "commits": truth_commits,
    }
    (dest / "truth.json").write_text(json.dumps(truth, indent=1), encoding="utf-8")
    return repo


def repo_from_commits(commits: list[dict], dest: str | os.PathLike, *, start: str = "2026-09-07", tz_min: int = 0) -> Path:
    """Build a real repository from an explicit list of commits (used by the leak tests, which plant canaries in a fixture).

    Each commit dict: ``message`` (subject and optional body), ``author`` and ``email`` (optional), ``paths`` (list) or
    ``path``, ``lines`` (lines added in each path, default 10), ``minute`` (minutes after the previous commit, default 90).
    Absolute paths are made relative. Returns the repository path; no truth file is written."""
    dest = Path(dest)
    repo = dest / "repo"
    dest.mkdir(parents=True, exist_ok=True)
    repo.mkdir(parents=True, exist_ok=True)
    epoch0 = (date.fromisoformat(start) - date(1970, 1, 1)).days * 86400 + 9 * 3600 - tz_min * 60
    files: dict[str, list[str]] = {}
    out: list[_Commit] = []
    counter = 0
    t = epoch0
    for i, c in enumerate(commits):
        t += int(c.get("minute", 90)) * 60
        paths = list(c.get("paths") or ([c["path"]] if c.get("path") else ["src/app.py"]))
        changed: dict[str, str] = {}
        for p in paths:
            p = p.lstrip("/")
            cur = files.setdefault(p, [])
            for _ in range(int(c.get("lines", 10))):
                counter += 1
                cur.append(f"VALUE_{counter:06d} = {counter % 997}")
            changed[p] = "\n".join(cur) + "\n"
        msg = str(c.get("message", "update")) + "\n"
        out.append(_Commit(i + 1, t, str(c.get("author", "Dev")), msg, changed, "other", {}, email=str(c.get("email", "dev@example.test"))))
    env = _git_env(dest)
    _run(["git", "init", "-q", "--template=", "-b", "main", str(repo)], dest, env)
    _run(["git", "fast-import", "--quiet"], repo, env, _stream(out, tz_min, "Dev", "dev@example.test"))
    _run(["git", "reset", "-q", "--hard", "main"], repo, env)
    return repo


def load_truth(repo_or_dest: str | os.PathLike) -> dict:
    p = Path(repo_or_dest)
    for cand in (p / "truth.json", p.parent / "truth.json"):
        if cand.exists():
            return json.loads(cand.read_text(encoding="utf-8"))
    raise FileNotFoundError("truth.json not found beside the repository")


def make_cohort(dest: str | os.PathLike, replicate: int = 0, *, canary: bool = False, strength: float = 1.0, days: int = 42,
                jitter: float = 1.0) -> dict:
    """Four learner repos and eight expert repos under ``dest/<person>/``. Returns
    ``{"learners": {person: repo}, "experts": {person: repo}, "replicate": n, "canary": bool, "strength": s}``."""
    dest = Path(dest)
    out: dict = {"learners": {}, "experts": {}, "replicate": replicate, "canary": canary, "strength": strength, "generator": GENERATOR}
    for key, specs in (("learners", learner_specs(replicate, canary=canary, strength=strength, days=days, jitter=jitter)),
                       ("experts", expert_specs(replicate, canary=canary, days=days, jitter=jitter))):
        for s in specs:
            out[key][s.person] = make_repo(s, dest / s.person)
    return out


def cohort_index(dest: str | os.PathLike) -> dict | None:
    p = Path(dest) / "cohort.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def ensure_cohort(dest: str | os.PathLike, replicate: int = 0, *, canary: bool = False) -> dict:
    """Materialise the default cohort once (idempotent). The index file is written last, so a half-written cohort is rebuilt."""
    dest = Path(dest)
    idx = cohort_index(dest)
    if idx and idx.get("generator") == GENERATOR and idx.get("replicate") == replicate and idx.get("canary") == canary:
        return idx
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    made = make_cohort(dest, replicate, canary=canary)
    idx = {"generator": GENERATOR, "replicate": replicate, "canary": canary,
           "learners": {k: str(v.relative_to(dest)) for k, v in made["learners"].items()},
           "experts": {k: str(v.relative_to(dest)) for k, v in made["experts"].items()}}
    (dest / "cohort.json").write_text(json.dumps(idx, indent=1), encoding="utf-8")
    return idx
