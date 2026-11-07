"""Screenshot retention: the latest frame at full size, at most one previous thumbnail, nothing kept beyond that."""
from __future__ import annotations

import io

from PIL import Image, ImageDraw

from understudy_agent.context import FrameRetention


def shot(n: int, w: int = 1280, h: int = 800) -> bytes:
    im = Image.new("RGB", (w, h), (245, 245, 245))
    d = ImageDraw.Draw(im)
    d.rectangle([40 + n * 7, 60, 300 + n * 7, 140], fill=(30, 100, 220))
    for i in range(n % 5):
        d.text((50, 200 + 30 * i), "field %d value" % i, fill=(0, 0, 0))
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def test_never_more_than_two_frames_and_tokens_stay_bounded_over_150_steps():
    r = FrameRetention()
    toks = []
    for n in range(150):
        plan = r.push(shot(n))
        assert 1 <= len(plan.frames) <= 2
        assert plan.frames[0].role == "current" and (len(plan.frames) == 1 or plan.frames[1].role == "previous_thumb")
        toks.append(plan.tokens)
    assert max(toks) <= 1150 + 200 and toks[0] <= 1150 and toks[1] == toks[149]
    assert r.pushed == 150 and r.released >= 148                                 # every older frame was let go, none accumulated


def test_the_current_frame_is_full_size_and_the_previous_is_a_small_jpeg():
    r = FrameRetention()
    r.push(shot(0))
    plan = r.push(shot(1))
    cur, prev = plan.frames
    assert (cur.width, cur.height) == (1152, 720) and cur.mime == "image/png"
    assert max(prev.width, prev.height) <= 384 and prev.mime == "image/jpeg" and prev.tokens < cur.tokens // 5


def test_only_a_thumbnail_and_a_fingerprint_are_held_between_steps_never_a_full_frame():
    r = FrameRetention()
    full = shot(3)
    plan = r.push(full)
    assert r.held_bytes < 300_000
    assert not any(v is plan.frames[0].data for v in vars(r).values())          # the full frame is not an attribute of the object
    r.clear()
    assert r.held_bytes == 0


def test_change_detection_and_the_hint_sentence():
    r = FrameRetention()
    assert r.push(shot(0)).changed is None
    same = r.push(shot(0))
    assert same.changed is False and "did not change" in same.hint
    moved = r.push(shot(2))
    assert moved.changed is True and "changed" in moved.hint and "Image 2" in moved.hint


def test_without_previous_one_frame_and_the_older_frame_is_released():
    r = FrameRetention(keep_previous=False)
    r.push(shot(0))
    plan = r.push(shot(1))
    assert len(plan.frames) == 1 and plan.dropped == 1 and r.held_bytes < 300_000
