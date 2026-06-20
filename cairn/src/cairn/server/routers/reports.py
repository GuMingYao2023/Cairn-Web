from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from cairn.server.db import get_conn
from cairn.server.models import ReportListItem, ReportOut

router = APIRouter(tags=["reports"])


@router.get("/reports", response_model=list[ReportListItem])
def list_reports():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, project_id, title, created_at FROM reports ORDER BY created_at DESC"
        ).fetchall()
        return [
            ReportListItem(
                id=row["id"],
                project_id=row["project_id"],
                title=row["title"],
                created_at=row["created_at"],
            )
            for row in rows
        ]


@router.get("/reports/{report_id}", response_model=ReportOut)
def get_report(report_id: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM reports WHERE id = ?", (report_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Report not found")
        return ReportOut(
            id=row["id"],
            project_id=row["project_id"],
            title=row["title"],
            content=row["content"],
            created_at=row["created_at"],
        )


@router.delete("/reports/{report_id}", status_code=204)
def delete_report(report_id: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM reports WHERE id = ?", (report_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(404, "Report not found")
        conn.execute("DELETE FROM reports WHERE id = ?", (report_id,))
    return Response(status_code=204)
