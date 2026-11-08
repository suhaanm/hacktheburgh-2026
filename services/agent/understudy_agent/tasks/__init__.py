"""Open-ended tasks: a worker types or says any task; Knack routes it, asks for a click when it matters, and reports back.

    from understudy_agent.tasks import submit_task
    submit_task("summarise this CSV", source="voice")    # same path as POST /tasks

See docs/TASKS.md. Nothing here is imported by the sandbox demo path.
"""
from .manager import TaskError, TaskManager, get_manager, reset_manager, submit_task

__all__ = ["TaskError", "TaskManager", "get_manager", "reset_manager", "submit_task"]
