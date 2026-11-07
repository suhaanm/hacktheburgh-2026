"""Agent runtime (BGA-1 to BGA-6): a parent that plans child agents, and children that work in isolated workspaces.

Built on the existing supervisor, SafetyPipeline, approval queue, audit log and kill flag; no new trust paths. Off by
default behind UNDERSTUDY_X_AGENTS (or UNDERSTUDY_X); importing this package has no side effects.
"""
from .policy import agents_enabled

__all__ = ["agents_enabled"]
