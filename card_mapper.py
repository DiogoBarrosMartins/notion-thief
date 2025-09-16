# card_mapper.py
import json, os, time, requests
from typing import Iterable, Dict, Optional

CARD_DB = "card_map.json"

_session = requests.Session()
_session.headers.update({"User-Agent": "mtga-historian/1.0 (+discord-bot)"})

def load_card_map() -> Dict[str, str]:
    if os.path.exists(CARD_DB):
        try:
            with open(CARD_DB, "r", encoding="utf-8") as f:
                return {str(k): str(v) for k, v in json.load(f).items()}
        except Exception:
            pass
    return {}

def _save_atomic(path: str, data: dict):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)

def save_card_map(card_map: Dict[str, str]) -> None:
    _save_atomic(CARD_DB, card_map)

def _fetch_from_scryfall(grp_id: int) -> Optional[str]:
    try:
        r = _session.get(f"https://api.scryfall.com/cards/arena/{grp_id}", timeout=8)
        if r.ok:
            js = r.json()
            n = js.get("name")
            if n:
                return n
    except Exception:
        pass

    url = "https://api.scryfall.com/cards/search"
    params = {
        "q": f"arena:{grp_id} OR arena_id:{grp_id}",
        "unique": "prints",
        "order": "released",
        "include_extras": "true",
        "include_variations": "true",
        "include_multilingual": "true",
    }
    while True:
        try:
            s = _session.get(url, params=params, timeout=12)
        except Exception:
            break
        if not s.ok:
            break
        js = s.json()
        for c in js.get("data", []):
            if str(c.get("arena_id") or "") == str(grp_id):
                return c.get("name")
        if js.get("has_more") and js.get("next_page"):
            url = js["next_page"]
            params = None
            continue
        break
    return None

def get_card_name(grp_id, card_map: Dict[str, str], quiet: bool = False) -> str:
    key = str(grp_id)
    if key in card_map and card_map[key]:
        return card_map[key]
    if not quiet:
        print(f"🌐 resolving {key} ...")
    name = _fetch_from_scryfall(int(grp_id))
    if name:
        card_map[key] = name
        save_card_map(card_map)
        if not quiet:
            print(f"✅ {key} → {name}")
        return name
    card_map[key] = f"Unknown({key})"
    save_card_map(card_map)
    if not quiet:
        print(f"⚠️ not found {key}")
    return card_map[key]

def resolve_many(grp_ids: Iterable[int], card_map: Dict[str, str], delay: float = 0.05) -> None:
    seen = set()
    for gid in grp_ids:
        if gid is None: continue
        k = str(gid)
        if k in seen: continue
        seen.add(k)
        if k not in card_map or not card_map[k] or card_map[k].startswith("Unknown("):
            _ = get_card_name(gid, card_map, quiet=True)
            if delay: time.sleep(delay)
    save_card_map(card_map)
