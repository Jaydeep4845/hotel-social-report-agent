"""FastAPI app: JSON API under /api, plus the single-page UI at /."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

load_dotenv()

from app import db, export, importer, llm, report  # noqa: E402  (needs env loaded first)
from app.metrics import build_metrics  # noqa: E402

logging.basicConfig(level=logging.INFO)
STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_app):
    db.init_db()
    if db.is_empty():
        db.seed_from_files()
    yield


app = FastAPI(
    title="Hotel Social Report Agent",
    description="Import social-media metrics, generate evidence-based client reports, approve, export.",
    version="0.1.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


# ---- helpers -------------------------------------------------------------

def require_client(client_id):
    client = db.get_client(client_id)
    if not client:
        raise HTTPException(404, "Client not found")
    return client


def require_report(client_id, report_id):
    require_client(client_id)
    r = db.get_report(client_id, report_id)
    if not r:
        # same answer whether it doesn't exist or belongs to another client
        raise HTTPException(404, "Report not found")
    return r


class ApproveBody(BaseModel):
    reviewer: str = Field(min_length=2, max_length=60)
    summary: str | None = Field(default=None, max_length=3000)
    excluded_insights: list[str] = []
    note: str | None = Field(default=None, max_length=500)


class RejectBody(BaseModel):
    reviewer: str = Field(min_length=2, max_length=60)
    note: str = Field(min_length=3, max_length=500)


# ---- pages ---------------------------------------------------------------

@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC / "index.html")


# ---- API -----------------------------------------------------------------

@app.get("/api/status")
def status():
    return {
        "llm_enabled": llm.is_enabled(),
        "llm_model": os.environ.get("LLM_MODEL", "claude-opus-5-5") if llm.is_enabled() else None,
    }


@app.get("/api/clients")
def list_clients():
    return db.list_clients()


@app.get("/api/clients/{client_id}/overview")
def overview(client_id: str):
    client = require_client(client_id)
    posts = db.get_posts(client_id)
    return {"client": client, "post_count": len(posts), "metrics": build_metrics(posts) if posts else None}


@app.post("/api/clients/{client_id}/import")
async def import_posts(client_id: str, file: UploadFile = File(...)):
    require_client(client_id)
    raw = await file.read()
    if len(raw) > 2_000_000:
        raise HTTPException(413, "File too large (max 2 MB)")
    rows, errors = importer.parse_csv(raw)
    if errors:
        raise HTTPException(422, {"message": "Import rejected, nothing was saved", "errors": errors})
    count = db.upsert_posts(client_id, rows)
    db.log(client_id, "data_imported", note=f"{count} posts from {file.filename}")
    return {"imported": count}


@app.get("/api/sample.csv", response_class=PlainTextResponse)
def sample_csv():
    """A small example of the expected import format."""
    path = db.DATA_DIR / "atlas-marrakech.csv"
    lines = path.read_text(encoding="utf-8").splitlines()[:6]
    return Response("\n".join(lines) + "\n", media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=sample.csv"})


@app.post("/api/clients/{client_id}/reports", status_code=201)
def create_report(client_id: str):
    require_client(client_id)
    try:
        report_id = report.generate(client_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return db.get_report(client_id, report_id)


@app.get("/api/clients/{client_id}/reports")
def list_reports(client_id: str):
    require_client(client_id)
    return db.list_reports(client_id)


@app.get("/api/clients/{client_id}/reports/{report_id}")
def get_report(client_id: str, report_id: int):
    r = require_report(client_id, report_id)
    r["audit"] = db.get_audit(client_id, report_id)
    return r


@app.post("/api/clients/{client_id}/reports/{report_id}/approve")
def approve(client_id: str, report_id: int, body: ApproveBody):
    r = require_report(client_id, report_id)
    if r["status"] != "draft":
        raise HTTPException(409, f"Report is already {r['status']}")

    payload = r["payload"]
    changes = []
    if body.summary and body.summary.strip() != payload["summary"]:
        payload["summary"] = body.summary.strip()
        payload["summary_source"] = "edited by reviewer"
        changes.append("summary edited")
    if body.excluded_insights:
        before = len(payload["insights"])
        payload["insights"] = [i for i in payload["insights"] if i["id"] not in body.excluded_insights]
        removed = before - len(payload["insights"])
        if removed:
            changes.append(f"{removed} insight(s) removed")

    note = "; ".join(filter(None, [body.note, *changes])) or None
    db.set_report_status(client_id, report_id, "approved", body.reviewer, note, payload)
    db.log(client_id, "approved", report_id, actor=body.reviewer, note=note)
    return get_report(client_id, report_id)


@app.post("/api/clients/{client_id}/reports/{report_id}/reject")
def reject(client_id: str, report_id: int, body: RejectBody):
    r = require_report(client_id, report_id)
    if r["status"] != "draft":
        raise HTTPException(409, f"Report is already {r['status']}")
    db.set_report_status(client_id, report_id, "rejected", body.reviewer, body.note)
    db.log(client_id, "rejected", report_id, actor=body.reviewer, note=body.note)
    return get_report(client_id, report_id)


@app.get("/api/clients/{client_id}/reports/{report_id}/export")
def export_report(client_id: str, report_id: int, fmt: str = "md"):
    r = require_report(client_id, report_id)
    if r["status"] != "approved":
        raise HTTPException(409, "Only approved reports can be exported")
    audit = db.get_audit(client_id, report_id)
    name = f"{client_id}_{r['period']}_report"

    if fmt == "md":
        body, media = export.to_markdown(r, audit), "text/markdown"
    elif fmt == "csv":
        body, media = export.to_csv(r), "text/csv"
    elif fmt == "json":
        body, media = export.to_json(r, audit), "application/json"
    else:
        raise HTTPException(400, "fmt must be md, csv or json")

    db.log(client_id, "exported", report_id, note=fmt)
    return Response(body, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{name}.{fmt}"'})


@app.post("/api/demo/reset")
def reset_demo():
    db.reset_demo()
    return {"ok": True}
