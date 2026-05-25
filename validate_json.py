import json
from pathlib import Path

files = [
    "tools/scrape_config_builder/helper_input/appointments-in-general-practice.json",
    "tools/scrape_config_builder/helper_input/acute-discharge-situation-report.json",
    "tools/scrape_config_builder/helper_input/cancer-waiting-times.json",
]

for fpath in files:
    p = Path(fpath)
    print(f"\n=== {p.name} ===")
    try:
        data = json.load(p.open(encoding="utf-8"))
        print("JSON valid")
        print(f"  schema_version: {data.get('schema_version')}")
        print(f"  dataset_id: {data.get('dataset_id')}")
        targets = data.get("targets", [])
        print(f"  targets: {len(targets)}")

        for i, t in enumerate(targets):
            sid = t.get("sub_dataset_id")
            pages = t.get("sample_pages", [])
            hints = t.get("hints", {})
            ap_hint = t.get("archive_pattern_hint")
            ap_in_hints = hints.get("archive_pattern")
            print(
                f"  [{i}] {sid}: pages={len(pages)}, "
                f"archive_pattern_hint={ap_hint}, "
                f"archive_pattern_in_hints={ap_in_hints}"
            )
    except json.JSONDecodeError as e:
        print(f"JSON ERROR: {e}")
    except Exception as e:
        print(f"ERROR: {e}")
