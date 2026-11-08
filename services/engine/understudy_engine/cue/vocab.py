"""Pack vocabulary for Cue: short step labels, the fixed reason table and the fixed question templates (CUE-4, CUE-8).

Nothing on the screen is model-written. A step is an id from the pack's ``expert_steps.yaml``; its short label and its one-line
reason come from tables here (built in for the three shipped packs) or from an optional ``cue:`` block in the pack's own
``pack.yaml`` (``short_labels: {step: text}``, ``reasons: {step: {id, text}}``), which wins when present and valid.
Lengths are enforced: a chip is 40 characters or fewer, a whisper 8 words or fewer, a reason 12 words or fewer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..coach.steps import StepPolicy
from ..cogs.mapper import Mapping
from .target import step_target

CHIP_MAX = 40
WHISPER_WORDS = 8
REASON_WORDS = 12
LABEL_MAX = 32          # "Next: " + label must fit the chip

SHORT_LABELS: dict[str, dict[str, str]] = {
    "benefits-processor": {
        "read_case": "Read the household record", "calc_a": "Run calculator A", "calc_b": "Run calculator B",
        "calc_c": "Run calculator C", "cliff_a": "Check cliff edges (A)", "cliff_b": "Check cliff edges (B)",
        "cliff_c": "Check cliff edges (C)", "reconcile": "Reconcile the three results",
        "write_note": "Copy figures to the note", "verify_note": "Read the note back",
    },
    "programmer": {
        "read_trace_first": "Read the failing trace", "inspect_inputs": "Look at the sample inputs",
        "write_failing_test": "Write a failing test", "edit_and_commit": "Make the smallest change",
        "rerun_and_confirm": "Re-run the tests", "probe_edges": "Try the edges in the console",
        "review_diff": "Review the diff", "commit_fix": "Commit the fix",
        # role-depth checks (RD, 7 Nov 2026): hand-written, at most 32 characters
        "reproduce_locally": "Reproduce it locally", "bisect_change": "Bisect to the bad change", "add_logging": "Add a log line",
        "write_commit_msg": "Write the commit message", "open_pr": "Open the pull request", "read_ci": "Read the CI result",
        "answer_review": "Answer the review comments", "review_peer_pr": "Review the pull request", "watch_prod": "Watch the release",
        "roll_back_safely": "Roll back one step", "profile_hot_path": "Profile the hot path", "write_migration": "Write the migration",
    },
    "data-analyst": {
        "profile_inputs": "Profile the inputs", "clean_data": "Fix what the profile showed",
        "run_and_inspect": "Run it, inspect the rows", "reconcile_to_control": "Reconcile with the control",
        "segment_breakdown": "Cut the data by segment", "sanity_check": "Sanity-check the number",
        "report_answer": "Report the answer",
        # role-depth checks (RD, 7 Nov 2026): hand-written, at most 32 characters
        "trace_source": "Trace it to the source", "join_safely": "Join without multiplying rows", "set_grain": "Set the grain of the answer",
        "check_magnitude": "Check the scale and units", "quantify_uncertainty": "Say how sure the number is",
        "write_finding": "Write the finding and caveat", "peer_check": "Get a second check", "make_reproducible": "Restart and run it all",
        "parameterise_report": "Make the changing bits inputs", "schedule_refresh": "Schedule the refresh", "document_metric": "Write down the metric",
    },
}

# reason id -> one line (12 words or fewer). Ids resolve to text here; the gate and the ledger only ever carry the id.
REASONS: dict[str, str] = {
    "why.read_case": "The record holds the facts every calculator needs.",
    "why.enter_once": "Copy the household from the record; retyping invites mistakes.",
    "why.cliff": "A figure near a limit can flip the answer.",
    "why.reconcile": "Three results can disagree; decide which to trust first.",
    "why.note": "A note that names its evidence can be checked later.",
    "why.verify_note": "Reading it back catches copy slips.",
    "why.trace_first": "The first wrong line in the log shows the real cause.",
    "why.small_change": "A small change is easier to review and undo.",
    "why.rerun": "Only a passing re-run shows the change worked.",
    "why.profile": "Bad rows hide in inputs; look before you query.",
    "why.inspect": "Reading the rows catches what a total hides.",
    "why.sanity": "A number you cannot explain should not be trusted.",
    "why.inspect_inputs": "Real inputs include the odd ones; read them before you edit.",
    "why.failing_test": "A test that fails first proves the fix later.",
    "why.edges": "Bugs live at the edges: empty, one item, exactly full.",
    "why.review_diff": "Reading the diff catches changes that are not the fix.",
    "why.commit": "A clear message tells the next reader what changed and why.",
    "why.clean": "Fix what the profile found before it reaches the total.",
    "why.control": "A total that disagrees with the control figure is wrong somewhere.",
    "why.segment": "An overall number can hide a difference between segments.",
    "why.report": "Say what the number is and how sure you are.",
    # role-depth reasons (RD, 7 Nov 2026), 12 words or fewer
    "why.reproduce": "A failure you can repeat on your machine is half fixed.",
    "why.bisect": "Halving the history finds the bad change faster than guessing.",
    "why.add_logging": "A log line with the ids saves the next incident.",
    "why.commit_msg": "Say what changed and why; you will not remember later.",
    "why.open_pr": "A clear description lets a reviewer start in one sitting.",
    "why.read_ci": "Read the first red job before you ask anyone to look.",
    "why.answer_review": "Every comment deserves a change or a reason.",
    "why.review_peer": "A review that names one blocking reason gets acted on.",
    "why.watch_prod": "The first ten minutes after a release show whether it works.",
    "why.roll_back": "Know what the release wrote before you roll it back.",
    "why.profile_hot": "The widest bar is rarely where you think it is.",
    "why.migration": "Small steps that can be undone keep the data safe.",
    "why.trace": "A column's meaning lives at its source, not in its name.",
    "why.join": "A join on a repeated key quietly multiplies rows.",
    "why.grain": "Counting the wrong unit gives a right-looking wrong number.",
    "why.magnitude": "A number off by a factor of ten looks fine until checked.",
    "why.interval": "A number without an interval claims more than it knows.",
    "why.finding": "A finding with its caveat can be trusted and challenged.",
    "why.peer": "A second pair of eyes catches what you stopped seeing.",
    "why.repro": "A result that cannot be rerun cannot be trusted.",
    "why.params": "Inputs you can change beat values you retype every week.",
    "why.schedule": "A refresh nobody watches needs an alert when it fails.",
    "why.metric_doc": "A metric without a definition becomes three different numbers.",
    "why.generic": "This is the step experts take next.",
}

STEP_REASON: dict[str, dict[str, str]] = {
    "benefits-processor": {
        "read_case": "why.read_case", "calc_a": "why.enter_once", "calc_b": "why.enter_once", "calc_c": "why.enter_once",
        "cliff_a": "why.cliff", "cliff_b": "why.cliff", "cliff_c": "why.cliff", "reconcile": "why.reconcile",
        "write_note": "why.note", "verify_note": "why.verify_note",
    },
    "programmer": {
        "read_trace_first": "why.trace_first", "inspect_inputs": "why.inspect_inputs", "write_failing_test": "why.failing_test",
        "edit_and_commit": "why.small_change", "rerun_and_confirm": "why.rerun", "probe_edges": "why.edges",
        "review_diff": "why.review_diff", "commit_fix": "why.commit",
        "reproduce_locally": "why.reproduce", "bisect_change": "why.bisect", "add_logging": "why.add_logging", "write_commit_msg": "why.commit_msg",
        "open_pr": "why.open_pr", "read_ci": "why.read_ci", "answer_review": "why.answer_review", "review_peer_pr": "why.review_peer",
        "watch_prod": "why.watch_prod", "roll_back_safely": "why.roll_back", "profile_hot_path": "why.profile_hot", "write_migration": "why.migration",
    },
    "data-analyst": {
        "profile_inputs": "why.profile", "clean_data": "why.clean", "run_and_inspect": "why.inspect",
        "reconcile_to_control": "why.control", "segment_breakdown": "why.segment", "sanity_check": "why.sanity",
        "report_answer": "why.report",
        "trace_source": "why.trace", "join_safely": "why.join", "set_grain": "why.grain", "check_magnitude": "why.magnitude",
        "quantify_uncertainty": "why.interval", "write_finding": "why.finding", "peer_check": "why.peer", "make_reproducible": "why.repro",
        "parameterise_report": "why.params", "schedule_refresh": "why.schedule", "document_metric": "why.metric_doc",
    },
}

# Question templates by ambiguity type: fixed text, never model-written (CUE-4).
QUESTIONS: dict[str, str] = {
    "close_call": "Which of these is next?",
    "screen_disagrees": "I can see more than one option. Which is next?",
    "unclear": "I cannot tell where you are. What is next?",
}
OTHER_LABEL = "Something else"


def words(text: str) -> int:
    return len(text.split())


def short(label: str, limit: int = LABEL_MAX) -> str:
    """Truncate a pack label at a word boundary to ``limit`` characters (no ellipsis games: it stays pack text)."""
    label = re.sub(r"\s+", " ", label.strip())
    if len(label) <= limit:
        return label
    cut = label[:limit].rsplit(" ", 1)[0]
    return cut or label[:limit]


def chip_text(label: str) -> str:
    return ("Next: " + short(label))[:CHIP_MAX]


def whisper_text(label: str) -> str:
    """A whisper of 8 words or fewer: the short label's first five words after 'Next,'."""
    ws = short(label).split()[: WHISPER_WORDS - 3]
    return "Next, " + " ".join(ws)


@dataclass
class StepVocab:
    role: str
    policy: StepPolicy
    labels: dict[str, str] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)         # step id -> reason id
    reason_text: dict[str, str] = field(default_factory=dict)     # reason id -> text (pack overrides included)
    mapping: Mapping | None = None                                # the pack's cog mapping: where the control for a step is (the coach's source)

    def label(self, step_id: str) -> str:
        if step_id in self.labels:
            return self.labels[step_id]
        s = self.policy.steps.get(step_id)
        return short(s.label if s else step_id)

    def skill(self, step_id: str) -> str:
        s = self.policy.steps.get(step_id)
        return (s.skill if s and s.skill else step_id)

    def reason_id(self, step_id: str) -> str:
        return self.reasons.get(step_id) or "why.generic"

    def text_of(self, reason_id: str) -> str | None:
        return self.reason_text.get(reason_id) or REASONS.get(reason_id)

    def target(self, step_id: str) -> dict | None:
        """``{zone, label_hint, role_hint}`` for a step: the coach's own answer from the pack's mapping (``cue.target``), or None."""
        return step_target(self.policy.steps.get(step_id), self.mapping)

    def group(self, step_id: str) -> str:
        return self.policy.pattern_mates(step_id)[0]

    def cogs(self, step_id: str) -> tuple[str, ...]:
        s = self.policy.steps.get(step_id)
        return tuple(s.cogs) if s else ()


def _valid_override(table: object, kind: str) -> dict:
    out: dict = {}
    if not isinstance(table, dict):
        return out
    for k, v in table.items():
        if not isinstance(k, str):
            continue
        if kind == "label" and isinstance(v, str) and 0 < len(v) <= LABEL_MAX:
            out[k] = v
        elif kind == "reason" and isinstance(v, dict) and isinstance(v.get("id"), str) and isinstance(v.get("text"), str) \
                and 0 < words(v["text"]) <= REASON_WORDS and re.fullmatch(r"[a-z][a-z0-9_.\-]{0,40}", v["id"]):
            out[k] = {"id": v["id"], "text": v["text"]}
    return out


def build_vocab(role: str, policy: StepPolicy, pack_cue: dict | None = None, mapping: Mapping | None = None) -> StepVocab:
    labels = dict(SHORT_LABELS.get(role, {}))
    reasons = dict(STEP_REASON.get(role, {}))
    texts = dict(REASONS)
    pc = pack_cue or {}
    labels.update(_valid_override(pc.get("short_labels"), "label"))
    for step, r in _valid_override(pc.get("reasons"), "reason").items():
        reasons[step] = r["id"]
        texts[r["id"]] = r["text"]
    return StepVocab(role, policy, labels, reasons, texts, mapping)


_CACHE: dict[tuple[str, str], StepVocab] = {}


def get_vocab(role: str, root=None) -> StepVocab | None:
    """The vocabulary for a role's pack, or None when the pack is unknown or has no step policy."""
    from ..packs import PackError, load_pack

    key = (role, str(root or ""))
    if key not in _CACHE:
        try:
            pack = load_pack(role, root)
            policy = StepPolicy.from_pack(pack)
            _CACHE[key] = build_vocab(role, policy, pack.data.get("cue"), pack.cog_mapping())
        except (PackError, KeyError, FileNotFoundError, OSError):
            return None
    return _CACHE[key]


def clear_cache() -> None:
    _CACHE.clear()


# ---- skill names for sentences (GRO-1): "the cliff check", not an id. Pack curriculum labels are used when present.
SKILL_NAMES: dict[str, str] = {
    "enter-household-once": "entering the household once", "check-the-cliff": "the cliff check",
    "reconcile-before-noting": "reconciling before the note", "note-with-evidence": "the note with its evidence",
    "read_case": "reading the record first", "verify_note": "reading the note back",
    "read_trace_first": "reading the failing trace", "edit_and_commit": "the smallest change",
    "rerun_and_confirm": "re-running the tests", "profile_inputs": "profiling the inputs",
    "run_and_inspect": "inspecting the rows", "sanity_check": "the sanity check",
}


def skill_info(role: str, skill: str, root=None) -> dict[str, str]:
    """``{label, name}`` for a skill id: the pack curriculum's label and an optional ``name``, else a built-in short noun phrase, else the id."""
    from ..packs import PackError, load_pack

    label = None
    name = None
    try:
        cur = load_pack(role, root).file("curriculum")
        for s in cur.get("skills", []) if isinstance(cur, dict) else []:
            if s.get("id") == skill:
                label = s.get("label")
                name = s.get("name")
                break
    except (PackError, KeyError, FileNotFoundError, OSError, AttributeError):
        pass
    name = name or SKILL_NAMES.get(skill) or label or skill
    return {"label": label or name, "name": name}
