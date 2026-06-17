# LORI Drive Render Backend

This is the backend API for LORI Drive, the Delivery Operations Command Center.

## What this backend does

It connects Voiceflow to Supabase.

Voiceflow will call this Render backend. Render will safely query Supabase views, then return clean results back to Voiceflow.

## Main endpoints

- `/health`
- `/batch-summary?batch_code=JESSUP-DEMO-001&api_key=YOUR_LORI_API_KEY`
- `/worst-drivers?batch_code=JESSUP-DEMO-001&limit=10&api_key=YOUR_LORI_API_KEY`
- `/best-drivers?batch_code=JESSUP-DEMO-001&limit=10&api_key=YOUR_LORI_API_KEY`
- `/risk-summary?batch_code=JESSUP-DEMO-001&api_key=YOUR_LORI_API_KEY`
- `/supervisor-actions?batch_code=JESSUP-DEMO-001&api_key=YOUR_LORI_API_KEY`
- `/driver-360?employee_id=DEMO-D007&batch_code=JESSUP-DEMO-001&api_key=YOUR_LORI_API_KEY`
- `/leadership-briefing?batch_code=JESSUP-DEMO-001&api_key=YOUR_LORI_API_KEY`
- `/voiceflow/summary?batch_code=JESSUP-DEMO-001&api_key=YOUR_LORI_API_KEY`

## Render settings

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

## Required Render environment variables

```text
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
LORI_API_KEY=
```

`SUPABASE_SERVICE_ROLE_KEY` should be your Supabase Secret key. Do not put this key into Voiceflow.
