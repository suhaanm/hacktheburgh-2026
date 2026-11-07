"""Exemplar roles and spawn kinds. Importing this package registers them (roles, menus, schemas, verifiers, kinds)."""
from . import base, creative, data, longhorizon, programming  # noqa: F401
from .base import GOALS, KINDS, MENUS, Exemplar, Menu, WorkspaceNeeds, load_playbook

__all__ = ["GOALS", "KINDS", "MENUS", "Exemplar", "Menu", "WorkspaceNeeds", "load_playbook"]
