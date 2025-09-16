# mtga_log_watcher.py
import time
import json
import os
import re
from datetime import datetime
import requests

from card_mapper import load_card_map, get_card_name, resolve_many

# =======================
# Config
# =======================
LOG_PATH = os.getenv(
    "MTGA_LOG_PATH",
    r"C:\Users\Diogo\AppData\LocalLow\Wizards Of The Coast\MTGA\Player.log",
)
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip()
HISTORY_FILE = "matches.json"
DISCORD_CHUNK = 1800
INVERT_SEAT = os.getenv("INVERT_SEAT", "0") == "1"  # only use if you find seats flipped
ANNOUNCE_PLAYS = os.getenv("ANNOUNCE_PLAYS", "1") == "1"

# =======================
# State
# =======================
card_map = load_card_map()

current_match = {
    "id": None,
    "format": None,
    "player_deck": None,
    "opponent": None,
    "opponent_deck": None,
    "player_decklist": None,
    "plays": [],
    "my_team_id": None,
    "my_seat": None,
    "opening_emitted": False,
    "finished": False,
}
_seen_play_instances = set()
_seen_plays = set()
instance_index = {}        # instanceId -> {grpId, controllerSeatId, ownerSeatId, zoneId, zone}
zone_id_name = {}          # zoneId -> "hand"/"stack"/"battlefield"/...
last_deck_sig = None

# =======================
# Utils
# =======================
def ts_now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _post_webhook(text: str):
    if not WEBHOOK_URL or not text:
        return
    try:
        requests.post(WEBHOOK_URL, json={"content": text}, timeout=6)
    except Exception as e:
        print("⚠️ Webhook error:", e)

def _announce(msg: str):
    print(msg)
    _post_webhook(msg)

def _post_long(text: str):
    if not text:
        return
    if not WEBHOOK_URL:
        print(text)
        return
    buf = ""
    for line in text.splitlines(True):
        if len(buf) + len(line) > DISCORD_CHUNK:
            _post_webhook(buf)
            buf = ""
        buf += line
    if buf:
        _post_webhook(buf)

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_match(match_data):
    history = load_history()
    history.append(match_data)
    tmp = HISTORY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    os.replace(tmp, HISTORY_FILE)

# Tail with rotation
def follow(path):
    f = open(path, "r", encoding="utf-8", errors="ignore")
    f.seek(0, 2)
    try:
        while True:
            line = f.readline()
            if not line:
                try:
                    size = os.path.getsize(path)
                    if f.tell() > size:
                        f.close()
                        f = open(path, "r", encoding="utf-8", errors="ignore")
                        f.seek(0, 2)
                except FileNotFoundError:
                    time.sleep(0.2)
                time.sleep(0.1)
                continue
            yield line
    finally:
        try:
            f.close()
        except Exception:
            pass

# =======================
# Streaming JSON parser
# =======================
_buffer = []
_open = 0
_in_string = False
_escaped = False
MAX_CHUNK = 8_000_000

STATE_RE    = re.compile(r"STATE CHANGED.*{\"old\":\"(?P<old>[^\"]+)\",\"new\":\"(?P<new>[^\"]+)\"}")
# We’ll see this for lots of things (GreToClientEvent, etc.) so just capture the “Match to <ID>: …” header.
MATCH_TO_RE = re.compile(r"Match to (?P<uid>[A-Z0-9]+):")

def _decode_request(val):
    v = val
    for _ in range(3):
        if isinstance(v, str):
            s = v.strip()
            if s.startswith("{") or s.startswith("["):
                try:
                    v = json.loads(v)
                    continue
                except Exception:
                    break
        break
    return v

def feed_and_parse(line: str):
    """
    - If it's a state change → pseudo-event {"_state": {old,new}}
    - If it has the "Match to <UID>:" header → {"_me_seen": True} (used to learn our seat later)
    - Otherwise accumulate JSON by brace counting.
    """
    out = []

    m = STATE_RE.search(line)
    if m:
        out.append({"_state": {"old": m.group("old"), "new": m.group("new")}})

    # marker that we're inside a match stream for *this* client
    if MATCH_TO_RE.search(line):
        out.append({"_me_seen": True})

    global _buffer, _open, _in_string, _escaped
    for c in line:
        if _open == 0:
            if c == "{":
                _buffer = ["{"]; _open = 1
                _in_string = False; _escaped = False
            else:
                continue
        else:
            _buffer.append(c)
            if _escaped:
                _escaped = False
            elif c == "\\":
                _escaped = True
            elif c == '"':
                _in_string = not _in_string
            elif not _in_string:
                if c == "{":
                    _open += 1
                elif c == "}":
                    _open -= 1
                    if _open == 0:
                        raw = "".join(_buffer)
                        _buffer = []
                        try:
                            obj = json.loads(raw)
                            if isinstance(obj, dict) and "request" in obj:
                                obj["request"] = _decode_request(obj["request"])
                            out.append(obj)
                        except Exception:
                            pass
        if _open > 0 and len(_buffer) > MAX_CHUNK:
            # broken JSON; reset parser to avoid memory blowup
            _buffer = []; _open = 0; _in_string = False; _escaped = False
    return out

# =======================
# Zone & object helpers
# =======================
def _simplify_zone(z) -> str:
    s = str(z).lower()
    if "hand" in s: return "hand"
    if "stack" in s: return "stack"
    if "battlefield" in s: return "battlefield"
    if "library" in s: return "library"
    if "graveyard" in s: return "graveyard"
    if "exile" in s: return "exile"
    if "command" in s: return "command"
    if "revealed" in s: return "revealed"
    return s

def _seat_label(seat):
    if seat is None:
        return "Player"
    s = int(seat)
    mine = current_match.get("my_seat")
    if mine in (1, 2):
        if INVERT_SEAT:
            mine = 1 if mine == 2 else 2
        return "You" if s == mine else "Opponent"
    # fallback (rare)
    if INVERT_SEAT:
        return "You" if s == 2 else "Opponent"
    return "You" if s == 1 else "Opponent"

def _index_gameobjects(objs):
    if not isinstance(objs, list): return
    for o in objs:
        if not isinstance(o, dict): continue
        t = o.get("type") or o.get("GameObjectType") or o.get("gameObjectType")
        if "Card" not in str(t): continue
        inst = o.get("instanceId")
        if inst is None: continue
        rec = instance_index.get(inst, {})
        for k in ("grpId", "controllerSeatId", "ownerSeatId", "zoneId"):
            if k in o:
                rec[k] = o.get(k)
        # derive zone name
        zid = rec.get("zoneId")
        if zid is not None:
            rec["zone"] = zone_id_name.get(zid)
        instance_index[inst] = rec

def _index_zones(zones):
    if not isinstance(zones, list): return
    for z in zones:
        if not isinstance(z, dict): continue
        zid = z.get("zoneId")
        ztype = z.get("type") or z.get("zoneType") or z.get("visibility") or ""
        if zid is None: continue
        zone_id_name[zid] = _simplify_zone(ztype)

def _announce_play(instance_id, grp_id, seat, zone_name):
    if not ANNOUNCE_PLAYS:
        return
    if instance_id in _seen_play_instances:
        return
    _seen_play_instances.add(instance_id)

    card_name = get_card_name(grp_id, card_map, quiet=True)
    who = _seat_label(seat)

    sig = (int(grp_id), who, zone_name, len(current_match["plays"]))
    if sig in _seen_plays:
        return
    _seen_plays.add(sig)

    if zone_name == "stack":
        _announce(f"✨ {who} cast: **{card_name}** (stack)")
    elif zone_name == "battlefield":
        _announce(f"🃏 {who} played: **{card_name}** → battlefield")
    else:
        _announce(f"🃏 {who} moved: **{card_name}** → {zone_name}")

    current_match["plays"].append({
        "t": ts_now(), "who": who, "card": card_name, "zone": zone_name
    })

def _maybe_emit_opening_hand():
    if current_match["opening_emitted"]:
        return
    my = current_match.get("my_seat")
    if my not in (1, 2): 
        return
    # collect cards currently in your hand
    hand_ids = []
    for rec in instance_index.values():
        if rec.get("zone") == "hand" and (rec.get("controllerSeatId") == my or rec.get("ownerSeatId") == my):
            gid = rec.get("grpId")
            if gid is not None:
                hand_ids.append(gid)
    if not hand_ids:
        return
    resolve_many(hand_ids, card_map)
    names = [get_card_name(gid, card_map, quiet=True) for gid in hand_ids]

    current_match["opening_emitted"] = True
    lines = ["✋ **Your opening hand**:"] + [f"- {n}" for n in names]
    _post_long("\n".join(lines))

def _handle_annotations(annotations):
    if not isinstance(annotations, list): return
    for ann in annotations:
        types = ann.get("type") or []
        # Zone transfers carry draws / casts / battlefield entries
        if not any("ZoneTransfer" in t for t in types):
            continue

        # details -> dict
        dmap = {}
        for d in ann.get("details", []):
            k = d.get("key")
            if not k: continue
            if "valueInt32" in d and d["valueInt32"]:
                dmap[k] = d["valueInt32"][0]
            elif "valueString" in d and d["valueString"]:
                dmap[k] = d["valueString"][0]

        src = dmap.get("zone_src"); dst = dmap.get("zone_dest")
        src_name = _simplify_zone(zone_id_name.get(src, ""))
        dst_name = _simplify_zone(zone_id_name.get(dst, ""))

        for inst in ann.get("affectedIds") or []:
            rec = instance_index.get(inst, {})
            grp = rec.get("grpId")
            seat = rec.get("controllerSeatId") or rec.get("ownerSeatId")
            if grp is None:
                continue
            # draw: library → hand
            if src_name == "library" and dst_name == "hand":
                who = _seat_label(seat)
                name = get_card_name(grp, card_map, quiet=True)
                _announce(f"📥 {who} drew: **{name}**")
                current_match["plays"].append({"t": ts_now(), "who": who, "card": name, "zone": "draw"})
                continue
            # cast: X → stack
            if dst_name == "stack":
                _announce_play(inst, grp, seat, "stack")
                continue
            # entered battlefield
            if dst_name == "battlefield":
                _announce_play(inst, grp, seat, "battlefield")
                continue

# =======================
# Decklist helpers
# =======================
def _resolve_list(entries):
    out, grp_ids = [], []
    for it in entries or []:
        cid = it.get("cardId") or it.get("grpId")
        qty = int(it.get("quantity", 1))
        if cid is None: continue
        grp_ids.append(cid)
        name = get_card_name(cid, card_map, quiet=True)
        out.append((qty, name))
    agg = {}
    for qty, name in out:
        agg[name] = agg.get(name, 0) + qty
    return sorted([(q, n) for n, q in agg.items()], key=lambda x: x[1].lower()), grp_ids

def _format_decklist(deck_name, fmt, main, side):
    lines = []
    lines.append(f"🟢 **Deck:** {deck_name} ({fmt or '??'})")
    lines.append("**Main**:")
    for q, n in main: lines.append(f"{q} {n}")
    if side:
        lines.append(""); lines.append("**Sideboard**:")
        for q, n in side: lines.append(f"{q} {n}")
    return "\n".join(lines)

def _deck_signature(summary: dict, deck: dict):
    name = (summary or {}).get("Name") or ""
    main = tuple(sorted(((int(x.get("cardId") or x.get("grpId")), int(x.get("quantity", 1)))
                         for x in (deck or {}).get("MainDeck", []))))
    side = tuple(sorted(((int(x.get("cardId") or x.get("grpId")), int(x.get("quantity", 1)))
                         for x in (deck or {}).get("Sideboard", []))))
    return (name, main, side)

def _emit_decklist(summary: dict, deck: dict):
    global last_deck_sig
    sig = _deck_signature(summary, deck)
    if sig == last_deck_sig:
        return
    last_deck_sig = sig

    deck_name = summary.get("Name") or current_match["player_deck"] or "??"
    fmt = None
    for a in summary.get("Attributes") or []:
        if a.get("name") == "Format":
            fmt = a.get("value"); break

    main, main_ids = _resolve_list((deck or {}).get("MainDeck"))
    side, side_ids = _resolve_list((deck or {}).get("Sideboard"))
    resolve_many(main_ids + side_ids, card_map)
    main, _ = _resolve_list((deck or {}).get("MainDeck"))
    side, _ = _resolve_list((deck or {}).get("Sideboard"))

    current_match["player_deck"] = deck_name
    current_match["format"] = fmt
    current_match["player_decklist"] = {"main": main, "side": side}

    _post_long(_format_decklist(deck_name, fmt, main, side))

# =======================
# Handlers
# =======================
def handle_top(obj: dict):
    if current_match["finished"]:
        return

    # 0) state changes
    if "_state" in obj:
        st = obj["_state"]
        if st.get("new") == "Playing":
            _announce("🎮 You entered **Playing** — I’ll start reporting plays.")
        if st.get("new") == "MatchCompleted" and current_match["id"]:
            # Fallback if no structured result seen
            _finish_match("Unknown")
        return

    # 1) any line from our client stream (helps seat inference later)
    if obj.get("_me_seen"):
        # nothing to store directly; real seat is read in _walk below
        pass

    # 2) requests (EventSetDeckV2 / DeckUpsertDeckV2 / etc.)
    req = obj.get("request")
    if isinstance(req, dict):
        _handle_request(req)

    # 3) walk any nested GRE messages
    _walk(obj)

    # 4) concede detector (client->match messages)
    if isinstance(obj, dict) and "clientToMatchServiceMessageType" in obj:
        val = str(obj.get("clientToMatchServiceMessageType") or "")
        if "concede" in val.lower():
            _finish_match("Loss")

def _handle_request(req: dict):
    # Full decklist
    summary = req.get("Summary") or {}
    deck = req.get("Deck") or {}
    if deck.get("MainDeck") or deck.get("Sideboard"):
        _emit_decklist(summary, deck)
    else:
        # Just deck name/format
        dn = summary.get("Name")
        if dn:
            fmt = None
            for a in summary.get("Attributes") or []:
                if a.get("name") == "Format":
                    fmt = a.get("value"); break
            if current_match["player_deck"] != dn or current_match["format"] != fmt:
                current_match["player_deck"] = dn
                current_match["format"] = fmt
                _announce(f"🟢 New match: **{dn}** ({fmt or '??'})")

    # Opponent name if present
    if "opponentScreenName" in req:
        if current_match["opponent"] != req.get("opponentScreenName"):
            current_match["opponent"] = req.get("opponentScreenName")
            _announce(f"👤 Opponent: **{current_match['opponent']}**")

def _walk(node):
    if isinstance(node, dict):
        # ——— MatchGameRoomStateChangedEvent (players + finalMatchResult)
        ev = node.get("matchGameRoomStateChangedEvent")
        if isinstance(ev, dict):
            _handle_match_room_event(ev)

        # ——— Old camel-case final result
        if "FinalMatchResult" in node:
            _handle_result_old(node)

        # ——— GRE events (modern)
        gre = node.get("greToClientEvent")
        if isinstance(gre, dict):
            msgs = gre.get("greToClientMessages") or []
            for msg in msgs:
                # Learn your seat from any GRE message (the packet is targeted to “your” client)
                sys_seats = msg.get("systemSeatIds")
                if not current_match.get("my_seat") and isinstance(sys_seats, list) and sys_seats:
                    # seat ids here are the “viewer/recipient” seat; that’s us
                    current_match["my_seat"] = int(sys_seats[0])

                gsm = msg.get("gameStateMessage") or msg.get("gameState") or {}
                if isinstance(gsm, dict):
                    if "zones" in gsm: _index_zones(gsm["zones"])
                    if "gameObjects" in gsm: _index_gameobjects(gsm["gameObjects"])
                    if "annotations" in gsm: _handle_annotations(gsm["annotations"])
                    _maybe_emit_opening_hand()

        # ——— Fallback direct nodes
        if "zones" in node: _index_zones(node["zones"])
        if "gameObjects" in node: _index_gameobjects(node["gameObjects"])
        if "annotations" in node: _handle_annotations(node["annotations"])
        _maybe_emit_opening_hand()

        # ——— Single card dumps
        t = node.get("type") or node.get("GameObjectType") or node.get("gameObjectType")
        if t and "Card" in str(t) and ("grpId" in node):
            inst = node.get("instanceId")
            rec = instance_index.get(inst or f"grp:{node.get('grpId')}", {})
            for k in ("grpId", "controllerSeatId", "ownerSeatId", "zoneId"):
                if k in node: rec[k] = node.get(k)
            if "zone" in node:
                rec["zone"] = node.get("zone")
            else:
                zid = rec.get("zoneId")
                if zid is not None: rec["zone"] = zone_id_name.get(zid)
            instance_index[inst or f"grp:{node.get('grpId')}"] = rec

        for v in node.values():
            _walk(v)

    elif isinstance(node, list):
        for it in node:
            _walk(it)

def _handle_match_room_event(ev: dict):
    """
    Handles MatchGameRoomStateChangedEvent (players + finalMatchResult).
    """
    gri = (ev.get("gameRoomInfo") or {}).get("gameRoomConfig") or {}
    reserved = gri.get("reservedPlayers") or []
    match_id = gri.get("matchId") or ev.get("matchId")

    # Infer *your* team using your seat if available
    if reserved:
        my = None
        opp = None
        my_seat = current_match.get("my_seat")
        if my_seat in (1, 2):
            for p in reserved:
                if p.get("systemSeatId") == my_seat:
                    my = p
                else:
                    opp = p
        else:
            # fallback heuristic: assume 2 players, you are seat 1
            if len(reserved) == 2:
                my, opp = reserved[0], reserved[1]

        if my:
            current_match["my_team_id"] = my.get("teamId")
            current_match["my_seat"] = my.get("systemSeatId", current_match.get("my_seat"))
        if opp and not current_match.get("opponent"):
            current_match["opponent"] = opp.get("playerName")
        if match_id and not current_match["id"]:
            current_match["id"] = match_id

    # Structured final result (modern, lowercase)
    final = ev.get("finalMatchResult")
    if isinstance(final, dict) and not current_match["finished"]:
        winning = None
        for r in final.get("resultList") or []:
            if r.get("scope") == "MatchScope_Match" and r.get("result") == "ResultType_WinLoss":
                winning = r.get("winningTeamId"); break
        if winning is None and (final.get("resultList") or []):
            winning = (final["resultList"][0].get("winningTeamId"))

        result_label = "Unknown"
        my_team = current_match.get("my_team_id")
        if my_team is not None and isinstance(winning, int):
            result_label = "Win" if winning == my_team else "Loss"

        _finish_match(result_label, match_id or final.get("matchId"))

def _handle_result_old(data: dict):
    """
    Support the older format with 'FinalMatchResult' at the top-level.
    """
    if current_match["finished"]:
        return
    current_match["id"] = current_match["id"] or data.get("matchId")
    result = data.get("FinalMatchResult") or "Unknown"
    _finish_match(result)

def _finish_match(result_label: str, match_id: str | None = None):
    if current_match["finished"]:
        return
    current_match["finished"] = True

    global last_deck_sig
    if match_id:
        current_match["id"] = current_match["id"] or match_id
    ended_at = ts_now()

    match_data = {
        "id": current_match["id"],
        "result": result_label,
        "time": ended_at,
        "format": current_match.get("format"),
        "player_deck": current_match.get("player_deck"),
        "player_decklist": current_match.get("player_decklist"),
        "opponent": current_match.get("opponent"),
        "opponent_deck": current_match.get("opponent_deck"),
        "plays": current_match.get("plays", []),
    }

    _announce(
        f"📜 **Match finished!**\n"
        f"➡️ Result: **{result_label}**\n"
        f"🃏 You: {match_data['player_deck'] or '??'}\n"
        f"⚔️ Opponent: {match_data['opponent'] or '??'}"
    )
    save_match(match_data)

    # reset for next match
    current_match.update({
        "id": None, "format": None, "player_deck": None, "opponent": None,
        "opponent_deck": None, "player_decklist": None, "plays": [],
        "my_team_id": None, "my_seat": None, "opening_emitted": False,
        "finished": False,
    })
    _seen_play_instances.clear()
    _seen_plays.clear()
    instance_index.clear()
    zone_id_name.clear()
    last_deck_sig = None

# =======================
# Main
# =======================
if __name__ == "__main__":
    print("👀 Tailing Player.log…")
    for line in follow(LOG_PATH):
        try:
            events = feed_and_parse(line)
            for ev in events:
                if isinstance(ev, dict):
                    handle_top(ev)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print("⚠️ Processing error:", e)
