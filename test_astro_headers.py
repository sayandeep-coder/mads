import os
import httpx
from dotenv import load_dotenv

load_dotenv()
key = os.environ.get("AstrologyAPI")

if not key:
    print("No key found!")
    exit(1)

headers_to_test = [
    {"x-api-key": key},
    {"Authorization": f"Bearer {key}"},
    {"Authorization": key},
    {"API-Key": key},
    {"apikey": key},
    {"x-api-key": key, "Content-Type": "application/json"}
]

for headers in headers_to_test:
    try:
        r = httpx.post("https://json.freeastrologyapi.com/planets", json={}, headers=headers)
        print(f"Headers: {list(headers.keys())} -> Status: {r.status_code}, Text: {r.text[:50]}")
    except Exception as e:
        print(e)
