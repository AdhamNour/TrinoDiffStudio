import json
import os
import re

logs_dir = r"c:\Users\anhassan\nera_automations\logs\dwh\run_id=manual__2026-08-03T12%3A55%3A38.165621+00%3A00"

for root, _, files in os.walk(logs_dir):
    for file in files:
        if not file.endswith('.log'): continue
        file_path = os.path.join(root, file)
        
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if not line.strip(): continue
                try:
                    entry = json.loads(line)
                    if entry.get("level", "").lower() == "error":
                        print(f"FAILED TASK: {os.path.basename(os.path.dirname(file_path))}")
                        print(f"ERROR EVENT: {entry.get('event')}")
                        print("-" * 50)
                except:
                    if "error" in line.lower() or "exception" in line.lower() or "failed" in line.lower():
                        print(f"FAILED TASK (RAW): {os.path.basename(os.path.dirname(file_path))}")
                        print(line.strip())
                        print("-" * 50)
