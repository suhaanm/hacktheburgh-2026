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
    selectors = [r["when"] for key in ("nav", "tab", "page") for r in cap.get(key, [])] + [r["selector"] for r in cap["elements"]]
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
            if c.get("critical") and not c["required"]:
                errs.append(f"{name}: expert check {c['id']} is critical but not required")
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
    # --- the oracle label must say what it is
    if "oracle" in pack and "not law" not in pack.get("oracle_note", "").lower():
        errs.append(f"{name}: pack.yaml has an oracle but oracle_note does not say it is simplified and not law")
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
