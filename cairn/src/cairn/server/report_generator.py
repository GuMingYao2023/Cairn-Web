"""Generate detailed Markdown penetration-testing reports from project graphs."""

from __future__ import annotations

import sqlite3
from collections import deque
from datetime import datetime, timezone

from cairn.server.services import next_report_id


def generate_and_save_report(conn: sqlite3.Connection, project_id: str) -> str | None:
    """Generate a report for the given completed project and persist it.

    Returns the report id on success, or None if the project has no data to report.
    Best-effort: failures here do not affect the completion transaction.
    """
    content = _build_report_content(conn, project_id)
    if content is None:
        return None

    rid = next_report_id(conn)
    proj = conn.execute(
        "SELECT title, created_at FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    title = f"{proj['title']} - Report"

    conn.execute(
        "INSERT INTO reports (id, project_id, title, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (rid, project_id, title, content, _utcnow()),
    )
    return rid


def _build_report_content(conn: sqlite3.Connection, project_id: str) -> str | None:
    """Build the Markdown report body. Returns None when the project graph is empty."""
    proj = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if proj is None:
        return None

    facts = conn.execute(
        "SELECT * FROM facts WHERE project_id = ? ORDER BY id", (project_id,)
    ).fetchall()
    intents = conn.execute(
        "SELECT * FROM intents WHERE project_id = ? ORDER BY created_at",
        (project_id,),
    ).fetchall()
    hints = conn.execute(
        "SELECT * FROM hints WHERE project_id = ? ORDER BY created_at",
        (project_id,),
    ).fetchall()

    if not facts:
        return None

    # Build lookup maps
    facts_by_id = {f["id"]: f["description"] for f in facts}
    intents_by_id = {i["id"]: i for i in intents}

    # Build intent sources map
    sources_by_intent: dict[str, list[str]] = {}
    for i in intents:
        rows = conn.execute(
            "SELECT fact_id FROM intent_sources WHERE intent_id = ? AND project_id = ? ORDER BY rowid",
            (i["id"], project_id),
        ).fetchall()
        sources_by_intent[i["id"]] = [r["fact_id"] for r in rows]

    # Build: fact_id → list of intents that consume it (for forward traversal)
    consumers: dict[str, list[str]] = {}
    for iid, srcs in sources_by_intent.items():
        for fid in srcs:
            consumers.setdefault(fid, []).append(iid)

    origin_desc = facts_by_id.get("origin", "(unknown)")
    goal_desc = facts_by_id.get("goal", "(unknown)")

    lines: list[str] = []
    lines.append(f"# 渗透测试报告 — {proj['title']}")
    lines.append("")
    lines.append(f"- **项目 ID**: `{project_id}`")
    lines.append(f"- **创建时间**: {_format_ts(proj['created_at'])}")
    lines.append(f"- **完成时间**: {_format_ts(_utcnow())}")
    lines.append(f"- **状态**: {proj['status']}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 1. 概述")
    lines.append("")
    lines.append(f"**Origin (起点)**: {origin_desc}")
    lines.append("")
    lines.append(f"**Goal (目标)**: {goal_desc}")
    lines.append("")

    # ── Section 2: Reproduction Chain ──────────────────────────────────────
    steps = _build_reproduction_chain(
        intents, sources_by_intent, facts_by_id, consumers
    )
    lines.append("---")
    lines.append("")
    lines.append("## 2. 复现流程")
    lines.append("")
    if steps:
        for idx, step in enumerate(steps, 1):
            lines.append(f"### Step {idx}: {step['intent_id']}")
            lines.append("")
            lines.append(f"- **探索方向**: {step['description']}")
            lines.append(f"- **基于事实**: {', '.join(step['from'])}")
            lines.append(f"- **执行者**: {step['worker']}")
            lines.append(f"- **创建时间**: {_format_ts(step['created_at'])}")
            if step["concluded_at"]:
                lines.append(f"- **完成时间**: {_format_ts(step['concluded_at'])}")
            if step["discovery"]:
                lines.append(f"- **发现结果**: {step['discovery']}")
            lines.append("")
    else:
        lines.append("*(无 Intent 流程记录)*")
        lines.append("")

    # ── Section 3: Complete Timeline ───────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## 3. 完整时间线")
    lines.append("")

    timeline = _build_timeline(proj, facts, intents, hints, sources_by_intent)
    for entry in timeline:
        ts = _format_ts(entry["ts"])
        marker = entry["marker"]
        text = entry["text"]
        lines.append(f"- `[{ts}]` **{marker}** {text}")
    lines.append("")

    # ── Section 4: Key Facts ───────────────────────────────────────────────
    lines.append("---")
    lines.append("")
    lines.append("## 4. 关键事实清单")
    lines.append("")
    for f in facts:
        label = ""
        if f["id"] == "origin":
            label = " *(起点)*"
        elif f["id"] == "goal":
            label = " *(目标)*"
        lines.append(f"- **{f['id']}**{label}: {f['description']}")
    lines.append("")

    # ── Section 5: Hints ───────────────────────────────────────────────────
    if hints:
        lines.append("---")
        lines.append("")
        lines.append("## 5. 人工提示")
        lines.append("")
        for h in hints:
            lines.append(f"- `[{_format_ts(h['created_at'])}]` **{h['creator']}**: {h['content']}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"*报告由 Cairn 自动生成于 {_format_ts(_utcnow())}*")
    lines.append("")

    return "\n".join(lines)


def _build_reproduction_chain(
    intents: list[sqlite3.Row],
    sources_by_intent: dict[str, list[str]],
    facts_by_id: dict[str, str],
    consumers: dict[str, list[str]],
) -> list[dict[str, str]]:
    """Topologically sorted chain of concluded intents from origin toward goal."""
    # BFS from origin facts through intent graph
    visited_intents: set[str] = set()
    ordered: list[sqlite3.Row] = []

    # Only consider concluded intents (they have to_fact_id) and non-bootstrap
    concluded = [i for i in intents if i["to_fact_id"] is not None]
    # Also include the completion intent (to_fact_id = 'goal')
    by_id = {i["id"]: i for i in concluded}

    # Build adjacency: intent A → intent B if A's output fact is in B's sources
    adjacency: dict[str, list[str]] = {}
    indegree: dict[str, int] = {}
    for i in concluded:
        adjacency.setdefault(i["id"], [])
        indegree.setdefault(i["id"], 0)

    for i in concluded:
        out_fact = i["to_fact_id"]
        if out_fact and out_fact in consumers:
            for next_iid in consumers[out_fact]:
                if next_iid in by_id:
                    adjacency.setdefault(i["id"], []).append(next_iid)
                    indegree[next_iid] = indegree.get(next_iid, 0) + 1

    # Kahn's algorithm for topological sort
    queue: deque[str] = deque()
    for i in concluded:
        srcs = sources_by_intent.get(i["id"], [])
        # Start with intents that consume "origin" or have only origin-level sources
        if "origin" in srcs or indegree.get(i["id"], 0) == 0:
            queue.append(i["id"])

    while queue:
        iid = queue.popleft()
        if iid in visited_intents:
            continue
        visited_intents.add(iid)
        intent = by_id.get(iid)
        if intent is not None:
            ordered.append(intent)
        for next_iid in adjacency.get(iid, []):
            indegree[next_iid] -= 1
            if indegree[next_iid] == 0:
                queue.append(next_iid)

    # Add any remaining intents not visited (disconnected subgraphs)
    for i in concluded:
        if i["id"] not in visited_intents:
            ordered.append(i)
            visited_intents.add(i["id"])

    result: list[dict[str, str]] = []
    for i in ordered:
        srcs = sources_by_intent.get(i["id"], [])
        out_fact_id = i["to_fact_id"]
        discovery = ""
        if out_fact_id and out_fact_id != "goal":
            discovery = facts_by_id.get(out_fact_id, "")
        elif out_fact_id == "goal":
            discovery = f"🎯 **达成目标**: {facts_by_id.get('goal', '')}"

        result.append({
            "intent_id": i["id"],
            "description": i["description"],
            "from": srcs,
            "worker": i["worker"] or i["creator"],
            "created_at": i["created_at"],
            "concluded_at": i["concluded_at"] or "",
            "discovery": discovery,
        })

    return result


def _build_timeline(
    proj: sqlite3.Row,
    facts: list[sqlite3.Row],
    intents: list[sqlite3.Row],
    hints: list[sqlite3.Row],
    sources_by_intent: dict[str, list[str]],
) -> list[dict[str, str]]:
    """Build chronological timeline entries."""
    entries: list[tuple[str, int, str, str]] = []  # (ts, order, marker, text)
    order = 0

    facts_by_id = {f["id"]: f["description"] for f in facts}

    # Project created
    entries.append((
        proj["created_at"],
        order,
        "PROJECT",
        f"项目创建: {proj['title']}",
    ))
    order += 1

    # Hints
    for h in hints:
        entries.append((
            h["created_at"],
            order,
            "HINT",
            f"{h['creator']}: {h['content']}",
        ))
        order += 1

    # Intents declared and concluded
    for i in intents:
        srcs = sources_by_intent.get(i["id"], [])
        from_str = ", ".join(srcs)
        entries.append((
            i["created_at"],
            order,
            "INTENT",
            f"声明 {i['id']} by {i['creator']}: {i['description']} (from: {from_str})",
        ))
        order += 1

        if i["concluded_at"] and i["to_fact_id"]:
            actor = i["worker"] or i["creator"]
            if i["to_fact_id"] == "goal":
                entries.append((
                    i["concluded_at"],
                    order,
                    "COMPLETED",
                    f"项目完成 by {actor} via {i['id']} (from: {from_str})",
                ))
            else:
                desc = facts_by_id.get(i["to_fact_id"], "")
                entries.append((
                    i["concluded_at"],
                    order,
                    "CONCLUDE",
                    f"{i['id']} by {actor} → {i['to_fact_id']}: {desc}",
                ))
            order += 1

    entries.sort(key=lambda e: (e[0], e[1]))
    return [{"ts": e[0], "marker": e[2], "text": e[3]} for e in entries]


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_ts(ts: str | None) -> str:
    if not ts:
        return "(unknown)"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ts
