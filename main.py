"""
main.py — AgriSaathi Edge AI
FastAPI application entry-point.

Sensor API      : POST /api/update-sensors  (WiFi push from ESP32)
                  GET  /api/sensor-data     (frontend polling)
AI Diagnostics  : POST /api/diagnose-leaf  (Groq Vision multimodal fusion)
Chatbot         : POST /api/chat           (Groq text, per-session history)
Dashboard       : GET  /                   (Jinja2 → templates/dashboard.html)
"""

from __future__ import annotations

import base64
import json
import math
import re
import threading
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

import uvicorn
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from groq import Groq

from config import get_settings
from schemas import (
    ChatMessage,
    ChatRequest,
    ChatResponse,
    DiagnosisErrorResponse,
    DiagnosisResponse,
    SensorDataResponse,
    SensorPayload,
    SensorUpdateResponse,
)

# ── Bootstrap ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
settings  = get_settings()

app = FastAPI(
    title=settings.app_title,
    description="Precision agriculture real-time hybrid AI platform",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


# ── Groq client (lazy) ─────────────────────────────────────────────────────────
_groq_client: Groq | None = None

def get_groq_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        if not settings.groq_api_key:
            raise HTTPException(
                status_code=503,
                detail="GROQ_API_KEY is not configured. Add it to your .env file.",
            )
        _groq_client = Groq(api_key=settings.groq_api_key)
    return _groq_client


# ── In-memory sensor state ─────────────────────────────────────────────────────
latest_data: Dict = {
    "soil_moisture": 0,
    "soil_moisture_pct": 0,
    "moisture": 0,
    "soil_temperature": 28.5,
    "temperature": 28.5,
    "temp": 28.5,
    "humidity": 60.0,
    "vpd": 0.85,
    "soil_ph": 6.1,
    "ph": 6.1,
    "soil_ec": 0.4,
    "ec": 0.4,
    "N": 40,
    "P": 10,
    "K": 60,
    "nitrogen": 40,
    "phosphorus": 10,
    "potassium": 60,
    "pump_status": "OFF",
    "pump": "OFF",
    "pest_alert": False,
    "fungal_risk": False,
    "sunlight": "DAYLIGHT",
    "rainfall": 0.0,
    "status": "success",
    "message": "Waiting for ESP32…",
}

# ── Per-session chat history ───────────────────────────────────────────────────
chat_histories: Dict[str, List[ChatMessage]] = defaultdict(list)
_history_lock = threading.Lock()


# ── Helpers ────────────────────────────────────────────────────────────────────
def calculate_vpd(temperature: float, humidity: float) -> float:
    vp_sat = 0.61078 * math.exp((17.27 * temperature) / (temperature + 237.3))
    vp_act = vp_sat * (humidity / 100.0)
    return round(vp_sat - vp_act, 2)


def _apply_sensor_dict(d: dict) -> None:
    for k, v in d.items():
        latest_data[k] = v

    t = d.get("temperature",   latest_data["temperature"])
    h = d.get("humidity",      latest_data["humidity"])
    m = d.get("soil_moisture", latest_data["soil_moisture"])

    latest_data["moisture"]          = m
    latest_data["soil_moisture_pct"] = m
    latest_data["temp"]              = t
    latest_data["soil_temperature"]  = t
    latest_data["ph"]   = d.get("soil_ph",     latest_data.get("ph",  latest_data["soil_ph"]))
    latest_data["ec"]   = d.get("soil_ec",     latest_data.get("ec",  latest_data["soil_ec"]))
    latest_data["pump"] = d.get("pump_status", latest_data["pump_status"])
    latest_data["vpd"]  = calculate_vpd(t, h)

    latest_data["nitrogen"]   = latest_data.get("N", latest_data["nitrogen"])
    latest_data["phosphorus"] = latest_data.get("P", latest_data["phosphorus"])
    latest_data["potassium"]  = latest_data.get("K", latest_data["potassium"])
    latest_data["message"]    = "Live"


def _parse_json_response(raw: str) -> dict:
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model response")
    return json.loads(match.group())


# ── Routes — Dashboard ─────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def serve_dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "field_name": settings.field_name},
    )


# ── Routes — Sensor Telemetry ──────────────────────────────────────────────────
@app.post("/api/update-sensors", response_model=SensorUpdateResponse)
async def update_sensors(payload: SensorPayload) -> SensorUpdateResponse:
    """ESP32 WiFi push endpoint — merges payload into live state store."""
    _apply_sensor_dict(payload.model_dump(exclude_none=True))
    return SensorUpdateResponse(vpd=latest_data["vpd"])


@app.get("/api/sensor-data", response_model=SensorDataResponse)
async def get_sensor_data() -> SensorDataResponse:
    """Frontend polling endpoint — returns full current sensor state."""
    return SensorDataResponse(
        soil_moisture=latest_data["soil_moisture"],
        temperature=latest_data["temperature"],
        humidity=latest_data["humidity"],
        vpd=latest_data["vpd"],
        ph=latest_data["ph"],
        ec=latest_data["ec"],
        N=latest_data["N"],
        P=latest_data["P"],
        K=latest_data["K"],
        pump_status=latest_data["pump_status"],
        pest_alert=bool(latest_data["pest_alert"]),
        fungal_risk=bool(latest_data.get("fungal_risk", False)),
        sunlight=latest_data["sunlight"],
        rainfall=float(latest_data.get("rainfall", 0.0)),
    )


# ── Routes — Multimodal AI Leaf Diagnosis ─────────────────────────────────────
def _build_diagnosis_prompt() -> str:
    d = latest_data
    return f"""You are AgriSaathi, an expert agronomist AI.

LIVE GROUND SENSOR READINGS:
- Soil Moisture : {d['soil_moisture']}%
- Temperature   : {d['temperature']}°C
- Humidity      : {d['humidity']}%
- VPD           : {d['vpd']} kPa
- Nitrogen (N)  : {d['N']} ppm
- Phosphorus (P): {d['P']} ppm
- Potassium (K) : {d['K']} ppm
- Soil pH       : {d['ph']}
- Soil EC       : {d['ec']} dS/m

CROSS-CHECK FUSION RULES:
1. If leaf shows yellowing AND soil_moisture < 25 → status_type = "OVERRIDE_WATER"
2. If leaf shows yellowing AND N < 50 ppm → status_type = "OVERRIDE_NUTRIENT"
3. Otherwise identify the disease → status_type = "CONFIRMED_PATHOGEN"

Analyse the leaf image. Return ONLY valid JSON, no markdown:

{{
  "title": "<disease or condition name>",
  "status_type": "<OVERRIDE_WATER | OVERRIDE_NUTRIENT | CONFIRMED_PATHOGEN>",
  "confidence": <float 0.0-1.0>,
  "cross_check": "<visual findings vs sensor data>",
  "prescription": "<English treatment>",
  "prescription_telugu": "<Telugu treatment>"
}}"""


@app.post(
    "/api/diagnose-leaf",
    response_model=DiagnosisResponse,
    responses={422: {"model": DiagnosisErrorResponse}, 503: {"model": DiagnosisErrorResponse}},
)
async def diagnose_leaf(file: UploadFile = File(...)) -> DiagnosisResponse:
    """Multimodal AI foliar disease analysis using Groq Vision."""
    client = get_groq_client()

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")

    # Encode image as base64 for Groq vision API
    mime_type    = file.content_type or "image/jpeg"
    b64_image    = base64.b64encode(image_bytes).decode("utf-8")
    image_url    = f"data:{mime_type};base64,{b64_image}"

    try:
        response = client.chat.completions.create(
            model=settings.groq_vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_url}},
                        {"type": "text",      "text": _build_diagnosis_prompt()},
                    ],
                }
            ],
            max_tokens=1024,
            temperature=0.3,
        )
        raw_text = response.choices[0].message.content.strip()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Groq Vision API error: {exc}")

    try:
        return DiagnosisResponse(**_parse_json_response(raw_text))
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Failed to parse model response: {exc}. Raw: {raw_text[:500]}",
        )


# ── Routes — Conversational AI Chatbot ────────────────────────────────────────
def _build_system_prompt() -> str:
    d = latest_data
    return f"""You are AgriSaathi, a friendly and expert AI agronomist assistant for Indian farmers.
You are embedded in a precision agriculture dashboard for {settings.field_name}.

CURRENT FIELD SENSOR READINGS:
- Soil Moisture : {d['soil_moisture']}%
- Temperature   : {d['temperature']}°C  |  Humidity: {d['humidity']}%
- VPD           : {d['vpd']} kPa
- Nitrogen (N)  : {d['N']} ppm  |  Phosphorus (P): {d['P']} ppm  |  Potassium (K): {d['K']} ppm
- Soil pH       : {d['ph']}  |  Soil EC: {d['ec']} dS/m
- Pump Status   : {d['pump_status']}  |  Pest Alert: {d['pest_alert']}

RULES:
- Be concise, practical, farmer-friendly.
- Reference live sensor data when relevant.
- Respond in the same language the farmer uses (English or Telugu).
- For disease/pest concerns recommend the AI Leaf Scanner.
- Do NOT recommend unverified chemicals."""


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Agronomist AI chatbot with per-session multi-turn history via Groq."""
    client     = get_groq_client()
    session_id = request.session_id

    with _history_lock:
        history = chat_histories[session_id]
        history.append(ChatMessage(role="user", text=request.message))
        if len(history) > settings.chat_history_max:
            chat_histories[session_id] = history[-settings.chat_history_max:]
            history = chat_histories[session_id]

    # Build Groq messages list — Groq uses "assistant" not "model"
    messages = [{"role": "system", "content": _build_system_prompt()}]
    for msg in history:
        role = "assistant" if msg.role == "model" else "user"
        messages.append({"role": role, "content": msg.text})

    try:
        response = client.chat.completions.create(
            model=settings.groq_text_model,
            messages=messages,
            max_tokens=1024,
            temperature=0.7,
        )
        reply_text = response.choices[0].message.content.strip()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Groq API error: {exc}")

    with _history_lock:
        chat_histories[session_id].append(ChatMessage(role="assistant", text=reply_text))

    return ChatResponse(reply=reply_text, session_id=session_id)


# ── Catch-all for legacy mobile APK routes ────────────────────────────────────
@app.api_route(
    "/{full_path:path}",
    methods=["GET", "POST", "PUT", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def catch_all(request: Request, full_path: str):
    return dict(latest_data)


# ── Entry-point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )
