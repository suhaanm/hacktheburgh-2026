"""Proactive intelligence (PRO-1 to PRO-3): judge, verify, prepare, press to fire.

At most three cards a morning, each with editable prepared content, a risk class and source tags. Code ranks (``judge``),
re-checks against the live world and drops what went stale (``verify``), builds the content from templates (``prepare``);
the worker's press, and nothing else, enqueues an approval item or starts a background run (``fire``). Nothing fires unprompted.

Design from the owner's own prose notes on Sentient OS (judge, research and prepare, execute on the user's press; few cards;
stale items dropped), reimplemented here in our own code and words (decision D24). Off by default behind
``UNDERSTUDY_X_PROACTIVE`` (or the master ``UNDERSTUDY_X``); the P0 demo path never imports this package.

Importing the package is cheap and has no side effects; the heavy readers import their sources lazily.
"""
from .paths import enabled

__all__ = ["enabled"]
