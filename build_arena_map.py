import io
import json
import zipfile
import requests

MTGJSON_URL = "https://mtgjson.com/api/v5/AllPrintings.json.zip"
OUT_FILE = "card_overrides.json"  # card_mapper.py will auto-merge this

def main():
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

    print("🔎 building arenaId → name map ...")
    out = {}
    data_sets = (data.get("data") or {})
    for set_code, set_obj in data_sets.items():
        for c in set_obj.get("cards", []):
            identifiers = c.get("identifiers") or {}
            # MTGJSON v5 typically uses "mtgArenaId"
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
            # keep first seen; enough for name resolution
            if k not in out:
                out[k] = name

    print(f"✅ mapped {len(out)} arenaId → name")
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"💾 wrote {OUT_FILE} ({len(out)} entries)")

if __name__ == "__main__":
    main()
