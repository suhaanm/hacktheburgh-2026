"""Stand-in SQLite (and Postgres, BigQuery) MCP server (CONNECTIONS). Ours, written with the official MCP Python SDK; NOT Google's Toolbox.

Serves a small database of INVENTED data over stdio, with the tool names of the real Toolbox sources (``list_tables``, ``execute_sql``, and
the BigQuery and Postgres read tools) so the same class table applies:

    python sqlite_server.py --db <file> [--name sqlite|postgres|bigquery] [--synthetic <data/synthetic folder>]

The file is built on first use: a made-up claims queue (60 rows, fixed seed, no real people) and, when a synthetic activity folder exists
(``<synthetic>/<persona>/events.jsonl``), a table of daily COUNTS of its events by persona, role and type (no event content is copied).
``execute_sql`` runs the statement it is given in this example database only; the agent decides whether the statement may run (a single read-only
statement does; anything else waits for the worker's click). No network.
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

RO = ToolAnnotations(read_only_hint=True)
DB: Path = Path("example.db")
NAME = "sqlite"
SYN: Path | None = None
MAX_ROWS = 200


def _build(path: Path, synthetic: Path | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        return
    rnd = random.Random(20261107)
    con = sqlite3.connect(path)
    con.execute("create table claims (case_ref text primary key, kind text, age_days integer, handler text, state text, amount_gbp real)")
    handlers = ["Handler A", "Handler B", "Handler C", "Handler D"]
    kinds = ["new_claim", "change_of_circumstances", "housing_cost", "review"]
    rows = [(f"EX-{100 + i}", rnd.choice(kinds), rnd.randint(0, 28), rnd.choice(handlers), rnd.choice(["open", "waiting", "closed"]),
             round(rnd.uniform(40, 520), 2)) for i in range(60)]
    con.executemany("insert into claims values (?,?,?,?,?,?)", rows)
    con.execute("create table monthly_totals (month text, kind text, cases integer, median_days real)")
    con.executemany("insert into monthly_totals values (?,?,?,?)", [(f"2026-{m:02d}", k, rnd.randint(20, 90), round(rnd.uniform(2, 9), 1))
                                                                      for m in range(1, 11) for k in kinds])
    con.execute("create table events_daily (persona text, role text, day text, type text, n integer)")
    if synthetic and synthetic.is_dir():
        counts: Counter[tuple[str, str, str, str]] = Counter()
        for f in sorted(synthetic.glob("*/events.jsonl")):
            with f.open(encoding="utf-8") as fh:
                for i, line in enumerate(fh):
                    if i >= 50_000:
                        break
                    try:
                        e = json.loads(line)
                        counts[(f.parent.name, str(e.get("role", "")), str(e.get("t", ""))[:10], str(e.get("type", "")))] += 1
                    except ValueError:
                        continue
        con.executemany("insert into events_daily values (?,?,?,?,?)", [(*k, n) for k, n in sorted(counts.items())[:5000]])
    con.commit()
    con.close()


def _fmt(cur: sqlite3.Cursor) -> str:
    cols = [d[0] for d in (cur.description or [])]
    rows = cur.fetchmany(MAX_ROWS)
    if not cols:
        return "ok"
    return "\n".join([" | ".join(cols), *[" | ".join("" if v is None else str(v) for v in r) for r in rows]])


server = MCPServer("example-database")


@server.tool(annotations=RO)
def list_tables() -> str:
    """List the tables and their columns."""
    con = sqlite3.connect(DB)
    try:
        out = []
        for (t,) in con.execute("select name from sqlite_master where type='table' order by name"):
            out.append(f"{t}: " + ", ".join(r[1] for r in con.execute(f"pragma table_info({t})")))
        return "\n".join(out)
    finally:
        con.close()


@server.tool()
def execute_sql(sql: str) -> str:
    """Run one SQL statement against the example database."""
    con = sqlite3.connect(DB)
    try:
        cur = con.execute(sql)
        out = _fmt(cur)
        con.commit()
        return out
    finally:
        con.close()


# Names the real BigQuery and Postgres sources use, answered from the same example data.
@server.tool(annotations=RO)
def list_dataset_ids() -> str:
    """BigQuery stand-in: the datasets (one)."""
    return "example_claims"


@server.tool(annotations=RO)
def list_table_ids(dataset: str = "example_claims") -> str:
    """BigQuery stand-in: the tables."""
    return list_tables()


@server.tool(annotations=RO)
def get_table_info(table: str) -> str:
    """BigQuery stand-in: columns of a table."""
    con = sqlite3.connect(DB)
    try:
        return "\n".join(f"{r[1]} {r[2]}" for r in con.execute(f"pragma table_info({''.join(c for c in table if c.isalnum() or c == '_')})"))
    finally:
        con.close()


@server.tool(annotations=RO)
def database_overview() -> str:
    """Postgres stand-in: sizes of the tables."""
    con = sqlite3.connect(DB)
    try:
        return "\n".join(f"{t}: {con.execute(f'select count(*) from {t}').fetchone()[0]} rows"
                         for (t,) in con.execute("select name from sqlite_master where type='table' order by name").fetchall())
    finally:
        con.close()


def main(argv: list[str] | None = None) -> None:
    global DB, NAME, SYN
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--name", default="sqlite")
    ap.add_argument("--synthetic", default=None)
    a = ap.parse_args(argv)
    DB, NAME = Path(a.db), a.name
    SYN = Path(a.synthetic) if a.synthetic else None
    _build(DB, SYN)
    server.run("stdio")


if __name__ == "__main__":
    main(sys.argv[1:])
