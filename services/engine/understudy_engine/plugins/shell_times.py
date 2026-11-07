"""Shell-history timestamps (CAP-8): times only. The command text is never kept.

Formats recognised, line by line:

* zsh extended history: ``: 1730000000:12;command`` (epoch seconds, elapsed seconds, then the command);
* bash with ``HISTTIMEFORMAT``: a ``#1730000000`` line followed by the command line;
* fish: ``- cmd: ...`` followed by ``  when: 1730000000``.

The parser looks only at the leading timestamp (or the ``when:`` value) and drops the rest of the line on the spot, so
no command, path, argument or secret is ever held in a variable that outlives the loop iteration, let alone in an item.
History without timestamps yields nothing (counted as ``untimed_lines``).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from .base import RawItem, Source, overlaps

UTC = timezone.utc
_ZSH = re.compile(r"^: (\d{9,11}):(\d+);")
_BASH = re.compile(r"^#(\d{9,11})$")
_FISH_WHEN = re.compile(r"^\s+when: (\d{9,11})$")
_FISH_CMD = re.compile(r"^- cmd:")


class ShellTimesSource(Source):
    plugin_id = "shell_times"
    schema_id = "shell_time.v1"

    def __init__(self, text: str | None = None, *, path: str | Path | None = None, shell: str = "auto"):
        super().__init__()
        if (text is None) == (path is None):
            raise ValueError("give exactly one of text or path")
        if path is not None:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        self._text = text or ""
        self._shell = shell

    def read(self, since: datetime | None = None, until: datetime | None = None) -> Iterator[RawItem]:
        out: list[RawItem] = []
        for line in self._text.split("\n"):
            kind, epoch, dur = None, None, 0
            m = _ZSH.match(line)
            if m and self._shell in ("auto", "zsh"):
                kind, epoch, dur = "zsh", int(m.group(1)), int(m.group(2))
            else:
                m = _BASH.match(line)
                if m and self._shell in ("auto", "bash"):
                    kind, epoch = "bash", int(m.group(1))
                else:
                    m = _FISH_WHEN.match(line)
                    if m and self._shell in ("auto", "fish"):
                        kind, epoch = "fish", int(m.group(1))
            if kind is None:
                if line and not line.startswith("#") and not _FISH_CMD.match(line) and not line.startswith(" "):
                    self._note("untimed_lines")        # a bare command line (bash after its #epoch line is counted too; harmless)
                continue
            t0 = datetime.fromtimestamp(epoch, UTC)
            t1 = t0 + timedelta(seconds=dur)
            if overlaps(t0, t1, since, until):
                out.append(RawItem("shell_time", t0, t1, {"shell": kind, "duration_s": dur}))
        out.sort(key=lambda r: r.t0)
        self._note("events_read", len(out))
        yield from out
