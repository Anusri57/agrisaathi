"""
schemas.py — AgriSaathi Edge AI
All Pydantic request / response models used across the API.
"""

from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


# ── Sensor Telemetry ───────────────────────────────────────────────────────────

class SensorPayload(BaseModel):
    """JSON body posted by an ESP32 device to /api/update-sensors."""
    soil_moisture: Optional[float] = Field(None, ge=0, le=100, description="Volumetric soil moisture (%)")
    temperature: Optional[float] = Field(None, description="Ambient temperature (°C)")
    humidity: Optional[float] = Field(None, ge=0, le=100, description="Relative humidity (%)")
    soil_ph: Optional[float] = Field(None, ge=0, le=14, description="Soil pH")
    soil_ec: Optional[float] = Field(None, ge=0, description="Soil electrical conductivity (dS/m)")
    N: Optional[float] = Field(None, ge=0, description="Nitrogen (ppm)")
    P: Optional[float] = Field(None, ge=0, description="Phosphorus (ppm)")
    K: Optional[float] = Field(None, ge=0, description="Potassium (ppm)")
    pump_status: Optional[Literal["ON", "OFF"]] = None
    pest_alert: Optional[bool] = None
    fungal_risk: Optional[bool] = None
    sunlight: Optional[str] = None
    rainfall: Optional[float] = Field(None, ge=0, description="Rainfall (mm)")


class SensorUpdateResponse(BaseModel):
    """Acknowledgement returned to the ESP32 after a successful push."""
    status: Literal["ok"] = "ok"
    vpd: float = Field(..., description="Freshly calculated VPD (kPa)")


class SensorDataResponse(BaseModel):
    """Full sensor state returned to the frontend dashboard."""
    soil_moisture: float
    temperature: float
    humidity: float
    vpd: float
    ph: float
    ec: float
    N: float
    P: float
    K: float
    pump_status: str
    pest_alert: bool
    fungal_risk: bool = False
    sunlight: str
    rainfall: float
    status: str = "success"


# ── Multimodal AI Leaf Diagnosis ───────────────────────────────────────────────

class DiagnosisResponse(BaseModel):
    """
    Structured response from the multimodal foliar disease analysis.
    The Gemini model is prompted to return data matching this exact schema.
    """
    title: str = Field(..., description="Short disease / condition name")
    status_type: Literal["OVERRIDE_WATER", "OVERRIDE_NUTRIENT", "CONFIRMED_PATHOGEN"] = Field(
        ..., description="Decision class: abiotic override or confirmed pathogen"
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Model confidence (0–1)")
    cross_check: str = Field(..., description="Explanation of visual findings vs soil sensor readings")
    prescription: str = Field(..., description="English treatment prescription")
    prescription_telugu: str = Field(..., description="Telugu localised treatment prescription")


class DiagnosisErrorResponse(BaseModel):
    """Returned when the AI call fails or the image cannot be processed."""
    error: str
    detail: Optional[str] = None


# ── Conversational Chatbot ─────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    """Message sent from the frontend chatbot panel."""
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(
        default="default",
        description="Client-generated session identifier for multi-turn history",
    )


class ChatResponse(BaseModel):
    """Reply from the agronomist AI chatbot."""
    reply: str
    session_id: str


# ── Internal helpers ───────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    """Single turn stored in the in-memory chat history."""
    role: Literal["user", "model", "assistant"]
    text: str
