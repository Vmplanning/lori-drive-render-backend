import os
import re
import uuid
import csv
import io
from datetime import date, datetime
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
def parse_int(value: Any) -> Optional[int]:
    """Safely convert CSV values into integers."""
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).strip()))
    except Exception:
        return None


def parse_float(value: Any) -> Optional[float]:
    """Safely convert CSV values into numbers."""
    if value is None or value == "":
        return None
    try:
        cleaned = str(value).strip().replace("%", "")
        number = float(cleaned)
        return number
    except Exception:
        return None


def normalize_on_time_rate(value: Any) -> Optional[float]:
    """Normalize on-time rate values into decimal format when possible."""
    number = parse_float(value)
    if number is None:
        return None
    if number > 1 and number <= 100:
        return round(number / 100, 4)
    return number


def calculate_uploaded_driver_risk(
    overall_score: Optional[float],
    missed_deliveries: Optional[int],
    customer_complaints: Optional[int],
) -> str:
    """Assign a basic risk level from uploaded driver performance data."""
    score = overall_score if overall_score is not None else 75
    missed = missed_deliveries or 0
    complaints = customer_complaints or 0

    if score < 65 or missed >= 5 or complaints >= 2:
        return "Corrective Action"
    if score < 80 or missed >= 3 or complaints >= 1:
        return "Watch List"
    if score < 90:
        return "Solid Performer"
    return "Elite Performer"


def build_uploaded_driver_action(risk_level: str) -> str:
    """Create a leadership-ready recommended action."""
    if risk_level == "Corrective Action":
        return "Prioritize supervisor review, coaching documentation, and follow-up before additional route escalation."
    if risk_level == "Watch List":
        return "Schedule coaching conversation and monitor next reporting cycle for safety, route, or service improvement."
    if risk_level == "Solid Performer":
        return "Maintain standard performance monitoring and consider targeted recognition if trend remains positive."
    return "Recognize as a strong performer and consider for peer mentoring, route leadership, or positive reinforcement."


async def supabase_select(table_name: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Select rows from Supabase through the REST API."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=500, detail="Supabase environment variables are not configured.")

    url = f"{SUPABASE_URL}/rest/v1/{table_name}"

    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(url, headers=headers, params=params)

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail={
                "message": "Supabase select failed.",
                "table": table_name,
                "supabase_status": response.status_code,
                "supabase_response": response.text,
            },
        )

    return response.json()


async def supabase_delete_by_batch(table_name: str, batch_code: str) -> None:
    """Delete existing parsed records for a batch before re-parsing."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=500, detail="Supabase environment variables are not configured.")

    url = f"{SUPABASE_URL}/rest/v1/{table_name}"

    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.delete(
            url,
            headers=headers,
            params={"batch_code": f"eq.{batch_code}"},
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail={
                "message": "Supabase delete failed.",
                "table": table_name,
                "supabase_status": response.status_code,
                "supabase_response": response.text,
            },
        )


async def supabase_update_by_batch(
    table_name: str,
    batch_code: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Update a Supabase row by batch code."""
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
        response = await client.patch(
            url,
            headers=headers,
            params={"batch_code": f"eq.{batch_code}"},
            json=payload,
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail={
                "message": "Supabase update failed.",
                "table": table_name,
                "supabase_status": response.status_code,
                "supabase_response": response.text,
            },
        )

    rows = response.json()
    return rows[0] if rows else {}


async def download_from_supabase_storage(bucket_name: str, storage_path: str) -> bytes:
    """Download an uploaded file from Supabase Storage."""
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise HTTPException(status_code=500, detail="Supabase environment variables are not configured.")

    url = f"{SUPABASE_URL}/storage/v1/object/{bucket_name}/{storage_path}"

    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.get(url, headers=headers)

    if response.status_code >= 400:
        raise HTTPException(
            status_code=response.status_code,
            detail={
                "message": "Supabase storage download failed.",
                "bucket": bucket_name,
                "path": storage_path,
                "supabase_status": response.status_code,
                "supabase_response": response.text,
            },
        )

    return response.content


def parse_driver_performance_csv(
    file_bytes: bytes,
    batch_code: str,
    source_file_name: str,
) -> List[Dict[str, Any]]:
    """Parse the uploaded Driver Performance CSV into normalized driver records."""
    text = file_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    parsed_rows: List[Dict[str, Any]] = []

    for row in reader:
        employee_id = (row.get("employee_id") or "").strip()
        driver_name = (row.get("driver_name") or "").strip()
        supervisor_name = (row.get("supervisor_name") or "").strip()
        route_id = (row.get("route_id") or "").strip()
        delivery_station = (row.get("delivery_station") or "").strip()

        tenure_months = parse_int(row.get("tenure_months"))
        routes_completed = parse_int(row.get("routes_completed"))
        on_time_rate = normalize_on_time_rate(row.get("on_time_rate"))
        missed_deliveries = parse_int(row.get("missed_deliveries"))
        customer_complaints = parse_int(row.get("customer_complaints"))
        overall_score = parse_float(row.get("overall_score"))

        risk_level = calculate_uploaded_driver_risk(
            overall_score=overall_score,
            missed_deliveries=missed_deliveries,
            customer_complaints=customer_complaints,
        )

        parsed_rows.append(
            {
                "batch_code": batch_code,
                "employee_id": employee_id,
                "driver_name": driver_name,
                "supervisor_name": supervisor_name,
                "route_id": route_id,
                "delivery_station": delivery_station,
                "tenure_months": tenure_months,
                "routes_completed": routes_completed,
                "on_time_rate": on_time_rate,
                "missed_deliveries": missed_deliveries,
                "customer_complaints": customer_complaints,
                "overall_score": overall_score,
                "safety_score": None,
                "route_score": None,
                "payroll_score": None,
                "training_score": None,
                "calculated_risk_level": risk_level,
                "recommended_action": build_uploaded_driver_action(risk_level),
                "source_file_name": source_file_name,
            }
        )

    return parsed_rows


@app.post("/parse-driver-performance")
async def parse_driver_performance(
    batch_code: str = Query(...),
    api_key: str = Query(...),
):
    """
    Parses the uploaded Driver Performance CSV for a batch,
    stores driver records in Supabase,
    and updates the batch upload record.
    """
    require_lori_key(api_key)

    file_rows = await supabase_select(
        "lori_uploaded_files",
        {
            "select": "*",
            "batch_code": f"eq.{batch_code}",
            "file_type": "eq.Driver Performance File",
            "order": "uploaded_at.desc",
            "limit": "1",
        },
    )

    if not file_rows:
        raise HTTPException(
            status_code=404,
            detail=f"No Driver Performance File found for batch {batch_code}.",
        )

    file_record = file_rows[0]
    bucket_name = file_record.get("storage_bucket") or "lori-batch-uploads"
    storage_path = file_record.get("storage_path")
    source_file_name = file_record.get("original_file_name") or "driver_performance.csv"

    if not storage_path:
        raise HTTPException(status_code=500, detail="Uploaded file record is missing storage_path.")

    file_bytes = await download_from_supabase_storage(bucket_name, storage_path)

    parsed_rows = parse_driver_performance_csv(
        file_bytes=file_bytes,
        batch_code=batch_code,
        source_file_name=source_file_name,
    )

    await supabase_delete_by_batch("lori_uploaded_driver_scores", batch_code)

    inserted_count = 0
    risk_summary: Dict[str, int] = {}

    for parsed_row in parsed_rows:
        await supabase_insert("lori_uploaded_driver_scores", parsed_row)
        inserted_count += 1
        risk = parsed_row.get("calculated_risk_level") or "Unclassified"
        risk_summary[risk] = risk_summary.get(risk, 0) + 1

    updated_batch = await supabase_update_by_batch(
        "lori_batch_uploads",
        batch_code,
        {
            "batch_status": "parsed",
            "total_drivers_found": inserted_count,
            "notes": f"Driver Performance File parsed successfully. {inserted_count} driver records inserted.",
        },
    )

    return {
        "status": "success",
        "message": "Driver Performance File parsed successfully.",
        "batch_code": batch_code,
        "source_file_name": source_file_name,
        "drivers_parsed": inserted_count,
        "risk_summary": risk_summary,
        "batch_status": "parsed",
        "updated_batch": updated_batch,
        "next_step": "Connect parsed driver records to dashboard, reports, and LORI assistant workflows.",
    }
def uploaded_risk_summary_from_rows(drivers: List[Dict[str, Any]]) -> Dict[str, int]:
    """Summarize parsed uploaded driver rows by calculated risk level."""
    summary = {
        "Corrective Action": 0,
        "Watch List": 0,
        "Solid Performer": 0,
        "Elite Performer": 0,
    }

    for driver in drivers:
        risk = driver.get("calculated_risk_level") or "Unclassified"
        summary[risk] = summary.get(risk, 0) + 1

    return summary


def driver_score_for_sort(driver: Dict[str, Any]) -> float:
    """Return a usable score for sorting uploaded drivers."""
    score = parse_float(driver.get("overall_score"))
    return score if score is not None else 0.0


async def get_uploaded_batch_or_latest(batch_code: Optional[str]) -> Dict[str, Any]:
    """Get a requested uploaded batch or the latest uploaded batch."""
    if batch_code:
        rows = await supabase_select(
            "lori_batch_uploads",
            {
                "select": "*",
                "batch_code": f"eq.{batch_code}",
                "limit": "1",
            },
        )
    else:
        rows = await supabase_select(
            "lori_batch_uploads",
            {
                "select": "*",
                "order": "created_at.desc",
                "limit": "1",
            },
        )

    if not rows:
        raise HTTPException(status_code=404, detail="No uploaded batch found.")

    return rows[0]


async def get_uploaded_driver_rows(batch_code: str) -> List[Dict[str, Any]]:
    """Get parsed uploaded driver score rows for a batch."""
    return await supabase_select(
        "lori_uploaded_driver_scores",
        {
            "select": "*",
            "batch_code": f"eq.{batch_code}",
            "order": "overall_score.desc",
        },
    )


@app.get("/uploaded-batch-summary")
async def uploaded_batch_summary(
    api_key: str = Query(...),
    batch_code: Optional[str] = Query(None),
):
    """
    Summary for the latest or requested uploaded/parsed batch.
    Used by the Lovable dashboard.
    """
    require_lori_key(api_key)

    batch = await get_uploaded_batch_or_latest(batch_code)
    resolved_batch_code = batch["batch_code"]

    drivers = await get_uploaded_driver_rows(resolved_batch_code)
    risk_summary = uploaded_risk_summary_from_rows(drivers)

    response_text = (
        f"Uploaded batch {resolved_batch_code} is {batch.get('batch_status')}. "
        f"I found {len(drivers)} parsed driver records. "
        f"Risk summary: {risk_summary.get('Corrective Action', 0)} driver requires corrective action, "
        f"{risk_summary.get('Watch List', 0)} drivers are on the watch list, "
        f"{risk_summary.get('Solid Performer', 0)} are solid performers, and "
        f"{risk_summary.get('Elite Performer', 0)} are elite performers."
    )

    return {
        "status": "success",
        "batch_code": resolved_batch_code,
        "batch_status": batch.get("batch_status"),
        "organization_name": batch.get("organization_name"),
        "location_name": batch.get("location_name"),
        "location_code": batch.get("location_code"),
        "uploaded_by": batch.get("uploaded_by"),
        "report_period_start": batch.get("report_period_start"),
        "report_period_end": batch.get("report_period_end"),
        "total_files": batch.get("total_files"),
        "total_drivers_found": len(drivers),
        "risk_summary": risk_summary,
        "response_text": response_text,
        "next_step": "Use this uploaded batch summary to power the leadership dashboard and report cards.",
    }


@app.get("/uploaded-risk-summary")
async def uploaded_risk_summary(
    api_key: str = Query(...),
    batch_code: Optional[str] = Query(None),
):
    """
    Risk summary from parsed uploaded driver records.
    """
    require_lori_key(api_key)

    batch = await get_uploaded_batch_or_latest(batch_code)
    resolved_batch_code = batch["batch_code"]
    drivers = await get_uploaded_driver_rows(resolved_batch_code)

    summary = uploaded_risk_summary_from_rows(drivers)

    return [
        {"risk_level": "Corrective Action", "driver_count": summary.get("Corrective Action", 0)},
        {"risk_level": "Watch List", "driver_count": summary.get("Watch List", 0)},
        {"risk_level": "Solid Performer", "driver_count": summary.get("Solid Performer", 0)},
        {"risk_level": "Elite Performer", "driver_count": summary.get("Elite Performer", 0)},
    ]


@app.get("/uploaded-worst-drivers")
async def uploaded_worst_drivers(
    api_key: str = Query(...),
    batch_code: Optional[str] = Query(None),
    limit: int = Query(3, ge=1, le=25),
):
    """
    Highest-risk drivers from parsed uploaded batch data.
    """
    require_lori_key(api_key)

    batch = await get_uploaded_batch_or_latest(batch_code)
    resolved_batch_code = batch["batch_code"]
    drivers = await get_uploaded_driver_rows(resolved_batch_code)

    risk_order = {
        "Corrective Action": 1,
        "Watch List": 2,
        "Solid Performer": 3,
        "Elite Performer": 4,
    }

    sorted_drivers = sorted(
        drivers,
        key=lambda d: (
            risk_order.get(d.get("calculated_risk_level") or "", 99),
            driver_score_for_sort(d),
        ),
    )

    results = []

    for driver in sorted_drivers[:limit]:
        results.append(
            {
                "employee_id": driver.get("employee_id"),
                "driver_name": driver.get("driver_name"),
                "supervisor_name": driver.get("supervisor_name"),
                "route_id": driver.get("route_id"),
                "risk_level": driver.get("calculated_risk_level"),
                "overall_score": driver.get("overall_score"),
                "missed_deliveries": driver.get("missed_deliveries"),
                "customer_complaints": driver.get("customer_complaints"),
                "recommended_action": driver.get("recommended_action"),
                "batch_code": resolved_batch_code,
            }
        )

    return results


@app.get("/uploaded-best-drivers")
async def uploaded_best_drivers(
    api_key: str = Query(...),
    batch_code: Optional[str] = Query(None),
    limit: int = Query(3, ge=1, le=25),
):
    """
    Best drivers from parsed uploaded batch data.
    """
    require_lori_key(api_key)

    batch = await get_uploaded_batch_or_latest(batch_code)
    resolved_batch_code = batch["batch_code"]
    drivers = await get_uploaded_driver_rows(resolved_batch_code)

    sorted_drivers = sorted(
        drivers,
        key=lambda d: driver_score_for_sort(d),
        reverse=True,
    )

    results = []

    for driver in sorted_drivers[:limit]:
        results.append(
            {
                "employee_id": driver.get("employee_id"),
                "driver_name": driver.get("driver_name"),
                "supervisor_name": driver.get("supervisor_name"),
                "route_id": driver.get("route_id"),
                "risk_level": driver.get("calculated_risk_level"),
                "overall_score": driver.get("overall_score"),
                "on_time_rate": driver.get("on_time_rate"),
                "routes_completed": driver.get("routes_completed"),
                "recommended_action": driver.get("recommended_action"),
                "batch_code": resolved_batch_code,
            }
        )

    return results


@app.get("/uploaded-driver-360")
async def uploaded_driver_360(
    api_key: str = Query(...),
    batch_code: Optional[str] = Query(None),
    employee_id: Optional[str] = Query(None),
    driver_name: Optional[str] = Query(None),
):
    """
    Driver 360 profile from parsed uploaded batch data.
    """
    require_lori_key(api_key)

    batch = await get_uploaded_batch_or_latest(batch_code)
    resolved_batch_code = batch["batch_code"]

    params = {
        "select": "*",
        "batch_code": f"eq.{resolved_batch_code}",
        "limit": "1",
    }

    if employee_id:
        params["employee_id"] = f"eq.{employee_id}"
    elif driver_name:
        params["driver_name"] = f"ilike.*{driver_name}*"
    else:
        params["order"] = "overall_score.asc"

    rows = await supabase_select("lori_uploaded_driver_scores", params)

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="No uploaded driver profile found for the provided search.",
        )

    driver = rows[0]

    return {
        "batch_code": resolved_batch_code,
        "employee_id": driver.get("employee_id"),
        "driver_name": driver.get("driver_name"),
        "supervisor_name": driver.get("supervisor_name"),
        "route_id": driver.get("route_id"),
        "delivery_station": driver.get("delivery_station"),
        "tenure_months": driver.get("tenure_months"),
        "routes_completed": driver.get("routes_completed"),
        "on_time_rate": driver.get("on_time_rate"),
        "missed_deliveries": driver.get("missed_deliveries"),
        "customer_complaints": driver.get("customer_complaints"),
        "overall_score": driver.get("overall_score"),
        "safety_score": driver.get("safety_score"),
        "route_score": driver.get("route_score"),
        "payroll_score": driver.get("payroll_score"),
        "training_score": driver.get("training_score"),
        "risk_level": driver.get("calculated_risk_level"),
        "recommended_action": driver.get("recommended_action"),
        "source_file_name": driver.get("source_file_name"),
    }
MONTH_NAMES = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}


def parse_date_safe(value: Any) -> Optional[date]:
    """Safely parse a date returned from Supabase."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def format_birthday(month: Any, day: Any) -> str:
    """Format birthday month/day without storing a full birthdate."""
    try:
        month_int = int(month)
        day_int = int(day)
        month_name = MONTH_NAMES.get(month_int, f"Month {month_int}")
        return f"{month_name} {day_int}"
    except Exception:
        return "Not available"


async def find_driver_master_record(
    employee_id: Optional[str] = None,
    driver_name: Optional[str] = None,
    question: Optional[str] = None,
) -> Dict[str, Any]:
    """Find a driver by employee ID, driver name, or name mentioned inside a question."""
    if employee_id:
        rows = await supabase_select(
            "lori_driver_master",
            {
                "select": "*",
                "employee_id": f"eq.{employee_id}",
                "limit": "1",
            },
        )
        if rows:
            return rows[0]

    if driver_name:
        rows = await supabase_select(
            "lori_driver_master",
            {
                "select": "*",
                "driver_name": f"ilike.*{driver_name}*",
                "limit": "1",
            },
        )
        if rows:
            return rows[0]

    if question:
        all_drivers = await supabase_select(
            "lori_driver_master",
            {
                "select": "*",
                "order": "driver_name.asc",
            },
        )

        question_lower = question.lower()

        for driver in all_drivers:
            name = (driver.get("driver_name") or "").lower()
            preferred = (driver.get("preferred_name") or "").lower()
            emp_id = (driver.get("employee_id") or "").lower()

            if emp_id and emp_id in question_lower:
                return driver

            if name and name in question_lower:
                return driver

            if preferred and preferred in question_lower:
                return driver

    raise HTTPException(
        status_code=404,
        detail="No matching driver was found. Try using the driver name or employee ID.",
    )


async def get_driver_intelligence_payload(
    employee_id: Optional[str] = None,
    driver_name: Optional[str] = None,
    question: Optional[str] = None,
) -> Dict[str, Any]:
    """Collect the full driver intelligence profile from all driver tables."""
    master = await find_driver_master_record(
        employee_id=employee_id,
        driver_name=driver_name,
        question=question,
    )

    resolved_employee_id = master["employee_id"]

    credentials = await supabase_select(
        "lori_driver_credentials",
        {
            "select": "*",
            "employee_id": f"eq.{resolved_employee_id}",
            "order": "expiration_date.asc",
        },
    )

    counseling = await supabase_select(
        "lori_driver_counseling",
        {
            "select": "*",
            "employee_id": f"eq.{resolved_employee_id}",
            "order": "counseling_date.desc",
        },
    )

    routes = await supabase_select(
        "lori_driver_routes",
        {
            "select": "*",
            "employee_id": f"eq.{resolved_employee_id}",
            "order": "route_date.desc",
            "limit": "10",
        },
    )

    metrics = await supabase_select(
        "lori_driver_metrics",
        {
            "select": "*",
            "employee_id": f"eq.{resolved_employee_id}",
            "order": "metric_period_end.desc",
            "limit": "5",
        },
    )

    safety_events = await supabase_select(
        "lori_driver_safety_events",
        {
            "select": "*",
            "employee_id": f"eq.{resolved_employee_id}",
            "order": "event_date.desc",
            "limit": "10",
        },
    )

    notes = await supabase_select(
        "lori_driver_notes",
        {
            "select": "*",
            "employee_id": f"eq.{resolved_employee_id}",
            "order": "note_date.desc",
            "limit": "10",
        },
    )

    alerts = await supabase_select(
        "lori_driver_alerts",
        {
            "select": "*",
            "employee_id": f"eq.{resolved_employee_id}",
            "order": "due_date.asc",
        },
    )

    timeline = await supabase_select(
        "lori_driver_timeline",
        {
            "select": "*",
            "employee_id": f"eq.{resolved_employee_id}",
            "order": "event_date.desc",
            "limit": "15",
        },
    )

    answer_text = build_driver_intelligence_answer(
        master=master,
        credentials=credentials,
        counseling=counseling,
        routes=routes,
        metrics=metrics,
        safety_events=safety_events,
        notes=notes,
        alerts=alerts,
        timeline=timeline,
        question=question,
    )

    return {
        "status": "success",
        "driver": master,
        "credentials": credentials,
        "counseling": counseling,
        "routes": routes,
        "metrics": metrics,
        "safety_events": safety_events,
        "notes": notes,
        "alerts": alerts,
        "timeline": timeline,
        "answer_text": answer_text,
    }


def build_driver_intelligence_answer(
    master: Dict[str, Any],
    credentials: List[Dict[str, Any]],
    counseling: List[Dict[str, Any]],
    routes: List[Dict[str, Any]],
    metrics: List[Dict[str, Any]],
    safety_events: List[Dict[str, Any]],
    notes: List[Dict[str, Any]],
    alerts: List[Dict[str, Any]],
    timeline: List[Dict[str, Any]],
    question: Optional[str] = None,
) -> str:
    """Create a leadership-ready answer from the driver intelligence profile."""
    q = (question or "").lower()
    driver_name = master.get("driver_name") or "this driver"
    employee_id = master.get("employee_id") or "Unknown"
    supervisor = master.get("supervisor_name") or "Not listed"
    location = master.get("location_name") or "Not listed"
    primary_route = master.get("primary_route_id") or "Not listed"
    birthday = format_birthday(master.get("birthday_month"), master.get("birthday_day"))

    latest_metric = metrics[0] if metrics else {}
    latest_route = routes[0] if routes else {}
    open_alerts = [a for a in alerts if (a.get("status") or "").lower() == "open"]
    critical_alerts = [
        a for a in open_alerts
        if (a.get("alert_level") or "").lower() in ["critical", "high"]
    ]
    open_counseling = [
        c for c in counseling
        if (c.get("status") or "").lower() == "open"
    ]

    if "dot" in q or "credential" in q or "expire" in q or "expiration" in q:
        if not credentials:
            return f"I do not see credential records for {driver_name}."

        lines = [
            f"Credential Readout for {driver_name}",
            f"Employee ID: {employee_id}",
            f"Supervisor: {supervisor}",
            "",
        ]

        for credential in credentials:
            lines.append(
                f"{credential.get('credential_type')}: {credential.get('credential_status')} — "
                f"expires {credential.get('expiration_date')} "
                f"({credential.get('days_until_expiration')} days until expiration). "
                f"Alert Level: {credential.get('alert_level')}. "
                f"Notes: {credential.get('notes')}"
            )

        return "\n".join(lines)

    if "birthday" in q:
        return (
            f"{driver_name}'s birthday is listed as {birthday}. "
            f"For privacy, LORI stores month and day only in this demo, not a full birthdate."
        )

    if "counsel" in q or "coaching" in q or "follow" in q:
        if not counseling:
            return f"I do not see counseling or coaching records for {driver_name}."

        lines = [
            f"Counseling and Coaching History for {driver_name}",
            f"Supervisor: {supervisor}",
            "",
        ]

        for item in counseling[:5]:
            lines.append(
                f"{item.get('counseling_date')}: {item.get('counseling_type')} — "
                f"{item.get('counseling_reason')}. Outcome: {item.get('outcome')}. "
                f"Follow-up: {item.get('follow_up_date')}. Status: {item.get('status')}. "
                f"Priority: {item.get('priority')}."
            )

        return "\n".join(lines)

    if "route" in q:
        if not routes:
            return f"I do not see route records for {driver_name}."

        return (
            f"Route Readout for {driver_name}\n"
            f"Primary Route: {primary_route}\n"
            f"Latest Route: {latest_route.get('route_id')} — {latest_route.get('route_name')}\n"
            f"Planned Stops: {latest_route.get('planned_stops')}\n"
            f"Completed Stops: {latest_route.get('completed_stops')}\n"
            f"Missed Stops: {latest_route.get('missed_stops')}\n"
            f"On-Time Rate: {latest_route.get('on_time_rate')}\n"
            f"Route Score: {latest_route.get('route_score')}\n"
            f"Route Risk Flag: {latest_route.get('route_risk_flag')}\n"
            f"Notes: {latest_route.get('notes')}"
        )

    if "safety" in q or "event" in q:
        if not safety_events:
            return f"I do not see safety events for {driver_name}."

        lines = [
            f"Safety Event Readout for {driver_name}",
            "",
        ]

        for event in safety_events[:5]:
            lines.append(
                f"{event.get('event_date')}: {event.get('event_type')} "
                f"({event.get('severity')}) on {event.get('route_id')}. "
                f"{event.get('description')} Corrective action required: "
                f"{event.get('corrective_action_required')}."
            )

        return "\n".join(lines)

    if "alert" in q or "risk" in q or "everything" in q or "profile" in q or not question:
        lines = [
            f"Driver Intelligence Profile: {driver_name}",
            f"Employee ID: {employee_id}",
            f"Supervisor: {supervisor}",
            f"Location: {location}",
            f"Primary Route: {primary_route}",
            f"Birthday: {birthday}",
            "",
            "Performance Snapshot:",
            f"Overall Score: {latest_metric.get('overall_score', 'Not available')}",
            f"Risk Level: {latest_metric.get('risk_level', 'Not available')}",
            f"Trend Direction: {latest_metric.get('trend_direction', 'Not available')}",
            f"Recommended Action: {latest_metric.get('recommended_action', 'Not available')}",
            "",
            "Open Alerts:",
        ]

        if open_alerts:
            for alert in open_alerts[:5]:
                lines.append(
                    f"- {alert.get('alert_level')}: {alert.get('alert_title')} — "
                    f"{alert.get('alert_detail')} Due: {alert.get('due_date')}. "
                    f"Recommended Action: {alert.get('recommended_action')}"
                )
        else:
            lines.append("- No open alerts found.")

        lines.append("")
        lines.append("Counseling / Coaching:")

        if open_counseling:
            for item in open_counseling[:3]:
                lines.append(
                    f"- {item.get('counseling_date')}: {item.get('counseling_type')} — "
                    f"{item.get('counseling_reason')}. Follow-up: {item.get('follow_up_date')}. "
                    f"Status: {item.get('status')}."
                )
        else:
            lines.append("- No open counseling follow-ups found.")

        lines.append("")
        lines.append("Leadership Readout:")

        if critical_alerts:
            lines.append(
                f"{driver_name} has critical or high-priority items that require leadership review "
                f"before continued escalation."
            )
        else:
            lines.append(
                f"{driver_name} does not currently show critical open alerts in the demo intelligence layer."
            )

        return "\n".join(lines)

    return (
        f"I found {driver_name}. Employee ID: {employee_id}. Supervisor: {supervisor}. "
        f"Latest risk level: {latest_metric.get('risk_level', 'Not available')}. "
        f"Ask about DOT expiration, counseling, routes, safety events, birthday, alerts, or full profile."
    )


@app.get("/driver-search")
async def driver_search(
    api_key: str = Query(...),
    query: Optional[str] = Query(None),
):
    """
    Search driver master records by name or employee ID.
    """
    require_lori_key(api_key)

    if query:
        all_drivers = await supabase_select(
            "lori_driver_master",
            {
                "select": "*",
                "order": "driver_name.asc",
            },
        )

        q = query.lower()
        matches = [
            driver for driver in all_drivers
            if q in (driver.get("driver_name") or "").lower()
            or q in (driver.get("preferred_name") or "").lower()
            or q in (driver.get("employee_id") or "").lower()
        ]

        return matches[:10]

    return await supabase_select(
        "lori_driver_master",
        {
            "select": "*",
            "order": "driver_name.asc",
            "limit": "25",
        },
    )


@app.get("/driver-intelligence")
async def driver_intelligence(
    api_key: str = Query(...),
    employee_id: Optional[str] = Query(None),
    driver_name: Optional[str] = Query(None),
    question: Optional[str] = Query(None),
):
    """
    Main driver intelligence endpoint for Voiceflow.
    Answers deeper questions about a driver using all driver intelligence tables.
    """
    require_lori_key(api_key)

    return await get_driver_intelligence_payload(
        employee_id=employee_id,
        driver_name=driver_name,
        question=question,
    )


@app.get("/driver-compliance-watch")
async def driver_compliance_watch(
    api_key: str = Query(...),
    days: int = Query(30, ge=0, le=365),
):
    """
    Show drivers with expired or upcoming credentials.
    """
    require_lori_key(api_key)

    credentials = await supabase_select(
        "lori_driver_credentials",
        {
            "select": "*",
            "order": "days_until_expiration.asc",
        },
    )

    results = []

    for credential in credentials:
        days_until = credential.get("days_until_expiration")
        status = (credential.get("credential_status") or "").lower()

        include = False

        if days_until is not None:
            try:
                include = int(days_until) <= days
            except Exception:
                include = False

        if status in ["expired", "overdue"]:
            include = True

        if include:
            results.append(credential)

    return {
        "status": "success",
        "watch_window_days": days,
        "drivers_found": len(results),
        "credentials": results,
        "answer_text": f"I found {len(results)} credential records that are expired, overdue, or due within {days} days.",
    }


@app.get("/driver-counseling-due")
async def driver_counseling_due(
    api_key: str = Query(...),
    days: int = Query(30, ge=0, le=365),
):
    """
    Show open counseling follow-ups due within a date window.
    """
    require_lori_key(api_key)

    counseling_rows = await supabase_select(
        "lori_driver_counseling",
        {
            "select": "*",
            "order": "follow_up_date.asc",
        },
    )

    today = date.today()
    results = []

    for row in counseling_rows:
        if (row.get("status") or "").lower() != "open":
            continue

        follow_up_date = parse_date_safe(row.get("follow_up_date"))

        if follow_up_date is None:
            continue

        days_until = (follow_up_date - today).days

        if days_until <= days:
            row["days_until_follow_up"] = days_until
            results.append(row)

    return {
        "status": "success",
        "watch_window_days": days,
        "drivers_found": len(results),
        "counseling_follow_ups": results,
        "answer_text": f"I found {len(results)} open counseling follow-ups due within {days} days.",
    }


@app.get("/driver-birthday-watch")
async def driver_birthday_watch(
    api_key: str = Query(...),
    month: Optional[int] = Query(None, ge=1, le=12),
):
    """
    Show driver birthdays by month. Stores only month/day for privacy.
    """
    require_lori_key(api_key)

    selected_month = month or date.today().month

    drivers = await supabase_select(
        "lori_driver_master",
        {
            "select": "*",
            "birthday_month": f"eq.{selected_month}",
            "order": "birthday_day.asc",
        },
    )

    results = []

    for driver in drivers:
        results.append(
            {
                "employee_id": driver.get("employee_id"),
                "driver_name": driver.get("driver_name"),
                "preferred_name": driver.get("preferred_name"),
                "supervisor_name": driver.get("supervisor_name"),
                "location_name": driver.get("location_name"),
                "birthday": format_birthday(driver.get("birthday_month"), driver.get("birthday_day")),
                "privacy_note": "Only birthday month and day are stored in this demo.",
            }
        )

    return {
        "status": "success",
        "month": selected_month,
        "month_name": MONTH_NAMES.get(selected_month, str(selected_month)),
        "drivers_found": len(results),
        "birthdays": results,
        "answer_text": f"I found {len(results)} driver birthdays in {MONTH_NAMES.get(selected_month, str(selected_month))}.",
    }
# ============================================================
# LORI DRIVE — NEW DRIVER INTAKE ENDPOINT
# Saves a manually entered driver into Supabase.
# Demonstration Data Only — Not Company Proprietary Data
# ============================================================

class NewDriverIntakeRequest(BaseModel):
    employee_id: str
    full_name: str
    preferred_name: Optional[str] = None
    driver_role: Optional[str] = None
    employment_status: Optional[str] = None
    hire_date: Optional[str] = None

    supervisor_name: Optional[str] = None
    location: Optional[str] = None
    location_code: Optional[str] = None
    primary_route_id: Optional[str] = None
    station_operation: Optional[str] = None

    phone_last4: Optional[str] = None
    email: Optional[str] = None

    birthday_month: Optional[str] = None
    birthday_day: Optional[str] = None

    dot_medical_card_expiration: Optional[str] = None
    cdl_license_status: Optional[str] = None
    license_class: Optional[str] = None
    defensive_driving_status: Optional[str] = None
    training_status: Optional[str] = None

    driver_qualification_file_status: Optional[str] = None
    onboarding_checklist_status: Optional[str] = None
    background_screening_status: Optional[str] = None
    initial_safety_orientation_status: Optional[str] = None

    manager_notes: Optional[str] = None
    compliance_notes: Optional[str] = None
    supervisor_notes: Optional[str] = None


def lori_supabase_headers():
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }


async def lori_supabase_insert(table_name: str, payload: dict):
    url = f"{SUPABASE_URL}/rest/v1/{table_name}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            headers=lori_supabase_headers(),
            json=payload
        )

    if response.status_code not in [200, 201]:
        raise HTTPException(
            status_code=500,
            detail={
                "message": f"Supabase insert failed for {table_name}",
                "status_code": response.status_code,
                "response": response.text
            }
        )

    try:
        return response.json()
    except Exception:
        return {"raw_response": response.text}


async def lori_supabase_upsert_driver_master(payload: dict):
    url = f"{SUPABASE_URL}/rest/v1/lori_driver_master?on_conflict=employee_id"

    headers = lori_supabase_headers()
    headers["Prefer"] = "resolution=merge-duplicates,return=representation"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            url,
            headers=headers,
            json=payload
        )

    if response.status_code not in [200, 201]:
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Supabase upsert failed for lori_driver_master",
                "status_code": response.status_code,
                "response": response.text
            }
        )

    try:
        return response.json()
    except Exception:
        return {"raw_response": response.text}

def lori_normalize_birthday_month(value):
    if value is None:
        return None

    text = str(value).strip()

    if text == "":
        return None

    month_lookup = {
        "1": 1, "01": 1, "jan": 1, "january": 1,
        "2": 2, "02": 2, "feb": 2, "february": 2,
        "3": 3, "03": 3, "mar": 3, "march": 3,
        "4": 4, "04": 4, "apr": 4, "april": 4,
        "5": 5, "05": 5, "may": 5,
        "6": 6, "06": 6, "jun": 6, "june": 6,
        "7": 7, "07": 7, "jul": 7, "july": 7,
        "8": 8, "08": 8, "aug": 8, "august": 8,
        "9": 9, "09": 9, "sep": 9, "sept": 9, "september": 9,
        "10": 10, "oct": 10, "october": 10,
        "11": 11, "nov": 11, "november": 11,
        "12": 12, "dec": 12, "december": 12
    }

    return month_lookup.get(text.lower())


def lori_normalize_birthday_day(value):
    if value is None:
        return None

    text = str(value).strip()

    if text == "":
        return None

    try:
        day = int(text)
        if day < 1 or day > 31:
            return None
        return day
    except Exception:
        return None
@app.post("/new-driver")
async def create_new_driver(
    driver: NewDriverIntakeRequest,
    api_key: str = Query(None)
):
    if api_key != LORI_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")

    now_value = datetime.utcnow().isoformat()

    employee_id = driver.employee_id.strip()
    full_name = driver.full_name.strip()

    if not employee_id:
        raise HTTPException(status_code=400, detail="Employee ID is required.")

    if not full_name:
        raise HTTPException(status_code=400, detail="Driver full name is required.")
    birthday_month_value = lori_normalize_birthday_month(driver.birthday_month)
    birthday_day_value = lori_normalize_birthday_day(driver.birthday_day)
    master_payload = {
        "employee_id": employee_id,
        "driver_name": full_name,
        "preferred_name": driver.preferred_name,
        "driver_role": driver.driver_role,
        "employment_status": driver.employment_status or "Active",
        "hire_date": driver.hire_date,
        "supervisor_name": driver.supervisor_name,
        "location": driver.location,
        "location_code": driver.location_code,
        "primary_route_id": driver.primary_route_id,
        "station_operation": driver.station_operation,
        "phone_last4": driver.phone_last4,
        "email": driver.email,
                "birthday_month": birthday_month_value,
        "birthday_day": birthday_day_value,
        "record_source": "Manual New Driver Intake",
        "created_at": now_value,
        "updated_at": now_value
    }

    master_payload = {k: v for k, v in master_payload.items() if v is not None}

    saved_master = await lori_supabase_upsert_driver_master(master_payload)

    credential_records_created = []

    if driver.dot_medical_card_expiration:
        dot_payload = {
            "employee_id": employee_id,
            "credential_type": "DOT Medical Card",
            "credential_status": "Active",
            "expiration_date": driver.dot_medical_card_expiration,
            "notes": "Created through LORI New Driver Intake.",
            "created_at": now_value,
            "updated_at": now_value
        }
        credential_records_created.append(
            await lori_supabase_insert("lori_driver_credentials", dot_payload)
        )

    if driver.cdl_license_status or driver.license_class:
        license_payload = {
            "employee_id": employee_id,
            "credential_type": "CDL / License",
            "credential_status": driver.cdl_license_status or "Needs Review",
            "license_class": driver.license_class,
            "notes": "Created through LORI New Driver Intake.",
            "created_at": now_value,
            "updated_at": now_value
        }
        license_payload = {k: v for k, v in license_payload.items() if v is not None}
        credential_records_created.append(
            await lori_supabase_insert("lori_driver_credentials", license_payload)
        )

    onboarding_notes = []

    if driver.driver_qualification_file_status:
        onboarding_notes.append(f"Driver Qualification File: {driver.driver_qualification_file_status}")

    if driver.onboarding_checklist_status:
        onboarding_notes.append(f"Onboarding Checklist: {driver.onboarding_checklist_status}")

    if driver.background_screening_status:
        onboarding_notes.append(f"Background / Screening: {driver.background_screening_status}")

    if driver.initial_safety_orientation_status:
        onboarding_notes.append(f"Initial Safety Orientation: {driver.initial_safety_orientation_status}")

    if driver.training_status:
        onboarding_notes.append(f"Training Status: {driver.training_status}")

    if driver.defensive_driving_status:
        onboarding_notes.append(f"Defensive Driving Certification: {driver.defensive_driving_status}")

    note_text_parts = []

    if onboarding_notes:
        note_text_parts.append("Compliance Setup:\n" + "\n".join(onboarding_notes))

    if driver.manager_notes:
        note_text_parts.append("Manager Notes:\n" + driver.manager_notes)

    if driver.compliance_notes:
        note_text_parts.append("Compliance Notes:\n" + driver.compliance_notes)

    if driver.supervisor_notes:
        note_text_parts.append("Supervisor Notes:\n" + driver.supervisor_notes)

    note_record_created = None

    if note_text_parts:
        note_payload = {
            "employee_id": employee_id,
            "note_type": "New Driver Intake",
            "note_text": "\n\n".join(note_text_parts),
            "created_by": "LORI New Driver Intake",
            "created_at": now_value,
            "updated_at": now_value
        }
        note_record_created = await lori_supabase_insert("lori_driver_notes", note_payload)

    timeline_payload = {
        "employee_id": employee_id,
        "event_type": "New Driver Created",
        "event_title": "New driver profile created",
        "event_summary": f"{full_name} was manually added to LORI and staged for compliance review.",
        "created_at": now_value
    }

    timeline_record_created = None

    try:
        timeline_record_created = await lori_supabase_insert("lori_driver_timeline", timeline_payload)
    except Exception:
        timeline_record_created = {
            "status": "timeline_not_created",
            "message": "Driver was saved, but the timeline record could not be created."
        }

    return {
        "status": "success",
        "message": "New driver profile created and staged for compliance review.",
        "employee_id": employee_id,
        "driver_name": full_name,
        "saved_master_record": saved_master,
        "credential_records_created": credential_records_created,
        "note_record_created": note_record_created,
        "timeline_record_created": timeline_record_created,
        "next_steps": [
            "Open Driver 360",
            "Review driver file readiness",
            "Add missing credentials",
            "Assign supervisor follow-up",
            "Confirm DOT/FMCSA-sensitive records against official company files"
        ]
    }
# ============================================================
# LORI DRIVE COMMAND CENTER
# Regulatory Intelligence Backend
# Adds live-ready regulatory alert scan endpoints
# ============================================================

import hashlib
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional

import httpx
from fastapi import Query, HTTPException


REGULATORY_KEYWORDS = [
    "fmcsa",
    "dot",
    "department of transportation",
    "transportation",
    "motor carrier",
    "commercial motor vehicle",
    "driver",
    "drivers",
    "cdl",
    "medical card",
    "hours of service",
    "drug",
    "alcohol",
    "safety",
    "inspection",
    "vehicle",
    "fleet",
    "compliance",
    "rule",
    "notice",
    "regulation",
    "enforcement",
    "crash",
    "carrier",
    "hazmat",
    "hazardous materials",
    "electronic logging",
    "eld",
]


def lori_regulatory_require_key(api_key: Optional[str]) -> None:
    if LORI_API_KEY and api_key != LORI_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


def lori_regulatory_supabase_headers(prefer: Optional[str] = None) -> Dict[str, str]:
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def lori_regulatory_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def lori_regulatory_clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def lori_regulatory_parse_date(value: Any) -> Optional[str]:
    if not value:
        return None

    text = str(value).strip()

    try:
        parsed = parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except Exception:
        pass

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def lori_regulatory_hash(*parts: Any) -> str:
    raw = "||".join([str(p or "") for p in parts])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def lori_regulatory_is_relevant(title: str, summary: str, source: Dict[str, Any]) -> bool:
    combined = f"{title} {summary} {source.get('source_name', '')} {source.get('category', '')}".lower()

    if source.get("source_type") in ["Federal", "State"] and source.get("agency"):
        agency = str(source.get("agency", "")).lower()
        if "transportation" in agency:
            return True
        if "motor carrier" in agency:
            return True

    return any(keyword in combined for keyword in REGULATORY_KEYWORDS)


async def lori_regulatory_supabase_get(query_path: str) -> Any:
    url = f"{SUPABASE_URL}/rest/v1/{query_path}"

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, headers=lori_regulatory_supabase_headers())

    if response.status_code >= 400:
        raise HTTPException(
            status_code=500,
            detail=f"Supabase GET failed: {response.text}",
        )

    return response.json()


async def lori_regulatory_supabase_post(table: str, payload: Dict[str, Any]) -> Any:
    url = f"{SUPABASE_URL}/rest/v1/{table}"

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            url,
            headers=lori_regulatory_supabase_headers("return=representation"),
            json=payload,
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=500,
            detail=f"Supabase POST failed: {response.text}",
        )

    return response.json()


async def lori_regulatory_supabase_patch(table: str, row_id: str, payload: Dict[str, Any]) -> Any:
    url = f"{SUPABASE_URL}/rest/v1/{table}?id=eq.{row_id}"

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.patch(
            url,
            headers=lori_regulatory_supabase_headers("return=representation"),
            json=payload,
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=500,
            detail=f"Supabase PATCH failed: {response.text}",
        )

    return response.json()


async def lori_regulatory_alert_exists(content_hash: str) -> bool:
    safe_hash = content_hash.replace("'", "")
    rows = await lori_regulatory_supabase_get(
        f"lori_regulatory_alerts?content_hash=eq.{safe_hash}&select=id&limit=1"
    )
    return bool(rows)


async def lori_regulatory_fetch_rss(source: Dict[str, Any]) -> List[Dict[str, Any]]:
    feed_url = source.get("feed_url") or source.get("source_url")
    if not feed_url:
        return []

    items: List[Dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(
            feed_url,
            headers={"User-Agent": "LORI-Regulatory-Scanner/1.0"},
        )

    if response.status_code >= 400:
        raise Exception(f"RSS fetch failed for {feed_url}: {response.status_code}")

    root = ET.fromstring(response.text)

    for item in root.findall(".//item"):
        title = lori_regulatory_clean_text(item.findtext("title"))
        link = lori_regulatory_clean_text(item.findtext("link"))
        summary = lori_regulatory_clean_text(
            item.findtext("description") or item.findtext("summary")
        )
        published_raw = item.findtext("pubDate") or item.findtext("published") or item.findtext("updated")
        published_at = lori_regulatory_parse_date(published_raw)

        if not title:
            continue

        if not lori_regulatory_is_relevant(title, summary, source):
            continue

        items.append(
            {
                "title": title,
                "summary": summary,
                "url": link,
                "published_at": published_at,
                "raw": {
                    "source": "rss",
                    "feed_url": feed_url,
                    "published_raw": published_raw,
                },
            }
        )

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//atom:entry", ns):
        title = lori_regulatory_clean_text(entry.findtext("atom:title", default="", namespaces=ns))
        summary = lori_regulatory_clean_text(
            entry.findtext("atom:summary", default="", namespaces=ns)
            or entry.findtext("atom:content", default="", namespaces=ns)
        )
        published_raw = (
            entry.findtext("atom:published", default="", namespaces=ns)
            or entry.findtext("atom:updated", default="", namespaces=ns)
        )
        published_at = lori_regulatory_parse_date(published_raw)

        link = ""
        link_el = entry.find("atom:link", ns)
        if link_el is not None:
            link = link_el.attrib.get("href", "")

        if not title:
            continue

        if not lori_regulatory_is_relevant(title, summary, source):
            continue

        items.append(
            {
                "title": title,
                "summary": summary,
                "url": link,
                "published_at": published_at,
                "raw": {
                    "source": "atom",
                    "feed_url": feed_url,
                    "published_raw": published_raw,
                },
            }
        )

    return items[:20]


async def lori_regulatory_fetch_federal_register(source: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []

    api_urls = [
        "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bagencies%5D%5B%5D=federal-motor-carrier-safety-administration&order=newest&per_page=10",
        "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bagencies%5D%5B%5D=transportation-department&order=newest&per_page=10",
    ]

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for api_url in api_urls:
            response = await client.get(
                api_url,
                headers={"User-Agent": "LORI-Regulatory-Scanner/1.0"},
            )

            if response.status_code >= 400:
                continue

            data = response.json()

            for doc in data.get("results", []):
                title = lori_regulatory_clean_text(doc.get("title"))
                summary = lori_regulatory_clean_text(doc.get("abstract") or doc.get("type"))
                url = doc.get("html_url") or doc.get("pdf_url") or doc.get("public_inspection_pdf_url")
                published_at = lori_regulatory_parse_date(doc.get("publication_date"))

                if not title:
                    continue

                if not lori_regulatory_is_relevant(title, summary, source):
                    continue

                items.append(
                    {
                        "title": title,
                        "summary": summary,
                        "url": url,
                        "published_at": published_at,
                        "raw": {
                            "source": "federal_register",
                            "document_number": doc.get("document_number"),
                            "type": doc.get("type"),
                            "publication_date": doc.get("publication_date"),
                            "agencies": doc.get("agencies"),
                        },
                    }
                )

    return items[:20]


async def lori_regulatory_fetch_source(source: Dict[str, Any]) -> List[Dict[str, Any]]:
    source_format = str(source.get("source_format") or "").lower()
    source_name = str(source.get("source_name") or "").lower()

    if "federal register" in source_name or source_format == "api":
        return await lori_regulatory_fetch_federal_register(source)

    if source.get("feed_url") or source_format == "rss":
        return await lori_regulatory_fetch_rss(source)

    return []


def lori_regulatory_priority_for_item(item: Dict[str, Any]) -> str:
    text = f"{item.get('title', '')} {item.get('summary', '')}".lower()

    if any(word in text for word in ["final rule", "effective", "emergency", "enforcement"]):
        return "High"

    if any(word in text for word in ["proposed rule", "notice", "comment", "guidance"]):
        return "Watch"

    return "Informational"


def lori_regulatory_build_operational_impact(item: Dict[str, Any]) -> str:
    return (
        "This update may require review for potential impact on driver operations, "
        "station readiness, safety procedures, DOT/FMCSA compliance planning, "
        "company policy, supervisor briefing, or leadership awareness."
    )


def lori_regulatory_build_recommended_preparation(item: Dict[str, Any]) -> str:
    return (
        "Review the official source, confirm whether the update applies to the operating location, "
        "identify affected drivers or supervisors, determine whether policy or training updates are needed, "
        "and prepare a leadership briefing if operational impact is confirmed."
    )


@app.get("/regulatory-alerts")
async def get_regulatory_alerts(
    api_key: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    limit: int = Query(10),
):
    lori_regulatory_require_key(api_key)

    limit = max(1, min(limit, 50))

    query = (
        "lori_regulatory_alerts?"
        "select=*"
        "&order=created_at.desc"
        f"&limit={limit}"
    )

    if state:
        query += f"&state_code=eq.{state.upper()}"

    alerts = await lori_regulatory_supabase_get(query)

    latest_logs = await lori_regulatory_supabase_get(
        "lori_regulatory_scan_logs?select=*&order=created_at.desc&limit=1"
    )

    latest_log = latest_logs[0] if latest_logs else None

    if alerts:
        status_message = "New or stored regulatory alerts are available for review."
        result = "Regulatory Update Requires Review"
    else:
        status_message = "No new verified regulatory updates found in the current stored alert set."
        result = "No New Verified Updates Found"

    return {
        "status": "success",
        "result": result,
        "message": status_message,
        "last_checked": latest_log.get("scan_completed_at") if latest_log else None,
        "latest_scan": latest_log,
        "alerts_count": len(alerts),
        "alerts": alerts,
        "disclaimer": (
            "LORI provides operational decision support. Regulatory alerts, transportation laws, "
            "DOT/FMCSA updates, state law changes, labor/HR updates, and compliance-sensitive matters "
            "must be verified against official sources and reviewed by appropriate compliance, HR, "
            "labor relations, or legal personnel before formal action."
        ),
    }


@app.get("/regulatory-scan-log")
async def get_regulatory_scan_log(
    api_key: Optional[str] = Query(None),
    limit: int = Query(10),
):
    lori_regulatory_require_key(api_key)

    limit = max(1, min(limit, 50))

    logs = await lori_regulatory_supabase_get(
        f"lori_regulatory_scan_logs?select=*&order=created_at.desc&limit={limit}"
    )

    return {
        "status": "success",
        "scan_logs": logs,
    }


@app.post("/regulatory-scan")
async def run_regulatory_scan(
    api_key: Optional[str] = Query(None),
    operating_state: Optional[str] = Query("MD"),
    station_code: Optional[str] = Query("JESSUP-01"),
):
    lori_regulatory_require_key(api_key)

    scan_log_payload = {
        "scan_started_at": lori_regulatory_now_iso(),
        "scan_status": "Started",
        "operating_state": operating_state.upper() if operating_state else None,
        "station_code": station_code or "JESSUP-01",
        "federal_check_status": "Started",
        "state_check_status": "Started",
        "dot_fmcsa_check_status": "Started",
        "labor_hr_check_status": "Pending",
        "sources_checked": 0,
        "alerts_found": 0,
        "new_alerts_found": 0,
        "result_summary": "Regulatory scan started.",
    }

    created_log = await lori_regulatory_supabase_post(
        "lori_regulatory_scan_logs",
        scan_log_payload,
    )

    scan_log_id = created_log[0]["id"] if created_log else None

    sources = await lori_regulatory_supabase_get(
        "lori_regulatory_sources?is_active=eq.true&select=*"
    )

    sources_checked = 0
    alerts_found = 0
    new_alerts_found = 0
    errors: List[str] = []
    stored_alerts: List[Dict[str, Any]] = []

    for source in sources:
        try:
            source_state = source.get("state_code")
            source_type = source.get("source_type")

            if source_type == "State" and source_state and operating_state:
                if source_state.upper() != operating_state.upper():
                    continue

            items = await lori_regulatory_fetch_source(source)
            sources_checked += 1
            alerts_found += len(items)

            for item in items:
                content_hash = lori_regulatory_hash(
                    source.get("id"),
                    item.get("title"),
                    item.get("url"),
                    item.get("published_at"),
                )

                exists = await lori_regulatory_alert_exists(content_hash)
                if exists:
                    continue

                priority = lori_regulatory_priority_for_item(item)

                alert_payload = {
                    "source_id": source.get("id"),
                    "alert_title": item.get("title"),
                    "alert_summary": item.get("summary"),
                    "alert_body": item.get("summary"),
                    "source_type": source.get("source_type"),
                    "agency": source.get("agency"),
                    "jurisdiction": source.get("jurisdiction"),
                    "state_code": source.get("state_code"),
                    "category": source.get("category"),
                    "published_at": item.get("published_at"),
                    "source_url": item.get("url"),
                    "alert_priority": priority,
                    "alert_status": "New",
                    "applies_to": [
                        "Drivers",
                        "Supervisors",
                        "Station Leadership",
                        "Fleet Operations",
                    ],
                    "operational_impact": lori_regulatory_build_operational_impact(item),
                    "recommended_preparation": lori_regulatory_build_recommended_preparation(item),
                    "source_verification_status": "Official source found - leadership verification recommended",
                    "content_hash": content_hash,
                    "raw_payload": item.get("raw"),
                }

                inserted_alert = await lori_regulatory_supabase_post(
                    "lori_regulatory_alerts",
                    alert_payload,
                )

                if inserted_alert:
                    new_alerts_found += 1
                    stored_alerts.append(inserted_alert[0])

        except Exception as exc:
            errors.append(f"{source.get('source_name', 'Unknown source')}: {str(exc)}")

    if new_alerts_found > 0:
        scan_status = "Completed - New Alerts Found"
        result_summary = f"Regulatory scan completed. {new_alerts_found} new alert(s) found."
    else:
        scan_status = "Completed - No New Verified Updates Found"
        result_summary = "Regulatory scan completed. No new verified updates found from configured sources."

    federal_status = "Checked" if sources_checked > 0 else "No active federal sources checked"
    state_status = "Checked" if operating_state else "No operating state selected"
    dot_status = "Checked" if sources_checked > 0 else "No DOT/FMCSA sources checked"

    update_payload = {
        "scan_completed_at": lori_regulatory_now_iso(),
        "scan_status": scan_status,
        "federal_check_status": federal_status,
        "state_check_status": state_status,
        "dot_fmcsa_check_status": dot_status,
        "labor_hr_check_status": "Pending source connection",
        "sources_checked": sources_checked,
        "alerts_found": alerts_found,
        "new_alerts_found": new_alerts_found,
        "result_summary": result_summary,
        "error_message": "\n".join(errors) if errors else None,
    }

    if scan_log_id:
        await lori_regulatory_supabase_patch(
            "lori_regulatory_scan_logs",
            scan_log_id,
            update_payload,
        )

    return {
        "status": "success",
        "scan_status": scan_status,
        "operating_state": operating_state,
        "station_code": station_code,
        "sources_checked": sources_checked,
        "alerts_found": alerts_found,
        "new_alerts_found": new_alerts_found,
        "result_summary": result_summary,
        "new_alerts": stored_alerts,
        "errors": errors,
        "disclaimer": (
            "LORI provides operational decision support. Regulatory alerts must be verified against "
            "official federal, state, DOT/FMCSA, HR, compliance, labor relations, or legal sources before formal action."
        ),
    }
# ============================================================
# LORI REGULATORY INTELLIGENCE
# Company-Specific Filter Override
# Focus: Food distribution / commercial delivery fleet
# Excludes irrelevant aviation / FAA / aircraft updates
# ============================================================

COMPANY_PROFILE_NAME = "Food Authority / Food Distribution Delivery Fleet"

COMPANY_RELEVANT_KEYWORDS = [
    "fmcsa",
    "federal motor carrier safety administration",
    "dot",
    "department of transportation",
    "motor carrier",
    "commercial motor vehicle",
    "cmv",
    "carrier",
    "driver",
    "drivers",
    "cdl",
    "commercial driver's license",
    "commercial driver",
    "driver qualification",
    "driver qualification file",
    "dqf",
    "medical card",
    "dot medical",
    "medical examiner",
    "hours of service",
    "hos",
    "electronic logging",
    "eld",
    "drug",
    "alcohol",
    "controlled substance",
    "testing",
    "safety",
    "inspection",
    "vehicle inspection",
    "pre-trip",
    "post-trip",
    "fleet",
    "truck",
    "trucking",
    "delivery",
    "route",
    "logistics",
    "transportation",
    "warehouse",
    "distribution",
    "food distribution",
    "food delivery",
    "foodservice",
    "refrigerated",
    "cold chain",
    "hazmat",
    "hazardous materials",
    "compliance",
    "rule",
    "notice",
    "regulation",
    "enforcement",
]

COMPANY_EXCLUDED_KEYWORDS = [
    "faa",
    "federal aviation administration",
    "aviation",
    "aircraft",
    "airworthiness",
    "airspace",
    "airport",
    "runway",
    "helicopter",
    "rotorcraft",
    "bell textron",
    "boeing",
    "airbus",
    "flight",
    "pilot",
    "federal airway",
    "vortac",
    "tacan",
    "navigation aid",
    "class e airspace",
    "domestic very high frequency",
    "vhf",
    "air traffic",
    "aeronautical",
    "maritime",
    "vessel",
    "coast guard",
    "railroad",
    "railway",
    "pipeline safety",
    "transit rail",
]


def lori_company_text_blob(title: str, summary: str, source: Dict[str, Any]) -> str:
    return f"""
    {title or ''}
    {summary or ''}
    {source.get('source_name', '') or ''}
    {source.get('agency', '') or ''}
    {source.get('category', '') or ''}
    {source.get('source_type', '') or ''}
    """.lower()


def lori_regulatory_is_relevant(title: str, summary: str, source: Dict[str, Any]) -> bool:
    """
    Company-specific relevance filter.

    This keeps LORI focused on a food distribution / commercial delivery
    transportation operation instead of pulling unrelated DOT items such as
    FAA, aircraft, helicopter, aviation, airspace, railroad, maritime, or pipeline notices.
    """

    combined = lori_company_text_blob(title, summary, source)

    # Hard exclude aviation / aircraft / non-fleet transportation categories.
    if any(excluded in combined for excluded in COMPANY_EXCLUDED_KEYWORDS):
        return False

    source_name = str(source.get("source_name") or "").lower()
    agency = str(source.get("agency") or "").lower()
    category = str(source.get("category") or "").lower()

    # FMCSA sources are highly relevant to commercial fleet operations.
    if "federal motor carrier safety administration" in agency:
        return True

    if "fmcsa" in source_name or "fmcsa" in category:
        return True

    # DOT items must still match company-relevant transportation operations.
    if any(keyword in combined for keyword in COMPANY_RELEVANT_KEYWORDS):
        return True

    return False


async def lori_regulatory_fetch_federal_register(source: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Company-specific Federal Register scanner.

    Only scans FMCSA documents for now.
    Avoids broad DOT-wide Federal Register pulls that include FAA aviation,
    aircraft, helicopter, airspace, railroad, maritime, and unrelated items.
    """

    items: List[Dict[str, Any]] = []

    api_urls = [
        "https://www.federalregister.gov/api/v1/documents.json?conditions%5Bagencies%5D%5B%5D=federal-motor-carrier-safety-administration&order=newest&per_page=20"
    ]

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        for api_url in api_urls:
            response = await client.get(
                api_url,
                headers={"User-Agent": "LORI-Regulatory-Scanner/1.0"},
            )

            if response.status_code >= 400:
                continue

            data = response.json()

            for doc in data.get("results", []):
                title = lori_regulatory_clean_text(doc.get("title"))
                summary = lori_regulatory_clean_text(doc.get("abstract") or doc.get("type"))
                url = doc.get("html_url") or doc.get("pdf_url") or doc.get("public_inspection_pdf_url")
                published_at = lori_regulatory_parse_date(doc.get("publication_date"))

                if not title:
                    continue

                if not lori_regulatory_is_relevant(title, summary, source):
                    continue

                items.append(
                    {
                        "title": title,
                        "summary": summary,
                        "url": url,
                        "published_at": published_at,
                        "raw": {
                            "source": "federal_register",
                            "company_profile": COMPANY_PROFILE_NAME,
                            "document_number": doc.get("document_number"),
                            "type": doc.get("type"),
                            "publication_date": doc.get("publication_date"),
                            "agencies": doc.get("agencies"),
                        },
                    }
                )

    return items[:20]


def lori_regulatory_build_operational_impact(item: Dict[str, Any]) -> str:
    return (
        "This update may require review for potential impact on commercial delivery operations, "
        "driver qualification, DOT/FMCSA compliance readiness, fleet safety, vehicle inspection, "
        "driver policy, supervisor briefing, training, audit readiness, or leadership awareness. "
        "It should be reviewed for relevance to food distribution, delivery routes, commercial drivers, "
        "warehouse-to-customer transportation, and fleet operations."
    )


def lori_regulatory_build_recommended_preparation(item: Dict[str, Any]) -> str:
    return (
        "Review the official source, confirm whether the update applies to the company’s commercial delivery fleet, "
        "identify affected drivers, supervisors, vehicles, routes, policies, or audit areas, determine whether training "
        "or policy updates are needed, and prepare a leadership briefing if operational impact is confirmed."
    )
# ============================================================
# LORI REGULATORY INTELLIGENCE
# Voiceflow-ready daily alert briefing endpoint
# Allows user to ask: "Tell me the alerts for today."
# ============================================================

def lori_regulatory_short_date(value: Any) -> str:
    if not value:
        return "Not listed"

    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.strftime("%b %d, %Y")
    except Exception:
        return str(value)


def lori_regulatory_safe_line(value: Any, fallback: str = "Not listed") -> str:
    cleaned = lori_regulatory_clean_text(value)
    return cleaned if cleaned else fallback


def lori_regulatory_build_alert_briefing(
    alerts: List[Dict[str, Any]],
    latest_scan: Optional[Dict[str, Any]],
    requested_state: Optional[str] = None,
) -> str:
    today_label = datetime.now(timezone.utc).strftime("%b %d, %Y")

    if latest_scan:
        scan_status = latest_scan.get("scan_status") or "Scan status not listed"
        sources_checked = latest_scan.get("sources_checked", 0)
        alerts_found = latest_scan.get("alerts_found", 0)
        new_alerts_found = latest_scan.get("new_alerts_found", 0)
        scan_completed = lori_regulatory_short_date(latest_scan.get("scan_completed_at"))
        operating_state = latest_scan.get("operating_state") or requested_state or "Not selected"
        station_code = latest_scan.get("station_code") or "Not listed"
        result_summary = latest_scan.get("result_summary") or "No scan summary listed."
    else:
        scan_status = "No scan log found"
        sources_checked = 0
        alerts_found = 0
        new_alerts_found = 0
        scan_completed = "Not listed"
        operating_state = requested_state or "Not selected"
        station_code = "Not listed"
        result_summary = "No completed regulatory scan is available yet."

    if not alerts:
        return f"""Regulatory Alert Briefing — Today

Date:
{today_label}

Status:
No new verified regulatory alerts are currently listed for review.

Latest Scan:
{scan_status}

Sources Checked:
{sources_checked}

Operating State:
{operating_state}

Station:
{station_code}

Result:
{result_summary}

Recommended Next Action:
No immediate regulatory briefing is required based on the current stored alert set. Continue monitoring and verify official DOT, FMCSA, state, HR, compliance, labor relations, or legal sources before taking formal action.

Compliance Note:
LORI provides operational decision support. Regulatory alerts, transportation laws, DOT/FMCSA updates, state law changes, labor/HR updates, and compliance-sensitive matters must be verified against official sources and reviewed by appropriate compliance, HR, labor relations, or legal personnel before formal action."""

    lines = []
    lines.append("Regulatory Alert Briefing — Today")
    lines.append("")
    lines.append("Date:")
    lines.append(today_label)
    lines.append("")
    lines.append("Current Status:")
    lines.append("New regulatory alerts require leadership review.")
    lines.append("")
    lines.append("Latest Scan:")
    lines.append(str(scan_status))
    lines.append("")
    lines.append("Operating State:")
    lines.append(str(operating_state))
    lines.append("")
    lines.append("Station:")
    lines.append(str(station_code))
    lines.append("")
    lines.append("Sources Checked:")
    lines.append(str(sources_checked))
    lines.append("")
    lines.append("Alerts Found:")
    lines.append(str(alerts_found))
    lines.append("")
    lines.append("New Alerts Found:")
    lines.append(str(new_alerts_found))
    lines.append("")
    lines.append("Top Alerts for Leadership Review:")

    for index, alert in enumerate(alerts[:5], start=1):
        title = lori_regulatory_safe_line(alert.get("alert_title"))
        agency = lori_regulatory_safe_line(alert.get("agency"))
        category = lori_regulatory_safe_line(alert.get("category"))
        priority = lori_regulatory_safe_line(alert.get("alert_priority"))
        published = lori_regulatory_short_date(alert.get("published_at"))
        impact = lori_regulatory_safe_line(alert.get("operational_impact"))
        preparation = lori_regulatory_safe_line(alert.get("recommended_preparation"))
        verification = lori_regulatory_safe_line(alert.get("source_verification_status"))

        lines.append("")
        lines.append(f"{index}. {title}")
        lines.append(f"Agency: {agency}")
        lines.append(f"Category: {category}")
        lines.append(f"Priority: {priority}")
        lines.append(f"Published: {published}")
        lines.append(f"Operational Impact: {impact}")
        lines.append(f"Recommended Preparation: {preparation}")
        lines.append(f"Verification Status: {verification}")

    lines.append("")
    lines.append("Recommended Next Action:")
    lines.append(
        "Review the top alerts, confirm official source relevance, identify affected drivers, supervisors, policies, audits, or training areas, and add confirmed items to the leadership briefing or compliance follow-up list."
    )

    lines.append("")
    lines.append("Compliance Note:")
    lines.append(
        "LORI provides operational decision support. Regulatory alerts, transportation laws, DOT/FMCSA updates, state law changes, labor/HR updates, and compliance-sensitive matters must be verified against official sources and reviewed by appropriate compliance, HR, labor relations, or legal personnel before formal action."
    )

    return "\n".join(lines)


@app.get("/voiceflow/regulatory-alerts")
async def voiceflow_regulatory_alerts(
    api_key: Optional[str] = Query(None),
    question: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    limit: int = Query(5),
):
    lori_regulatory_require_key(api_key)

    limit = max(1, min(limit, 10))

    alerts = await lori_regulatory_supabase_get(
        "lori_regulatory_alerts?select=*&order=created_at.desc&limit=25"
    )

    filtered_alerts = []

    if state:
        requested_state = state.upper()
        for alert in alerts:
            alert_state = alert.get("state_code")
            if alert_state is None or str(alert_state).upper() == requested_state:
                filtered_alerts.append(alert)
    else:
        filtered_alerts = alerts

    filtered_alerts = filtered_alerts[:limit]

    latest_logs = await lori_regulatory_supabase_get(
        "lori_regulatory_scan_logs?select=*&order=created_at.desc&limit=1"
    )

    latest_scan = latest_logs[0] if latest_logs else None

    answer_text = lori_regulatory_build_alert_briefing(
        filtered_alerts,
        latest_scan,
        state,
    )

    return {
        "status": "success",
        "question": question,
        "alerts_count": len(filtered_alerts),
        "latest_scan": latest_scan,
        "answer_text": answer_text,
    }
# ============================================================
# LORI DRIVE COMMAND CENTER
# Agreement / Policy Intelligence Backend
# Searches uploaded/demo policy, agreement, work rule, and CBA sections
# and returns Voiceflow-ready review guidance.
# ============================================================

from typing import Any, Dict, List, Optional
from fastapi import Query, HTTPException
import re


POLICY_REVIEW_KEYWORDS = {
    "attendance": [
        "attendance",
        "call out",
        "call-out",
        "callout",
        "absence",
        "late",
        "tardy",
        "no call",
        "no show",
        "scheduled assignment",
        "report to work",
    ],
    "discipline": [
        "discipline",
        "corrective action",
        "write up",
        "write-up",
        "coaching",
        "counseling",
        "progressive",
        "formal action",
        "warning",
        "suspension",
        "termination",
    ],
    "safety": [
        "safety",
        "accident",
        "incident",
        "unsafe",
        "inspection",
        "vehicle",
        "pre trip",
        "pre-trip",
        "post trip",
        "post-trip",
        "hazard",
    ],
    "route": [
        "route",
        "assignment",
        "bid",
        "run",
        "delivery",
        "schedule",
        "dispatch",
        "route assignment",
    ],
    "overtime": [
        "overtime",
        "hours",
        "extra work",
        "premium",
        "pay",
        "payroll",
        "timekeeping",
    ],
    "seniority": [
        "seniority",
        "bid",
        "bidding",
        "assignment",
        "preference",
        "order",
    ],
    "grievance": [
        "grievance",
        "dispute",
        "appeal",
        "union",
        "labor relations",
        "representation",
    ],
    "policy": [
        "policy",
        "work rule",
        "sop",
        "procedure",
        "company policy",
        "driver policy",
    ],
    "agreement": [
        "agreement",
        "contract",
        "cba",
        "collective bargaining",
        "union agreement",
        "labor agreement",
    ],
}


def lori_policy_clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def lori_policy_terms(text: str) -> List[str]:
    text = lori_policy_clean_text(text).lower()
    text = re.sub(r"[^a-z0-9\s\-]", " ", text)
    return [term for term in text.split() if len(term) >= 3]


def lori_policy_detect_situation_type(question: str) -> str:
    q = lori_policy_clean_text(question).lower()

    best_type = "Policy / Agreement Review"
    best_score = 0

    for situation_type, keywords in POLICY_REVIEW_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            if keyword in q:
                score += 1
        if score > best_score:
            best_score = score
            best_type = situation_type.title()

    return best_type


def lori_policy_score_section(question: str, section: Dict[str, Any], document: Dict[str, Any]) -> int:
    q = lori_policy_clean_text(question).lower()

    section_blob = " ".join(
        [
            lori_policy_clean_text(section.get("section_title")),
            lori_policy_clean_text(section.get("section_text")),
            lori_policy_clean_text(section.get("article_number")),
            lori_policy_clean_text(section.get("section_number")),
            " ".join(section.get("topic_tags") or []),
            " ".join(section.get("risk_tags") or []),
            " ".join(section.get("applies_to") or []),
            lori_policy_clean_text(document.get("document_title")),
            lori_policy_clean_text(document.get("document_type")),
            lori_policy_clean_text(document.get("summary")),
        ]
    ).lower()

    score = 0

    for term in lori_policy_terms(q):
        if term in section_blob:
            score += 2

    for situation_type, keywords in POLICY_REVIEW_KEYWORDS.items():
        if any(keyword in q for keyword in keywords):
            for keyword in keywords:
                if keyword in section_blob:
                    score += 3

    return score


async def lori_policy_supabase_get(query_path: str) -> Any:
    url = f"{SUPABASE_URL}/rest/v1/{query_path}"

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, headers=lori_regulatory_supabase_headers())

    if response.status_code >= 400:
        raise HTTPException(
            status_code=500,
            detail=f"Supabase GET failed: {response.text}",
        )

    return response.json()


async def lori_policy_supabase_post(table: str, payload: Dict[str, Any]) -> Any:
    url = f"{SUPABASE_URL}/rest/v1/{table}"

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            url,
            headers=lori_regulatory_supabase_headers("return=representation"),
            json=payload,
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=500,
            detail=f"Supabase POST failed: {response.text}",
        )

    return response.json()


def lori_policy_build_supervisor_language(situation_type: str) -> str:
    if situation_type.lower() == "attendance":
        return (
            "This conversation should be positioned as an attendance expectation review. "
            "The supervisor should confirm the facts, review the attendance or call-out record, "
            "explain the expectation clearly, and document the discussion without making a final "
            "discipline or agreement determination."
        )

    if situation_type.lower() == "discipline":
        return (
            "This conversation should be positioned as a coaching and documentation review. "
            "The supervisor should focus on facts, prior coaching history, expectations, and corrective steps. "
            "Formal discipline should not be finalized until HR, labor relations, compliance, or leadership review is complete."
        )

    if situation_type.lower() == "safety":
        return (
            "This conversation should be positioned as a safety expectation and prevention review. "
            "The supervisor should confirm the safety facts, document what occurred, reinforce the required behavior, "
            "and determine whether training, vehicle inspection, or compliance follow-up is needed."
        )

    if situation_type.lower() == "route":
        return (
            "This conversation should be positioned as a route assignment and operational expectation review. "
            "The supervisor should confirm the assignment facts, schedule impact, route instructions, and whether policy, "
            "agreement, dispatch, or leadership review is needed."
        )

    return (
        "This conversation should be positioned as an operational expectation review. "
        "The supervisor should confirm the facts, compare the situation to the applicable policy or agreement language, "
        "document the discussion, and avoid final conclusions until the matter is reviewed by the appropriate leader, "
        "HR, labor relations, compliance, or legal reviewer."
    )


def lori_policy_build_answer(
    question: str,
    situation_type: str,
    matches: List[Dict[str, Any]],
    review_request: Optional[Dict[str, Any]] = None,
) -> str:
    if not matches:
        return f"""Agreement / Policy Review

Situation Type:
{situation_type}

Status:
I do not see a matching agreement or policy section in the currently searchable LORI policy records.

Recommended Next Action:
Upload or confirm the relevant union agreement, company policy, work rule, SOP, or driver policy so LORI can compare the situation against the official language.

Supervisor Guidance:
Do not make a final policy, agreement, labor, HR, or disciplinary determination until the official document is reviewed.

Compliance Note:
This is not a final HR, legal, labor, or contract determination. HR, labor relations, compliance, legal, or leadership review is recommended before formal action."""

    top_match = matches[0]
    top_section = top_match["section"]
    top_document = top_match["document"]

    lines = []

    lines.append("Agreement / Policy Review")
    lines.append("")
    lines.append("Situation Type:")
    lines.append(situation_type)
    lines.append("")
    lines.append("Primary Document:")
    lines.append(lori_policy_clean_text(top_document.get("document_title")) or "Not listed")
    lines.append("")
    lines.append("Document Type:")
    lines.append(lori_policy_clean_text(top_document.get("document_type")) or "Not listed")
    lines.append("")
    lines.append("Potentially Relevant Section:")
    section_label_parts = [
        lori_policy_clean_text(top_section.get("article_number")),
        lori_policy_clean_text(top_section.get("section_number")),
        lori_policy_clean_text(top_section.get("section_title")),
    ]
    section_label = " — ".join([part for part in section_label_parts if part])
    lines.append(section_label or "Section not listed")
    lines.append("")
    lines.append("Relevant Language:")
    lines.append(lori_policy_clean_text(top_section.get("section_text")))
    lines.append("")
    lines.append("Operational Concern:")
    lines.append(
        "The situation may require review against the identified agreement, policy, work rule, or procedure. "
        "The section appears relevant for operational review, but it should not be treated as a final violation finding."
    )
    lines.append("")
    lines.append("Facts to Confirm:")
    lines.append(
        "Confirm the date, time, driver or employee involved, supervisor, prior coaching history, documentation, "
        "applicable route or assignment details, and whether the official agreement or company policy version is current."
    )
    lines.append("")
    lines.append("Recommended Supervisor Language:")
    lines.append(lori_policy_build_supervisor_language(situation_type))
    lines.append("")
    lines.append("Recommended Next Action:")
    lines.append(
        "Review the official document, confirm the facts, document the discussion, and route the matter to HR, labor relations, "
        "compliance, legal, or leadership review before formal action if discipline, contract interpretation, or policy enforcement is being considered."
    )

    if len(matches) > 1:
        lines.append("")
        lines.append("Additional Sections to Review:")
        for index, match in enumerate(matches[1:4], start=2):
            section = match["section"]
            document = match["document"]
            label_parts = [
                lori_policy_clean_text(document.get("document_title")),
                lori_policy_clean_text(section.get("article_number")),
                lori_policy_clean_text(section.get("section_number")),
                lori_policy_clean_text(section.get("section_title")),
            ]
            label = " — ".join([part for part in label_parts if part])
            lines.append(f"{index}. {label}")

    lines.append("")
    lines.append("HR / Labor / Compliance Note:")
    lines.append(
        "This is not a final HR, legal, labor, or contract determination. HR, labor relations, compliance, legal, or leadership review is recommended before formal action."
    )

    return "\n".join(lines)


async def lori_policy_find_matches(question: str, limit: int = 5) -> List[Dict[str, Any]]:
    documents = await lori_policy_supabase_get(
        "lori_policy_documents?select=*&order=created_at.desc&limit=100"
    )

    sections = await lori_policy_supabase_get(
        "lori_policy_sections?select=*&order=created_at.desc&limit=500"
    )

    docs_by_id = {doc.get("id"): doc for doc in documents}

    scored: List[Dict[str, Any]] = []

    for section in sections:
        doc = docs_by_id.get(section.get("document_id"), {})
        score = lori_policy_score_section(question, section, doc)

        if score > 0:
            scored.append(
                {
                    "score": score,
                    "section": section,
                    "document": doc,
                }
            )

    scored.sort(key=lambda item: item["score"], reverse=True)

    return scored[:limit]


@app.get("/policy-documents")
async def get_policy_documents(
    api_key: Optional[str] = Query(None),
    limit: int = Query(25),
):
    lori_regulatory_require_key(api_key)

    limit = max(1, min(limit, 100))

    documents = await lori_policy_supabase_get(
        f"lori_policy_documents?select=*&order=created_at.desc&limit={limit}"
    )

    return {
        "status": "success",
        "documents_count": len(documents),
        "documents": documents,
    }


@app.get("/policy-search")
async def policy_search(
    api_key: Optional[str] = Query(None),
    query: str = Query(...),
    limit: int = Query(5),
):
    lori_regulatory_require_key(api_key)

    limit = max(1, min(limit, 10))

    matches = await lori_policy_find_matches(query, limit)

    return {
        "status": "success",
        "query": query,
        "matches_count": len(matches),
        "matches": matches,
    }


@app.get("/voiceflow/policy-review")
async def voiceflow_policy_review(
    api_key: Optional[str] = Query(None),
    question: str = Query(...),
    driver_name: Optional[str] = Query(None),
    employee_id: Optional[str] = Query(None),
    supervisor_name: Optional[str] = Query(None),
    limit: int = Query(5),
):
    lori_regulatory_require_key(api_key)

    limit = max(1, min(limit, 10))

    situation_type = lori_policy_detect_situation_type(question)

    review_payload = {
        "request_text": question,
        "driver_name": driver_name,
        "employee_id": employee_id,
        "supervisor_name": supervisor_name,
        "situation_type": situation_type,
        "operating_state": "MD",
        "station_code": "JESSUP-01",
        "review_status": "Open",
        "priority": "Review Needed",
    }

    created_review = await lori_policy_supabase_post(
        "lori_policy_review_requests",
        review_payload,
    )

    review_request = created_review[0] if created_review else None

    matches = await lori_policy_find_matches(question, limit)

    answer_text = lori_policy_build_answer(
        question=question,
        situation_type=situation_type,
        matches=matches,
        review_request=review_request,
    )

    if review_request and matches:
        top_match = matches[0]
        finding_payload = {
            "review_request_id": review_request.get("id"),
            "document_id": top_match["document"].get("id"),
            "section_id": top_match["section"].get("id"),
            "finding_type": "Policy / Agreement Review",
            "confidence_level": "Needs Human Review",
            "issue_summary": question,
            "potentially_relevant_section": top_match["section"].get("section_title"),
            "relevant_language": top_match["section"].get("section_text"),
            "operational_concern": (
                "This may require review against the identified agreement, policy, work rule, or procedure."
            ),
            "facts_to_confirm": (
                "Confirm the facts, involved driver or employee, date, supervisor, documentation, current policy version, and prior coaching history."
            ),
            "recommended_supervisor_language": lori_policy_build_supervisor_language(situation_type),
            "recommended_next_action": (
                "Review the official document and route the matter to HR, labor relations, compliance, legal, or leadership review before formal action."
            ),
        }

        await lori_policy_supabase_post(
            "lori_policy_findings",
            finding_payload,
        )

    return {
        "status": "success",
        "question": question,
        "situation_type": situation_type,
        "matches_count": len(matches),
        "review_request": review_request,
        "answer_text": answer_text,
    }
# ============================================================
# LORI DRIVE COMMAND CENTER
# Enhanced Counseling Language Override
# Upgrades Agreement / Policy Review responses with polished,
# supervisor-ready counseling scripts based on the policy issue.
# ============================================================

def lori_policy_build_enhanced_counseling_script(
    situation_type: str,
    question: str,
    section: Dict[str, Any],
    document: Dict[str, Any],
) -> str:
    situation = lori_policy_clean_text(situation_type).lower()
    section_title = lori_policy_clean_text(section.get("section_title")) or "the applicable policy or agreement section"
    document_title = lori_policy_clean_text(document.get("document_title")) or "the applicable policy or agreement document"

    if situation == "attendance":
        return f"""Supervisor Counseling Script — Attendance / Call-Out Review

Opening Statement:
I want to review an attendance and call-out concern with you in a clear and professional way. This conversation is intended to confirm the facts, review expectations, and prevent this from becoming a larger performance or compliance issue.

Policy / Agreement Reference:
The section currently flagged for review is "{section_title}" from "{document_title}." This section appears relevant because it addresses attendance expectations, call-out procedures, documentation, and supervisor follow-up.

Facts to Confirm:
Before any conclusion is made, we need to confirm the date or dates involved, the scheduled assignment, whether proper call-out steps were followed, whether notice was timely, whether documentation exists, and whether there is any prior coaching or pattern that should be reviewed.

Expectation:
The operational expectation is that drivers report to scheduled assignments on time and follow the established call-out process when they are unable to report. The call-out process is important because it allows the station to protect route coverage, customer commitments, staffing plans, and driver accountability.

Operational Impact:
When call-outs are repeated, late, undocumented, or inconsistent with procedure, it can affect route coverage, supervisor planning, customer service, overtime exposure, team fairness, and overall station reliability.

Employee Response Prompt:
Before we determine next steps, I want to give you an opportunity to explain what happened from your perspective. Is there any information, documentation, or context we should review before this matter is evaluated further?

Corrective Expectation:
Going forward, the expectation is that you follow the call-out procedure exactly, communicate as early as required, provide any required documentation, and understand that repeated attendance issues may require additional review under company policy, applicable work rules, or agreement language.

Documentation Language:
This conversation should be documented as an attendance expectation review and fact-confirmation discussion. It should not be written as a final policy violation, contract violation, or disciplinary determination unless HR, labor relations, compliance, legal, or leadership review confirms the appropriate next step.

Recommended Next Step:
Review the official policy or agreement language, verify the attendance record, confirm prior coaching history, document the conversation, and determine whether this should remain at the coaching level or be escalated for HR/labor review.

HR / Labor / Compliance Note:
This is not a final HR, legal, labor, or contract determination. Formal action should be reviewed by HR, labor relations, compliance, legal, or leadership before being finalized."""

    if situation == "discipline":
        return f"""Supervisor Counseling Script — Progressive Coaching / Discipline Review

Opening Statement:
I want to review this concern with you in a factual and professional manner. The purpose of this conversation is to clarify expectations, review the available facts, and determine whether coaching, documentation, or further review is appropriate.

Policy / Agreement Reference:
The section currently flagged for review is "{section_title}" from "{document_title}." This section appears relevant because it addresses coaching, documentation, progressive review, or the steps that should be considered before formal action.

Facts to Confirm:
Before any decision is made, we need to confirm what occurred, when it occurred, who was involved, whether prior coaching exists, whether the issue is isolated or repeated, and whether the official policy or agreement requires specific steps before escalation.

Expectation:
The expectation is that performance, conduct, safety, and operational concerns are addressed through a fair, documented, and consistent review process.

Operational Impact:
Unresolved concerns can affect safety, route reliability, team accountability, compliance readiness, and leadership confidence in the operation.

Employee Response Prompt:
I want to give you the opportunity to respond and provide any context or documentation that should be considered before next steps are determined.

Corrective Expectation:
Going forward, you are expected to correct the concern, follow the applicable work rule or policy expectation, and understand that repeated or unresolved concerns may require additional review.

Documentation Language:
This should be documented as a coaching and fact-review conversation unless HR, labor relations, compliance, legal, or leadership confirms that formal discipline is appropriate.

Recommended Next Step:
Confirm the facts, review the official policy or agreement, check prior documentation, and determine whether the matter should remain coaching or move to formal review.

HR / Labor / Compliance Note:
This is not a final disciplinary, contract, labor, or legal determination. Formal action should be reviewed before being finalized."""

    if situation == "safety":
        return f"""Supervisor Counseling Script — Safety Expectation Review

Opening Statement:
I want to review a safety-related concern with you. This conversation is focused on prevention, accountability, and making sure expectations are clear before the issue creates greater operational or compliance risk.

Policy / Agreement Reference:
The section currently flagged for review is "{section_title}" from "{document_title}." This section appears relevant because it may relate to safety expectations, vehicle readiness, inspection behavior, or driver responsibility.

Facts to Confirm:
We need to confirm what happened, when it happened, whether a vehicle, route, customer location, or inspection was involved, whether there were any safety events, and whether documentation or witness information exists.

Expectation:
The expectation is that drivers follow all safety procedures, report concerns immediately, complete required checks, and operate in a way that protects themselves, the public, customers, equipment, and the company.

Operational Impact:
Safety concerns can affect driver readiness, fleet reliability, customer delivery, DOT/FMCSA compliance posture, insurance exposure, and leadership confidence.

Employee Response Prompt:
Please explain what happened from your perspective and identify anything that may have contributed to the issue.

Corrective Expectation:
Going forward, the expectation is full compliance with safety procedures, timely communication of hazards or equipment concerns, and immediate correction of any unsafe behavior or missed process.

Documentation Language:
This should be documented as a safety expectation and prevention review. Any formal finding should be validated against safety records, policy, training records, and leadership/compliance review.

Recommended Next Step:
Confirm the facts, review safety documentation, determine whether retraining or inspection follow-up is needed, and document the supervisor discussion.

HR / Labor / Compliance Note:
This is not a final safety, HR, labor, legal, or compliance determination. Formal action should be reviewed before being finalized."""

    if situation == "route":
        return f"""Supervisor Counseling Script — Route Assignment / Operational Expectation Review

Opening Statement:
I want to review a route or assignment concern with you so we can confirm the facts, clarify expectations, and prevent operational disruption going forward.

Policy / Agreement Reference:
The section currently flagged for review is "{section_title}" from "{document_title}." This section appears relevant because it may relate to route assignment, dispatch expectations, scheduling, work rules, or operational coverage.

Facts to Confirm:
We need to confirm the assigned route, scheduled time, dispatch instruction, communication history, supervisor direction, and whether the issue affected customer delivery, route completion, or staffing.

Expectation:
The expectation is that route assignments and dispatch instructions are followed unless a supervisor approves a change or an operational exception is documented.

Operational Impact:
Route issues can affect customer service, service windows, staffing, overtime, delivery completion, supervisor planning, and team accountability.

Employee Response Prompt:
Please explain what happened and whether there was any confusion, delay, instruction issue, route condition, or communication problem that should be reviewed.

Corrective Expectation:
Going forward, route instructions, schedule expectations, and communication procedures must be followed. Any route concern should be escalated promptly to supervision.

Documentation Language:
This should be documented as a route assignment and expectation review. It should not be treated as a final agreement or policy violation without confirming the applicable work rule and operational facts.

Recommended Next Step:
Review dispatch records, route assignment details, supervisor notes, and applicable policy or agreement language before determining next steps.

HR / Labor / Compliance Note:
This is not a final HR, legal, labor, contract, or policy determination. Formal action should be reviewed before being finalized."""

    return f"""Supervisor Counseling Script — Operational Expectation Review

Opening Statement:
I want to review this concern with you in a factual and professional way. The goal is to clarify expectations, confirm the facts, and determine the appropriate next step without jumping to conclusions.

Policy / Agreement Reference:
The section currently flagged for review is "{section_title}" from "{document_title}." This section appears relevant for review, but it should not be treated as a final violation finding without human review.

Facts to Confirm:
We need to confirm what occurred, when it occurred, who was involved, whether documentation exists, whether prior coaching applies, and whether the official policy, agreement, work rule, or procedure is current.

Expectation:
The expectation is that all drivers and team members follow applicable policies, work rules, supervisor instructions, safety requirements, and operational procedures.

Operational Impact:
If not addressed, this type of issue may affect accountability, safety, route reliability, team fairness, documentation quality, compliance readiness, or leadership confidence.

Employee Response Prompt:
Before next steps are determined, I want to give you an opportunity to provide your perspective and any information that should be considered.

Corrective Expectation:
Going forward, the expectation is that the concern is corrected, the applicable policy or work rule is followed, and any future issue is communicated promptly through the proper channel.

Documentation Language:
This should be documented as a coaching and expectation-setting discussion unless HR, labor relations, compliance, legal, or leadership review confirms that formal action is appropriate.

Recommended Next Step:
Review the official document, confirm the facts, document the conversation, and determine whether coaching, monitoring, additional training, or formal review is appropriate.

HR / Labor / Compliance Note:
This is not a final HR, legal, labor, contract, or policy determination. Formal action should be reviewed before being finalized."""


def lori_policy_build_answer(
    question: str,
    situation_type: str,
    matches: List[Dict[str, Any]],
    review_request: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Enhanced policy/agreement answer.
    Overrides the earlier version to include stronger counseling language.
    """

    if not matches:
        return f"""Agreement / Policy Review

Situation Type:
{situation_type}

Status:
I do not see a matching agreement or policy section in the currently searchable LORI policy records.

Recommended Next Action:
Upload or confirm the relevant union agreement, company policy, work rule, SOP, or driver policy so LORI can compare the situation against the official language.

Supervisor Counseling Guidance:
Before counseling, the supervisor should confirm the facts, identify the correct document, review the current policy or agreement language, and avoid making a final violation statement until HR, labor relations, compliance, legal, or leadership review is complete.

Recommended Supervisor Language:
“I want to review this matter with you to clarify expectations and confirm the facts. This conversation is not a final policy, agreement, or disciplinary determination. We will review the applicable policy or agreement language before determining next steps.”

Compliance Note:
This is not a final HR, legal, labor, or contract determination. HR, labor relations, compliance, legal, or leadership review is recommended before formal action."""

    top_match = matches[0]
    top_section = top_match["section"]
    top_document = top_match["document"]

    section_label_parts = [
        lori_policy_clean_text(top_section.get("article_number")),
        lori_policy_clean_text(top_section.get("section_number")),
        lori_policy_clean_text(top_section.get("section_title")),
    ]
    section_label = " — ".join([part for part in section_label_parts if part])

    counseling_script = lori_policy_build_enhanced_counseling_script(
        situation_type=situation_type,
        question=question,
        section=top_section,
        document=top_document,
    )

    lines = []

    lines.append("Agreement / Policy Review")
    lines.append("")
    lines.append("Situation Type:")
    lines.append(situation_type)
    lines.append("")
    lines.append("Primary Document:")
    lines.append(lori_policy_clean_text(top_document.get("document_title")) or "Not listed")
    lines.append("")
    lines.append("Document Type:")
    lines.append(lori_policy_clean_text(top_document.get("document_type")) or "Not listed")
    lines.append("")
    lines.append("Potentially Relevant Section:")
    lines.append(section_label or "Section not listed")
    lines.append("")
    lines.append("Relevant Language:")
    lines.append(lori_policy_clean_text(top_section.get("section_text")))
    lines.append("")
    lines.append("Operational Concern:")
    lines.append(
        "The situation may require review against the identified agreement, policy, work rule, or procedure. "
        "The section appears relevant for operational review, but it should not be treated as a final violation finding."
    )
    lines.append("")
    lines.append("Facts to Confirm:")
    lines.append(
        "Confirm the date, time, driver or employee involved, supervisor, prior coaching history, documentation, "
        "applicable route or assignment details, whether the official agreement or company policy version is current, "
        "and whether HR, labor relations, compliance, legal, or leadership review is required before formal action."
    )
    lines.append("")
    lines.append(counseling_script)
    lines.append("")
    lines.append("Recommended Next Action:")
    lines.append(
        "Use the counseling script as a supervisor-ready starting point, verify the official document language, confirm the facts, "
        "document the conversation, and route the matter to HR, labor relations, compliance, legal, or leadership review before any formal action."
    )

    if len(matches) > 1:
        lines.append("")
        lines.append("Additional Sections to Review:")
        for index, match in enumerate(matches[1:4], start=2):
            section = match["section"]
            document = match["document"]
            label_parts = [
                lori_policy_clean_text(document.get("document_title")),
                lori_policy_clean_text(section.get("article_number")),
                lori_policy_clean_text(section.get("section_number")),
                lori_policy_clean_text(section.get("section_title")),
            ]
            label = " — ".join([part for part in label_parts if part])
            lines.append(f"{index}. {label}")

    lines.append("")
    lines.append("HR / Labor / Compliance Note:")
    lines.append(
        "This is not a final HR, legal, labor, or contract determination. HR, labor relations, compliance, legal, or leadership review is recommended before formal action."
    )

    return "\n".join(lines)
# ============================================================
# LORI DRIVE COMMAND CENTER
# Compliance & Policy Center Upload / Intake Endpoint
# Stores uploaded agreement, policy, SOP, and work-rule documents
# in Supabase Storage and creates document metadata records.
# ============================================================

from fastapi import UploadFile, File, Form
import uuid
import mimetypes


POLICY_UPLOAD_BUCKET = "policy-agreement-uploads"


def lori_policy_safe_filename(filename: str) -> str:
    filename = filename or "uploaded-policy-document"
    filename = filename.strip().replace("\\", "/").split("/")[-1]
    filename = re.sub(r"[^a-zA-Z0-9._-]+", "_", filename)
    filename = filename.strip("_")
    return filename or "uploaded-policy-document"


def lori_policy_safe_document_type(document_type: Optional[str]) -> str:
    allowed_types = {
        "Union Agreement / CBA",
        "Company Policy",
        "Driver Work Rules",
        "SOP / Procedure",
        "Safety Policy",
        "Attendance Policy",
        "Discipline / Progressive Coaching Policy",
        "Route Assignment Rules",
        "Overtime / Scheduling Rules",
        "Other Policy / Agreement",
    }

    if document_type in allowed_types:
        return document_type

    return "Other Policy / Agreement"


def lori_policy_storage_headers(content_type: Optional[str] = None) -> Dict[str, str]:
    base_headers = lori_regulatory_supabase_headers()

    headers = {
        "apikey": base_headers.get("apikey", ""),
        "Authorization": base_headers.get("Authorization", ""),
        "x-upsert": "true",
    }

    if content_type:
        headers["Content-Type"] = content_type

    return headers


async def lori_policy_upload_to_storage(
    file_bytes: bytes,
    file_path: str,
    content_type: str,
) -> Dict[str, Any]:
    upload_url = f"{SUPABASE_URL}/storage/v1/object/{POLICY_UPLOAD_BUCKET}/{file_path}"

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            upload_url,
            headers=lori_policy_storage_headers(content_type),
            content=file_bytes,
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=500,
            detail=f"Supabase Storage upload failed: {response.text}",
        )

    return {
        "storage_status": "uploaded",
        "storage_path": file_path,
        "storage_response": response.text,
    }


@app.post("/policy-document-intake")
async def policy_document_intake(
    api_key: Optional[str] = Form(None),

    document_title: str = Form(...),
    document_type: str = Form("Company Policy"),
    company_name: str = Form("Demonstration Company"),
    operating_state: str = Form("MD"),
    station_code: str = Form("JESSUP-01"),

    document_version: Optional[str] = Form(None),
    effective_date: Optional[str] = Form(None),
    expiration_date: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),

    file: Optional[UploadFile] = File(None),
):
    """
    Upload/intake endpoint for Compliance & Policy Center.

    This creates a searchable document metadata record now.
    Full PDF/text extraction and section parsing will be connected later.
    """

    lori_regulatory_require_key(api_key)

    cleaned_document_title = lori_policy_clean_text(document_title)
    cleaned_document_type = lori_policy_safe_document_type(document_type)
    cleaned_company_name = lori_policy_clean_text(company_name) or "Demonstration Company"
    cleaned_operating_state = lori_policy_clean_text(operating_state).upper() or "MD"
    cleaned_station_code = lori_policy_clean_text(station_code).upper() or "JESSUP-01"

    source_file_name = None
    source_file_path = None
    source_file_url = None
    upload_status = "Metadata Created / Pending File Upload"

    if file is not None:
        original_filename = lori_policy_safe_filename(file.filename or "policy-document")
        file_bytes = await file.read()

        if file_bytes:
            guessed_type = file.content_type or mimetypes.guess_type(original_filename)[0] or "application/octet-stream"

            unique_id = str(uuid.uuid4())
            source_file_path = (
                f"{cleaned_station_code}/"
                f"{cleaned_document_type.replace(' ', '_').replace('/', '_')}/"
                f"{unique_id}_{original_filename}"
            )

            await lori_policy_upload_to_storage(
                file_bytes=file_bytes,
                file_path=source_file_path,
                content_type=guessed_type,
            )

            source_file_name = original_filename
            source_file_url = f"{POLICY_UPLOAD_BUCKET}/{source_file_path}"
            upload_status = "Uploaded / Pending Extraction"

    summary = (
        f"{cleaned_document_type} uploaded or registered for LORI Compliance & Policy Center review. "
        f"Document is staged for section extraction, topic tagging, policy search, agreement review, "
        f"and supervisor-ready counseling intelligence."
    )

    payload = {
        "document_title": cleaned_document_title,
        "document_type": cleaned_document_type,
        "company_name": cleaned_company_name,
        "operating_state": cleaned_operating_state,
        "station_code": cleaned_station_code,
        "document_status": upload_status,
        "document_version": document_version,
        "effective_date": effective_date or None,
        "expiration_date": expiration_date or None,
        "source_file_name": source_file_name,
        "source_file_path": source_file_path,
        "source_file_url": source_file_url,
        "summary": summary,
        "notes": notes or "Uploaded through LORI Compliance & Policy Center. Extraction pending.",
        "created_by": "LORI Compliance Policy Center",
    }

    created = await lori_policy_supabase_post(
        "lori_policy_documents",
        payload,
    )

    document_record = created[0] if created else None

    return {
        "status": "success",
        "message": "Policy/agreement document intake completed.",
        "document_status": upload_status,
        "document": document_record,
        "storage_bucket": POLICY_UPLOAD_BUCKET,
        "source_file_name": source_file_name,
        "source_file_path": source_file_path,
        "next_step": (
            "Document metadata is saved. Full text extraction, clause parsing, section tagging, "
            "and searchable policy intelligence can now be connected as the next backend upgrade."
        ),
        "disclaimer": (
            "LORI provides operational decision support. Uploaded agreements, policies, SOPs, and work rules "
            "must be reviewed by authorized HR, labor relations, compliance, legal, or leadership personnel "
            "before formal action."
        ),
    }


@app.get("/policy-intake-status")
async def policy_intake_status(
    api_key: Optional[str] = Query(None),
    limit: int = Query(10),
):
    lori_regulatory_require_key(api_key)

    limit = max(1, min(limit, 50))

    documents = await lori_policy_supabase_get(
        f"lori_policy_documents?select=*&order=created_at.desc&limit={limit}"
    )

    pending_extraction = [
        doc for doc in documents
        if "Pending Extraction" in str(doc.get("document_status") or "")
        or "Pending File Upload" in str(doc.get("document_status") or "")
    ]

    return {
        "status": "success",
        "documents_count": len(documents),
        "pending_extraction_count": len(pending_extraction),
        "documents": documents,
        "message": (
            "Compliance & Policy Center document intake is active. "
            "Documents can be uploaded or registered and staged for extraction."
        ),
    }
# ============================================================
# LORI DRIVE COMMAND CENTER
# Policy / Agreement Document Extraction Endpoint
# Extracts uploaded PDF/TXT policy documents from Supabase Storage,
# splits them into searchable sections, tags topics, and updates
# the document status to Extracted / Searchable.
# ============================================================

from io import BytesIO


async def lori_policy_download_from_storage(file_path: str) -> bytes:
    download_url = f"{SUPABASE_URL}/storage/v1/object/{POLICY_UPLOAD_BUCKET}/{file_path}"

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(
            download_url,
            headers=lori_policy_storage_headers(),
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=500,
            detail=f"Supabase Storage download failed: {response.text}",
        )

    return response.content


async def lori_policy_supabase_patch(
    table: str,
    record_id: str,
    payload: Dict[str, Any],
) -> Any:
    url = f"{SUPABASE_URL}/rest/v1/{table}?id=eq.{record_id}"

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.patch(
            url,
            headers=lori_regulatory_supabase_headers("return=representation"),
            json=payload,
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=500,
            detail=f"Supabase PATCH failed: {response.text}",
        )

    return response.json()


async def lori_policy_supabase_delete_sections(document_id: str) -> None:
    url = f"{SUPABASE_URL}/rest/v1/lori_policy_sections?document_id=eq.{document_id}"

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.delete(
            url,
            headers=lori_regulatory_supabase_headers(),
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=500,
            detail=f"Supabase DELETE failed: {response.text}",
        )


async def lori_policy_supabase_post_many(
    table: str,
    payload: List[Dict[str, Any]],
) -> Any:
    if not payload:
        return []

    url = f"{SUPABASE_URL}/rest/v1/{table}"

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            url,
            headers=lori_regulatory_supabase_headers("return=representation"),
            json=payload,
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=500,
            detail=f"Supabase batch POST failed: {response.text}",
        )

    return response.json()


def lori_policy_extract_text_from_file(
    file_bytes: bytes,
    file_name: Optional[str],
) -> str:
    safe_name = (file_name or "").lower()

    if safe_name.endswith(".txt"):
        return file_bytes.decode("utf-8", errors="ignore")

    if safe_name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=(
                    "PDF extraction requires the pypdf package. "
                    "Add pypdf to requirements.txt and redeploy Render."
                ),
            ) from exc

        reader = PdfReader(BytesIO(file_bytes))
        pages = []

        for page_index, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception:
                page_text = ""

            if page_text.strip():
                pages.append(f"\n\n--- Page {page_index} ---\n{page_text}")

        return "\n".join(pages).strip()

    try:
        return file_bytes.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def lori_policy_extract_topic_tags(text: str) -> List[str]:
    blob = lori_policy_clean_text(text).lower()
    tags = []

    for topic, keywords in POLICY_REVIEW_KEYWORDS.items():
        if any(keyword in blob for keyword in keywords):
            tags.append(topic)

    if "call-out" in blob or "call out" in blob or "callout" in blob:
        if "call-out" not in tags:
            tags.append("call-out")

    if "driver" in blob:
        if "driver operations" not in tags:
            tags.append("driver operations")

    if not tags:
        tags.append("general policy")

    return tags


def lori_policy_extract_risk_tags(text: str) -> List[str]:
    blob = lori_policy_clean_text(text).lower()
    risk_tags = []

    if any(term in blob for term in ["attendance", "call-out", "call out", "absence", "late", "no call", "no show"]):
        risk_tags.append("attendance risk")

    if any(term in blob for term in ["discipline", "corrective", "coaching", "counseling", "warning"]):
        risk_tags.append("coaching / discipline review")

    if any(term in blob for term in ["safety", "incident", "accident", "inspection", "vehicle"]):
        risk_tags.append("safety review")

    if any(term in blob for term in ["union", "agreement", "contract", "cba", "grievance", "labor"]):
        risk_tags.append("HR / labor review recommended")

    if any(term in blob for term in ["documentation", "document", "record"]):
        risk_tags.append("documentation needed")

    if not risk_tags:
        risk_tags.append("review needed")

    return risk_tags


def lori_policy_parse_section_heading(heading: str) -> Dict[str, Any]:
    clean_heading = lori_policy_clean_text(heading)

    article_number = None
    section_number = None
    section_title = clean_heading

    section_match = re.search(
        r"(section|sec\.?)\s+([0-9]+(?:\.[0-9]+)*)\s*[—\-:]\s*(.+)",
        clean_heading,
        flags=re.IGNORECASE,
    )

    if section_match:
        section_number = section_match.group(2).strip()
        section_title = section_match.group(3).strip()
        return {
            "article_number": None,
            "section_number": section_number,
            "section_title": section_title,
        }

    article_match = re.search(
        r"(article)\s+([0-9ivxlcdm]+)\s*[—\-:]\s*(.+)",
        clean_heading,
        flags=re.IGNORECASE,
    )

    if article_match:
        article_number = f"Article {article_match.group(2).strip()}"
        section_title = article_match.group(3).strip()
        return {
            "article_number": article_number,
            "section_number": None,
            "section_title": section_title,
        }

    policy_match = re.search(
        r"(policy area)\s+([0-9]+)\s*[—\-:]\s*(.+)",
        clean_heading,
        flags=re.IGNORECASE,
    )

    if policy_match:
        article_number = f"Policy Area {policy_match.group(2).strip()}"
        section_title = policy_match.group(3).strip()
        return {
            "article_number": article_number,
            "section_number": None,
            "section_title": section_title,
        }

    return {
        "article_number": article_number,
        "section_number": section_number,
        "section_title": section_title,
    }


def lori_policy_split_text_into_sections(text: str) -> List[Dict[str, Any]]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()

    if not normalized:
        return []

    heading_pattern = re.compile(
        r"(?im)^(section\s+[0-9]+(?:\.[0-9]+)*\s*[—\-:]\s*.+|article\s+[0-9ivxlcdm]+\s*[—\-:]\s*.+|policy area\s+[0-9]+\s*[—\-:]\s*.+)$"
    )

    matches = list(heading_pattern.finditer(normalized))
    sections: List[Dict[str, Any]] = []

    if matches:
        for index, match in enumerate(matches):
            heading = match.group(1).strip()
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
            section_body = normalized[start:end].strip()

            parsed = lori_policy_parse_section_heading(heading)

            full_text = f"{heading}\n{section_body}".strip()

            if len(full_text) < 30:
                continue

            sections.append(
                {
                    "article_number": parsed.get("article_number"),
                    "section_number": parsed.get("section_number"),
                    "section_title": parsed.get("section_title"),
                    "section_text": full_text,
                    "page_number": None,
                    "topic_tags": lori_policy_extract_topic_tags(full_text),
                    "risk_tags": lori_policy_extract_risk_tags(full_text),
                    "applies_to": ["drivers", "supervisors", "operations leadership"],
                }
            )

    if not sections:
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", normalized) if p.strip()]
        current_chunk = []
        current_length = 0
        chunk_number = 1

        for paragraph in paragraphs:
            current_chunk.append(paragraph)
            current_length += len(paragraph)

            if current_length >= 1200:
                chunk_text = "\n\n".join(current_chunk).strip()
                sections.append(
                    {
                        "article_number": "Extracted Text",
                        "section_number": str(chunk_number),
                        "section_title": f"Extracted Policy Section {chunk_number}",
                        "section_text": chunk_text,
                        "page_number": None,
                        "topic_tags": lori_policy_extract_topic_tags(chunk_text),
                        "risk_tags": lori_policy_extract_risk_tags(chunk_text),
                        "applies_to": ["drivers", "supervisors", "operations leadership"],
                    }
                )
                chunk_number += 1
                current_chunk = []
                current_length = 0

        if current_chunk:
            chunk_text = "\n\n".join(current_chunk).strip()
            sections.append(
                {
                    "article_number": "Extracted Text",
                    "section_number": str(chunk_number),
                    "section_title": f"Extracted Policy Section {chunk_number}",
                    "section_text": chunk_text,
                    "page_number": None,
                    "topic_tags": lori_policy_extract_topic_tags(chunk_text),
                    "risk_tags": lori_policy_extract_risk_tags(chunk_text),
                    "applies_to": ["drivers", "supervisors", "operations leadership"],
                }
            )

    return sections[:100]


async def lori_policy_get_document_for_extraction(
    document_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if document_id:
        records = await lori_policy_supabase_get(
            f"lori_policy_documents?select=*&id=eq.{document_id}&limit=1"
        )
        return records[0] if records else None

    documents = await lori_policy_supabase_get(
        "lori_policy_documents?select=*&order=created_at.desc&limit=50"
    )

    for document in documents:
        status = str(document.get("document_status") or "")
        file_path = document.get("source_file_path")

        if file_path and "Pending Extraction" in status:
            return document

    return None


@app.post("/policy-document-extract")
async def policy_document_extract(
    api_key: Optional[str] = Query(None),
    document_id: Optional[str] = Query(None),
):
    lori_regulatory_require_key(api_key)

    document = await lori_policy_get_document_for_extraction(document_id)

    if not document:
        return {
            "status": "not_found",
            "message": "No uploaded policy/agreement document is currently pending extraction.",
            "sections_created": 0,
            "answer_text": (
                "No uploaded policy or agreement document is currently pending extraction. "
                "Upload a document first or provide a valid document_id."
            ),
        }

    doc_id = document.get("id")
    file_path = document.get("source_file_path")
    file_name = document.get("source_file_name") or document.get("document_title")

    if not file_path:
        return {
            "status": "missing_file",
            "message": "The selected policy/agreement document does not have a stored file path.",
            "document": document,
            "sections_created": 0,
        }

    file_bytes = await lori_policy_download_from_storage(file_path)

    extracted_text = lori_policy_extract_text_from_file(
        file_bytes=file_bytes,
        file_name=file_name,
    )

    if not extracted_text.strip():
        await lori_policy_supabase_patch(
            "lori_policy_documents",
            doc_id,
            {
                "document_status": "Extraction Failed / No Text Found",
                "notes": "LORI attempted extraction, but no readable text was found. This may be a scanned PDF requiring OCR.",
            },
        )

        return {
            "status": "no_text_found",
            "message": "No readable text was found in the uploaded document.",
            "document_id": doc_id,
            "sections_created": 0,
            "answer_text": (
                "LORI could not extract readable text from this document. "
                "If this is a scanned PDF, OCR will be needed in a later upgrade."
            ),
        }

    sections = lori_policy_split_text_into_sections(extracted_text)

    if not sections:
        return {
            "status": "no_sections_created",
            "message": "Text was extracted, but no sections were created.",
            "document_id": doc_id,
            "extracted_character_count": len(extracted_text),
            "sections_created": 0,
        }

    await lori_policy_supabase_delete_sections(doc_id)

    insert_payload = []

    for section in sections:
        insert_payload.append(
            {
                "document_id": doc_id,
                "article_number": section.get("article_number"),
                "section_number": section.get("section_number"),
                "section_title": section.get("section_title"),
                "page_number": section.get("page_number"),
                "section_text": section.get("section_text"),
                "topic_tags": section.get("topic_tags"),
                "risk_tags": section.get("risk_tags"),
                "applies_to": section.get("applies_to"),
            }
        )

    created_sections = await lori_policy_supabase_post_many(
        "lori_policy_sections",
        insert_payload,
    )

    await lori_policy_supabase_patch(
        "lori_policy_documents",
        doc_id,
        {
            "document_status": "Extracted / Searchable",
            "summary": (
                f"{document.get('document_type') or 'Policy / Agreement'} extracted by LORI. "
                f"{len(created_sections)} searchable section(s) created for policy search, agreement review, "
                f"supervisor-ready counseling language, HR/labor/compliance review, and operational decision support."
            ),
            "notes": (
                f"Extraction complete. LORI created {len(created_sections)} searchable section(s). "
                "Human review is still required before formal HR, labor, legal, compliance, or leadership action."
            ),
        },
    )

    answer_text = f"""Policy / Agreement Extraction Complete

Document:
{document.get("document_title")}

Status:
Extracted / Searchable

Sections Created:
{len(created_sections)}

What LORI Can Do Now:
- Search this uploaded document
- Identify potentially relevant sections
- Support agreement or policy review
- Generate supervisor-ready counseling language
- Stage HR, labor, compliance, legal, or leadership review notes

Important Note:
This extraction supports operational decision-making. The official document and extracted sections should be verified by authorized HR, labor relations, compliance, legal, or leadership personnel before formal action."""

    return {
        "status": "success",
        "message": "Policy/agreement document extraction completed.",
        "document_id": doc_id,
        "document_title": document.get("document_title"),
        "source_file_name": file_name,
        "extracted_character_count": len(extracted_text),
        "sections_created": len(created_sections),
        "sections": created_sections,
        "answer_text": answer_text,
    }


@app.get("/policy-extraction-status")
async def policy_extraction_status(
    api_key: Optional[str] = Query(None),
    limit: int = Query(20),
):
    lori_regulatory_require_key(api_key)

    limit = max(1, min(limit, 100))

    documents = await lori_policy_supabase_get(
        f"lori_policy_documents?select=*&order=created_at.desc&limit={limit}"
    )

    extracted_count = len([
        doc for doc in documents
        if "Extracted / Searchable" in str(doc.get("document_status") or "")
    ])

    pending_count = len([
        doc for doc in documents
        if "Pending Extraction" in str(doc.get("document_status") or "")
    ])

    failed_count = len([
        doc for doc in documents
        if "Extraction Failed" in str(doc.get("document_status") or "")
    ])

    return {
        "status": "success",
        "documents_count": len(documents),
        "extracted_count": extracted_count,
        "pending_extraction_count": pending_count,
        "failed_extraction_count": failed_count,
        "documents": documents,
    }
