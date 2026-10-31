"""NetSage AI — FastAPI backend."""

from __future__ import annotations

import asyncio
import csv
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from ai_service import diagnose as ai_diagnose
from rule_checker import check_show_output

load_dotenv()

DATA_DIR = Path(__file__).resolve().parent / "data"
CSV_PATH = DATA_DIR / "responsible_ai_log.csv"
CSV_FIELDS = [
    "timestamp",
    "case_id",
    "status",
    "edited_fix",
    "root_cause",
    "confidence",
    "osi_layer",
    "next_command",
    "symptom",
]

@asynccontextmanager
async def lifespan(_app: FastAPI):
    _ensure_csv()
    yield


app = FastAPI(title="NetSage AI", version="1.0.0", lifespan=lifespan)

origins = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DiagnoseRequest(BaseModel):
    symptom: str = Field(..., min_length=1)
    show_output: str = Field(..., min_length=1)


class ReviewRequest(BaseModel):
    case_id: str
    status: Literal["Accept", "Edit", "Reject"]
    edited_fix: str = ""
    root_cause: str = ""
    confidence: str = ""
    osi_layer: str = ""
    next_command: str = ""
    symptom: str = ""


def _ensure_csv() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not CSV_PATH.exists():
        with CSV_PATH.open("w", newline="", encoding="utf-8") as fh:
            csv.DictWriter(fh, fieldnames=CSV_FIELDS).writeheader()


def _read_rows() -> list[dict[str, str]]:
    _ensure_csv()
    with CSV_PATH.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/diagnose")
async def diagnose(body: DiagnoseRequest) -> dict:
    rules_task = asyncio.to_thread(check_show_output, body.show_output)
    ai_task = ai_diagnose(body.symptom, body.show_output)
    rules, ai = await asyncio.gather(rules_task, ai_task)
    return {
        "case_id": str(uuid.uuid4()),
        "rules": rules,
        "ai": ai,
    }


@app.post("/api/review")
async def review(body: ReviewRequest) -> dict:
    _ensure_csv()
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "case_id": body.case_id,
        "status": body.status,
        "edited_fix": body.edited_fix,
        "root_cause": body.root_cause,
        "confidence": body.confidence,
        "osi_layer": body.osi_layer,
        "next_command": body.next_command,
        "symptom": body.symptom,
    }
    with CSV_PATH.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writerow(row)
    return {"ok": True, "logged": row}


@app.get("/api/stats")
async def stats() -> dict:
    rows = _read_rows()
    total = len(rows)
    counts = {"Accept": 0, "Edit": 0, "Reject": 0}
    issue_types: dict[str, int] = {}
    for row in rows:
        status = row.get("status") or ""
        if status in counts:
            counts[status] += 1
        layer = (row.get("osi_layer") or "Unknown").strip() or "Unknown"
        issue_types[layer] = issue_types.get(layer, 0) + 1
    agreement_rate = round((counts["Accept"] / total) * 100, 1) if total else 0.0
    return {
        "total_reviewed": total,
        "accept_count": counts["Accept"],
        "edit_count": counts["Edit"],
        "reject_count": counts["Reject"],
        "agreement_rate": agreement_rate,
        "issue_types": issue_types,
    }

