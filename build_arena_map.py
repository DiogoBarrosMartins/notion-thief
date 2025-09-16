# build_arena_map.py
import io
import json
import zipfile
import requests
import os

MTGJSON_URL = "https://mtgjson.com/api/v5/AllPrintings.json.zip"
SCRYFALL_BULK = "https://api.scryfall.com/bulk-data"
CARD_DB = "card_map.json"
MANUAL_OVERRIDES = "manual_overrides.json"

def fetch_from_mtgjson() -> dict:
    print(f"↓ downloading {MTGJSON_URL} ...")
    r = requests.get(MTGJSON_URL, stream=True, timeout=120)
    r.raise_for_status()

    print("📦 reading AllPrintings.json from zip ...")
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        json_name = next((n for n in zf.namelist() if n.endswith(".json")), None)
        if not json_name:
            raise RuntimeError("No .json found inside MTGJSON zip")
        with zf.open(json_name) as f:
            data = json.load(f)

    print("🔎 building arenaId → name map (MTGJSON) ...")
    out = {}
    data_sets = (data.get("data") or {})
    for set_obj in data_sets.values():
        for c in set_obj.get("cards", []):
            identifiers = c.get("identifiers") or {}
            arena_id = (
                identifiers.get("mtgArenaId")
                or identifiers.get("arenaId")
                or identifiers.get("mtgaId")
            )
            if not arena_id:
                continue
            name = c.get("name")
            if not name:
                continue
            k = str(arena_id)
            if k not in out:  # keep first seen
                out[k] = name

    print(f"✅ mapped {len(out)} arenaId → name from MTGJSON")
    return out

def merge_scryfall_default_cards(out: dict) -> int:
    print("🪄 also merging Scryfall default_cards bulk …")
    try:
        meta = requests.get(SCRYFALL_BULK, timeout=30)
        meta.raise_for_status()
        items = meta.json().get("data", [])
        default = next((i for i in items if i.get("type") == "default_cards"), None)
        if not default:
            print("⚠️ Could not find default_cards in bulk-data list")
            return 0

        bulk_url = default["download_uri"]
        r = requests.get(bulk_url, timeout=180)
        r.raise_for_status()
        blob = r.json()
    except Exception as e:
        print(f"⚠️ Scryfall bulk failed, skipping merge: {e}")
        return 0

    added = 0
    for c in blob:
        aid = c.get("arena_id")
        name = c.get("name")
        if aid and name:
            k = str(aid)
            if k not in out:
                out[k] = name
                added += 1
    print(f"✅ merged +{added} from Scryfall default_cards")
    return added

def merge_manual_overrides(out: dict) -> int:
    if not os.path.exists(MANUAL_OVERRIDES):
        return 0
    try:
        with open(MANUAL_OVERRIDES, "r", encoding="utf-8") as f:
            manual = json.load(f)
        added = 0
        for k, v in manual.items():
            if v and str(k) not in out:
                out[str(k)] = str(v)
                added += 1
        print(f"✅ merged +{added} from manual_overrides.json")
        return added
    except Exception as e:
        print(f"⚠️ Failed to merge manual_overrides.json: {e}")
        return 0

def main():
    out = fetch_from_mtgjson()
    merge_scryfall_default_cards(out)
    merge_manual_overrides(out)
    print(f"💾 writing {CARD_DB} ({len(out)} entries)")
    with open(CARD_DB, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print("✅ done")

if __name__ == "__main__":
    main()

LOCAL_FILE = "local_sets.json"
if os.path.exists(LOCAL_FILE):
    print(f"📦 merging local sets from {LOCAL_FILE} ...")
    with open(LOCAL_FILE, "r", encoding="utf-8") as f:
        local_data = json.load(f)
    for set_code, set_obj in (local_data.get("data") or {}).items():
        for c in set_obj.get("cards", []):
            identifiers = c.get("identifiers") or {}
            arena_id = identifiers.get("mtgArenaId") or identifiers.get("arenaId") or identifiers.get("mtgaId")
            if not arena_id:
                continue
            name = c.get("name")
            if not name:
                continue
            k = str(arena_id)
            if k not in out:
                out[k] = name
                print(f"  ➕ added {name} ({arena_id}) from local set {set_code}")