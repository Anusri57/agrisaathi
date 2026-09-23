# AgriSaathi Edge AI — Feature Specification

**Version:** 1.0  
**Date:** September 2026  
**Project:** Precision Agriculture Platform — Real-Time Hybrid AI System  

---

## 1. Overview

AgriSaathi Edge AI converts a hardcoded monolithic dashboard into a dynamic, API-driven, real-time hybrid AI system. The platform ingests live telemetry from ESP32 ground sensors, performs multimodal AI foliar disease analysis by fusing leaf imagery with soil sensor data, and delivers bilingual agronomic prescriptions (English + Telugu).

---

## 2. User Stories & Requirements (EARS Notation)

### 2.1 Sensor Telemetry

| ID | Statement |
|----|-----------|
| REQ-01 | **While** an ESP32 device is powered on, **the system shall** accept a POST request to `/api/update-sensors` containing a JSON sensor payload and persist it to the in-memory sensor state store. |
| REQ-02 | **When** a frontend client polls `/api/sensor-data`, **the system shall** return the latest sensor readings including `soil_moisture`, `temperature`, `humidity`, `vpd`, `soil_ph`, `soil_ec`, `N`, `P`, `K`, `pump_status`, `pest_alert`, and `sunlight`. |
| REQ-03 | **Where** the hardware is connected via USB serial (COM port), **the system shall** continuously read JSON lines from the serial port at 115200 baud and update the sensor state. |
| REQ-04 | **The system shall** automatically calculate VPD from temperature and humidity using the Magnus formula whenever either value updates. |
| REQ-05 | **If** the serial port is unavailable, **the system shall** not crash; it shall retry every 2 seconds and serve the last-known sensor state. |

### 2.2 Multimodal AI Foliar Diagnostics

| ID | Statement |
|----|-----------|
| REQ-06 | **When** a user uploads a leaf image to `POST /api/diagnose-leaf`, **the system shall** send the image and current ground sensor context to the Gemini Vision model and return a structured JSON diagnosis. |
| REQ-07 | **The system shall** enforce a cross-check fusion rule: if visual yellowing is detected AND `soil_moisture` < 25%, the diagnosis shall be overridden to "Drought Stress" (`status_type: OVERRIDE_WATER`). |
| REQ-08 | **The system shall** enforce a cross-check fusion rule: if visual yellowing is detected AND `N` < 50 ppm, the diagnosis shall be overridden to "Nitrogen Deficiency" (`status_type: OVERRIDE_NUTRIENT`). |
| REQ-09 | **If** neither override condition is met, **the system shall** return the AI-identified pathogen diagnosis (`status_type: CONFIRMED_PATHOGEN`). |
| REQ-10 | **The system shall** return bilingual prescriptions in both English and Telugu for every diagnosis. |
| REQ-11 | **The system shall** return a `confidence` float (0.0–1.0) with every diagnosis. |

### 2.3 Conversational AI Chatbot

| ID | Statement |
|----|-----------|
| REQ-12 | **When** a user submits a message to `POST /api/chat`, **the system shall** respond with agronomic advice using the Gemini language model with the current sensor state injected as context. |
| REQ-13 | **The system shall** maintain per-session chat history (in-memory) using a session ID so multi-turn conversations are coherent. |
| REQ-14 | **The chatbot shall** respond in the same language the user writes in (English or Telugu). |

### 2.4 Frontend Dashboard

| ID | Statement |
|----|-----------|
| REQ-15 | **The system shall** poll `/api/sensor-data` every 2 seconds and update all DOM metric values without page reload. |
| REQ-16 | **When** sensor data updates, **the system shall** dynamically update the VPD status text and color based on the current VPD value. |
| REQ-17 | **When** a leaf image is selected, **the system shall** call `/api/diagnose-leaf` and render the structured response into the diagnosis card. |
| REQ-18 | **The dashboard shall** include a floating chatbot panel that opens/closes and communicates with `/api/chat`. |
| REQ-19 | **The system shall** be mobile-first and retain the existing card/grid layout. |

### 2.5 ESP32 Firmware

| ID | Statement |
|----|-----------|
| REQ-20 | **The firmware shall** read sensors and POST a JSON payload to `/api/update-sensors` over WiFi every 2 seconds. |

---

## 3. Technical Design

### 3.1 System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        ESP32 Device                             │
│  [Soil Moisture] [Temp/Humidity] [NPK] [pH] [EC] [SW-420]      │
│                   POST /api/update-sensors                       │
└──────────────────────────┬──────────────────────────────────────┘
                           │ WiFi / USB Serial
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                 FastAPI Backend (main.py)                        │
│                                                                 │
│  ┌─────────────────┐  ┌────────────────────┐  ┌─────────────┐ │
│  │  Serial Thread  │  │  Sensor State Store│  │  Chat Store │ │
│  │  (COM5 reader)  │─▶│  latest_data dict  │  │  (per sess) │ │
│  └─────────────────┘  └────────────────────┘  └─────────────┘ │
│                                │                               │
│  ┌─────────────────────────────┼──────────────────────────┐   │
│  │           API Routes        │                          │   │
│  │  GET  /api/sensor-data ─────┘                          │   │
│  │  POST /api/update-sensors                              │   │
│  │  POST /api/diagnose-leaf ──▶ Gemini Vision API         │   │
│  │  POST /api/chat          ──▶ Gemini Text API           │   │
│  │  GET  /                  ──▶ Dashboard HTML            │   │
│  └────────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              Browser / Mobile Dashboard                         │
│  [Weather Box] [Pest Alert] [Pump Badge] [6-Metric Grid]        │
│  [VPD Gauge] [NPK Index] [AI Leaf Scanner] [Chatbot Panel]      │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 File Structure

```
agrisaathi/
├── main.py           # FastAPI app, routes, serial thread, Gemini integration
├── config.py         # Environment variables, settings
├── schemas.py        # Pydantic models for requests/responses
├── templates/
│   └── dashboard.html  # Frontend dashboard (served by FastAPI)
├── firmware/
│   └── esp32_sensor.ino  # ESP32 Arduino sketch
├── requirements.txt
└── .env.example
```

### 3.3 API Interface Definitions

#### `POST /api/update-sensors`
**Request Body (ESP32 JSON Payload):**
```json
{
  "soil_moisture": 42,
  "temperature": 29.3,
  "humidity": 65.0,
  "soil_ph": 6.2,
  "soil_ec": 0.45,
  "N": 55,
  "P": 18,
  "K": 72,
  "pump_status": "ON",
  "pest_alert": false,
  "sunlight": "DAYLIGHT",
  "rainfall": 0.0
}
```
**Response:**
```json
{ "status": "ok", "vpd": 1.04 }
```

#### `GET /api/sensor-data`
**Response:**
```json
{
  "soil_moisture": 42,
  "temperature": 29.3,
  "humidity": 65.0,
  "vpd": 1.04,
  "ph": 6.2,
  "ec": 0.45,
  "N": 55,
  "P": 18,
  "K": 72,
  "pump_status": "ON",
  "pest_alert": false,
  "sunlight": "DAYLIGHT",
  "rainfall": 0.0,
  "status": "success"
}
```

#### `POST /api/diagnose-leaf`
**Request:** `multipart/form-data` with field `file` (image/jpeg or image/png)

**Response:**
```json
{
  "title": "Early Blight (Alternaria solani)",
  "status_type": "CONFIRMED_PATHOGEN",
  "confidence": 0.894,
  "cross_check": "Soil moisture at 42% and Nitrogen at 55 ppm are within normal ranges. Abiotic stress ruled out. Concentric brown lesions with yellow halo on older leaves are consistent with Alternaria early blight.",
  "prescription": "Spray Mancozeb 75 WP at 2.5g/L or Copper Oxychloride 50 WP at 3g/L. Remove and destroy infected leaves. Apply within 48 hours.",
  "prescription_telugu": "మాంకోజెబ్ 75 WP 2.5 గ్రా/లీ లేదా కాపర్ ఆక్సీక్లోరైడ్ 50 WP 3 గ్రా/లీ పిచికారీ చేయండి. సోకిన ఆకులను తీసివేసి నాశనం చేయండి. 48 గంటలలోపు చర్యలు తీసుకోండి."
}
```

#### `POST /api/chat`
**Request:**
```json
{
  "message": "My crop leaves are turning yellow, what should I do?",
  "session_id": "user_abc123"
}
```
**Response:**
```json
{
  "reply": "Based on your current soil readings (Moisture: 42%, N: 55 ppm), the yellowing is unlikely to be drought or nitrogen deficiency. I recommend scanning a leaf using the AI Foliar Scanner above for a precise diagnosis.",
  "session_id": "user_abc123"
}
```

### 3.4 Gemini Fusion Prompt Design

The `/api/diagnose-leaf` endpoint constructs a structured prompt:

```
You are AgriSaathi, an expert agronomist AI.

GROUND SENSOR CONTEXT (live readings):
- Soil Moisture: {soil_moisture}%
- Temperature: {temperature}°C
- Humidity: {humidity}%
- Nitrogen (N): {N} ppm
- Phosphorus (P): {P} ppm
- Potassium (K): {K} ppm
- Soil pH: {ph}
- Soil EC: {ec} dS/m
- VPD: {vpd} kPa

CROSS-CHECK RULES (apply strictly):
1. If you detect yellowing/chlorosis AND soil_moisture < 25%, 
   set status_type = "OVERRIDE_WATER" (Drought Stress — not a pathogen).
2. If you detect yellowing AND N < 50 ppm, 
   set status_type = "OVERRIDE_NUTRIENT" (Nitrogen Deficiency — not a pathogen).
3. Otherwise identify the specific disease and set status_type = "CONFIRMED_PATHOGEN".

Analyze the attached leaf image and return ONLY a valid JSON object:
{
  "title": string,
  "status_type": "OVERRIDE_WATER" | "OVERRIDE_NUTRIENT" | "CONFIRMED_PATHOGEN",
  "confidence": float (0.0-1.0),
  "cross_check": string (explain visual findings vs soil metrics),
  "prescription": string (English treatment),
  "prescription_telugu": string (Telugu treatment)
}
```

### 3.5 Data Flow — Leaf Diagnosis

```
User selects image
      │
      ▼
Frontend: FormData POST /api/diagnose-leaf
      │
      ▼
Backend: Read image bytes + current sensor state
      │
      ▼
Gemini Vision API (image + structured prompt)
      │
      ▼
Parse JSON from model response
      │
      ▼
Return DiagnosisResponse to frontend
      │
      ▼
Frontend: Render diagCard with title, confidence, cross_check, prescription
```

---

## 4. Task Breakdown

| # | Task | File(s) | Priority |
|---|------|---------|----------|
| 1 | Create spec.md | `spec.md` | P0 |
| 2 | Environment config | `config.py`, `.env.example` | P0 |
| 3 | Pydantic schemas | `schemas.py` | P0 |
| 4 | Main FastAPI app (serial + all routes) | `main.py` | P0 |
| 5 | Dynamic dashboard HTML/JS with chatbot | `templates/dashboard.html` | P0 |
| 6 | ESP32 firmware sketch | `firmware/esp32_sensor.ino` | P1 |
| 7 | Dependencies file | `requirements.txt` | P0 |

---

## 5. Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GEMINI_API_KEY` | Google AI Studio API key | *(required)* |
| `SERIAL_PORT` | COM port for ESP32 USB | `COM5` |
| `SERIAL_BAUD` | Baud rate | `115200` |
| `HOST` | Server bind address | `0.0.0.0` |
| `PORT` | Server port | `8080` |
| `CHAT_HISTORY_MAX` | Max messages per session | `20` |

---

## 6. Non-Functional Requirements

- Serial read failures must not crash the server — silent retry.
- All AI errors must return a structured error JSON (not HTTP 500 raw stack traces).
- CORS must be open (`*`) to support mobile APK clients.
- The dashboard must be fully functional offline for the sensor panel (AI features degrade gracefully with error messages when API key is missing).
