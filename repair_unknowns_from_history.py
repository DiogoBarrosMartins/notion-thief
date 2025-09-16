import re, json
from card_mapper import load_card_map, get_card_name, resolve_many

HISTORY = "matches.json"
pat = re.compile(r"Unknown\((\d+)\)")

with open(HISTORY, "r", encoding="utf-8") as f:
    hist = json.load(f)

ids = set()
def collect(val):
    if isinstance(val, str):
        for m in pat.finditer(val): ids.add(int(m.group(1)))

for m in hist:
    collect(m.get("result") or "")
    collect(m.get("player_deck") or "")
    if m.get("plays"):
        for p in m["plays"]:
            collect(p.get("card") or "")
    dl = m.get("player_decklist") or {}
    for part in ("main","side"):
        for qn in dl.get(part) or []:
            if isinstance(qn, list) and len(qn)==2:
                collect(qn[1])

cmap = load_card_map()
resolve_many(sorted(ids), cmap, delay=0.08)

def replace(val):
    if isinstance(val, str):
        return pat.sub(lambda mm: get_card_name(int(mm.group(1)), cmap, quiet=True), val)
    return val

for m in hist:
    m["result"] = replace(m.get("result"))
    m["player_deck"] = replace(m.get("player_deck"))
    if m.get("plays"):
        for p in m["plays"]:
            p["card"] = replace(p.get("card"))
    dl = m.get("player_decklist") or {}
    out_main, out_side = [], []
    for part, dest in (("main", out_main), ("side", out_side)):
        for qn in dl.get(part) or []:
            if isinstance(qn, list) and len(qn)==2:
                dest.append([qn[0], replace(qn[1])])
    m["player_decklist"] = {"main": out_main, "side": out_side}

with open(HISTORY, "w", encoding="utf-8") as f:
    json.dump(hist, f, indent=2, ensure_ascii=False)

print(f"✅ Replaced {len(ids)} Unknown(...) occurrences in {HISTORY}")
