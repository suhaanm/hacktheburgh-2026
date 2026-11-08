#!/usr/bin/env python
"""Standalone role pack validator (ROL-1) until the engine's loader exists.

    uv run python packages/packs/validate.py              # every pack, plus the schema examples
    uv run python packages/packs/validate.py PACK_DIR ... # specific pack directories
    uv run python packages/packs/validate.py --quiet

Checks, per pack: every YAML and JSON file under the pack parses (a silent parse failure would degrade
loaders to "no checklist"); pack.yaml against packages/schema/pack.schema.json; every file it points at
against the matching sub-schema; cross-file references (cogs, zones, skills, templates, sites); the
mapping's test vectors through the reference mapper (refmap.py). Across packs: the three packs differ
visibly. Exit code 1 on any error.
"""
from __future__ import annotations

import json
import re
import sys
from collections import deque
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCHEMA_DIR = ROOT / "packages" / "schema"

sys.path.insert(0, str(HERE))
from refmap import map_events  # noqa: E402

BASE_ZONES = ("doc", "form_field", "search_box", "query_edit", "compare_view", "check_box", "decision_btn", "help")
MATCH_KEYS = ("type", "zone", "role", "source")
BASE_COGS = ("READ", "SEARCH", "REFORMULATE", "NAVIGATE", "ENTER", "COPY", "PASTE",
             "COMPARE", "CHECK", "DECIDE", "IDLE", "REVERT", "ASK")
QUESTION_IDS = ["tools", "risky", "tone", "pace", "hours"]
TASK_FILES = {"task.yaml": "task", "household_generator.yaml": "household_generator", "sites.yaml": "sites"}


# ---------------------------------------------------------------- loading helpers

def load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


_PACK_SCHEMA: dict | None = None


def pack_schema() -> dict:
    global _PACK_SCHEMA
    if _PACK_SCHEMA is None:
        _PACK_SCHEMA = load_json(SCHEMA_DIR / "pack.schema.json")
    return _PACK_SCHEMA


def def_validator(name: str) -> Draft202012Validator:
    """Validator for one of the $defs in pack.schema.json (sub-file schemas)."""
    return Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": pack_schema()["$defs"]})


def schema_errors(validator: Draft202012Validator, data: Any, where: str) -> list[str]:
    out = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(map(str, e.absolute_path))):
        path = "/".join(str(p) for p in err.absolute_path) or "(root)"
        out.append(f"{where}: {path}: {err.message[:300]}")
    return out


# ---------------------------------------------------------------- helpers for the zone config

def _as_list(v: Any) -> list:
    return v if isinstance(v, list) else [v]


def _check_capture(pack: str, site: str, cap: dict, zones: set[str]) -> list[str]:
    """Zones named in a capture config must be in the vocabulary and every selector must look like CSS."""
    errs: list[str] = []
    named: list[str] = [cap["nav_default"], cap["tab_default"]]
    named += [r["zone"] for key in ("nav", "tab", "page") for r in cap.get(key, [])]
    named += [r["zone"] for r in cap["elements"]]
    for z in named:
        if z not in zones:
            errs.append(f"{pack}: capture config for site {site}: zone {z!r} is not in the pack's zone vocabulary")
    mk = cap.get("markers") or {}
    if mk.get("task_start") and mk["task_start"]["zone"] not in zones:
        errs.append(f"{pack}: capture config for site {site}: markers.task_start zone {mk['task_start']['zone']!r} is not in the pack's zone vocabulary")
    if mk.get("progress") and not mk.get("task_start"):
        errs.append(f"{pack}: capture config for site {site}: progress markers without a task_start marker")
    selectors = [r["when"] for key in ("nav", "tab", "page") for r in cap.get(key, [])] + [r["selector"] for r in cap["elements"]]
    selectors += [r["when"] for r in mk.get("progress", [])] + ([mk["task_end"]["when"]] if mk.get("task_end") else [])
    for sel in selectors:
        if sel.count("[") != sel.count("]") or sel.count("(") != sel.count(")") or sel.count('"') % 2:
            errs.append(f"{pack}: capture config for site {site}: selector {sel!r} has unbalanced brackets or quotes")
    return errs


def _zone_used_by_capture(pack_dir: Path, pack: dict, mapping: dict, zone: str) -> bool:
    """A zone is live if some capture config can emit it (mapping capture_sites or tasks/sites.yaml)."""
    caps = list(mapping.get("capture_sites", []))
    if "tasks" in pack:
        sites_file = pack_dir / pack["tasks"] / "sites.yaml"
        if sites_file.is_file():
            try:
                caps += [s["capture"] for s in load_yaml(sites_file)["sites"] if "capture" in s]
            except Exception:  # noqa: BLE001
                pass
    for cap in caps:
        if zone in (cap["nav_default"], cap["tab_default"]):
            return True
        if any(r["zone"] == zone for key in ("nav", "tab", "page", "elements") for r in cap.get(key, [])):
            return True
    return zone in BASE_ZONES  # base zones are also derived from ARIA roles by the extension itself


def parse_all_files(pack_dir: Path) -> list[str]:
    """Every .yaml, .yml and .json file under the pack must parse."""
    errs: list[str] = []
    for path in sorted(pack_dir.rglob("*")):
        if path.is_file() and path.suffix in (".yaml", ".yml", ".json"):
            try:
                load_json(path) if path.suffix == ".json" else load_yaml(path)
            except (yaml.YAMLError, json.JSONDecodeError, UnicodeDecodeError) as e:
                first = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
                errs.append(f"{pack_dir.name}/{path.relative_to(pack_dir)}: does not parse: {first}")
    return errs


# ---------------------------------------------------------------- one pack

def validate_pack(pack_dir: Path) -> list[str]:
    """Return a list of error strings for one pack directory (empty list means valid)."""
    pack_dir = Path(pack_dir)
    errs: list[str] = []
    name = pack_dir.name
    pack_yaml = pack_dir / "pack.yaml"
    if not pack_yaml.is_file():
        return [f"{name}: pack.yaml missing"]
    parse_errs = parse_all_files(pack_dir)
    if parse_errs:
        return parse_errs
    pack = load_yaml(pack_yaml)

    errs += schema_errors(Draft202012Validator(pack_schema()), pack, f"{name}/pack.yaml")
    if errs:
        return errs  # structure is wrong; cross checks would only add noise

    if pack["id"] != name:
        errs.append(f"{name}/pack.yaml: id {pack['id']!r} must equal the directory name")

    # --- onboarding
    qs = pack["onboarding"]["questions"]
    if [q["id"] for q in qs] != QUESTION_IDS:
        errs.append(f"{name}: onboarding question ids must be {QUESTION_IDS} in order, got {[q['id'] for q in qs]}")
    for q in qs:
        if q["kind"] in ("multi", "single"):
            values = [o["value"] for o in q["options"]]
            if len(values) != len(set(values)):
                errs.append(f"{name}: question {q['id']} has duplicate option values")
            if q["kind"] == "single" and sum(1 for o in q["options"] if o.get("default")) != 1:
                errs.append(f"{name}: single question {q['id']} must have exactly one default option")
        if q["id"] == "risky":
            for o in q["options"]:
                if "risk_class" not in o or "patterns" not in o:
                    errs.append(f"{name}: risky option {o['value']} needs risk_class and patterns")
        if q["id"] in ("tone", "pace") and q["kind"] != "single":
            errs.append(f"{name}: question {q['id']} must be kind single")
        if q["id"] == "hours" and q["kind"] != "hours":
            errs.append(f"{name}: question hours must be kind hours")
        if q["id"] in ("tools", "risky") and q["kind"] != "multi":
            errs.append(f"{name}: question {q['id']} must be kind multi")

    # --- referenced files
    def need(rel: str, schema_def: str, label: str, kind: str = "yaml") -> Any:
        path = pack_dir / rel
        if not path.is_file():
            errs.append(f"{name}: {label} file {rel} is missing")
            return None
        try:
            data = load_yaml(path) if kind == "yaml" else load_json(path)
        except (yaml.YAMLError, json.JSONDecodeError) as e:
            errs.append(f"{name}/{rel}: cannot parse: {e}")
            return None
        errs.extend(schema_errors(def_validator(schema_def), data, f"{name}/{rel}"))
        return data

    mapping = need(pack["cogs"]["mapping"], "mapping", "mapping")
    steps = need(pack["expert_policy"]["steps"], "expert_steps", "expert steps") if "expert_policy" in pack else None
    routines = need(pack["routines"], "routine_templates", "routines")
    curriculum = need(pack["curriculum"], "curriculum", "curriculum")
    persona = need(pack["persona"], "persona", "persona")
    priors = need(pack["priors"], "priors", "priors")
    sensitive = need(pack["risk_classes"]["sensitive_fields"], "sensitive_fields", "sensitive fields", "json")
    habits = need(pack["habits"], "habits", "habits") if "habits" in pack else None

    if "tasks" in pack:
        tasks_dir = pack_dir / pack["tasks"]
        if not tasks_dir.is_dir():
            errs.append(f"{name}: tasks directory {pack['tasks']} is missing")
        else:
            for fname, sdef in TASK_FILES.items():
                need(f"{pack['tasks'].rstrip('/')}/{fname}", sdef, f"task file {fname}")

    extra = list(pack["cogs"]["extra"])
    all_cogs = set(BASE_COGS) | set(extra)
    for c in extra:
        if c in BASE_COGS:
            errs.append(f"{name}: extra cog {c} duplicates a base cog")

    def check_cogs(cogs: list[str], where: str) -> None:
        for c in cogs:
            if c not in all_cogs:
                errs.append(f"{name}: {where}: unknown cog {c}")

    # --- risk classes and sensitive patterns
    for cls in ("irreversible", "outward"):
        for pat in pack["risk_classes"][cls]:
            try:
                re.compile(pat, re.I)
            except re.error as e:
                errs.append(f"{name}: risk_classes.{cls} pattern {pat!r} is not a regex: {e}")
    global_sensitive = load_json(SCHEMA_DIR / "sensitive_fields.json")
    sens_patterns: list[re.Pattern] = []
    for src in (global_sensitive, sensitive or {}):
        for pat in src.get("patterns", []):
            try:
                sens_patterns.append(re.compile(pat, re.I))
            except re.error as e:
                errs.append(f"{name}: sensitive pattern {pat!r} is not a regex: {e}")

    # --- mapping (engine default_mapping.yaml format; zones are enums, no page text)
    zones: set[str] = set()
    site_ids: set[str] = set()
    if mapping and not errs:
        zones = set(mapping["zones"])
        if list(mapping["extra_cogs"]) != extra:
            errs.append(f"{name}: mapping extra_cogs {mapping['extra_cogs']} must equal pack.yaml cogs.extra {extra}")
        for z in BASE_ZONES:
            if z not in zones:
                errs.append(f"{name}: mapping zones must include the base zone {z}")
        produced: set[str] = set()
        used_zones: set[str] = set()
        for i, rule in enumerate(mapping["rules"]):
            where = f"mapping rule #{i + 1}"
            cog = rule["cog"]
            if cog is not None:
                check_cogs([cog], where)
                produced.add(cog)
            if "reformulate_as" in rule:
                check_cogs([rule["reformulate_as"]], f"{where}.reformulate_as")
            for z in _as_list(rule["match"].get("zone", [])):
                used_zones.add(z)
                if z not in zones:
                    errs.append(f"{name}: {where}: zone {z!r} is not in the pack's zone vocabulary")
        for c in extra:
            if c not in produced:
                errs.append(f"{name}: extra cog {c} is never produced by a mapping rule")
        for z in sorted(zones - used_zones):
            if not _zone_used_by_capture(pack_dir, pack, mapping, z):
                errs.append(f"{name}: zone {z!r} is listed but no rule or capture config uses it")
        # capture config (thin packs here, deep packs in tasks/sites.yaml)
        for cs in mapping.get("capture_sites", []):
            site_ids.add(cs["id"])
            errs += _check_capture(name, cs["id"], cs, zones)
        for ex in mapping.get("examples", []):
            if len(ex["events"]) != len(ex["expect"]):
                errs.append(f"{name}: mapping example {ex['name']!r}: events and expect differ in length")
                continue
            for ev in ex["events"]:
                z = (ev.get("meta") or {}).get("zone")
                if z is not None and z not in zones:
                    errs.append(f"{name}: mapping example {ex['name']!r}: zone {z!r} is not in the vocabulary")
            got = map_events(mapping, ex["events"])
            if got != ex["expect"]:
                errs.append(f"{name}: mapping example {ex['name']!r}: expected {ex['expect']} but reference mapper gave {got}")
        if not mapping.get("examples"):
            errs.append(f"{name}: mapping.yaml has no test vectors (examples)")

    # --- onboarding tools options name capture sites; those must exist
    if "tasks" in pack and (pack_dir / pack["tasks"] / "sites.yaml").is_file():
        try:
            for st in load_yaml(pack_dir / pack["tasks"] / "sites.yaml")["sites"]:
                site_ids.add(st["id"])
        except Exception:  # noqa: BLE001  (already reported by schema validation)
            pass
    if mapping and site_ids:
        for q in qs:
            for o in q.get("options", []):
                if "site" in o and o["site"] not in site_ids:
                    errs.append(f"{name}: onboarding option {o['value']}: site {o['site']!r} is not a capture site")

    # --- curriculum
    skill_ids: set[str] = set()
    if curriculum and not errs:
        sk = curriculum["skills"]
        skill_ids = {s["id"] for s in sk}
        if len(skill_ids) != len(sk):
            errs.append(f"{name}: curriculum has duplicate skill ids")
        if sorted(s["order"] for s in sk) != list(range(1, len(sk) + 1)):
            errs.append(f"{name}: curriculum order must be 1..{len(sk)} without gaps")
        for s in sk:
            check_cogs(s["cogs"], f"curriculum skill {s['id']}")
            for p in s["prerequisites"]:
                if p not in skill_ids:
                    errs.append(f"{name}: curriculum skill {s['id']}: unknown prerequisite {p}")
                elif next(x for x in sk if x["id"] == p)["order"] >= s["order"]:
                    errs.append(f"{name}: curriculum skill {s['id']}: prerequisite {p} must come earlier")

    # --- expert steps
    if steps and not errs:
        check_ids = [c["id"] for c in steps["checks"]]
        if len(check_ids) != len(set(check_ids)):
            errs.append(f"{name}: expert steps have duplicate check ids")
        ids = set(check_ids)
        graph = {c["id"]: list(c["after"]) for c in steps["checks"]}
        for c in steps["checks"]:
            check_cogs(c["cogs"], f"expert check {c['id']}")
            for a in c["after"]:
                if a not in ids:
                    errs.append(f"{name}: expert check {c['id']}: unknown 'after' {a}")
            if "skill" in c and curriculum and c["skill"] not in skill_ids:
                errs.append(f"{name}: expert check {c['id']}: unknown skill {c['skill']}")
            if c.get("critical") and not c["required"] and not any(c["id"] in o["after"] for o in steps["checks"]):
                # a critical check that is not required is a CRITICAL GATE: the coach insists on it when a later check is started without it.
                # With no later check to start, nothing could ever make it matter.
                errs.append(f"{name}: expert check {c['id']} is critical but not required, and no check lists it in 'after' (a critical gate needs a check it gates)")
            tgt = (c.get("coach") or {}).get("target")
            if tgt and mapping:
                # the ring the coach or Cue draws for this check: its zone must be one the mapping turns into the check's first cog
                first_zones = {z for r in mapping["rules"] if r["cog"] == c["cogs"][0] for z in _as_list(r["match"].get("zone", []))}
                if tgt["zone"] not in zones:
                    errs.append(f"{name}: expert check {c['id']}: coach.target zone {tgt['zone']!r} is not in the pack's zone vocabulary")
                elif tgt["zone"] not in first_zones:
                    errs.append(f"{name}: expert check {c['id']}: coach.target zone {tgt['zone']!r} is not a zone the mapping turns into {c['cogs'][0]}")
        errs += _check_families(name, steps["checks"])
        if _has_cycle(graph):
            errs.append(f"{name}: expert steps 'after' relations contain a cycle")
        for r in steps.get("allowed_reorderings", []):
            for m in r.get("permutable", []):
                if m not in ids:
                    errs.append(f"{name}: allowed_reordering {r['id']}: unknown check {m}")
        if steps["coverage"] != pack["expert_policy"]["coverage"]:
            errs.append(f"{name}: expert steps coverage {steps['coverage']!r} disagrees with pack.yaml")

    # --- routines
    template_ids: set[str] = set()
    if routines and not errs:
        for t in routines["templates"]:
            if t["id"] in template_ids:
                errs.append(f"{name}: duplicate routine template {t['id']}")
            template_ids.add(t["id"])
            check_cogs(t["cogs"], f"routine template {t['id']}")
            check_cogs(t.get("skill_cogs", []), f"routine template {t['id']}.skill_cogs")
            check_cogs(t.get("judgement_cogs", []), f"routine template {t['id']}.judgement_cogs")
            for c in t.get("skill_cogs", []):
                if c not in t["cogs"]:
                    errs.append(f"{name}: routine template {t['id']}: skill_cog {c} is not in its cogs")
            if t["learning_relevant"] and not t.get("skill_cogs"):
                errs.append(f"{name}: routine template {t['id']}: learning_relevant needs skill_cogs")
            if len(set(t["cogs"])) < 2:
                errs.append(f"{name}: routine template {t['id']}: a template of one repeated cog is not matchable")
        check_cogs(routines.get("defaults", {}).get("judgement_cogs", []), "routines.defaults.judgement_cogs")
        errs += _check_template_extras(name, routines)

    # --- persona
    if persona and not errs:
        check_cogs(list(persona["cog_dwell_s"]), "persona.cog_dwell_s")
        for d in persona["apprentice"]["deficits"]:
            check_cogs(d["cogs"], f"persona deficit {d['id']}")
            if "insert_before" in d:
                check_cogs([d["insert_before"]], f"persona deficit {d['id']}.insert_before")
            if d["kind"] == "insert" and "insert_before" not in d:
                errs.append(f"{name}: persona deficit {d['id']}: kind insert needs insert_before")
            if d["kind"] == "slow" and "multiplier" not in d:
                errs.append(f"{name}: persona deficit {d['id']}: kind slow needs multiplier")
            if curriculum and d["skill"] not in skill_ids:
                errs.append(f"{name}: persona deficit {d['id']}: unknown skill {d['skill']}")
        for r in persona["planted_routines"]:
            if routines and r["template"] not in template_ids:
                errs.append(f"{name}: persona planted routine {r['id']}: unknown template {r['template']}")

    if priors and not errs:
        check_cogs(list(priors.get("cog_dwell_s", {})), "priors.cog_dwell_s")

    # --- deeper onboarding, connection suggestions, habits (role-depth content; every key is optional)
    if not errs:
        errs += _check_followups(name, pack)
        errs += _check_suggest_connections(name, pack)
        if habits:
            errs += _check_habits(name, habits, skill_ids, all_cogs)
    if not errs and pack["depth"] == "standard":
        errs += _check_standard(name, pack, mapping, steps, routines, curriculum, habits)

    # --- tasks (deep packs)
    if pack["depth"] == "deep" and "tasks" in pack and not errs:
        sites = load_yaml(pack_dir / pack["tasks"] / "sites.yaml")
        ports = [s["port"] for s in sites["sites"]]
        if not set(ports) <= {7801, 7802, 7803}:
            errs.append(f"{name}: sites.yaml ports must be within 7801 to 7803")
        for s in sites["sites"]:
            if "capture" in s:
                errs += _check_capture(name, s["id"], s["capture"], zones)
            if s["kind"] == "case_note" and s.get("served_by") not in {x["id"] for x in sites["sites"] if x["kind"] == "calculator"}:
                errs.append(f"{name}: sites.yaml: case_note must name the calculator that serves it (served_by)")
        task = load_yaml(pack_dir / pack["tasks"] / "task.yaml")
        if persona and task["id"] != persona.get("task"):
            errs.append(f"{name}: persona.task {persona.get('task')!r} must equal tasks/task.yaml id {task['id']!r}")
        if steps and task["id"] != steps["task"]:
            errs.append(f"{name}: expert_steps.task {steps['task']!r} must equal tasks/task.yaml id {task['id']!r}")
        calc_ids = {s["id"] for s in sites["sites"] if s["kind"] == "calculator"}
        for tok in task["goal_tokens"]:
            m = re.fullmatch(r"\{result:(\w+)@(\w+)\}", tok)
            if m and (m.group(1) not in task["result_fields"] or m.group(2) not in calc_ids):
                errs.append(f"{name}: task goal token {tok} names an unknown result field or site")
        gen = load_yaml(pack_dir / pack["tasks"] / "household_generator.yaml")
        cliff_ids = {c["id"] for c in gen["cliffs"]}
        for a in gen["archetypes"]:
            if "plants" in a and a["plants"] not in cliff_ids:
                errs.append(f"{name}: household_generator archetype {a['id']} plants unknown cliff {a['plants']}")
    # --- depth and coverage must agree. The schema already makes a thin pack's coverage stub; a standard pack (like a deep one) needs full
    cov = (pack.get("expert_policy") or {}).get("coverage")
    if pack["depth"] in ("standard", "deep") and cov != "full":
        errs.append(f"{name}: depth {pack['depth']} needs expert_policy.coverage full")
    # --- the oracle label must say what it is
    if "oracle" in pack and "not law" not in pack.get("oracle_note", "").lower():
        errs.append(f"{name}: pack.yaml has an oracle but oracle_note does not say it is simplified and not law")
    return errs


# ---------------------------------------------------------------- role-depth checks (optional pack content)

# What a `depth: standard` pack must carry (the schema describes the level; this is the measurable floor). Not a quality bar: the content is
# hand-written from the job and a validator cannot tell good from thin, only absent from present.
STANDARD_MINIMUM = {"cogs": 15, "checks": 15, "skills": 10, "templates": 8, "followups": 4, "habits": 8}

# routines/finder.py FinderConfig.min_len: "skeletons shorter than this are never a routine". A template shorter than this (repeats merged, as the
# finder merges them) could never be found or matched; a test in the engine keeps this number equal to the finder's.
FINDER_MIN_LEN = 4
FINDER_DROP = frozenset({"IDLE", "REVERT", "REFORMULATE"})      # routines/finder.py DROP_COGS: left out of a skeleton before it is measured


def _check_families(name: str, checks: list[dict]) -> list[str]:
    """A check with a `family` is an addition to the policy of the pack's one task. It must not be able to touch what the policy already
    scores: optional (so end-of-task skill tracing, which scores required checks, ignores it), starting with a cog no family-less check uses
    (so it is never started, partly matched or violated by a task that has no such cog), and never waited for by a family-less check."""
    errs: list[str] = []
    base = [c for c in checks if "family" not in c]
    base_cogs = {g for c in base for g in c["cogs"]}
    family_ids = {c["id"] for c in checks if "family" in c}
    for c in checks:
        if "family" not in c:
            late = [a for a in c["after"] if a in family_ids]
            if late:
                errs.append(f"{name}: expert check {c['id']} has no family but waits for family check(s) {late}")
            continue
        if c["required"]:
            errs.append(f"{name}: expert check {c['id']} has a family so it must be optional (required: false)")
        if c["cogs"][0] in base_cogs:
            errs.append(f"{name}: expert check {c['id']} has a family so its first cog {c['cogs'][0]} must not be used by any check without one")
    return errs


def _merged_len(cogs: list[str]) -> int:
    """The length of a skeleton the way the finder measures it: some cogs dropped, then repeats merged."""
    kept = [c for c in cogs if c not in FINDER_DROP]
    return sum(1 for i, c in enumerate(kept) if i == 0 or c != kept[i - 1])


def _check_template_extras(name: str, routines: dict) -> list[str]:
    """irreversibility, judgement_share, steps and tools are optional; when given they must agree with the rest of the template.
    Every template, old or new, must be long enough for the finder to ever report it."""
    errs: list[str] = []
    default_j = set((routines.get("defaults") or {}).get("judgement_cogs", []))
    for t in routines["templates"]:
        if _merged_len(t["cogs"]) < FINDER_MIN_LEN:
            errs.append(f"{name}: routine template {t['id']}: {_merged_len(t['cogs'])} steps once repeats are merged, but the routine finder never reports "
                        f"fewer than {FINDER_MIN_LEN}, so it could never be found")
        if "judgement_share" in t:
            j = default_j | set(t.get("judgement_cogs", []))
            want = round(sum(1 for c in t["cogs"] if c in j) / len(t["cogs"]), 2)
            if abs(want - t["judgement_share"]) > 0.011:
                errs.append(f"{name}: routine template {t['id']}: judgement_share {t['judgement_share']} but its cogs give {want} (the hit list's own formula)")
        if t.get("irreversibility") == "irreversible" and t["automatable"]:
            errs.append(f"{name}: routine template {t['id']}: an irreversible routine must not be automatable")
    return errs


def _question_options(pack: dict) -> dict[str, dict[str, dict]]:
    """question id -> option value -> option, for the five fixed questions and the follow-ups."""
    out: dict[str, dict[str, dict]] = {}
    for q in pack["onboarding"]["questions"]:
        out[q["id"]] = {o["value"]: o for o in q.get("options", [])}
    for f in pack["onboarding"].get("followups", []):
        out[f["id"]] = {o["value"]: o for o in f["options"]}
    return out


def _check_followups(name: str, pack: dict) -> list[str]:
    errs: list[str] = []
    fus = pack["onboarding"].get("followups", [])
    if not fus:
        return errs
    ids = [f["id"] for f in fus]
    if len(ids) != len(set(ids)):
        errs.append(f"{name}: onboarding followups have duplicate ids")
    fixed = {q["id"]: {o["value"] for o in q.get("options", [])} for q in pack["onboarding"]["questions"]}
    for f in fus:
        if f["id"] in QUESTION_IDS:
            errs.append(f"{name}: followup id {f['id']!r} is one of the five fixed question ids")
        values = [o["value"] for o in f["options"]]
        if len(values) != len(set(values)):
            errs.append(f"{name}: followup {f['id']} has duplicate option values")
        defaults = sum(1 for o in f["options"] if o.get("default"))
        if f["kind"] == "single" and defaults != 1:
            errs.append(f"{name}: single followup {f['id']} must have exactly one default option")
        for o in f["options"]:
            sets = o.get("sets") or {}
            for key in ("pace", "tone"):
                if key in sets and sets[key] not in fixed[key]:
                    errs.append(f"{name}: followup {f['id']} option {o['value']}: sets {key}={sets[key]!r}, which the pack's {key} question does not offer")
            for p in o.get("patterns", []):
                try:
                    re.compile(p, re.I)
                except re.error as e:
                    errs.append(f"{name}: followup {f['id']} option {o['value']}: pattern {p!r} is not a regex: {e}")
    return errs


def _check_suggest_connections(name: str, pack: dict) -> list[str]:
    errs: list[str] = []
    options = _question_options(pack)
    for key in pack.get("suggest_connections", {}):
        q, _, v = key.partition(":")
        if q not in options:
            errs.append(f"{name}: suggest_connections key {key!r}: no question {q!r}")
        elif v not in options[q]:
            errs.append(f"{name}: suggest_connections key {key!r}: question {q} has no option {v!r}")
    return errs


def _check_habits(name: str, habits: dict, skill_ids: set[str], all_cogs: set[str]) -> list[str]:
    errs: list[str] = []
    if habits["role"] != name:
        errs.append(f"{name}: habits.yaml role {habits['role']!r} must equal the pack id")
    ids = [h["id"] for h in habits["habits"]]
    if len(ids) != len(set(ids)):
        errs.append(f"{name}: habits.yaml has duplicate habit ids")
    for h in habits["habits"]:
        if skill_ids and h["skill"] not in skill_ids:
            errs.append(f"{name}: habit {h['id']}: unknown skill {h['skill']}")
        for c in h["cogs"]:
            if c not in all_cogs:
                errs.append(f"{name}: habit {h['id']}: unknown cog {c}")
    return errs


def _check_standard(name: str, pack: dict, mapping: dict | None, steps: dict | None, routines: dict | None,
                    curriculum: dict | None, habits: dict | None) -> list[str]:
    """The measurable floor of `depth: standard` (STANDARD_MINIMUM), plus: every extra cog is taught, checked or routinised somewhere."""
    errs: list[str] = []
    m = STANDARD_MINIMUM
    extra = pack["cogs"]["extra"]
    n_checks = len(steps["checks"]) if steps else 0
    n_skills = len(curriculum["skills"]) if curriculum else 0
    n_templates = len(routines["templates"]) if routines else 0
    n_followups = len(pack["onboarding"].get("followups", []))
    n_habits = len(habits["habits"]) if habits else 0
    for label, have, floor in (("cogs", len(extra), m["cogs"]), ("expert checks", n_checks, m["checks"]), ("curriculum skills", n_skills, m["skills"]),
                               ("routine templates", n_templates, m["templates"]), ("onboarding followups", n_followups, m["followups"]),
                               ("habits", n_habits, m["habits"])):
        if have < floor:
            errs.append(f"{name}: depth standard needs at least {floor} {label}, has {have}")
    if "suggest_connections" not in pack:
        errs.append(f"{name}: depth standard needs suggest_connections")
    used: set[str] = set()
    for c in (steps["checks"] if steps else []):
        used.update(c["cogs"])
    for s in (curriculum["skills"] if curriculum else []):
        used.update(s["cogs"])
    for t in (routines["templates"] if routines else []):
        used.update(t["cogs"])
    for c in extra:
        if c not in used:
            errs.append(f"{name}: extra cog {c} is not used by any expert check, curriculum skill or routine template")
    return errs


def _has_cycle(graph: dict[str, list[str]]) -> bool:
    indeg = {n: 0 for n in graph}
    for n, deps in graph.items():
        for d in deps:
            if d in indeg:
                indeg[n] += 1
    q = deque(n for n, k in indeg.items() if k == 0)
    seen = 0
    while q:
        n = q.popleft()
        seen += 1
        for m, deps in graph.items():
            if n in deps:
                indeg[m] -= 1
                if indeg[m] == 0:
                    q.append(m)
    return seen != len(graph)


# ---------------------------------------------------------------- across packs

def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else 1.0


def compare_packs(packs: dict[str, dict]) -> list[str]:
    """The packs must differ visibly in onboarding, extra cogs, risk classes and tone defaults."""
    errs: list[str] = []
    names = sorted(packs)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            pa, pb = packs[a], packs[b]
            tag = f"{a} vs {b}"
            ea, eb = set(pa["cogs"]["extra"]), set(pb["cogs"]["extra"])
            if ea & eb:
                errs.append(f"{tag}: extra cogs overlap: {sorted(ea & eb)}")
            ia, ib = set(pa["risk_classes"]["irreversible"]), set(pb["risk_classes"]["irreversible"])
            if _jaccard(ia, ib) > 0.4:
                errs.append(f"{tag}: irreversible risk classes too similar (Jaccard {_jaccard(ia, ib):.2f})")
            ta, tb = pa["tone_defaults"], pb["tone_defaults"]
            if (ta["length"], ta["voice"], ta.get("pace")) == (tb["length"], tb["voice"], tb.get("pace")):
                errs.append(f"{tag}: tone defaults are identical")
            qa = {q["id"]: q for q in pa["onboarding"]["questions"]}
            qb = {q["id"]: q for q in pb["onboarding"]["questions"]}
            for qid in ("tools", "risky"):
                va = {o["value"] for o in qa[qid]["options"]}
                vb = {o["value"] for o in qb[qid]["options"]}
                if _jaccard(va, vb) > 0.4:
                    errs.append(f"{tag}: question {qid} options too similar (Jaccard {_jaccard(va, vb):.2f})")
            for qid in QUESTION_IDS:
                if qa[qid]["prompt"] == qb[qid]["prompt"]:
                    errs.append(f"{tag}: question {qid} has the same prompt")
            if qa["hours"]["default_hours"] == qb["hours"]["default_hours"]:
                errs.append(f"{tag}: default hours are identical")
    return errs


# ---------------------------------------------------------------- schema package self-checks

EXAMPLE_SCHEMAS = {
    "steps.": "steps.schema.json",
    "routine.": "routine.schema.json",
    "queue_item.": "queue_item.schema.json",
    "memory.frontmatter.": "memory.frontmatter.schema.json",
    "ext_rect.": "ext_rect.schema.json",
    "recording.": "recording.schema.json",
    "event.": "event.schema.json",
    "cue.decisions.": "cue_decision.schema.json",
    "cue.growth_skill.": "cue_growth.schema.json",     # the same shape as cue.growth.: the figures for one skill (data.skill set)
    "cue.growth.": "cue_growth.schema.json",
    "cue.ledger.": "cue_ledger.schema.json",
}


def validate_schema_package() -> list[str]:
    """Every schema is itself valid JSON Schema, the lead's files still validate, and examples pass."""
    errs: list[str] = []
    for p in sorted(SCHEMA_DIR.glob("*.schema.json")):
        try:
            Draft202012Validator.check_schema(load_json(p))
        except Exception as e:  # noqa: BLE001
            errs.append(f"{p.name}: not a valid JSON Schema: {e}")
    errs += schema_errors(def_validator("sensitive_fields"), load_json(SCHEMA_DIR / "sensitive_fields.json"),
                          "schema/sensitive_fields.json")
    ex_dir = SCHEMA_DIR / "examples"
    if ex_dir.is_dir():
        for p in sorted(ex_dir.glob("*.json")):
            if p.name.startswith("invalid."):
                continue
            prefix = next((k for k in EXAMPLE_SCHEMAS if p.name.startswith(k)), None)
            if prefix is None:
                errs.append(f"schema/examples/{p.name}: no schema is registered for this file name")
                continue
            schema = load_json(SCHEMA_DIR / EXAMPLE_SCHEMAS[prefix])
            errs += schema_errors(Draft202012Validator(schema), load_json(p), f"schema/examples/{p.name}")
    return errs


# ---------------------------------------------------------------- CLI

def main(argv: list[str]) -> int:
    quiet = "--quiet" in argv
    args = [a for a in argv if not a.startswith("--")]
    pack_dirs = [Path(a) for a in args] if args else sorted(
        d for d in HERE.iterdir() if d.is_dir() and (d / "pack.yaml").is_file())
    failed = False

    def report(label: str, errs: list[str]) -> None:
        nonlocal failed
        if errs:
            failed = True
            print(f"FAIL  {label}")
            for e in errs:
                print(f"      {e}")
        elif not quiet:
            print(f"ok    {label}")

    report("schema package", validate_schema_package())
    loaded: dict[str, dict] = {}
    for d in pack_dirs:
        report(f"pack {d.name}", validate_pack(d))
        try:
            loaded[d.name] = load_yaml(d / "pack.yaml")
        except Exception:  # noqa: BLE001
            pass
    if len(loaded) > 1:
        report("packs differ visibly", compare_packs(loaded))
    if not pack_dirs:
        print("FAIL  no packs found")
        failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
