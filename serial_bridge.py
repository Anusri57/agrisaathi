"""
serial_bridge.py — AgriSaathi Serial → WiFi Bridge
Reads JSON from ESP32 on COM5 and forwards it to the local server.
Run this in a separate terminal while main.py is running.

Usage:
  python serial_bridge.py
"""
import json
import time
import urllib.request

import serial

SERIAL_PORT = "COM5"
BAUD_RATE   = 115200
SERVER_URL  = "http://localhost:8080/api/update-sensors"

print(f"[Bridge] Connecting to {SERIAL_PORT}...")

while True:
    try:
        ser = serial.Serial()
        ser.port     = SERIAL_PORT
        ser.baudrate = BAUD_RATE
        ser.timeout  = 2
        ser.dtr      = False
        ser.rts      = False
        ser.open()
        print(f"[Bridge] Connected. Forwarding to {SERVER_URL}")

        while True:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    # Validate JSON
                    data = json.loads(line)
                    if not isinstance(data, dict) or len(data) < 3:
                        continue  # skip incomplete payloads
                    # Forward to server
                    req = urllib.request.Request(
                        SERVER_URL,
                        data=line.encode("utf-8"),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=2) as resp:
                        print(f"[Bridge] → Server OK | {line[:60]}…")
                except json.JSONDecodeError:
                    pass  # skip malformed lines silently
                except Exception as e:
                    print(f"[Bridge] Forward error: {e}")

    except Exception as exc:
        print(f"[Bridge] Serial error: {exc}. Retrying in 3s…")
        time.sleep(3)
