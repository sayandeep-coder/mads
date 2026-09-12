import os
import httpx
from dotenv import load_dotenv

load_dotenv()

key = os.environ.get("ASTROLOGY_API_KEY") or os.environ.get("ASTROLOGYAPI") or os.environ.get("ASTROLOGYAPI_KEY") or os.environ.get("ASTROLOGY_API")

if not key:
    with open(".env") as f:
        for line in f:
            if "ASTROLOGY" in line.upper() or "API" in line.upper():
                key = line.strip().split("=")[1]
                break

if not key:
    print("No key found")
    exit(1)

headers = {
    "x-api-key": key,
    "Content-Type": "application/json"
}

payload = {
    "year": 2005, "month": 8, "date": 30,
    "hours": 11, "minutes": 53, "seconds": 0,
    "latitude": 22.37, "longitude": 88.17, "timezone": 5.5
}

try:
    r = httpx.post("https://json.freeastrologyapi.com/planets", json=payload, headers=headers)
    print("Status:", r.status_code)
    print("Response keys:", list(r.json().keys()) if r.status_code == 200 else r.text[:200])
except Exception as e:
    print("Error:", e)
