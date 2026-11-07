"""The adapters owners adopt: manifest-only, tier 3 text, tier 2 re-ordering through the real Guard."""
from __future__ import annotations

import io
import json

from PIL import Image

from understudy_agent.audit import AuditLog
from understudy_agent.context import (FrameRetention, Outcome, PageState, StepRecord, WorkingMemory, assert_metadata_only,
                                      computer_use_text, manifest_of_parts, split_tier2_state, tier2_messages)
from understudy_agent.models.mock_provider import MockProvider
from understudy_agent.queue import ApprovalQueue
from understudy_agent.security.denylist import Denylist
from understudy_agent.tiers.browser_agent import TOOL_HELP
from understudy_agent.tiers.heuristic import HeuristicModelPort
from understudy_agent.tiers.safety import Guard


def png(n=0):
    b = io.BytesIO()
    Image.new("RGB", (1280, 800), (240 - n, 240, 240)).save(b, "PNG")
    return b.getvalue()


def test_manifest_of_parts_measures_a_prompt_without_keeping_it():
    secret = "CANARY-77-secret-text"
    m = manifest_of_parts("planner", [("system", "You plan. " + secret, True), ("state", "STATE: {}", False)])
    d = m.to_meter_dict()
    assert_metadata_only(d)
    assert secret not in json.dumps(d) and d["prefix_tokens"] > 0 and [s["stable"] for s in d["sections"]] == [True, False]


def test_computer_use_text_is_goal_first_bounded_and_carries_the_task_state():
    wm = WorkingMemory("calc_a.household", handles=["household.rent"], pending=["household.rent"])
    fr = FrameRetention()
    sizes = []
    for n in range(1, 151):
        wm.record(StepRecord(n=n, kind="click", target=f"e{n % 20}", outcome=Outcome.OK, tier=3, page=PageState.FORM))
        plan = fr.push(png(n % 5))
        a = computer_use_text("Enter the household. FACTS you may type: {household.rent}", wm, plan, feedback="NOTE: the last action was refused.",
                              with_previous=True)
        sizes.append(a.manifest.total_tokens)
    assert a.text().startswith("Goal: Enter the household") and "TASK STATE" in a.text() and a.text().rstrip().endswith("toward the goal.")
    assert "NOTE: the last action was refused." in a.text() and "Image 1 is the current screen" in a.text()
    assert len(a.frames) == 2 and a.manifest.image_frames == 2
    assert max(sizes) < 2600 and sizes[-1] <= sizes[40] + 150                 # bounded, including the two frames
    assert a.manifest.prefix_hash == computer_use_text("Enter the household. FACTS you may type: {household.rent}", wm, plan).manifest.prefix_hash


def test_tier2_messages_move_the_stable_help_into_the_system_message_and_keep_the_guards_checks(tmp_path):
    port = HeuristicModelPort(MockProvider("benefits_clean"))
    guard = Guard(port, run_id="r_ctx", audit=AuditLog(tmp_path / "a.jsonl"), queue=ApprovalQueue(tmp_path / "q", audit=AuditLog(tmp_path / "a2.jsonl")),
                  denylist=Denylist(), mode="model_driven")
    seen = guard.observe_screen()
    state = {"page": "/a/1", "elements": [{"ref": "e1", "role": "textbox", "name": "Age"}], "params": ["adult1_age"],
             "param_meaning": {"adult1_age": "age of the first adult"}, "already_set_on_this_page": [], "recent": [], "actions_left": 12}
    stable, volatile = split_tier2_state(state)
    assert set(stable) == {"param_meaning"} and "params" in volatile and "elements" in volatile
    msgs = tier2_messages(guard, "Enter this household.", seen, tool_help=TOOL_HELP, state=state, labels_block="e1: Age")
    sys_text, user_text = msgs[0]["content"], msgs[1]["content"]
    assert "TOOLS (return exactly one" in sys_text and "FIXED FOR THIS RUN" in sys_text and "age of the first adult" in sys_text
    assert "TOOLS (return exactly one" not in user_text and user_text.rindex("STATE:") > user_text.index("Goal (from the worker)")
    assert "param_meaning" not in user_text


def test_default_sends_and_counts_one_frame_and_never_mentions_an_image_two():
    wm = WorkingMemory("g")
    fr = FrameRetention()
    fr.push(png(0), passthrough=True)
    plan = fr.push(png(0), passthrough=True)
    one = computer_use_text("Goal text", wm, plan)
    two = computer_use_text("Goal text", wm, plan, with_previous=True)
    assert len(one.frames) == 1 and one.manifest.image_frames == 1 and "Image 2" not in one.text()
    assert "did not change since the last step" in one.text()
    assert len(two.frames) == 2 and two.manifest.total_tokens > one.manifest.total_tokens and "Image 2" in two.text()


def test_passthrough_hands_back_the_callers_own_bytes_so_click_coordinates_stay_in_their_pixel_space():
    original = png(3)
    plan = FrameRetention().push(original, passthrough=True)
    cur = plan.frames[0]
    assert cur.data is original and (cur.width, cur.height) == (1152, 720)       # the size the provider will see, for token accounting


def test_the_openai_computer_use_profile_is_calibrated_and_the_default_is_not_touched():
    from understudy_agent.context import estimate_image_tokens

    assert estimate_image_tokens(1152, 720, "openai_cu") == 1860
    assert estimate_image_tokens(1280, 720) == 1150 and estimate_image_tokens(1280, 720, "default") == 1150
    wm = WorkingMemory("g")
    fr = FrameRetention()
    plan = fr.push(png(0), passthrough=True)
    a = computer_use_text("Goal text", wm, plan)
    b = computer_use_text("Goal text", wm, plan, image_profile="openai_cu")
    assert b.manifest.total_tokens - a.manifest.total_tokens == 1860 - estimate_image_tokens(1152, 720)
