"""Open-ended tasks: a worker types or says any task; Knack routes it, asks for a click when it matters, and reports back.

    from understudy_agent.tasks import submit_task
    submit_task("summarise this CSV", source="voice")    # same path as POST /tasks

See docs/TASKS.md. The agent server mounts the routes as an optional router: a failure to load them never breaks the other routes.
"""
from .manager import TaskError, TaskManager, get_manager, reset_manager, submit_task

__all__ = ["TaskError", "TaskManager", "get_manager", "reset_manager", "submit_task"]
