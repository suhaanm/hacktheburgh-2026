"""Decide what a tool call IS, in code, from OUR table and verb rules (CONNECTIONS). The server's own words about itself are hints from an
untrusted process, and they never lower a class:

1. A tool in the preset's table has the class the table gives (``tools.classes``). A server that marks ``delete_everything`` read-only changes
   nothing: the table, or the verb rules, say what it is.
2. A tool the table does not know: ``tools.unlisted: refuse`` (a server with a far bigger tool set than the consent covers) means it is never
   called. Otherwise the word lists of ``security/labels.py`` and our verb rules decide; a name nothing recognises is treated as a WRITE (a person
   decides). A ``destructiveHint`` can RAISE the class of such a tool; ``readOnlyHint`` never lowers anything.
3. Some tools are decided by their arguments, not their name: ``execute_sql`` is a read only when our code reads one read-only statement
   (``classify_sql``); a ``method`` or ``action`` argument that says delete makes any tool destructive.

Classes: read, write, send, destructive, execute. Everything but read needs a person's real click. destructive and execute can never be opted in.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

from understudy_engine.connections.manifest import Preset

from ..security.labels import ActionClass, classify_label

CLASS_ORDER = ("read", "write", "send", "destructive", "execute")
_RANK = {c: i for i, c in enumerate(CLASS_ORDER)}

READ_VERBS = frozenset({"get", "list", "search", "find", "read", "describe", "show", "fetch", "query", "count", "view", "lookup", "inspect",
                        "explain", "whoami", "info", "status", "log", "diff", "tree", "stat", "browse", "retrieve", "head", "cat", "ls", "peek"})
WRITE_VERBS = frozenset({"create", "add", "update", "edit", "write", "set", "put", "patch", "modify", "move", "rename", "copy", "merge", "push",
                         "commit", "checkout", "reset", "assign", "transition", "link", "unlink", "star", "unstar", "upload", "import", "append",
                         "insert", "save", "manage", "resize", "format", "watch", "unwatch", "mark", "dismiss", "post", "reply", "open", "close",
                         "fork", "enable", "toggle", "clear", "restart", "start", "stop", "cancel", "request", "submit", "sync", "apply", "attach"})
EXECUTE_VERBS = frozenset({"run", "execute", "exec", "eval", "deploy", "trigger", "invoke", "call", "launch", "install", "shell", "kill"})
DESTRUCTIVE_VERBS = frozenset({"delete", "remove", "destroy", "drop", "purge", "truncate", "erase", "wipe", "revoke", "uninstall", "prune"})
_ARG_METHOD_KEYS = ("method", "action", "operation", "op", "command")


@dataclass(frozen=True)
class Classification:
    klass: str                 # read | write | send | destructive | execute | unknown
    source: str                # table | sql | verbs | hint | unrecognised | unlisted_refused | argument
    refused: bool = False      # never callable (an unlisted tool of a preset that refuses them)

    @property
    def is_read(self) -> bool:
        return self.klass == "read" and not self.refused


def _words(name: str) -> list[str]:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    return [w for w in re.split(r"[^A-Za-z0-9]+", s.lower()) if w]


def _max(a: str, b: str) -> str:
    return a if _RANK[a] >= _RANK[b] else b


def verb_class(name: str) -> tuple[str, str]:
    """``(class, source)`` from the tool's NAME alone: the labels.py word lists first, then our verb rules. A name nothing recognises is a write."""
    words = _words(name)
    found = classify_label(" ".join(words))
    if found & {ActionClass.SYSTEM, ActionClass.CREDENTIAL, ActionClass.PERMISSION, ActionClass.INSTALL, ActionClass.PAY}:
        return "execute", "verbs"
    if ActionClass.DELETE in found or any(w in DESTRUCTIVE_VERBS for w in words):
        return "destructive", "verbs"
    if ActionClass.SEND in found:
        return "send", "verbs"
    if found & {ActionClass.POST, ActionClass.SUBMIT} or (words and words[0] in WRITE_VERBS) or any(w in WRITE_VERBS for w in words[:2]):
        return "write", "verbs"
    if words and words[0] in EXECUTE_VERBS:
        return "execute", "verbs"
    if words and words[0] in READ_VERBS:
        return "read", "verbs"
    return "write", "unrecognised"


# ------------------------------------------------------------------------------------------------------------ SQL
_READ_FIRST = frozenset({"select", "with", "explain", "show", "describe", "desc", "values", "table"})
_SQL_WRITE = frozenset({"insert", "update", "delete", "drop", "alter", "create", "truncate", "replace", "merge", "grant", "revoke", "attach", "detach",
                        "vacuum", "reindex", "analyze", "analyse", "copy", "call", "do", "set", "reset", "lock", "comment", "refresh", "cluster",
                        "load", "install", "import", "export", "begin", "commit", "rollback", "savepoint", "release", "into", "listen", "notify",
                        "prepare", "execute", "deallocate", "discard", "security", "owner", "returning"})
_SQL_DESTRUCTIVE = frozenset({"drop", "delete", "truncate"})
_SQL_FUNCS = frozenset({"pg_terminate_backend", "pg_cancel_backend", "pg_sleep", "lo_import", "lo_export", "load_extension", "readfile", "writefile",
                        "pg_read_file", "pg_read_binary_file", "dblink", "dblink_exec", "nextval", "setval", "set_config", "pg_reload_conf",
                        "pg_advisory_lock", "pg_ls_dir", "fts3_tokenizer"})
_PRAGMA_READ = frozenset({"table_info", "table_xinfo", "table_list", "index_list", "index_info", "index_xinfo", "foreign_key_list", "database_list",
                          "collation_list", "function_list", "compile_options"})
MAX_SQL = 20_000


def _strip_sql(sql: str) -> str | None:
    """The statement with every string, quoted name and comment replaced by a space, read in ONE left-to-right pass the way the engines read it (a quote
    inside a comment is not a string, a comment marker inside a string is not a comment). None when it cannot be read with certainty: an unterminated
    string or comment, or a MySQL executable comment."""
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        c = sql[i]
        if c in "'\"`":
            j = i + 1
            while True:
                k = sql.find(c, j)
                if k == -1:
                    return None
                if c != "`" and k + 1 < n and sql[k + 1] == c:       # a doubled quote is a quote inside the string
                    j = k + 2
                    continue
                break
            out.append(" ")
            i = k + 1
        elif sql.startswith("--", i):                                  # (a # is NOT a comment here: in Postgres it is an operator and the rest of the line is code)
            j = sql.find("\n", i)
            out.append(" ")
            i = n if j == -1 else j
        elif sql.startswith("/*", i):
            if sql.startswith("/*!", i):
                return None                                       # MySQL runs the inside of /*! ... */ as code
            j = sql.find("*/", i + 2)
            if j == -1:
                return None
            out.append(" ")
            i = j + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def classify_sql(sql: Any) -> str:
    """``read`` only for ONE statement made of read words and nothing else; ``destructive`` when it drops, deletes or truncates; otherwise ``write``.
    Fail closed: anything odd (a second statement, dollar quoting, an E-string, a backslash, any non-ASCII character, an unterminated string or comment,
    a side-effect function) is a write. This is a second line of defence, not a SQL parser: the presets also say to use a read-only database role."""
    if not isinstance(sql, str) or not sql.strip() or len(sql) > MAX_SQL or "\x00" in sql:
        return "write"
    # No normalisation: NFKC would turn a full-width quote into a real one that the database does not see. Anything outside ASCII is a click.
    if not sql.isascii() or "$" in sql or "\\" in sql or re.search(r"\be'", sql.lower()):
        return "write"
    bare = _strip_sql(sql)
    if bare is None:
        return "write"
    stmts = [x for x in bare.split(";") if x.strip()]
    toks = re.findall(r"[a-z_][a-z0-9_]*", bare.lower())
    if len(stmts) != 1:
        return "destructive" if any(t in _SQL_DESTRUCTIVE for t in toks) else "write"
    if any(t in _SQL_DESTRUCTIVE for t in toks):
        return "destructive"
    first = toks[0] if toks else ""
    if first == "pragma":
        name = toks[1] if len(toks) > 1 else ""
        return "read" if name in _PRAGMA_READ and "=" not in bare else "write"
    if first not in _READ_FIRST:
        return "write"
    if first == "explain" and any(t in ("analyze", "analyse") for t in toks):
        return "write"
    if any(t in _SQL_WRITE for t in toks) or any(t in _SQL_FUNCS for t in toks):
        return "write"
    return "read"


def _sql_text(args: Mapping[str, Any]) -> Any:
    for k in ("sql", "query", "statement", "q"):
        if k in args:
            return args[k]
    return None


# ------------------------------------------------------------------------------------------------------------ the decision
def classify(preset: Preset, tool: str, arguments: Mapping[str, Any] | None = None, annotations: Mapping[str, Any] | Any = None) -> Classification:
    """The class of ONE call. ``annotations`` is whatever the server said about the tool (readOnlyHint and the rest): it is read as a hint, may raise a
    class of a tool our table does not list, and never lowers one."""
    args = arguments or {}
    table = preset.tools.lookup(tool)
    if table is not None:
        klass, source = table, "table"
    elif preset.tools.unlisted == "refuse":
        return Classification("unknown", "unlisted_refused", refused=True)
    else:
        klass, source = verb_class(tool)
        hint = getattr(annotations, "destructive_hint", None)
        if hint is None and isinstance(annotations, Mapping):
            hint = annotations.get("destructiveHint", annotations.get("destructive_hint"))
        if hint is True and _RANK[klass] < _RANK["destructive"]:
            klass, source = "destructive", "hint"
    if preset.tools.classifiers.get(tool) == "sql":
        klass, source = classify_sql(_sql_text(args)), "sql"
    for k in _ARG_METHOD_KEYS:                    # a delete hidden in an argument: GitHub's issue_write(method="delete") and the like
        v = args.get(k)
        if isinstance(v, str) and any(w in DESTRUCTIVE_VERBS for w in _words(v)):
            klass, source = _max(klass, "destructive"), "argument"
    return Classification(klass, source)


# the mapping to the existing action-class gate (security/gates.py): a class becomes the verb its word list recognises
GATE_VERB = {"write": "post", "send": "send", "destructive": "delete", "execute": "download and run"}
