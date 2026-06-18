import os
import re
import uuid
from datetime import date
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


APP_NAME = "LORI Drive API"

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
LORI_API_KEY = os.getenv("LORI_API_KEY", "")

if not SUPABASE_URL:
    print("WARNING: SUPABASE_URL is not set.")
if not SUPABASE_SERVICE_ROLE_KEY:
    print("WARNING: SUPABASE_SERVICE_ROLE_KEY is not set.")
if not LORI_API_KEY:
    print("WARNING: LORI_API_KEY is not set. Set this before connecting Voiceflow.")


app = FastAPI(title=APP_NAME, version="1.0.0")

# For prototype use, this is open. For production, restrict this to your actual portal domain.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_lori_key(provided_key: Optional[str]) -> None:
    """Simple API-key check so random users cannot call your backend."""
    if not LORI_API_KEY:
        raise HTTPException(status_code=500, detail="LORI_API_KEY is not configured on the server.")
    if provided_key != LORI_API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized. Missing or invalid x-lori-api-key.")


async def supabase_get(view_name: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Query a Supabase table or view through the REST API."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=500, detail="Supabase environment variables are not configured.")

    url = f"{SUPABASE_URL}/rest/v1/{view_name}"

    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers, params=params)

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail={
                "message": "Supabase query failed.",
                "view": view_name,
                "supabase_status": response.status_code,
                "supabase_response": response.text,
            },
        )

    return response.json()


@app.get("/")
async def root():
    return {
        "name": APP_NAME,
        "status": "running",
        "message": "LORI Drive backend is live.",
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "supabase_url_configured": bool(SUPABASE_URL),
        "supabase_key_configured": bool(SUPABASE_SERVICE_ROLE_KEY),
        "lori_api_key_configured": bool(LORI_API_KEY),
    }


@app.get("/batch-summary")
async def batch_summary(
    batch_code: str = Query("JESSUP-DEMO-001"),
    x_lori_api_key: Optional[str] = Query(None, alias="api_key"),
):
    require_lori_key(x_lori_api_key)
    rows = await supabase_get(
        "lori_batch_summary",
        {
            "batch_code": f"eq.{batch_code}",
            "select": "*",
            "limit": "1",
        },
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No batch found for {batch_code}.")
    return rows[0]


@app.get("/worst-drivers")
async def worst_drivers(
    batch_code: str = Query("JESSUP-DEMO-001"),
    limit: int = Query(10, ge=1, le=100),
    x_lori_api_key: Optional[str] = Query(None, alias="api_key"),
):
    require_lori_key(x_lori_api_key)
    return await supabase_get(
        "lori_worst_drivers",
        {
            "batch_code": f"eq.{batch_code}",
            "select": "employee_id,driver_name,supervisor_name,safety_score,route_score,overall_score,risk_level,trend_direction,recommended_action",
            "limit": str(limit),
        },
    )


@app.get("/best-drivers")
async def best_drivers(
    batch_code: str = Query("JESSUP-DEMO-001"),
    limit: int = Query(10, ge=1, le=100),
    x_lori_api_key: Optional[str] = Query(None, alias="api_key"),
):
    require_lori_key(x_lori_api_key)
    return await supabase_get(
        "lori_best_drivers",
        {
            "batch_code": f"eq.{batch_code}",
            "select": "employee_id,driver_name,supervisor_name,safety_score,route_score,overall_score,risk_level,trend_direction,recommended_action",
            "limit": str(limit),
        },
    )


@app.get("/risk-summary")
async def risk_summary(
    batch_code: str = Query("JESSUP-DEMO-001"),
    x_lori_api_key: Optional[str] = Query(None, alias="api_key"),
):
    require_lori_key(x_lori_api_key)
    return await supabase_get(
        "lori_risk_summary",
        {
            "batch_code": f"eq.{batch_code}",
            "select": "risk_level,driver_count,average_overall_score,average_safety_score,average_route_score,average_compliance_score,average_payroll_score,average_training_score,lowest_overall_score,highest_overall_score",
            "order": "risk_level.asc",
        },
    )


@app.get("/supervisor-actions")
async def supervisor_actions(
    batch_code: str = Query("JESSUP-DEMO-001"),
    limit: int = Query(50, ge=1, le=200),
    x_lori_api_key: Optional[str] = Query(None, alias="api_key"),
):
    require_lori_key(x_lori_api_key)
    return await supabase_get(
        "lori_supervisor_action_list",
        {
            "batch_code": f"eq.{batch_code}",
            "select": "employee_id,driver_name,supervisor_name,action_type,action_reason,priority,due_date,status,notes,priority_sort_order",
            "order": "priority_sort_order.asc,due_date.asc",
            "limit": str(limit),
        },
    )


@app.get("/driver-360")
async def driver_360(
    employee_id: str = Query(..., description="Example: DEMO-D007"),
    batch_code: str = Query("JESSUP-DEMO-001"),
    x_lori_api_key: Optional[str] = Query(None, alias="api_key"),
):
    require_lori_key(x_lori_api_key)
    rows = await supabase_get(
        "lori_driver_360",
        {
            "batch_code": f"eq.{batch_code}",
            "employee_id": f"eq.{employee_id}",
            "select": "*",
            "limit": "1",
        },
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No driver profile found for {employee_id} in {batch_code}.")
    return rows[0]


@app.get("/leadership-briefing")
async def leadership_briefing(
    batch_code: str = Query("JESSUP-DEMO-001"),
    x_lori_api_key: Optional[str] = Query(None, alias="api_key"),
):
    require_lori_key(x_lori_api_key)
    rows = await supabase_get(
        "lori_leadership_briefings",
        {
            "batch_code": f"eq.{batch_code}",
            "report_type": "eq.Daily Leadership Briefing",
            "select": "batch_code,organization_name,location_name,report_type,report_title,report_body,created_by,created_at",
            "limit": "1",
        },
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"No leadership briefing found for {batch_code}.")
    return rows[0]


@app.get("/voiceflow/summary")
async def voiceflow_summary(
    batch_code: str = Query("JESSUP-DEMO-001"),
    x_lori_api_key: Optional[str] = Query(None, alias="api_key"),
):
    """Returns a clean sentence Voiceflow can speak back."""
    require_lori_key(x_lori_api_key)

    batch_rows = await supabase_get(
        "lori_batch_summary",
        {
            "batch_code": f"eq.{batch_code}",
            "select": "*",
            "limit": "1",
        },
    )
    risk_rows = await supabase_get(
        "lori_risk_summary",
        {
            "batch_code": f"eq.{batch_code}",
            "select": "risk_level,driver_count",
        },
    )

    if not batch_rows:
        raise HTTPException(status_code=404, detail=f"No batch found for {batch_code}.")

    batch = batch_rows[0]
    risk_map = {row["risk_level"]: row["driver_count"] for row in risk_rows}

    response_text = (
        f"Batch {batch['batch_code']} is {batch['batch_status']}. "
        f"I found {batch['total_drivers_found']} drivers, {batch['total_safety_events']} safety events, "
        f"{batch['total_payroll_exceptions']} payroll exceptions, {batch['total_training_gaps']} training gaps, "
        f"and {batch['total_compliance_gaps']} compliance gaps. "
        f"Risk summary: {risk_map.get('Corrective Action Needed', 0)} driver requires corrective action, "
        f"{risk_map.get('Watch List', 0)} drivers are on the watch list, "
        f"{risk_map.get('Solid Performer', 0)} are solid performers, and "
        f"{risk_map.get('Elite Performer', 0)} are elite performers."
    )

    return {
        "batch_code": batch_code,
        "response_text": response_text,
        "batch_summary": batch,
        "risk_summary": risk_rows,
    }
def clean_file_name(filename: str) -> str:
    """Make uploaded file names safe for storage paths."""
    name = filename or "uploaded-file"
    name = name.strip().replace(" ", "_")
    name = re.sub(r"[^A-Za-z0-9._-]", "", name)
    return name or "uploaded-file"


async def supabase_insert(table_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Insert one row into a Supabase table through the REST API."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=500, detail="Supabase environment variables are not configured.")

    url = f"{SUPABASE_URL}/rest/v1/{table_name}"

    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=payload)

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail={
                "message": "Supabase insert failed.",
                "table": table_name,
                "supabase_status": response.status_code,
                "supabase_response": response.text,
            },
        )

    rows = response.json()
    return rows[0] if rows else {}


async def upload_to_supabase_storage(
    bucket_name: str,
    storage_path: str,
    file: UploadFile,
) -> Dict[str, Any]:
    """Upload one file into a Supabase Storage bucket."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=500, detail="Supabase environment variables are not configured.")

    file_bytes = await file.read()

    url = f"{SUPABASE_URL}/storage/v1/object/{bucket_name}/{storage_path}"

    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": file.content_type or "application/octet-stream",
        "x-upsert": "true",
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, headers=headers, content=file_bytes)

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail={
                "message": "Supabase storage upload failed.",
                "bucket": bucket_name,
                "path": storage_path,
                "supabase_status": response.status_code,
                "supabase_response": response.text,
            },
        )

    return {
        "bucket": bucket_name,
        "path": storage_path,
        "file_name": file.filename,
        "content_type": file.content_type,
        "size_bytes": len(file_bytes),
    }


@app.post("/upload-batch")
async def upload_batch(
    api_key: str = Form(...),
    organization_name: str = Form(...),
    location_name: str = Form(...),
    location_code: str = Form(...),
    uploaded_by: str = Form(...),
    report_period_start: date = Form(...),
    report_period_end: date = Form(...),

    driver_performance_file: Optional[UploadFile] = File(None),
    safety_events_file: Optional[UploadFile] = File(None),
    payroll_exceptions_file: Optional[UploadFile] = File(None),
    training_gaps_file: Optional[UploadFile] = File(None),
    compliance_gaps_file: Optional[UploadFile] = File(None),
    route_performance_file: Optional[UploadFile] = File(None),
    supervisor_notes_file: Optional[UploadFile] = File(None),
):
    """
    Receives a LORI delivery operations batch from the portal,
    stores uploaded source files in Supabase Storage,
    and records batch/file tracking metadata in Supabase.
    """
    require_lori_key(api_key)

    bucket_name = "lori-batch-uploads"
    clean_location_code = location_code.strip().upper().replace(" ", "-")
    batch_code = f"{clean_location_code}-{report_period_end.strftime('%Y-%m-%d')}-{uuid.uuid4().hex[:6].upper()}"

    source_files = [
        ("Driver Performance File", driver_performance_file),
        ("Safety Events File", safety_events_file),
        ("Payroll Exceptions File", payroll_exceptions_file),
        ("Training Gaps File", training_gaps_file),
        ("Compliance Gaps File", compliance_gaps_file),
        ("Route Performance File", route_performance_file),
        ("Supervisor Notes File", supervisor_notes_file),
    ]

    uploaded_file_results = []

    for file_type, file in source_files:
        if file is None:
            continue

        safe_name = clean_file_name(file.filename)
        storage_path = f"{batch_code}/{file_type.replace(' ', '_').lower()}/{safe_name}"

        storage_result = await upload_to_supabase_storage(
            bucket_name=bucket_name,
            storage_path=storage_path,
            file=file,
        )

        file_record = await supabase_insert(
            "lori_uploaded_files",
            {
                "batch_code": batch_code,
                "file_type": file_type,
                "original_file_name": file.filename,
                "storage_bucket": bucket_name,
                "storage_path": storage_path,
                "uploaded_by": uploaded_by,
                "processing_status": "uploaded",
                "notes": "Uploaded through LORI Data Intake portal.",
            },
        )

        uploaded_file_results.append(
            {
                "file_type": file_type,
                "original_file_name": file.filename,
                "storage": storage_result,
                "record": file_record,
            }
        )

    batch_record = await supabase_insert(
        "lori_batch_uploads",
        {
            "batch_code": batch_code,
            "organization_name": organization_name,
            "location_name": location_name,
            "location_code": clean_location_code,
            "uploaded_by": uploaded_by,
            "report_period_start": report_period_start.isoformat(),
            "report_period_end": report_period_end.isoformat(),
            "batch_status": "uploaded",
            "total_files": len(uploaded_file_results),
            "notes": "Batch files uploaded successfully. File parsing and scoring will be connected in the next production step.",
        },
    )

    return {
        "status": "success",
        "message": "Batch uploaded successfully. File parsing and scoring will be connected in the next production step.",
        "batch_code": batch_code,
        "batch_status": "uploaded",
        "organization_name": organization_name,
        "location_name": location_name,
        "location_code": clean_location_code,
        "uploaded_by": uploaded_by,
        "report_period_start": report_period_start.isoformat(),
        "report_period_end": report_period_end.isoformat(),
        "files_uploaded": len(uploaded_file_results),
        "uploaded_files": uploaded_file_results,
        "batch_record": batch_record,
        "next_step": "Connect file parsing, scoring, dashboard refresh, and report generation.",
    }
