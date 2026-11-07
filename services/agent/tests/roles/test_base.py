"""The shared role-sandbox server: reset, state log, final, glitches, static files, CSP. No browser, ephemeral port."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

from understudy_agent.sandbox_roles.base import RoleServer, RoleSpec


@dataclass
class T:
    id: str = "t1"
    skill: str = "s"
    title: str = "Task one"
    variants: tuple = (1, 2)


@pytest.fixture()
def server(tmp_path: Path):
    (tmp_path / "x.js").write_text("console.log(1)")
    spec = RoleSpec(role="programmer", static_dir=tmp_path, tasks={"t1": T()},
                    render_page=lambda tid, v, ctx: f"<html><body>page {tid} v{v} {ctx['layout']} {ctx['glitch']}</body></html>", title="demo")
    with RoleServer(spec, port=0) as s:
        yield s


def test_health_reset_state_and_act(server):
    c = httpx.Client(base_url=server.url)
    assert c.get("/healthz").json() == {"ok": True, "role": "programmer", "epoch": 0}
    assert c.post("/api/act", json={"kind": "click", "zone": "test_runner"}).json()["seq"] == 1
    assert c.post("/api/act", json={"kind": "edit", "file": "a.js", "chars": 12}).json()["seq"] == 2
    s = c.get("/__state").json()
    assert s["counts"] == {"click": 1, "edit": 1} and s["events"][0]["zone"] == "test_runner" and s["events"][1]["seq"] == 2
    assert c.post("/__reset").json() == {"epoch": 1}
    s = c.get("/__state").json()
    assert s["events"] == [] and s["epoch"] == 1 and s["final"] is None


def test_bad_bodies_are_refused_and_strings_are_clipped(server):
    c = httpx.Client(base_url=server.url)
    assert c.post("/api/act", content=b"not json").status_code == 400
    assert c.post("/api/act", json={"no": "kind"}).status_code == 400
    assert c.post("/api/act", json={"kind": "x", "text": "a" * 10000}).status_code == 200
    assert len(c.get("/__state").json()["events"][0]["text"]) == 4000
    c.post("/api/final", json={"visible": {"passed": 3}})
    assert c.get("/__state").json()["final"] == {"visible": {"passed": 3}}


def test_pages_variants_unknown_and_csp(server):
    c = httpx.Client(base_url=server.url)
    r = c.get("/task/t1/2?layout=v2")
    assert r.status_code == 200 and "page t1 v2 v2" in r.text
    assert "connect-src 'self'" in r.headers["content-security-policy"] and "default-src 'none'" in r.headers["content-security-policy"]
    assert c.get("/task/t1/3").status_code == 404 and c.get("/task/zz/1").status_code == 404 and c.get("/task/t1/x").status_code == 404
    assert c.get("/__state").json()["task"] == {"id": "t1", "variant": 2, "layout": "v2"}
    assert c.get("/static/x.js").text == "console.log(1)"
    assert "Task one" in c.get("/").text


def test_glitch_503_once_then_ok_and_always(server):
    c = httpx.Client(base_url=server.url)
    r = c.get("/task/t1/1?glitch=503once")
    assert r.status_code == 503 and 'id=retry' in r.text
    assert c.get("/task/t1/1?glitch=503once").status_code == 200
    server.state.reset()
    assert c.get("/task/t1/1?glitch=503once").status_code == 503          # a reset starts the glitch over
    assert c.get("/task/t1/1?glitch=503always").status_code == 503 and c.get("/task/t1/1?glitch=503always").status_code == 503
    assert c.get("/task/t1/1?glitch=bogus").status_code == 200
