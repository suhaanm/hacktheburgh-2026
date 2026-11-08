"""Git habits route (GIT-1): ``GET /git/habits?person=&repo=``. Flag ``UNDERSTUDY_X_GIT=1`` or ``UNDERSTUDY_X=1``.

The engine app includes ``router`` only when this module imports and the flag is on (``enabled()``); the handlers also refuse
with 404 ``extension_off`` when the flag is off, so including the router unconditionally is harmless.

    GET /git/habits?person=p_git_learner_1&repo=r_git_learner_1[&author=a_xxx][&digest=auto|rules][&reword=0|1][&placebo=0|1]
        -> {meta: AnalyticMeta, data: {habits: [{id, label, learner, expert, delta, ci, flagged, n_den, n_num, suggestion?}],
            suggestions: [...], digest_source: "model"|"rules", n_commits, features, reference, ...}}
    GET /git/people -> {learners: [{person, repo}], experts: [...], registered: [...], default_person}

``repo`` is an id, never a path: the synthetic cohort or a repository the worker registered with ``UNDERSTUDY_GIT_REPOS``.
Responses hold numbers and enums only; no commit message, path, author name or email is ever returned (PRV-4).
"""
from __future__ import annotations

import threading
from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from .calendar import standin
from .gitanalysis import service
from .gitanalysis.source import GitSourceError

router = APIRouter(tags=["git"])


def enabled() -> bool:
    return service.flag_on()


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def _off() -> JSONResponse:
    return _error(404, "extension_off", "The git analysis layer is off. Set UNDERSTUDY_X_GIT=1 (or UNDERSTUDY_X=1) and restart the engine.")


@router.get("/git/habits")
def get_habits(
    person: str | None = Query(None, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$", description="learner id, e.g. p_git_learner_1"),
    repo: str | None = Query(None, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$", description="repository id, e.g. r_git_learner_1"),
    author: str | None = Query(None, max_length=20, pattern=r"^a_[0-9a-f]{10}$", description="keep one author of a registered repo"),
    digest: Literal["auto", "rules"] = "auto",
    reword: bool = False,
    placebo: bool = False,
):
    if not enabled():
        return _off()
    who, role = standin.caller()
    if standin.is_own(person, who) and not repo:
        # The worker's own page: their own commits, or nothing. Never another learner's repository, and never the shared default learner when nobody is named.
        if role != "programmer" or who not in service.worker_repos():
            return _error(404, "unknown_person", "There are no commits to show for you yet.")
        person = who
    try:
        return service.habits(person, repo, author=author, backend=digest, reword=reword or None, with_placebo=placebo)
    except service.GitServiceError as exc:
        return _error(exc.status, exc.code, str(exc))
    except GitSourceError as exc:
        return _error(422, exc.code, "That repository could not be read (is it a git repository with commits?).")


@router.get("/git/people")
def get_people():
    if not enabled():
        return _off()
    who, role = standin.caller()
    if who:                                         # someone is set up: the worker's page lists the worker's own repository, if they have one, and nobody else
        own = role == "programmer" and who in service.worker_repos()
        return {"learners": [{"person": who, "repo": service.repo_id_for(who)}] if own else [], "experts": [], "registered": sorted(service.registered_repos()),
                "default_person": who}
    return service.people()


def warm(background: bool = True) -> threading.Thread | None:
    """Materialise the synthetic cohort and compute the default person once, so the first request is quick."""
    def run() -> None:
        try:
            service.habits(service.DEFAULT_PERSON)
        except Exception:      # warm-up never raises
            pass
    if not background:
        run()
        return None
    th = threading.Thread(target=run, name="git-warm", daemon=True)
    th.start()
    return th
