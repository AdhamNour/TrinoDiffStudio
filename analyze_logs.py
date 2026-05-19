import os
import json
from collections import defaultdict

log_dir = "downloaded_logs"
error_categories = defaultdict(list)

for map_index in os.listdir(log_dir):
    map_dir = os.path.join(log_dir, map_index)
    if not os.path.isdir(map_dir): continue
    
    for log_file in os.listdir(map_dir):
        if not log_file.endswith(".log"): continue
        file_path = os.path.join(map_dir, log_file)
        
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if '"level":"error"' in line or '"level": "error"' in line:
                    try:
                        data = json.loads(line)
                        if data.get("level") == "error":
                            error_detail = data.get("error_detail", [])
                            if error_detail and isinstance(error_detail, list):
                                exc_type = error_detail[0].get("exc_type")
                                exc_value = error_detail[0].get("exc_value", "").strip()
                                error_msg = f"{exc_type}: {exc_value}"
                                error_categories[error_msg].append(f"{map_index}/{log_file}")
                    except Exception as e:
                        print(f"Error parsing line in {file_path}: {e}")

print("Error Categories Summary:")
print("=========================")
for err_msg, locations in error_categories.items():
    print(f"\n{err_msg}")
    print(f"Occurred {len(locations)} times in:")
    for loc in locations[:5]:
        print(f"  - {loc}")
    if len(locations) > 5:
        print(f"  - ... and {len(locations) - 5} more.")
