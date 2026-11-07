"""Screenshots of the programmer workbench (light and dark, 1440x900 and 390x844) into evals/study_roles/screens/programmer-*.png.
    uv run --package understudy-agent python services/agent/tests/roles/programmer/shots.py"""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "services" / "agent"))
from understudy_agent.sandbox_roles import programmer as P  # noqa: E402
from understudy_agent.sandbox_roles.programs_util import run_program  # noqa: E402

OUT = ROOT / "evals" / "study_roles" / "screens"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with P.make_server(0) as s, sync_playwright() as pw:
        b = pw.chromium.launch()
        for scheme in ("light", "dark"):
            for name, (w, h) in {"1440": (1440, 900), "390": (390, 844)}.items():
                ctx = b.new_context(viewport={"width": w, "height": h}, color_scheme=scheme)
                page = ctx.new_page()
                page.goto(s.case_url("p-discipline-2", 1))
                page.wait_for_selector("#editor")
                page.screenshot(path=str(OUT / f"programmer-start-{scheme}-{name}.png"), full_page=(name == "390"))
                run_program(page, [("click", "Run tests"), ("click", "Sample inputs"), ("fill", "Try an expression", "greeting('Ada', 11)"), ("click", "Evaluate"),
                                   ("click", "Review diff"), ("click", "Stage src/banner.js")])
                page.wait_for_timeout(400)
                page.screenshot(path=str(OUT / f"programmer-working-{scheme}-{name}.png"), full_page=True)
                over = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
                print(scheme, name, "horizontal overflow:", over)
                ctx.close()
        b.close()


if __name__ == "__main__":
    main()
