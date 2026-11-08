"""Regression for a test-isolation bug found by the first full run of the merged agent suite (8 Nov): the role-sandbox `browser` fixture held a
sync Playwright open for the whole session. The sync API keeps an asyncio loop running in the calling thread while it is open, so every later
test that called `asyncio.run()` (tests/tasks sorts after tests/roles) failed with "cannot be called from a running event loop" (seven failures,
all green when run alone). The fixture must be closed between modules."""
from __future__ import annotations

import asyncio


def test_the_browser_fixture_is_not_session_scoped(request):
    defs = request.session._fixturemanager.getfixturedefs("browser", request.node)
    assert defs, "the roles conftest no longer provides a `browser` fixture (update this test)"
    assert all(d.scope != "session" for d in defs), "a session-scoped sync Playwright blocks asyncio.run() in every later test"


def test_asyncio_run_works_in_a_test_that_does_not_use_the_browser():
    async def one() -> int:
        return 1

    assert asyncio.run(one()) == 1
