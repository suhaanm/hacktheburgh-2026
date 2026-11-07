"""Labelled synthetic fixture sets for the digest evaluation (LOC-2): 150 commits and 150 calendar entries.

Everything here is synthetic: invented components, invented people and companies (unusual surnames, ``example.test`` domains),
no real repository or calendar. Labels are PLANTED: each item is built from a recipe that fixes its label, then dressed with
wording, paths and numbers. About a third of the items carry planted canary strings (names, emails, absolute paths, customer
names, ticket ids, URLs) that must never appear in any output.

The labelling policy (the same rules the prompts state, written down so the labels are reproducible):

commits
  category   all paths tests -> test; all paths docs -> docs; otherwise from the message. Performance work and anything
             unclear -> other. Merges, bumps, CI, build, formatting, releases -> chore.
  risk       high: a revert; a huge change; a behaviour change in a sensitive area (authentication, sessions, payments,
             migrations, infrastructure, deployment, release); or a message that says a safety check is being turned off or
             data destroyed (some sensitive areas have innocuous paths, so the cue is in the message only).
             low: docs and tests; non-sensitive chores up to medium size; tiny changes; unclear 'other' up to small size.
             medium: everything else.
  quality    vague: nothing specific ("wip", "fixes"); ok: one specific line; clear: says why, or has a useful body.
  size/tests computed from the diffstat by the same functions the pipeline uses.

calendar entries
  category   by what the title and context say (see the prompt's guide); needs_prep is planted per recipe.
  recurring, duration and attendee buckets are computed from the generated fields.

Two splits: ``dev`` (a third, used to tune the prompts and rules) and ``test`` (two thirds, reported as the headline).
The fixtures are authored by the same hand that wrote the rules, which favours the rules; see the evaluation's limitations.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from .schemas import attendee_bucket, duration_bucket, is_test_path, size_bucket

SEED = 20261107

# ------------------------------------------------------------------------------------------------------------ canaries
FIRST = ["Aurelia", "Tobiah", "Ottoline", "Fenwick", "Marisol", "Casimir", "Thessaly", "Lucan", "Odalys", "Peregrine", "Wilhelmina", "Anselm"]
LAST = ["Quillfeather", "Marchbanks", "Brackenridge", "Hollowell", "Vandenberk", "Pennywhistle", "Oyelaran", "Fairweather",
        "Nettlefold", "Ashgrove", "Thornbury", "Lindqvist"]
CUSTOMERS = ["Zorblax Holdings", "Quillon Freight", "Brackwater Utilities", "Harrowgate Nimbus Ltd", "Ferrule & Strand",
             "Osprey Lantern Group", "Kestrel Wynd Insurance", "Tallow Row Foods"]
CITIES = ["Glasgow", "Manchester", "Leeds", "Bristol", "Aberdeen", "Cardiff", "Newcastle", "Belfast"]
HOME_DIRS = ["/Users/{f}/work/{p}", "/home/{f}/src/{p}", "C:\\Users\\{f}\\code\\{p}"]


def _person(rng: random.Random) -> tuple[str, str, str]:
    f, last = rng.choice(FIRST), rng.choice(LAST)
    return f, f"{f} {last}", f"{f.lower()}.{last.lower()}@example.test"


# ------------------------------------------------------------------------------------------------------------- commits
@dataclass(frozen=True)
class Comp:
    name: str
    path: str
    test: str
    sensitive: bool = False


COMPS = [
    Comp("report builder", "reports/builder.py", "tests/reports/test_builder.py"),
    Comp("CSV importer", "ingest/csv_importer.py", "tests/ingest/test_csv_importer.py"),
    Comp("search index", "search/index.py", "tests/search/test_index.py"),
    Comp("settings page", "web/settings_page.py", "tests/web/test_settings_page.py"),
    Comp("image resizer", "media/resize.py", "tests/media/test_resize.py"),
    Comp("notification digest", "notify/digest.py", "tests/notify/test_digest.py"),
    Comp("cart totals", "cart/totals.py", "tests/cart/test_totals.py"),
    Comp("upload client", "client/upload.py", "tests/client/test_upload.py"),
    Comp("job scheduler", "jobs/scheduler.py", "tests/jobs/test_scheduler.py"),
    Comp("webhook handler", "hooks/handler.py", "tests/hooks/test_handler.py"),
    Comp("audit viewer", "admin/audit_view.py", "tests/admin/test_audit_view.py"),
    Comp("onboarding flow", "web/onboarding.py", "tests/web/test_onboarding.py"),
    Comp("email queue", "mailer/queue.py", "tests/mailer/test_queue.py"),
    Comp("pricing table", "pricing/table.py", "tests/pricing/test_table.py"),
    Comp("dashboard widgets", "ui/widgets.tsx", "ui/widgets.test.tsx"),
    Comp("pagination helper", "lib/paginate.py", "tests/lib/test_paginate.py"),
    Comp("config loader", "core/config_loader.py", "tests/core/test_config_loader.py"),
    Comp("cache layer", "core/cache.py", "tests/core/test_cache.py"),
    Comp("slug generator", "lib/slugs.py", "tests/lib/test_slugs.py"),
    Comp("rate limiter", "api/limits.py", "tests/api/test_limits.py"),
    Comp("export button", "ui/ExportButton.tsx", "ui/ExportButton.test.tsx"),
    Comp("timezone helpers", "lib/tz.py", "tests/lib/test_tz.py"),
]
SENSITIVE = [
    Comp("login handler", "auth/login.py", "tests/auth/test_login.py", True),
    Comp("session store", "auth/session_store.py", "tests/auth/test_session_store.py", True),
    Comp("password reset flow", "auth/password_reset.py", "tests/auth/test_password_reset.py", True),
    Comp("payment gateway adapter", "payments/gateway.py", "tests/payments/test_gateway.py", True),
    Comp("refund flow", "payments/refunds.py", "tests/payments/test_refunds.py", True),
    Comp("token service", "auth/tokens.py", "tests/auth/test_tokens.py", True),
    Comp("deploy pipeline", ".github/workflows/deploy.yml", "tests/deploy/test_pipeline.py", True),
    Comp("network module", "infra/terraform/network.tf", "tests/infra/test_network.py", True),
    # innocuous paths, sensitivity visible in the message only
    Comp("permission checks", "core/gate.py", "tests/core/test_gate.py", True),
    Comp("payment ledger", "svc/ledger.py", "tests/svc/test_ledger.py", True),
    Comp("credential storage", "core/store.py", "tests/core/test_store.py", True),
    Comp("signature verification", "hooks/verify.py", "tests/hooks/test_verify.py", True),
]
FEATS = ["a dry-run mode", "per-team filters", "keyboard shortcuts", "a retry limit setting", "weekly summaries", "bulk selection",
         "an undo step", "a read-only view", "dark mode support", "sorting by date", "an offline queue", "inline previews"]
BUGS = ["the crash on empty input", "duplicate rows after a retry", "a wrong total when discounts stack", "the missing last page",
        "the stale cache after an edit", "a timezone shift on export", "the hang when the queue is empty", "negative counts after a refund",
        "a double submit on slow networks", "the broken link in the footer", "lost whitespace in exported names", "a race on shutdown"]
BAD = ["dropping the last row", "sending twice", "returning stale data", "ignoring the locale", "failing on unicode names",
       "crashing on empty files", "counting hidden items", "timing out on large inputs"]
EDGES = ["empty lists", "unicode names", "leap days", "very large files", "missing fields", "duplicate ids", "zero quantities", "expired links"]
ACTIONS = ["export their data", "pin a favourite view", "mute a thread", "rename a project", "schedule a send", "restore a deleted item"]
THINGS = ["validation", "date parsing", "error messages", "retry logic", "logging setup", "field mapping", "currency rounding", "path handling"]
WHY = [
    "Support kept hitting this and the workaround was a manual script.",
    "It was the slowest part of the nightly run and blocked the next job.",
    "The old behaviour surprised users and generated repeat tickets.",
    "Without it the next change would have had to copy the same logic a third time.",
    "This was the cause of last week's incident, so it needs to land before the freeze.",
    "Reviewers asked for it twice, and it keeps the module readable.",
]
WHY_TAIL = ["Closes #{n}.", "See the discussion in the design doc.", "No behaviour change intended.", "Tested by hand on staging data."]


@dataclass
class CommitFix:
    id: str
    split: str
    item: dict[str, Any]
    label: dict[str, Any]
    canaries: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


def _lines_for(rng: random.Random, bucket: str) -> int:
    lo, hi = {"tiny": (2, 10), "small": (11, 50), "medium": (51, 250), "large": (251, 1000), "huge": (1001, 4200)}[bucket]
    return rng.randint(lo, hi)


def _split_lines(rng: random.Random, total: int, n: int, add_share: float) -> list[tuple[int, int]]:
    total = max(total, n)
    extra = total - n
    cuts = sorted(rng.randint(0, extra) for _ in range(n - 1))
    parts = [1 + (b - a_) for a_, b in zip([0] + cuts, cuts + [extra])]
    out = []
    for p in parts:
        a_ = int(round(p * min(1.0, max(0.0, add_share + rng.uniform(-0.1, 0.1)))))
        out.append((a_, p - a_))
    return out


def _fill(tpl: str, rng: random.Random, comp: Comp) -> str:
    f = rng.choice(FIRST)
    ver = lambda: f"{rng.randint(1, 9)}.{rng.randint(0, 20)}.{rng.randint(0, 9)}"  # noqa: E731
    return tpl.format(
        comp=comp.name, Comp=comp.name[0].upper() + comp.name[1:], feat=rng.choice(FEATS), bug=rng.choice(BUGS),
        bad=rng.choice(BAD), edge=rng.choice(EDGES), action=rng.choice(ACTIONS), thing=rng.choice(THINGS),
        fmt=rng.choice(["JSON", "TSV", "XLSX", "Parquet", "NDJSON", "YAML"]), n=rng.randint(100, 9999),
        other=rng.choice(COMPS).name, first=f, why=rng.choice(WHY), tail=rng.choice(WHY_TAIL).format(n=rng.randint(100, 9999)),
        orig=rng.choice(ORIGS), sha="".join(rng.choice("0123456789abcdef") for _ in range(10)), pkg=rng.choice(PKGS),
        v1=ver(), v2=ver(), tool=rng.choice(TOOLS), branch=rng.choice(BRANCHES), team=rng.choice(TEAMS),
        dir=rng.choice(["src/", "services/", "ui/"]),
    )


# recipe: (template, quality, size choices, extra tags)
FEATURE_R = [
    ("Add {feat} to the {comp}", "ok", ["small", "medium", "medium", "large"]),
    ("Support {fmt} in the {comp}", "ok", ["small", "medium"]),
    ("Introduce {feat} for the {comp}", "ok", ["medium", "large"]),
    ("Let users {action} from the {comp}", "ok", ["small", "medium"]),
    ("{Comp} now supports {fmt}", "ok", ["small", "medium"]),
    ("Users can now {action}", "ok", ["small", "medium", "large"]),
    ("New {feat} view for the {comp}", "ok", ["medium", "large"]),
    ("Hook the {comp} up to the {other}", "ok", ["small", "medium"]),
    ("feat({comp}): {feat}", "ok", ["small", "medium"]),
    ("feat: add {feat}", "ok", ["medium"]),
    ("first pass at {feat}", "ok", ["medium", "large"]),
    ("Add {feat} to the {comp}\n\n{why} {tail}", "clear", ["medium", "large"]),
    ("Support {fmt} in the {comp}\n\n{why}", "clear", ["small", "medium"]),
    ("Rewrite the {comp} from scratch around {feat}", "ok", ["huge"]),
]
FIX_R = [
    ("Fix {bug} in the {comp}", "ok", ["tiny", "small", "small"]),
    ("Stop the {comp} from {bad}", "ok", ["tiny", "small"]),
    ("Handle {edge} in the {comp}", "ok", ["tiny", "small", "medium"]),
    ("Prevent {bad} when the {comp} gets {edge}", "ok", ["small"]),
    ("{Comp} no longer {bad}", "ok", ["tiny", "small"]),
    ("Make the {comp} cope with {edge}", "ok", ["small", "medium"]),
    ("Don't let the {comp} fall over on {edge}", "ok", ["tiny", "small"]),
    ("Off-by-one in {comp}", "ok", ["tiny"]),
    ("fix({comp}): {bug}", "ok", ["tiny", "small"]),
    ("fix: {bug}", "ok", ["tiny", "small"]),
    ("hotfix {bug}", "ok", ["tiny", "small"]),
    ("Fix {bug}\n\n{why} {tail}", "clear", ["small", "medium"]),
    ("Stop {comp} {bad}\n\nThe cache key ignored the locale, so the second request reused the first answer. {tail}", "clear", ["tiny", "small"]),
    ("fixes", "vague", ["tiny", "small"]),
    ("fix stuff", "vague", ["tiny", "small"]),
]
REFACTOR_R = [
    ("Refactor the {comp} into smaller functions", "ok", ["medium", "medium", "large"]),
    ("Extract a {thing} helper from the {comp}", "ok", ["small", "medium"]),
    ("Simplify control flow in the {comp}", "ok", ["small", "medium"]),
    ("Split the {comp} into a reader and a writer", "ok", ["medium", "large"]),
    ("Move {thing} out of the {comp} into its own module", "ok", ["medium"]),
    ("Replace callbacks with async/await in the {comp}", "ok", ["medium", "large"]),
    ("Use dataclasses instead of dicts in the {comp}", "ok", ["medium"]),
    ("Collapse the two {thing} code paths", "ok", ["small", "medium"]),
    ("{Comp} cleanup", "ok", ["small", "medium"]),
    ("refactor({comp}): share {thing} between callers", "ok", ["small", "medium"]),
    ("Refactor the {comp}\n\n{why} No behaviour change intended.", "clear", ["medium", "large"]),
    ("Restructure the repository into packages", "ok", ["huge"]),
]
TEST_R = [
    ("Add tests for {edge} in the {comp}", "ok", ["small", "medium"]),
    ("Cover {edge} in the {comp} tests", "ok", ["small", "medium"]),
    ("Test the {comp} against {fmt} fixtures", "ok", ["small", "medium"]),
    ("Fix flaky {comp} test", "ok", ["tiny", "small"]),
    ("Add a regression test for {bug}", "ok", ["small"]),
    ("Raise coverage for the {comp}", "ok", ["medium"]),
    ("test: {comp} {edge}", "ok", ["small"]),
    ("Add regression test for {bug}\n\nIt failed intermittently on CI before the fix. {tail}", "clear", ["small", "medium"]),
]
DOCS_R = [
    ("Document the {comp} configuration options", "ok", ["small"]),
    ("Update the README with {thing} setup steps", "ok", ["small"]),
    ("Fix a typo in the {comp} docs", "ok", ["tiny"]),
    ("Explain how the {comp} retries in the architecture notes", "ok", ["small"]),
    ("Clarify {thing} in the contributing guide", "ok", ["tiny", "small"]),
    ("docs: add a {comp} troubleshooting section", "ok", ["small"]),
    ("Add a changelog entry for {n}", "ok", ["tiny"]),
    ("Notes on running the {comp} locally\n\n{why}", "clear", ["small", "medium"]),
]
CHORE_R = [
    ("Bump {pkg} from {v1} to {v2}", "ok", ["tiny", "small"]),
    ("Update dependencies", "ok", ["small", "medium"]),
    ("Run the formatter over {dir}", "ok", ["medium", "large"]),
    ("Pin {pkg} to {v1}", "ok", ["tiny"]),
    ("Add {tool} to CI", "ok", ["small"]),
    ("Merge branch 'main' into {branch}", "ok", ["small", "medium"]),
    ("Merge pull request #{n} from {team}/{branch}", "ok", ["small", "medium"]),
    ("Update the Dockerfile base image", "ok", ["tiny"]),
    ("Release {v2}", "ok", ["tiny"]),
    ("chore: tidy {tool} config", "ok", ["tiny", "small"]),
    ("ci: cache dependencies between jobs", "ok", ["small"]),
    ("Bump {pkg} to {v2}\n\n{why}", "clear", ["tiny", "small"]),
]
REVERT_R = [
    ('Revert "{orig}"', "ok", ["small", "medium", "large"]),
    ("Back out the {comp} rewrite", "ok", ["medium", "large"]),
    ("Roll back {feat} until the bug is understood", "ok", ["small", "medium"]),
    ('Revert "{orig}"\n\nThis reverts commit {sha}. It broke the nightly import and we cannot reproduce it locally.', "clear", ["medium"]),
    ("revert {feat}", "ok", ["small", "medium"]),
]
OTHER_R = [
    ("wip", "vague", ["tiny", "small", "medium"]),
    ("asdf", "vague", ["tiny", "small"]),
    ("stuff", "vague", ["tiny", "small", "medium"]),
    ("more work on the {comp}", "vague", ["small", "medium"]),
    ("Speed up the {comp} by caching the {thing}", "ok", ["small", "medium"]),
    ("Reduce memory use in the {comp}", "ok", ["small", "medium"]),
    ("Spike: try a different approach to {thing}", "ok", ["medium"]),
    ("Experiment with batching in the {comp}", "ok", ["small", "medium"]),
    ("checkpoint before the weekend", "vague", ["small", "medium"]),
    ("Temporary hack so the demo works", "vague", ["tiny", "small"]),
    ("Optimise the {comp} query\n\nProfiling showed 80 percent of the time in one join. Added an index hint and a limit. {tail}", "clear", ["small"]),
    ("update", "vague", ["tiny", "small"]),
]
FEATURE_R += [("add stuff", "vague", ["small", "medium"]), ("new feature", "vague", ["small", "medium"]),
              ("Let users {action}\n\n{why}", "clear", ["small", "medium"]), ("Introduce {feat} for the {comp}\n\n{why} {tail}", "clear", ["medium", "large"])]
FIX_R += [("bugfix", "vague", ["tiny", "small"]), ("small fix", "vague", ["tiny"]), ("oops", "vague", ["tiny"]),
          ("Handle {edge} in the {comp}\n\n{why}", "clear", ["small", "medium"]),
          ("Fix {bug}\n\nRoot cause: the {comp} assumed ids were unique. {tail}", "clear", ["tiny", "small"])]
REFACTOR_R += [("cleanup", "vague", ["small", "medium"]), ("refactoring", "vague", ["medium"]), ("tidy", "vague", ["small"]),
               ("Extract a {thing} helper from the {comp}\n\n{why} No behaviour change intended.", "clear", ["small", "medium"])]
TEST_R += [("tests", "vague", ["small", "medium"]), ("more tests", "vague", ["small"]),
           ("Cover {edge} in the {comp} tests\n\n{why}", "clear", ["small", "medium"])]
DOCS_R += [("docs", "vague", ["tiny", "small"]), ("update docs", "vague", ["small"]),
           ("Document the {comp} configuration options\n\n{why}", "clear", ["small"])]
CHORE_R += [("update", "vague", ["tiny", "small"]), ("misc", "vague", ["small"]), ("chore", "vague", ["tiny"]),
            ("Update dependencies\n\n{why} A security advisory was published for one of them this week.", "clear", ["small", "medium"])]
REVERT_R += [("Back out the {comp} rewrite\n\nIt doubled latency in production; we will redo it behind a flag.", "clear", ["medium", "large"])]
OTHER_R += [("Speed up the {comp} by caching the {thing}\n\nCuts the p95 from 900 ms to 120 ms on the staging dataset. {tail}", "clear", ["small", "medium"]),
            ("Spike: batching in the {comp}\n\nThrowaway branch to measure whether batching helps; not meant to merge. {tail}", "clear", ["medium"])]
QUALITY_WEIGHTS = {  # (vague, clear); the rest is ok
    "feature": (0.08, 0.25), "fix": (0.16, 0.25), "refactor": (0.1, 0.2), "test": (0.1, 0.15), "docs": (0.1, 0.15),
    "chore": (0.12, 0.12), "revert": (0.0, 0.35), "other": (0.55, 0.12),
}


def _pick_recipe(rng: random.Random, category: str, recipes: list[tuple[str, str, list[str]]], used: dict[str, int]):
    v, c = QUALITY_WEIGHTS[category]
    r = rng.random()
    q = "vague" if r < v else ("clear" if r < v + c else "ok")
    pool = [x for x in recipes if x[1] == q] or [x for x in recipes if x[1] == "ok"]
    k = used.get(category + q, 0)
    used[category + q] = k + 1
    return pool[(k * 7 + rng.randint(0, 2)) % len(pool)] if k >= len(pool) else pool[k % len(pool)]


PKGS = ["lodash", "requests", "pytest", "react", "numpy", "axios", "pydantic", "express", "eslint", "tokenizer-lib"]
TOOLS = ["ruff", "eslint", "a type check", "pre-commit", "coverage upload", "a nightly build"]
BRANCHES = ["feature/export-v2", "release/2.4", "hotfix/queue-stall", "dev", "cleanup/imports"]
TEAMS = ["platform", "growth", "data", "core"]
ORIGS = ["Switch checkout to async payments", "Move the cache to Redis", "Add bulk selection to the table", "Upgrade the ORM",
         "Parallelise the nightly import", "Drop the legacy session table"]

SENSITIVE_CHORE_PATHS = [[".github/workflows/deploy.yml"], ["infra/terraform/versions.tf"], ["deploy/Dockerfile"], [".github/workflows/release.yml"]]
CHORE_PATHS = [["package.json", "package-lock.json"], ["pyproject.toml", "uv.lock"], [".github/workflows/ci.yml"], ["Dockerfile"],
               ["Makefile"], [".gitignore"], ["config/lint.yml"], ["requirements.txt"]]
SENSITIVE_CUES = [
    "Disable the signature check on the {comp} while we debug",
    "Skip the permission check for service accounts in the {comp}",
    "Drop the legacy {comp} table and its backups",
    "Temporarily turn off rate limiting for the {comp}",
    "Allow the {comp} to run without TLS verification in staging",
]


def _plant_risk(category: str, sensitive: bool, size: str, cue_high: bool) -> str:
    if category == "revert" or size == "huge" or cue_high:
        return "high"
    if sensitive and category not in ("docs", "test"):
        return "high"
    if category in ("docs", "test") or size == "tiny":
        return "low"
    if category == "chore":
        return "low" if size in ("small", "medium") else "medium"
    if category == "other":
        return "low" if size == "small" else "medium"
    return "medium"


def _canary_text(rng: random.Random, msg: str, canaries: list[str], style: str) -> str:
    f, full, email = _person(rng)
    cust = rng.choice(CUSTOMERS)
    if style == "customer":
        canaries += [cust]
        return msg.split("\n", 1)[0] + f" (reported by {cust})" + ("\n" + msg.split("\n", 1)[1] if "\n" in msg else "")
    if style == "person":
        canaries += [full]
        return msg + ("\n\n" if "\n" not in msg else "\n") + f"Thanks to {full} for spotting this."
    if style == "trailer":
        canaries += [email, full]
        return msg + ("\n\n" if "\n" not in msg else "\n") + f"Co-authored-by: {full} <{email}>"
    if style == "path":
        home = rng.choice(HOME_DIRS).format(f=f.lower(), p="secretproj")
        canaries += [home]
        return msg.split("\n", 1)[0] + f" ({home}/run.sh)" + ("\n" + msg.split("\n", 1)[1] if "\n" in msg else "")
    if style == "ticket":
        t = f"ACME-{rng.randint(1000, 9999)}"
        canaries += [t]
        return f"{t}: " + msg
    if style == "url":
        u = f"https://wiki.example.test/{f.lower()}/notes-{rng.randint(10, 99)}"
        canaries += [u]
        return msg + ("\n\n" if "\n" not in msg else "\n") + f"See {u}"
    return msg


def build_commits(seed: int = SEED) -> list[CommitFix]:
    rng = random.Random(seed)
    quotas = [("feature", FEATURE_R, 30), ("fix", FIX_R, 30), ("refactor", REFACTOR_R, 20), ("test", TEST_R, 14), ("docs", DOCS_R, 14),
              ("chore", CHORE_R, 16), ("revert", REVERT_R, 8), ("other", OTHER_R, 18)]
    out: list[CommitFix] = []
    used: dict[str, int] = {}
    for category, recipes, quota in quotas:
        for k in range(quota):
            tpl, quality, sizes = _pick_recipe(rng, category, recipes, used)
            size = rng.choice(sizes)
            cue_high = False
            sensitive_pool = category in ("feature", "fix", "refactor", "chore", "other") and rng.random() < 0.28
            comp = rng.choice(SENSITIVE if sensitive_pool else COMPS)
            if category == "other" and quality == "vague" and rng.random() < 0.4:
                comp = rng.choice(COMPS)
            tags: list[str] = []
            # a risky message cue (the paths may be innocuous)
            if category == "other" and rng.random() < 0.30:
                tpl, quality, cue_high = rng.choice(SENSITIVE_CUES), "ok", True
                comp = rng.choice([c for c in SENSITIVE if "/" in c.path and not c.path.startswith((".github", "infra"))]
                                  if rng.random() < 0.6 else COMPS)
                tags.append("message_only_risk")
            msg = _fill(tpl, rng, comp)
            # paths and numbers
            lines = _lines_for(rng, size)
            paths: list[str]
            if category == "test":
                paths = [comp.test] + ([rng.choice(COMPS).test] if rng.random() < 0.3 else [])
            elif category == "docs":
                paths = rng.choice([["README.md"], ["docs/guide.md"], ["docs/architecture.md", "docs/faq.md"], ["CONTRIBUTING.md"],
                                    ["CHANGELOG.md"], ["docs/auth.md"], ["docs/payments.md"]])
            elif category == "chore" and not cue_high:
                paths = rng.choice(SENSITIVE_CHORE_PATHS if sensitive_pool else CHORE_PATHS)
            else:
                paths = [comp.path]
                if rng.random() < 0.5:
                    paths.append(rng.choice(COMPS).path)
                if category in ("feature", "fix") and rng.random() < 0.3:
                    paths.append(comp.test)
                    tags.append("with_tests")
                if category in ("feature", "refactor", "other") and size in ("large", "huge"):
                    paths += [rng.choice(COMPS).path for _ in range(rng.randint(1, 4))]
            paths = list(dict.fromkeys(paths))
            share = {"feature": 0.85, "fix": 0.65, "refactor": 0.5, "test": 0.9, "docs": 0.9, "chore": 0.5, "revert": 0.2, "other": 0.7}[category]
            files = [{"path": p, "additions": a, "deletions": d}
                     for p, (a, d) in zip(paths, _split_lines(rng, lines, len(paths), share))]
            # canaries on about a third of items
            canaries: list[str] = []
            if rng.random() < 0.36:
                # a vague message stays vague only if the canary adds no wording (a ticket prefix or a trailer)
                style = rng.choice(["ticket", "trailer"] if quality == "vague" else ["customer", "person", "trailer", "path", "ticket", "url"])
                msg = _canary_text(rng, msg, canaries, style)
                tags.append(f"canary_{style}")
            if rng.random() < 0.15:                                    # a path that itself carries a name
                f, full, _ = _person(rng)
                files[0] = dict(files[0], path=f"customers/{full.split()[1].lower()}_{files[0]['path'].split('/')[-1]}")
                canaries.append(full.split()[1].lower() + "_")
                tags.append("canary_in_path")
            total = sum(f["additions"] + f["deletions"] for f in files)
            label_size = size_bucket(total)
            label = {
                "category": category,
                "size_bucket": label_size,
                "touches_tests": any(is_test_path(f["path"]) for f in files),
                "risk": _plant_risk(category, (comp.sensitive or (category == "chore" and sensitive_pool)) and category not in ("docs", "test"), label_size, cue_high),
                "message_quality": quality,
            }
            if "message_only_risk" in tags or (comp.sensitive and "/" in comp.path and comp.path.startswith(("core/", "svc/", "hooks/"))):
                tags.append("innocuous_sensitive_path")
            out.append(CommitFix(id="", split="", item={"message": msg, "files": files}, label=label, canaries=canaries, tags=tags))
    rng.shuffle(out)
    per: dict[str, int] = {}
    for i, c in enumerate(out):
        c.id = f"c{i + 1:03d}"
        n = per.get(c.label["category"], 0)
        per[c.label["category"]] = n + 1
        c.split = "dev" if n % 3 == 0 else "test"
    return out


# --------------------------------------------------------------------------------------------------------- calendar
@dataclass
class EventFix:
    id: str
    split: str
    item: dict[str, Any]
    label: dict[str, Any]
    canaries: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


TEAMS_E = ["Platform", "Growth", "Data", "Mobile", "Payments", "Support"]
PROJECTS = ["Atlas", "Lantern", "Harbour", "Meridian", "Tidewater", "Kestrel"]
DOCS_E = ["the Q1 proposal", "the migration plan", "the onboarding guide", "the incident write-up", "the pricing memo"]
FEATS_E = ["checkout redesign", "search v2", "usage dashboard", "bulk import", "notification settings"]

# (title template, needs_prep, attendees range, durations, recurring probability, uses_name)
ONE_R = [("1:1 with {name}", False, (2, 2), [30, 30, 45, 60], 0.7), ("{first} / {first2} 1:1", False, (2, 2), [30, 45], 0.8),
         ("Catch up with {name}", False, (2, 2), [30, 45], 0.1), ("Weekly check-in - {first}", False, (2, 2), [30], 0.9),
         ("Mentoring: {name}", False, (2, 2), [45, 60], 0.5), ("Skip-level with {name}", False, (2, 2), [30, 45], 0.4),
         ("{first} + me", False, (2, 2), [30], 0.3), ("Career chat with {first}", True, (2, 2), [45, 60], 0.0),
         ("Performance review 1:1 - {first}", True, (2, 2), [60], 0.0), ("One-on-one: {name}", False, (2, 2), [30, 45], 0.6),
         ("{first} <> {first2}", False, (2, 2), [30], 0.7), ("Pairing with {first}", False, (2, 2), [60, 90], 0.0),
         ("{first}: quick one", False, (2, 2), [15, 30], 0.0), ("Feedback session - {first}", True, (2, 2), [45], 0.0),
         ("{first} x me", False, (2, 2), [30, 45], 0.5)]
TEAM_R = [("Daily standup", False, (6, 12), [15], 0.95), ("{team} team sync", False, (5, 14), [30, 45], 0.8),
          ("Sprint planning", True, (6, 12), [60, 90], 0.9), ("Sprint retro", False, (6, 12), [60], 0.9), ("All hands", False, (30, 120), [60], 0.6),
          ("Engineering leads sync", False, (5, 9), [45], 0.9), ("Weekly team meeting", False, (8, 20), [60], 0.95),
          ("Q1 planning workshop", True, (10, 25), [180], 0.0), ("{team} huddle", False, (5, 9), [15, 30], 0.8),
          ("Backlog refinement", True, (5, 10), [60], 0.8), ("Kickoff for the {project} project", True, (8, 20), [60, 90], 0.0),
          ("Monthly town hall", False, (40, 150), [60], 0.9), ("Project {project} status meeting", False, (6, 14), [30, 45], 0.8),
          ("Team offsite day", True, (8, 20), [], 0.0), ("Wednesday catch-up for {project}", False, (5, 10), [30], 0.8),
          ("Where are we on {project}?", False, (5, 12), [30, 45], 0.0), ("{team} ways of working", False, (6, 14), [60], 0.0),
          ("Weekly metrics", False, (6, 12), [45], 0.9), ("Planning for Q2", True, (8, 16), [90, 120], 0.0),
          ("Ops handover", False, (4, 9), [30], 0.9), ("Release readiness", True, (6, 14), [30, 45], 0.0)]
REVIEW_R = [("Design review: {feat}", True, (4, 9), [60], 0.1), ("Code review - {project}", True, (2, 6), [30, 45, 60], 0.2),
            ("Architecture review board", True, (6, 12), [60, 90], 0.5), ("PR walkthrough: {feat}", True, (3, 8), [30, 45], 0.0),
            ("Demo: {feat}", True, (8, 30), [30, 45], 0.0), ("Post-incident review", True, (6, 14), [60], 0.0),
            ("Security review for {project}", True, (3, 8), [60, 90], 0.0), ("Roadmap review", True, (6, 12), [90], 0.3),
            ("Sprint demo", True, (10, 30), [45, 60], 0.9), ("Look over the {project} proposal together", True, (2, 5), [45], 0.0),
            ("Review {doc} with {first}", True, (2, 3), [30, 45], 0.0), ("Show and tell", False, (10, 25), [45], 0.8),
            ("Eyes on the {project} proposal", True, (3, 7), [30, 45], 0.0), ("Let's walk through {feat}", True, (3, 8), [45, 60], 0.0),
            ("Feedback on the {feat} spec", True, (3, 6), [45], 0.0), ("Teardown of last week's outage", True, (6, 12), [60], 0.0),
            ("Spec read-through: {feat}", True, (4, 8), [60], 0.0)]
FOCUS_R = [("Focus time", False, (0, 1), [60, 90, 120, 180], 0.7), ("Deep work", False, (0, 1), [90, 120, 180, 240], 0.6),
           ("Heads down: {project}", False, (0, 1), [120, 180], 0.1), ("Write {doc}", False, (0, 1), [90, 120], 0.0),
           ("No meetings", False, (0, 1), [180, 240], 0.5), ("Do not book", False, (0, 1), [60, 120], 0.4),
           ("Coding block", False, (0, 1), [120, 180], 0.5), ("Thinking time", False, (0, 1), [60], 0.2),
           ("Prepare slides for {project}", False, (0, 1), [60, 90], 0.0), ("Work on {project}", False, (0, 1), [120, 180, 240], 0.2),
           ("Prep for the {feat} demo", False, (0, 1), [60, 90], 0.0), ("Write up the {project} review", False, (0, 1), [90, 120], 0.0),
           ("Writing", False, (0, 1), [90, 120], 0.6), ("Protected afternoon", False, (0, 1), [180, 240], 0.3),
           ("Reading time", False, (0, 1), [45, 60], 0.4), ("Spec writing: {feat}", False, (0, 1), [120, 180], 0.0)]
SOCIAL_R = [("Team lunch", False, (6, 14), [60], 0.1), ("Coffee with {first}", False, (2, 2), [30], 0.1), ("Friday drinks", False, (8, 25), [90, 120], 0.8),
            ("Birthday cake for {first}", False, (8, 25), [30], 0.0), ("Pub quiz", False, (6, 16), [120], 0.1),
            ("Team dinner", False, (6, 14), [120], 0.0), ("Games afternoon", False, (8, 20), [90, 120], 0.0),
            ("Leaving do for {name}", False, (10, 30), [120], 0.0), ("Welcome breakfast for new starters", False, (6, 12), [45, 60], 0.0),
            ("Welcome lunch for {first}", False, (6, 12), [60], 0.0), ("Pizza Friday", False, (8, 20), [60], 0.9),
            ("Bowling night", False, (8, 18), [120], 0.0), ("Quiet drink after work", False, (3, 8), [60, 90], 0.0),
            ("Cake in the kitchen", False, (8, 20), [30], 0.0)]
ADMIN_R = [("Expenses", False, (0, 1), [15, 30], 0.3), ("Timesheets", False, (0, 1), [15, 30], 0.9), ("Inbox zero", False, (0, 1), [30, 45], 0.7),
           ("Compliance training", False, (0, 1), [45, 60], 0.0), ("Complete the security awareness module", False, (0, 1), [30, 45], 0.0),
           ("Weekly planning", False, (0, 1), [30, 45], 0.9), ("Benefits enrolment", False, (0, 1), [30], 0.0),
           ("Approve invoices", False, (0, 1), [30], 0.5), ("Book travel for the conference", False, (0, 1), [30], 0.0),
           ("Handover notes before leave", False, (0, 1), [45, 60], 0.0), ("Budget submission", True, (0, 2), [60, 90], 0.0),
           ("HR: update emergency contact", False, (0, 1), [15], 0.0),
           ("Sort out visa paperwork", False, (0, 1), [30, 45], 0.0), ("Chase receipts", False, (0, 1), [30], 0.0),
           ("Calendar housekeeping", False, (0, 1), [15, 30], 0.3), ("Weekly review", False, (0, 1), [30, 45], 0.9),
           ("Mandatory GDPR course", False, (0, 1), [45, 60], 0.0), ("Travel expenses", False, (0, 1), [30], 0.0)]
EXTERNAL_R = [("Call with {customer}", True, (3, 8), [30, 45, 60], 0.1), ("{customer} onboarding", True, (4, 10), [60, 90], 0.3),
              ("Vendor demo: {customer}", True, (3, 8), [45, 60], 0.0), ("Interview: {name}", True, (3, 5), [45, 60], 0.0),
              ("Partner sync - {customer}", False, (3, 8), [30, 45], 0.8), ("Sales discovery - {customer}", True, (3, 7), [45, 60], 0.0),
              ("Client workshop - {customer}", True, (6, 15), [120, 180], 0.0), ("Procurement call with {customer}", True, (3, 6), [30, 45], 0.0),
              ("{customer} QBR", True, (6, 14), [60, 90], 0.0), ("Intro call: {name}", True, (2, 4), [30], 0.0),
              ("Chat with the {customer} team", False, (3, 8), [30, 45], 0.1),
              ("{customer} - catch-up", False, (3, 8), [30], 0.7), ("Lunch with the {customer} people", False, (3, 8), [60], 0.0),
              ("Contract discussion: {customer}", True, (3, 7), [45, 60], 0.0), ("Pitch to {customer}", True, (4, 9), [45, 60], 0.0),
              ("Supplier call", False, (2, 5), [30], 0.2)]
TRAVEL_R = [("Flight to {city}", False, (0, 1), [90, 120, 180], 0.0), ("Train to {city}", False, (0, 1), [120, 180, 240], 0.0),
            ("Commute", False, (0, 1), [30, 45, 60], 0.9), ("Travel to {customer} site", False, (0, 1), [60, 90, 180], 0.0),
            ("Airport transfer", False, (0, 1), [45, 60], 0.0), ("Drive to the office", False, (0, 1), [30, 45], 0.5),
            ("Taxi to the station", False, (0, 1), [20, 30], 0.0), ("Return journey - {city}", False, (0, 1), [120, 180, 240, 360], 0.0),
            ("Heading to {city}", False, (0, 1), [120, 180], 0.0), ("Back from {city}", False, (0, 1), [120, 180], 0.0),
            ("Rail: {city}", False, (0, 1), [120, 240], 0.0)]
UNKNOWN_T = ["Meeting", "Call", "Hold", "TBD", "Busy", "(no title)", "?", "Private appointment", "Block", "Placeholder", "Event", "Appointment", "Tentative",
             "Sync", "Catch up", "Chat", "Discuss", "Follow up"]
DESCS = {
    "review": ["Please read the doc beforehand.", "Link to the Figma file is in the invite.", "Bring your comments.", "Agenda: walkthrough, concerns, decision."],
    "external": ["Dial-in: https://meet.example.test/j/{n}?pwd=abc123", "Agenda attached. Bring the pricing sheet.", "Contact: {email}, phone +44 7700 90{p}"],
    "team_meeting": ["Notes in the usual doc.", "Agenda: updates, blockers, next steps.", "Join: https://meet.example.test/team/{n}"],
    "one_to_one": ["Topics: workload, career, feedback.", "Notes: {url}"],
    "social": ["Booking under {name}.", "Meet at reception."], "admin": ["Deadline is Friday."], "focus": [], "travel": ["Booking ref {ref}"], "unknown": [],
}
LOCS = {"external": ["{customer} HQ, floor {n}", "online", ""], "team_meeting": ["Room {n}", "online", ""], "social": ["The Anchor pub", "Canteen"],
        "review": ["Room {n}", "online"], "one_to_one": ["online", ""], "travel": ["{city}"]}


def build_events(seed: int = SEED + 1) -> list[EventFix]:
    rng = random.Random(seed)
    base = datetime(2026, 11, 2, 9, 0, tzinfo=timezone.utc)
    quotas = [("one_to_one", ONE_R, 18), ("team_meeting", TEAM_R, 24), ("review", REVIEW_R, 18), ("focus", FOCUS_R, 18), ("social", SOCIAL_R, 14),
              ("admin", ADMIN_R, 14), ("external", EXTERNAL_R, 18), ("travel", TRAVEL_R, 10), ("unknown", None, 16)]
    out: list[EventFix] = []
    for category, recipes, quota in quotas:
        for k in range(quota):
            canaries: list[str] = []
            tags: list[str] = []
            f1, n1, e1 = _person(rng)
            f2, n2, _ = _person(rng)
            cust, city = rng.choice(CUSTOMERS), rng.choice(CITIES)
            if recipes is None:
                title, needs_prep, (a_lo, a_hi), durs, p_rec = UNKNOWN_T[k % len(UNKNOWN_T)], False, (0, 6), [30, 60], 0.1
            else:
                title, needs_prep, (a_lo, a_hi), durs, p_rec = recipes[k % len(recipes)]
            all_day = not durs
            title = title.format(name=n1, first=f1, first2=f2, team=rng.choice(TEAMS_E), project=rng.choice(PROJECTS), feat=rng.choice(FEATS_E),
                                 doc=rng.choice(DOCS_E), customer=cust, city=city)
            for token, kind in ((n1, "name"), (cust, "customer")):
                if token in title:
                    canaries.append(token)
                    tags.append(f"canary_{kind}")
            if "Interview" in title or "Intro call" in title:
                canaries.append(n1.split()[1])
            n_att = rng.randint(a_lo, a_hi)
            attendees = []
            for i in range(n_att):
                f, full, em = _person(rng)
                attendees.append({"name": full, "email": em})
            if attendees and rng.random() < 0.5:
                canaries += [attendees[0]["email"]]
                tags.append("canary_attendee")
            desc = ""
            if DESCS[category] and rng.random() < 0.5:
                d = rng.choice(DESCS[category])
                f, full, em = _person(rng)
                desc = d.format(n=rng.randint(100, 999), email=em, p=rng.randint(100, 999), url=f"https://wiki.example.test/{f.lower()}/1on1",
                                name=full, ref=f"BK{rng.randint(10000, 99999)}")
                for tok in (em, full):
                    if tok in desc:
                        canaries.append(tok)
                if "example.test" in desc:
                    canaries.append(desc[desc.index("https://"):].split()[0] if "https://" in desc else "meet.example.test")
                if "+44" in desc:
                    canaries.append("+44 7700 90" + desc.split("+44 7700 90")[1][:3])
                tags.append("description")
            loc = ""
            if category in LOCS and rng.random() < 0.6:
                loc = rng.choice(LOCS[category]).format(customer=cust, n=rng.randint(1, 9), city=city)
                if cust in loc:
                    canaries.append(cust)
            start = base + timedelta(days=rng.randint(0, 4), hours=rng.randint(0, 8), minutes=rng.choice([0, 15, 30, 45]))
            if all_day:
                start = start.replace(hour=0, minute=0)
                end = start + timedelta(days=1)
                minutes = 24 * 60
            else:
                minutes = rng.choice(durs)
                end = start + timedelta(minutes=minutes)
            recurring = rng.random() < p_rec
            item: dict[str, Any] = {"title": title, "start": start.isoformat(), "end": end.isoformat(), "attendees": attendees,
                                    "all_day": all_day}
            if desc:
                item["description"] = desc
            if loc:
                item["location"] = loc
            if recurring:
                item["recurrence"] = {"pattern": rng.choice(["daily", "weekly", "biweekly", "monthly"])}
            label = {"category": category, "recurring": recurring, "duration_bucket": duration_bucket(minutes, all_day),
                     "attendee_bucket": attendee_bucket(len(attendees)), "needs_prep": needs_prep}
            out.append(EventFix(id="", split="", item=item, label=label, canaries=sorted(set(canaries)), tags=tags))
    rng.shuffle(out)
    per: dict[str, int] = {}
    for i, e in enumerate(out):
        e.id = f"e{i + 1:03d}"
        n = per.get(e.label["category"], 0)
        per[e.label["category"]] = n + 1
        e.split = "dev" if n % 3 == 0 else "test"
    return out


def fixtures_fingerprint() -> str:
    """A short hash of the generated fixtures, so cached results are tied to the exact items that produced them."""
    import hashlib
    import json

    h = hashlib.sha256()
    for fx in build_commits() + build_events():
        h.update(json.dumps([fx.id, fx.split, fx.item, fx.label], sort_keys=True).encode())
    return h.hexdigest()[:12]
