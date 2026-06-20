"""Tests for report generation and API endpoints."""

from __future__ import annotations

from cairn.server.db import configure, get_conn
from cairn.server.report_generator import generate_and_save_report
from cairn.server.services import next_project_id, next_fact_id, next_intent_id, next_hint_id, utcnow


def _setup_test_project(conn) -> str:
    """Create a completed project with facts, intents, and hints."""
    pid = next_project_id(conn)
    now = utcnow()

    conn.execute(
        "INSERT INTO projects (id, title, status, bootstrap_enabled, created_at) "
        "VALUES (?, ?, 'completed', 1, ?)",
        (pid, "Test Report Project", now),
    )
    conn.execute(
        "INSERT INTO facts (id, project_id, description) VALUES (?, ?, ?)",
        ("origin", pid, "Target network 10.0.0.0/24"),
    )
    conn.execute(
        "INSERT INTO facts (id, project_id, description) VALUES (?, ?, ?)",
        ("goal", pid, "Exfiltrate database contents"),
    )

    fid1 = next_fact_id(conn, pid)
    conn.execute(
        "INSERT INTO facts (id, project_id, description) VALUES (?, ?, ?)",
        (fid1, pid, "Open port 3306 MySQL"),
    )
    fid2 = next_fact_id(conn, pid)
    conn.execute(
        "INSERT INTO facts (id, project_id, description) VALUES (?, ?, ?)",
        (fid2, pid, "MySQL root with empty password"),
    )
    fid3 = next_fact_id(conn, pid)
    conn.execute(
        "INSERT INTO facts (id, project_id, description) VALUES (?, ?, ?)",
        (fid3, pid, "Dumped all databases via mysqldump"),
    )

    conn.execute(
        "INSERT INTO hints (id, project_id, content, creator, created_at) VALUES (?, ?, ?, ?, ?)",
        (next_hint_id(conn, pid), pid, "Try default MySQL credentials", "analyst", now),
    )

    # Intent chain: origin → fid1 → fid2 → fid3 → goal
    iid1 = next_intent_id(conn, pid)
    conn.execute(
        "INSERT INTO intents (id, project_id, to_fact_id, description, creator, worker, created_at, concluded_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (iid1, pid, fid1, "Port scan target", "reasoner", "worker-a", now, now),
    )
    conn.execute("INSERT INTO intent_sources (intent_id, project_id, fact_id) VALUES (?, ?, ?)", (iid1, pid, "origin"))

    iid2 = next_intent_id(conn, pid)
    conn.execute(
        "INSERT INTO intents (id, project_id, to_fact_id, description, creator, worker, created_at, concluded_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (iid2, pid, fid2, "Test MySQL auth", "reasoner", "worker-b", now, now),
    )
    conn.execute("INSERT INTO intent_sources (intent_id, project_id, fact_id) VALUES (?, ?, ?)", (iid2, pid, fid1))

    iid3 = next_intent_id(conn, pid)
    conn.execute(
        "INSERT INTO intents (id, project_id, to_fact_id, description, creator, worker, created_at, concluded_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (iid3, pid, fid3, "Dump data via mysql client", "reasoner", "worker-c", now, now),
    )
    conn.execute("INSERT INTO intent_sources (intent_id, project_id, fact_id) VALUES (?, ?, ?)", (iid3, pid, fid2))

    iid4 = next_intent_id(conn, pid)
    conn.execute(
        "INSERT INTO intents (id, project_id, to_fact_id, description, creator, worker, created_at, concluded_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (iid4, pid, "goal", "Goal achieved — all DB data extracted", "reasoner", "worker-c", now, now),
    )
    conn.execute("INSERT INTO intent_sources (intent_id, project_id, fact_id) VALUES (?, ?, ?)", (iid4, pid, fid3))

    return pid


def test_generate_report_creates_record(tmp_path):
    """Report should be created with correct metadata and non-empty content."""
    db_path = tmp_path / "test-report.db"
    configure(db_path)

    with get_conn() as conn:
        pid = _setup_test_project(conn)
        rid = generate_and_save_report(conn, pid)
        assert rid is not None
        assert rid.startswith("rpt_")

        row = conn.execute("SELECT * FROM reports WHERE id = ?", (rid,)).fetchone()
        assert row is not None
        assert row["project_id"] == pid
        assert "Test Report Project" in row["title"]
        assert len(row["content"]) > 500  # Substantial report content

        # Content should include key sections
        content = row["content"]
        assert "渗透测试报告" in content
        assert "复现流程" in content
        assert "完整时间线" in content
        assert "关键事实清单" in content
        assert "人工提示" in content
        assert "10.0.0.0/24" in content
        assert "Exfiltrate database contents" in content
        assert "Port scan" in content
        assert "Test MySQL auth" in content


def test_generate_report_handles_empty_project(tmp_path):
    """Report generation should handle projects with only origin and goal."""
    db_path = tmp_path / "test-empty.db"
    configure(db_path)

    with get_conn() as conn:
        pid = next_project_id(conn)
        conn.execute(
            "INSERT INTO projects (id, title, status, bootstrap_enabled, created_at) VALUES (?, ?, 'completed', 1, ?)",
            (pid, "Minimal Project", utcnow()),
        )
        conn.execute(
            "INSERT INTO facts (id, project_id, description) VALUES (?, ?, ?)",
            ("origin", pid, "Start here"),
        )
        conn.execute(
            "INSERT INTO facts (id, project_id, description) VALUES (?, ?, ?)",
            ("goal", pid, "End here"),
        )

        rid = generate_and_save_report(conn, pid)
        assert rid is not None

        row = conn.execute("SELECT * FROM reports WHERE id = ?", (rid,)).fetchone()
        assert row is not None
        assert "Minimal Project" in row["title"]
        assert "Start here" in row["content"]
        assert "End here" in row["content"]


def test_report_list_and_delete_api(tmp_path):
    """Test the reports API via direct DB access pattern (used by routes)."""
    db_path = tmp_path / "test-api.db"
    configure(db_path)

    with get_conn() as conn:
        pid = _setup_test_project(conn)
        rid1 = generate_and_save_report(conn, pid)
        rid2 = generate_and_save_report(conn, pid)  # Can generate multiple reports

        # List
        rows = conn.execute(
            "SELECT id, project_id, title, created_at FROM reports ORDER BY created_at DESC"
        ).fetchall()
        assert len(rows) >= 2
        report_ids = {r["id"] for r in rows}
        assert rid1 in report_ids
        assert rid2 in report_ids

        # Get single
        row = conn.execute("SELECT * FROM reports WHERE id = ?", (rid1,)).fetchone()
        assert row is not None
        assert row["id"] == rid1

        # Delete
        conn.execute("DELETE FROM reports WHERE id = ?", (rid1,))
        deleted = conn.execute("SELECT 1 FROM reports WHERE id = ?", (rid1,)).fetchone()
        assert deleted is None

        # Verify rid2 still exists
        remaining = conn.execute("SELECT 1 FROM reports WHERE id = ?", (rid2,)).fetchone()
        assert remaining is not None
