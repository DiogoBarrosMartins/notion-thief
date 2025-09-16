# card_mapper.py
import json, os, time, requests
from typing import Iterable, Dict, Optional

CARD_DB = "card_map.json"
OVERRIDES_DB = "card_overrides.json"

_session = requests.Session()
_session.headers.update({"User-Agent": "mtga-historian/1.0 (+discord-bot)"})

def load_card_map() -> Dict[str, str]:
    # 1) start from OVERRIDES_DB (MTGJSON) -> authoritative English names
    m: Dict[str, str] = {}
    if os.path.exists(OVERRIDES_DB):
        try:
            with open(OVERRIDES_DB, "r", encoding="utf-8") as f:
                m.update({str(k): str(v) for k, v in json.load(f).items()})
        except Exception:
            pass

    # 2) layer your local cache on top, BUT ignore stale Unknown(...)
    if os.path.exists(CARD_DB):
        try:
            with open(CARD_DB, "r", encoding="utf-8") as f:
                local = json.load(f)
            for k, v in local.items():
                k = str(k); v = str(v)
                if v.startswith("Unknown(") and k in m and m[k]:
                    # keep the good override, skip stale Unknown
                    continue
                m[k] = v
        except Exception:
            pass

    return {str(k): str(v) for k, v in m.items()}

def _save_atomic(path: str, data: dict):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)

def save_card_map(card_map: Dict[str, str]) -> None:
    _save_atomic(CARD_DB, card_map)

def _fetch_from_scryfall(grp_id: int) -> Optional[str]:
    # 1) endpoint direto
    try:
        r = _session.get(f"https://api.scryfall.com/cards/arena/{grp_id}", timeout=8)
        if r.status_code == 200:
            name = r.json().get("name")
            if name:
                return name
        elif r.status_code == 429:
            time.sleep(0.5)
    except Exception:
        pass

    # 2) pesquisas alternativas com extras/variations e "pick" pelo arena_id
    queries = (f"arena:{grp_id}", f"arena_id:{grp_id}")
    for q in queries:
        tries = 0
        while tries < 2:
            tries += 1
            try:
                sr = _session.get(
                    "https://api.scryfall.com/cards/search",
                    params={
                        "q": q,
                        "unique": "prints",
                        "order": "released",
                        "include_extras": "true",
                        "include_variations": "true",
                    },
                    timeout=10,
                )
                if sr.status_code == 429:
                    time.sleep(0.5 * tries)
                    continue
                if sr.status_code == 200:
                    js = sr.json()
                    data = (js or {}).get("data") or []
                    if data:
                        for it in data:
                            if str(it.get("arena_id")) == str(grp_id):
                                nm = it.get("name")
                                if nm:
                                    return nm
                        nm = next((d.get("name") for d in data if d.get("name")), None)
                        if nm:
                            return nm
                break
            except Exception:
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
