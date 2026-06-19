import os
import re
import uuid
import csv
import io
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
        "birthday_month": driver.birthday_month,
        "birthday_day": driver.birthday_day,
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
