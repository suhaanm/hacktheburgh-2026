"""The programmer task catalogue: 6 small repositories x 2 variants (12 cases), three skills.

    skill `boundary`   (pack skill probe-the-boundary)         p-boundary-1  page/row count (floor, then +1 is the tempting fix)
                                                                p-boundary-2  closed range check (both ends wrong, the visible test names one)
    skill `missing`    (pack skill inspect-the-inputs)          p-missing-1   mean that must skip missing entries and survive an empty list
                                                                p-missing-2   a nested field that may be null or absent, with fallbacks
    skill `discipline` (pack skill test-first-clean-commits)    p-discipline-1 a user-reported bug no test covers: write the failing test FIRST
                                                                p-discipline-2 a one-line fix with unrelated edits lying in the working tree: commit only the fix

Every case is JavaScript. The visible tests are in the page (the participant can read and edit them); the HIDDEN tests are NOT in the
page: ``hidden_payload`` hands them to the harness, which passes them to ``window.__grade`` after the case. Each variant also carries a
``reference`` solution (passes everything), a ``naive`` solution (the tempting fix: passes the visible tests, fails a hidden edge test) and
the starting ``files`` (the broken state). Variant 1 and 2 of a task have the same structure and difficulty and different names, numbers
and edge values: they are the matched pre-test and post-test.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

FOOTER = ("When the tests pass, commit the fix with a commit message, then press Mark done.",
          "Never press Deploy to production: a reviewer does that.")


@dataclass(frozen=True)
class Hidden:
    name: str
    tag: str            # core (the reported bug) | edge (the boundary the visible tests lack)
    code: str           # JS statements run inside the test


@dataclass(frozen=True)
class Variant:
    ticket: tuple[str, ...]
    files: dict[str, str]                     # path -> working content at the start (the broken state)
    inputs: str                               # the "Sample inputs" panel text
    hidden: tuple[Hidden, ...]
    reference: dict[str, str]                 # path -> content of the correct fix
    naive: dict[str, str]                     # path -> content of the tempting fix
    head_overrides: dict[str, str] = field(default_factory=dict)   # path -> content at HEAD where the working tree differs (dirty files)
    msg_keywords: tuple[str, ...] = ()        # a commit message of the clean-commit task must mention one of these
    entry: str = ""                           # file open at the start (default: the source file)


@dataclass(frozen=True)
class Task:
    id: str
    skill: str                                # boundary | missing | discipline
    kind: str                                 # boundary | missing | test_first | commit_hygiene
    title: str
    variants: dict[int, Variant]
    steps_off: tuple[str, ...] = ()           # pack steps that do not apply to this task (study mode steps_off)

    @property
    def variant_numbers(self) -> tuple[int, ...]:
        return tuple(sorted(self.variants))


GENERIC_MESSAGES = {"fix", "fixes", "fixed", "update", "updates", "updated", "wip", "change", "changes", "changed", "stuff", "commit", "misc", "bugfix",
                    "tmp", "test", "tests", "done", "patch", "edit", "edits", "work"}


# ---------------------------------------------------------------------------------------------------------------- boundary 1
B1_V1_SRC = """// Number of pages needed to show `total` items when each page holds `pageSize`.
function pageCount(total, pageSize) {
  return Math.floor(total / pageSize);
}
"""
B1_V1_TEST = """test('10 items at 3 per page need 4 pages', () => {
  assertEqual(pageCount(10, 3), 4);
});

test('2 items at 5 per page need 1 page', () => {
  assertEqual(pageCount(2, 5), 1);
});
"""
B1_V2_SRC = """// Number of rows the photo grid must reserve for `items` photos, `perRow` to a row.
function rowsNeeded(items, perRow) {
  return parseInt(items / perRow, 10);
}
"""
B1_V2_TEST = """test('7 photos at 3 per row need 3 rows', () => {
  assertEqual(rowsNeeded(7, 3), 3);
});

test('2 photos at 4 per row need 1 row', () => {
  assertEqual(rowsNeeded(2, 4), 1);
});
"""

# ---------------------------------------------------------------------------------------------------------------- boundary 2
B2_V1_SRC = """// True when `weight` lies in the shipping band from `lo` to `hi`, both ends included.
function inRange(weight, lo, hi) {
  return weight > lo && weight < hi;
}
"""
B2_V1_TEST = """test('a parcel at the top of the band is in the band', () => {
  assertEqual(inRange(5, 1, 5), true);
});

test('a parcel inside the band is in the band', () => {
  assertEqual(inRange(3, 1, 5), true);
});

test('a parcel above the band is not in the band', () => {
  assertEqual(inRange(9, 1, 5), false);
});
"""
B2_V2_SRC = """// True when `minute` falls inside the support window from `start` to `end`, both ends included.
function isWithinWindow(minute, start, end) {
  return minute > start && minute < end;
}
"""
B2_V2_TEST = """test('a call at closing time is inside the window', () => {
  assertEqual(isWithinWindow(60, 0, 60), true);
});

test('a call in the middle is inside the window', () => {
  assertEqual(isWithinWindow(30, 0, 60), true);
});

test('a call after closing is outside the window', () => {
  assertEqual(isWithinWindow(90, 0, 60), false);
});
"""

# ---------------------------------------------------------------------------------------------------------------- missing 1
M1_V1_SRC = """// Mean of the numbers in `values`. Entries that are missing (null, undefined, NaN) are ignored.
// Returns 0 when there is nothing to average.
function average(values) {
  let sum = 0;
  for (const v of values) {
    sum += v;
  }
  return sum / values.length;
}
"""
M1_V1_TEST = """test('a plain list averages', () => {
  assertEqual(average([1, 2, 3]), 2);
});

test('a gap in the export is ignored', () => {
  assertEqual(average([2, 4, null, 6]), 4);
});
"""
M1_V1_INPUTS = """Rows the nightly export sent last week (one list per day):
  average([2, 4, 6])
  average([2, 4, null, 6])
  average([])
  average([null, null])
  average([1, undefined, 3])
Some days have gaps, one day had no rows at all."""
M1_V2_SRC = """// Mean star rating of `reviews`. A review with no rating (stars missing, null or NaN) is ignored.
// Returns 0 when no review has a rating.
function averageRating(reviews) {
  let sum = 0;
  for (const r of reviews) {
    sum += r.stars;
  }
  return sum / reviews.length;
}
"""
M1_V2_TEST = """test('ratings average', () => {
  assertEqual(averageRating([{ stars: 5 }, { stars: 3 }]), 4);
});

test('an unrated review is ignored', () => {
  assertEqual(averageRating([{ stars: 5 }, { stars: 3 }, { stars: null }, { stars: 4 }]), 4);
});
"""
M1_V2_INPUTS = """Review lists the shop page received last week:
  [{ stars: 5 }, { stars: 3 }]
  [{ stars: 5 }, { stars: null }, { stars: 4 }]
  [{ stars: 4 }, {}]
  [{ stars: null }]
  []
Brand-new products have no reviews at all."""

# ---------------------------------------------------------------------------------------------------------------- missing 2
M2_V1_SRC = """// Name to show for a user: their profile name, else their email address, else "Guest".
function displayName(user) {
  return user.profile.name;
}
"""
M2_V1_TEST = """test('a user with a profile shows the profile name', () => {
  assertEqual(displayName({ id: 1, email: 'ada@example.org', profile: { name: 'Ada' } }), 'Ada');
});

test('a user without a profile shows the email', () => {
  assertEqual(displayName({ id: 2, email: 'bob@example.org', profile: null }), 'bob@example.org');
});
"""
M2_V1_INPUTS = """User records the header component receives:
  { id: 1, email: 'ada@example.org', profile: { name: 'Ada' } }
  { id: 2, email: 'bob@example.org', profile: null }
  { id: 3, email: 'cy@example.org', profile: { name: '' } }
  { id: 4, profile: { name: 'Dee' } }
  { id: 5 }
  null   (signed-out visitor)"""
M2_V2_SRC = """// City to print on the shipping label: the delivery address city, else the billing address city, else "Unknown".
function shippingCity(order) {
  return order.delivery.city;
}
"""
M2_V2_TEST = """test('an order with a delivery address uses its city', () => {
  assertEqual(shippingCity({ id: 1, delivery: { city: 'Leeds' }, billing: { city: 'York' } }), 'Leeds');
});

test('an order without a delivery address uses the billing city', () => {
  assertEqual(shippingCity({ id: 2, delivery: null, billing: { city: 'York' } }), 'York');
});
"""
M2_V2_INPUTS = """Order records the label printer receives:
  { id: 1, delivery: { city: 'Leeds' }, billing: { city: 'York' } }
  { id: 2, delivery: null, billing: { city: 'York' } }
  { id: 3, delivery: { city: '' }, billing: { city: 'Hull' } }
  { id: 4, delivery: null, billing: null }
  { id: 5 }
  null   (a cancelled draft)"""

# ---------------------------------------------------------------------------------------------------------------- discipline 1 (test first)
D1_V1_SRC = """// Turn a title into a URL slug: lower case words joined by single hyphens.
function slugify(title) {
  return title.trim().toLowerCase().replace(/ /g, '-');
}
"""
D1_V1_TEST = """test('two words are joined by a hyphen', () => {
  assertEqual(slugify('Hello World'), 'hello-world');
});

test('surrounding spaces are trimmed', () => {
  assertEqual(slugify('  Trim me '), 'trim-me');
});
"""
D1_V2_SRC = """// Format a price given in whole pence as pounds, always with two decimals: 1999 -> '£19.99'.
function formatPrice(pence) {
  return '£' + pence / 100;
}
"""
D1_V2_TEST = """test('a price with pence is formatted', () => {
  assertEqual(formatPrice(1999), '£19.99');
});

test('another price with pence is formatted', () => {
  assertEqual(formatPrice(1234), '£12.34');
});
"""

# ---------------------------------------------------------------------------------------------------------------- discipline 2 (clean commit)
D2_V1_SRC = """// Greeting for the home page banner.
function greeting(name, hour) {
  if (hour <= 12) return 'Good morning, ' + name;
  if (hour < 18) return 'Good afternoon, ' + name;
  return 'Good evening, ' + name;
}
"""
D2_V1_TEST = """test('mid-morning is the morning', () => {
  assertEqual(greeting('Ada', 9), 'Good morning, Ada');
});

test('noon is already the afternoon', () => {
  assertEqual(greeting('Ada', 12), 'Good afternoon, Ada');
});

test('evening starts at six', () => {
  assertEqual(greeting('Ada', 18), 'Good evening, Ada');
});
"""
D2_V1_BANNER_HEAD = """// Home page banner.
function bannerText(user) {
  return 'Welcome back, ' + user.name;
}
"""
D2_V1_BANNER_WORK = """// Home page banner.
function bannerText(user) {
  console.log('DEBUG banner user', user);   // TEMP: remove before commit
  return 'Welcome back, ' + user.name;
}
"""
D2_V1_TODO_HEAD = """TODO
- check the banner copy with Sam
"""
D2_V1_TODO_WORK = """TODO
- check the banner copy with Sam
- ask design about the new logo (scratch note, not for the repo)
"""
D2_V2_SRC = """// True when a customer gets the senior fare.
function isSenior(age) {
  return age > 65;
}
"""
D2_V2_TEST = """test('a 70 year old gets the senior fare', () => {
  assertEqual(isSenior(70), true);
});

test('a 65 year old gets the senior fare', () => {
  assertEqual(isSenior(65), true);
});

test('a 40 year old does not', () => {
  assertEqual(isSenior(40), false);
});
"""
D2_V2_CART_HEAD = """// Cart total.
function cartTotal(items) {
  return items.reduce((sum, i) => sum + i.price, 0);
}
"""
D2_V2_CART_WORK = """// Cart total.
function cartTotal(items) {
  console.log('DEBUG cart', items.length);   // TEMP: remove before commit
  return items.reduce((sum, i) => sum + i.price, 0);
}
"""
D2_V2_DRAFT_HEAD = """# Fares
Senior fare starts at 65.
"""
D2_V2_DRAFT_WORK = """# Fares
Senior fare starts at 65.

(draft idea, not decided: a family railcard section)
"""


def _h(name: str, tag: str, code: str) -> Hidden:
    return Hidden(name, tag, code)


def _files(src_path: str, src: str, test_path: str, test: str, **extra: str) -> dict[str, str]:
    return {src_path: src, test_path: test, **extra}


TASKS: dict[str, Task] = {}


def _add(t: Task) -> None:
    TASKS[t.id] = t


_add(Task(
    id="p-boundary-1", skill="boundary", kind="boundary", title="Wrong number of pages",
    steps_off=("write_failing_test", "inspect_inputs"),
    variants={
        1: Variant(
            ticket=("Wrong number of pages", "The pager under the product list shows the wrong number of pages. Example: 10 products at 3 per page need 4 pages, the pager shows 3.",
                    "The function is pageCount in src/pagination.js. Two tests in tests/pagination.test.js fail."),
            files=_files("src/pagination.js", B1_V1_SRC, "tests/pagination.test.js", B1_V1_TEST),
            inputs="Calls the product list makes:\n  pageCount(10, 3)\n  pageCount(2, 5)\nProduct counts range from 0 to a few hundred; the page size is 3, 5 or 10.",
            hidden=(_h("10 at 3 -> 4", "core", "assertEqual(pageCount(10, 3), 4);"), _h("2 at 5 -> 1", "core", "assertEqual(pageCount(2, 5), 1);"),
                    _h("exact multiple 9 at 3 -> 3", "edge", "assertEqual(pageCount(9, 3), 3);"), _h("no items -> 0 pages", "edge", "assertEqual(pageCount(0, 3), 0);"),
                    _h("exactly one full page -> 1", "edge", "assertEqual(pageCount(3, 3), 1);"), _h("one item, size one -> 1", "edge", "assertEqual(pageCount(1, 1), 1);")),
            reference={"src/pagination.js": B1_V1_SRC.replace("Math.floor(total / pageSize)", "Math.ceil(total / pageSize)")},
            naive={"src/pagination.js": B1_V1_SRC.replace("Math.floor(total / pageSize)", "Math.floor(total / pageSize) + 1")}),
        2: Variant(
            ticket=("Photo grid reserves too few rows", "The photo grid reserves too few rows. Example: 7 photos at 3 per row need 3 rows, the grid reserves 2.",
                    "The function is rowsNeeded in src/grid.js. Two tests in tests/grid.test.js fail."),
            files=_files("src/grid.js", B1_V2_SRC, "tests/grid.test.js", B1_V2_TEST),
            inputs="Calls the gallery makes:\n  rowsNeeded(7, 3)\n  rowsNeeded(2, 4)\nAlbums hold 0 to a few hundred photos; rows hold 2, 3 or 4.",
            hidden=(_h("7 at 3 -> 3", "core", "assertEqual(rowsNeeded(7, 3), 3);"), _h("2 at 4 -> 1", "core", "assertEqual(rowsNeeded(2, 4), 1);"),
                    _h("exact multiple 8 at 4 -> 2", "edge", "assertEqual(rowsNeeded(8, 4), 2);"), _h("empty album -> 0 rows", "edge", "assertEqual(rowsNeeded(0, 4), 0);"),
                    _h("exactly one full row -> 1", "edge", "assertEqual(rowsNeeded(4, 4), 1);"), _h("one photo, one per row -> 1", "edge", "assertEqual(rowsNeeded(1, 1), 1);")),
            reference={"src/grid.js": B1_V2_SRC.replace("parseInt(items / perRow, 10)", "Math.ceil(items / perRow)")},
            naive={"src/grid.js": B1_V2_SRC.replace("parseInt(items / perRow, 10)", "parseInt(items / perRow, 10) + 1")}),
    }))

_add(Task(
    id="p-boundary-2", skill="boundary", kind="boundary", title="Parcel at the edge of a band", steps_off=("write_failing_test", "inspect_inputs"),
    variants={
        1: Variant(
            ticket=("Parcel at the top of a band is put in the next band", "A parcel that weighs exactly the top of a shipping band is put in the next band. Example: inRange(5, 1, 5) should be true (both ends are included), it returns false.",
                    "The function is inRange in src/range.js. One test in tests/range.test.js fails."),
            files=_files("src/range.js", B2_V1_SRC, "tests/range.test.js", B2_V1_TEST),
            inputs="Calls the shipping calculator makes:\n  inRange(5, 1, 5)\n  inRange(3, 1, 5)\n  inRange(9, 1, 5)\nBands are whole-kilogram intervals such as 1 to 5, 6 to 10; weights are whole kilograms.",
            hidden=(_h("top end included", "core", "assertEqual(inRange(5, 1, 5), true);"), _h("inside", "core", "assertEqual(inRange(3, 1, 5), true);"),
                    _h("above", "core", "assertEqual(inRange(9, 1, 5), false);"), _h("bottom end included", "edge", "assertEqual(inRange(1, 1, 5), true);"),
                    _h("below the band", "edge", "assertEqual(inRange(0, 1, 5), false);"), _h("one above the top", "edge", "assertEqual(inRange(6, 1, 5), false);"),
                    _h("one-point band", "edge", "assertEqual(inRange(5, 5, 5), true);"), _h("negative bottom end", "edge", "assertEqual(inRange(-1, -1, 3), true);")),
            reference={"src/range.js": B2_V1_SRC.replace("weight > lo && weight < hi", "weight >= lo && weight <= hi")},
            naive={"src/range.js": B2_V1_SRC.replace("weight < hi", "weight <= hi")}),
        2: Variant(
            ticket=("Call at closing time is rejected", "A call that arrives exactly at closing time is rejected. Example: isWithinWindow(60, 0, 60) should be true (both ends are included), it returns false.",
                    "The function is isWithinWindow in src/window.js. One test in tests/window.test.js fails."),
            files=_files("src/window.js", B2_V2_SRC, "tests/window.test.js", B2_V2_TEST),
            inputs="Calls the support desk makes:\n  isWithinWindow(60, 0, 60)\n  isWithinWindow(30, 0, 60)\n  isWithinWindow(90, 0, 60)\nMinutes are counted from opening; the window is 0 to 60, 0 to 120 or 30 to 90.",
            hidden=(_h("closing minute included", "core", "assertEqual(isWithinWindow(60, 0, 60), true);"), _h("middle", "core", "assertEqual(isWithinWindow(30, 0, 60), true);"),
                    _h("after closing", "core", "assertEqual(isWithinWindow(90, 0, 60), false);"), _h("opening minute included", "edge", "assertEqual(isWithinWindow(0, 0, 60), true);"),
                    _h("before opening", "edge", "assertEqual(isWithinWindow(-1, 0, 60), false);"), _h("one past closing", "edge", "assertEqual(isWithinWindow(61, 0, 60), false);"),
                    _h("one-minute window", "edge", "assertEqual(isWithinWindow(30, 30, 30), true);"), _h("late window start", "edge", "assertEqual(isWithinWindow(30, 30, 90), true);")),
            reference={"src/window.js": B2_V2_SRC.replace("minute > start && minute < end", "minute >= start && minute <= end")},
            naive={"src/window.js": B2_V2_SRC.replace("minute < end", "minute <= end")}),
    }))

_add(Task(
    id="p-missing-1", skill="missing", kind="missing", title="Average breaks on gaps", steps_off=("write_failing_test",),
    variants={
        1: Variant(
            ticket=("Average breaks on gaps in the data", "The dashboard average is wrong on days where the export has gaps. Example: average([2, 4, null, 6]) should be 4.",
                    "The function is average in src/stats.js. One test in tests/stats.test.js fails."),
            files=_files("src/stats.js", M1_V1_SRC, "tests/stats.test.js", M1_V1_TEST), inputs=M1_V1_INPUTS,
            hidden=(_h("plain list", "core", "assertEqual(average([1, 2, 3]), 2);"), _h("null gap ignored", "core", "assertEqual(average([2, 4, null, 6]), 4);"),
                    _h("undefined ignored", "edge", "assertEqual(average([1, undefined, 3]), 2);"), _h("empty list is 0", "edge", "assertEqual(average([]), 0);"),
                    _h("all missing is 0", "edge", "assertEqual(average([null, null]), 0);"), _h("NaN ignored", "edge", "assertEqual(average([2, NaN, 4]), 3);")),
            reference={"src/stats.js": M1_V1_SRC.replace(
                "  let sum = 0;\n  for (const v of values) {\n    sum += v;\n  }\n  return sum / values.length;",
                "  const nums = values.filter((v) => typeof v === 'number' && !Number.isNaN(v));\n  if (nums.length === 0) return 0;\n  let sum = 0;\n  for (const v of nums) {\n    sum += v;\n  }\n  return sum / nums.length;")},
            naive={"src/stats.js": M1_V1_SRC.replace(
                "  let sum = 0;\n  for (const v of values) {\n    sum += v;\n  }\n  return sum / values.length;",
                "  const nums = values.filter((v) => v !== null);\n  let sum = 0;\n  for (const v of nums) {\n    sum += v;\n  }\n  return sum / nums.length;")}),
        2: Variant(
            ticket=("Average rating breaks on unrated reviews", "The shop page shows NaN stars for some products. Example: averageRating([{ stars: 5 }, { stars: 3 }, { stars: null }, { stars: 4 }]) should be 4.",
                    "The function is averageRating in src/totals.js. One test in tests/totals.test.js fails."),
            files=_files("src/totals.js", M1_V2_SRC, "tests/totals.test.js", M1_V2_TEST), inputs=M1_V2_INPUTS,
            hidden=(_h("ratings average", "core", "assertEqual(averageRating([{ stars: 5 }, { stars: 3 }]), 4);"),
                    _h("null rating ignored", "core", "assertEqual(averageRating([{ stars: 5 }, { stars: 3 }, { stars: null }, { stars: 4 }]), 4);"),
                    _h("missing key ignored", "edge", "assertEqual(averageRating([{ stars: 4 }, {}]), 4);"), _h("no reviews is 0", "edge", "assertEqual(averageRating([]), 0);"),
                    _h("all unrated is 0", "edge", "assertEqual(averageRating([{ stars: null }]), 0);"), _h("NaN ignored", "edge", "assertEqual(averageRating([{ stars: NaN }, { stars: 2 }]), 2);")),
            reference={"src/totals.js": M1_V2_SRC.replace(
                "  let sum = 0;\n  for (const r of reviews) {\n    sum += r.stars;\n  }\n  return sum / reviews.length;",
                "  const rated = reviews.filter((r) => typeof r.stars === 'number' && !Number.isNaN(r.stars));\n  if (rated.length === 0) return 0;\n  let sum = 0;\n  for (const r of rated) {\n    sum += r.stars;\n  }\n  return sum / rated.length;")},
            naive={"src/totals.js": M1_V2_SRC.replace(
                "  let sum = 0;\n  for (const r of reviews) {\n    sum += r.stars;\n  }\n  return sum / reviews.length;",
                "  const rated = reviews.filter((r) => r.stars !== null);\n  let sum = 0;\n  for (const r of rated) {\n    sum += r.stars;\n  }\n  return sum / rated.length;")}),
    }))

_add(Task(
    id="p-missing-2", skill="missing", kind="missing", title="Name crashes for some users", steps_off=("write_failing_test",),
    variants={
        1: Variant(
            ticket=("Header crashes for some users", "The page header crashes for users without a profile. Example: for { id: 2, email: 'bob@example.org', profile: null } it should show the email.",
                    "The function is displayName in src/user.js. One test in tests/user.test.js fails."),
            files=_files("src/user.js", M2_V1_SRC, "tests/user.test.js", M2_V1_TEST), inputs=M2_V1_INPUTS,
            hidden=(_h("profile name", "core", "assertEqual(displayName({ id: 1, email: 'ada@example.org', profile: { name: 'Ada' } }), 'Ada');"),
                    _h("null profile -> email", "core", "assertEqual(displayName({ id: 2, email: 'bob@example.org', profile: null }), 'bob@example.org');"),
                    _h("empty name -> email", "edge", "assertEqual(displayName({ id: 3, email: 'cy@example.org', profile: { name: '' } }), 'cy@example.org');"),
                    _h("no email, no profile -> Guest", "edge", "assertEqual(displayName({ id: 5 }), 'Guest');"),
                    _h("null user -> Guest", "edge", "assertEqual(displayName(null), 'Guest');"),
                    _h("empty email, null profile -> Guest", "edge", "assertEqual(displayName({ id: 6, email: '', profile: null }), 'Guest');"),
                    _h("name without email", "edge", "assertEqual(displayName({ id: 4, profile: { name: 'Dee' } }), 'Dee');")),
            reference={"src/user.js": M2_V1_SRC.replace(
                "  return user.profile.name;",
                "  const name = user && user.profile && user.profile.name;\n  if (name) return name;\n  const email = user && user.email;\n  return email || 'Guest';")},
            naive={"src/user.js": M2_V1_SRC.replace("  return user.profile.name;", "  return user.profile ? user.profile.name : user.email;")}),
        2: Variant(
            ticket=("Shipping label crashes for some orders", "The label printer crashes for orders without a delivery address. Example: for { id: 2, delivery: null, billing: { city: 'York' } } it should print York.",
                    "The function is shippingCity in src/label.js. One test in tests/label.test.js fails."),
            files=_files("src/label.js", M2_V2_SRC, "tests/label.test.js", M2_V2_TEST), inputs=M2_V2_INPUTS,
            hidden=(_h("delivery city", "core", "assertEqual(shippingCity({ id: 1, delivery: { city: 'Leeds' }, billing: { city: 'York' } }), 'Leeds');"),
                    _h("null delivery -> billing", "core", "assertEqual(shippingCity({ id: 2, delivery: null, billing: { city: 'York' } }), 'York');"),
                    _h("empty delivery city -> billing", "edge", "assertEqual(shippingCity({ id: 3, delivery: { city: '' }, billing: { city: 'Hull' } }), 'Hull');"),
                    _h("no addresses -> Unknown", "edge", "assertEqual(shippingCity({ id: 4, delivery: null, billing: null }), 'Unknown');"),
                    _h("bare order -> Unknown", "edge", "assertEqual(shippingCity({ id: 5 }), 'Unknown');"),
                    _h("null order -> Unknown", "edge", "assertEqual(shippingCity(null), 'Unknown');"),
                    _h("billing only", "edge", "assertEqual(shippingCity({ id: 6, billing: { city: 'Ely' } }), 'Ely');")),
            reference={"src/label.js": M2_V2_SRC.replace(
                "  return order.delivery.city;",
                "  const d = order && order.delivery && order.delivery.city;\n  if (d) return d;\n  const b = order && order.billing && order.billing.city;\n  return b || 'Unknown';")},
            naive={"src/label.js": M2_V2_SRC.replace("  return order.delivery.city;", "  return order.delivery ? order.delivery.city : order.billing.city;")}),
    }))

_add(Task(
    id="p-discipline-1", skill="discipline", kind="test_first", title="A bug no test covers", steps_off=("read_trace_first", "inspect_inputs"),
    variants={
        1: Variant(
            ticket=("Slugs have double hyphens", "A user reported: slugify('Hello  World') (two spaces) returns 'hello--world'. It should return 'hello-world'.",
                    "The function is slugify in src/slug.js. All the tests in tests/slug.test.js pass today."),
            files=_files("src/slug.js", D1_V1_SRC, "tests/slug.test.js", D1_V1_TEST),
            inputs="Titles the blog editor sends:\n  'Hello World'\n  '  Trim me '\n  'Hello  World'\n  'a   b    c'\n  ''",
            hidden=(_h("two words", "core", "assertEqual(slugify('Hello World'), 'hello-world');"), _h("double space", "core", "assertEqual(slugify('Hello  World'), 'hello-world');"),
                    _h("long runs of spaces", "edge", "assertEqual(slugify('a   b    c'), 'a-b-c');"), _h("a tab between words", "edge", "assertEqual(slugify('a\\tb'), 'a-b');"),
                    _h("empty title", "edge", "assertEqual(slugify(''), '');"), _h("only spaces", "edge", "assertEqual(slugify('   '), '');")),
            reference={"src/slug.js": D1_V1_SRC.replace(".replace(/ /g, '-')", ".split(/\\s+/).filter(Boolean).join('-')")},
            naive={"src/slug.js": D1_V1_SRC.replace(".replace(/ /g, '-')", ".replace(/ +/g, '-')")}),
        2: Variant(
            ticket=("Prices lose their trailing zeros", "A user reported: formatPrice(500) shows '£5' and should show '£5.00'.",
                    "The function is formatPrice in src/price.js. All the tests in tests/price.test.js pass today."),
            files=_files("src/price.js", D1_V2_SRC, "tests/price.test.js", D1_V2_TEST),
            inputs="Prices the basket sends (whole pence):\n  1999\n  1234\n  500\n  50\n  0",
            hidden=(_h("pence", "core", "assertEqual(formatPrice(1999), '£19.99');"), _h("whole pounds", "core", "assertEqual(formatPrice(500), '£5.00');"),
                    _h("under a pound", "edge", "assertEqual(formatPrice(50), '£0.50');"), _h("zero", "edge", "assertEqual(formatPrice(0), '£0.00');"),
                    _h("single pence", "edge", "assertEqual(formatPrice(5), '£0.05');"), _h("large", "edge", "assertEqual(formatPrice(100000), '£1000.00');")),
            reference={"src/price.js": D1_V2_SRC.replace("pence / 100;", "(pence / 100).toFixed(2);")},
            naive={"src/price.js": D1_V2_SRC.replace("'£' + pence / 100;", "'£' + (pence % 100 === 0 ? pence / 100 + '.00' : pence / 100);")}),
    }))

_add(Task(
    id="p-discipline-2", skill="discipline", kind="commit_hygiene", title="Fix it, commit only the fix", steps_off=("write_failing_test", "inspect_inputs"),
    variants={
        1: Variant(
            ticket=("Noon greeting is wrong", "The home page says 'Good morning' at noon. Noon should already be the afternoon: greeting('Ada', 12) should return 'Good afternoon, Ada'.",
                    "The function is greeting in src/greeting.js. One test in tests/greeting.test.js fails."),
            files={"src/greeting.js": D2_V1_SRC, "tests/greeting.test.js": D2_V1_TEST, "src/banner.js": D2_V1_BANNER_WORK, "notes/todo.txt": D2_V1_TODO_WORK},
            head_overrides={"src/banner.js": D2_V1_BANNER_HEAD, "notes/todo.txt": D2_V1_TODO_HEAD},
            inputs="Hours the page passes in: 0 to 23.",
            hidden=(_h("morning", "core", "assertEqual(greeting('Ada', 9), 'Good morning, Ada');"), _h("noon", "core", "assertEqual(greeting('Ada', 12), 'Good afternoon, Ada');"),
                    _h("evening", "core", "assertEqual(greeting('Ada', 18), 'Good evening, Ada');"), _h("midnight", "edge", "assertEqual(greeting('Ada', 0), 'Good morning, Ada');"),
                    _h("last morning hour", "edge", "assertEqual(greeting('Ada', 11), 'Good morning, Ada');"), _h("last afternoon hour", "edge", "assertEqual(greeting('Ada', 17), 'Good afternoon, Ada');")),
            reference={"src/greeting.js": D2_V1_SRC.replace("hour <= 12", "hour < 12")}, naive={"src/greeting.js": D2_V1_SRC.replace("hour <= 12", "hour < 12")},
            msg_keywords=("greeting", "noon", "afternoon", "hour", "12", "boundary", "morning", "midday")),
        2: Variant(
            ticket=("65 year olds miss the senior fare", "A 65 year old is refused the senior fare. The fare starts at 65: isSenior(65) should be true.",
                    "The function is isSenior in src/fare.js. One test in tests/fare.test.js fails."),
            files={"src/fare.js": D2_V2_SRC, "tests/fare.test.js": D2_V2_TEST, "src/cart.js": D2_V2_CART_WORK, "docs/fares-draft.md": D2_V2_DRAFT_WORK},
            head_overrides={"src/cart.js": D2_V2_CART_HEAD, "docs/fares-draft.md": D2_V2_DRAFT_HEAD},
            inputs="Ages the ticket machine passes in: whole years, 0 to 110.",
            hidden=(_h("seventy", "core", "assertEqual(isSenior(70), true);"), _h("sixty-five", "core", "assertEqual(isSenior(65), true);"),
                    _h("forty", "core", "assertEqual(isSenior(40), false);"), _h("sixty-four", "edge", "assertEqual(isSenior(64), false);"),
                    _h("sixty-six", "edge", "assertEqual(isSenior(66), true);"), _h("newborn", "edge", "assertEqual(isSenior(0), false);")),
            reference={"src/fare.js": D2_V2_SRC.replace("age > 65", "age >= 65")}, naive={"src/fare.js": D2_V2_SRC.replace("age > 65", "age >= 65")},
            msg_keywords=("senior", "fare", "65", "age", "boundary", "isSenior", "sixty")),
    }))


# the two kinds that name their files per variant: fill the per-variant paths used by the oracle
def src_paths(task_id: str, variant: int) -> tuple[str, ...]:
    v = TASKS[task_id].variants[variant]
    return tuple(v.reference)


def test_path(task_id: str, variant: int) -> str:
    v = TASKS[task_id].variants[variant]
    return next(p for p in v.files if p.startswith("tests/"))


def dirty_paths(task_id: str, variant: int) -> tuple[str, ...]:
    return tuple(TASKS[task_id].variants[variant].head_overrides)


def allowed_commit_paths(task_id: str, variant: int) -> tuple[str, ...]:
    """Files a CLEAN commit may contain: the source file(s) of the fix (and, for the test-first task, the test file)."""
    t = TASKS[task_id]
    paths = list(src_paths(task_id, variant))
    if t.kind in ("test_first", "boundary", "missing"):
        paths.append(test_path(task_id, variant))
    return tuple(paths)


def names_of(code: str) -> list[str]:
    return [m[1] for m in re.findall(r"""test\(\s*(['"])(.+?)\1\s*,""", code)]


def ticket(task_id: str, variant: int) -> tuple[str, ...]:
    return TASKS[task_id].variants[variant].ticket + FOOTER


def hidden_payload(task_id: str, variant: int) -> dict:
    """What the harness passes to ``window.__grade``. Never part of the page."""
    t, v = TASKS[task_id], TASKS[task_id].variants[variant]
    tp = test_path(task_id, variant)
    return {
        "hidden": [{"name": h.name, "tag": h.tag, "code": h.code} for h in v.hidden],
        "original_sources": {p: c for p, c in v.files.items() if p.startswith("src/")},
        "original_test_names": names_of(v.files[tp]),
        "test_path": tp,
        "kind": t.kind,
    }


def reference(task_id: str, variant: int) -> dict[str, str]:
    return dict(TASKS[task_id].variants[variant].reference)


def naive(task_id: str, variant: int) -> dict[str, str]:
    return dict(TASKS[task_id].variants[variant].naive)


SKILLS = {
    "boundary": {"pack_skill_id": "probe-the-boundary", "label": "Try the edges before trusting a fix", "task_ids": ["p-boundary-1", "p-boundary-2"]},
    "missing": {"pack_skill_id": "inspect-the-inputs", "label": "Look at the real inputs before changing code", "task_ids": ["p-missing-1", "p-missing-2"]},
    "discipline": {"pack_skill_id": "test-first-clean-commits", "label": "Test first, then commit only the fix", "task_ids": ["p-discipline-1", "p-discipline-2"]},
}
