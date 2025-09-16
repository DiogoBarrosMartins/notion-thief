# fix_unknowns.py
import json, os, shutil
import card_mapper

# descobre o ficheiro de overrides
OVR = getattr(card_mapper, "OVERRIDES", None) or getattr(card_mapper, "OVERRIDES_DB", "card_overrides.json")
CARD_DB = getattr(card_mapper, "CARD_DB", "card_map.json")

if not os.path.exists(OVR):
    raise SystemExit(f"❌ Overrides file not found: {OVR}")

# carrega overrides e cache
with open(OVR, "r", encoding="utf-8") as f:
    over = {str(k): str(v) for k, v in json.load(f).items()}

m = card_mapper.load_card_map()

unknown_keys = [k for k, v in m.items() if str(v).startswith("Unknown(")]
print(f"🔎 Unknown entries in cache before: {len(unknown_keys)}")

changed = 0
for k in unknown_keys:
    if k in over and over[k]:
        m[k] = over[k]
        changed += 1

print(f"✅ Replaced {changed} Unknown(...) entries using {OVR}")

# backup e grava
if os.path.exists(CARD_DB):
    shutil.copyfile(CARD_DB, CARD_DB + ".bak")
card_mapper.save_card_map(m)

# sanity: mostra alguns IDs conhecidos se existirem
probe = ["96064", "96067", "96074"]
present = {pid: m.get(pid) for pid in probe if pid in m}
if present:
    print("🧪 Probe after fix:", present)
else:
    print("ℹ️ Probe IDs not in cache; they’ll resolve from overrides on next run.")
