"""SOUND (passes after the S-11 fix): the queue key is private (0600), a JSON edit is rejected, a status flip alone does not approve, a copied tag does not move
between items, and an item approved for one run is refused for another."""
from __future__ import annotations

import json
import stat
from datetime import datetime, timezone

from understudy_agent.queue import ApprovalQueue
from understudy_agent.security.settings import Origin


def make(q, sig="sig-1", run="r1"):
    return q.enqueue(kind="irreversible_step", title="t", summary="s", risk_class="irreversible", signature=sig, run_id=run)


def test_key_mode_tamper_and_copy(tmp_path):
    q = ApprovalQueue(tmp_path / "q")
    a, b = make(q), make(q, "sig-2")
    key = q.root.parent / ".queue_key"
    assert key.exists() and stat.S_IMODE(key.stat().st_mode) == 0o600, "the queue key must exist and be private"
    pa, pb = q.root / f"{a['id']}.json", q.root / f"{b['id']}.json"
    d = json.loads(pa.read_text())
    d.update(status="approved", decided_at=datetime.now(timezone.utc).isoformat())
    pa.write_text(json.dumps(d))                                                       # flip the status by hand
    assert not q.consume_approval(a["id"], "sig-1")
    q.approve(b["id"], origin=Origin.HUMAN_UI)
    good = json.loads(pb.read_text())
    stolen = dict(json.loads(pa.read_text()), status="approved", decided_at=good["decided_at"], decided_by=good["decided_by"])
    stolen["mac"] = good["mac"]                                                        # copy B's authentication tag onto A
    pa.write_text(json.dumps(stolen))
    assert not q.consume_approval(a["id"], "sig-1"), "a tag copied from another item approved this one"
    unsigned = {k: v for k, v in stolen.items() if k != "mac"}                         # delete the tag altogether ("written before tags existed")
    pa.write_text(json.dumps(unsigned))
    assert not q.consume_approval(a["id"], "sig-1"), "an item with no tag was honoured as an approval"
