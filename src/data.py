import json
import re
import secrets
from pathlib import Path

CAMPAIGNS = Path(__file__).parent.parent / "campaigns"


def _path(slug, *parts):
    return CAMPAIGNS / slug / Path(*parts)


def _load(slug, *parts):
    p = _path(slug, *parts)
    if not p.exists():
        return {}
    text = p.read_text().strip()
    if not text:
        return {}
    return json.loads(text)


def _save(slug, data, *parts):
    p = _path(slug, *parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2))


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


# ── NPCs ──────────────────────────────────────────────────────────────────────

def get_npcs(slug, include_hidden=True):
    npcs = _load(slug, "world/npcs.json").get("npcs", [])
    if not include_hidden:
        npcs = [n for n in npcs if not n.get("hidden", False)]
    return npcs


def add_npc(slug, name, role, relationship, description, hidden=True, faction=""):
    data = _load(slug, "world/npcs.json")
    data.setdefault("npcs", []).append({
        "id": slugify(name),
        "name": name,
        "role": role,
        "relationship": relationship,
        "description": description,
        "hidden": hidden,
        "faction": faction,
        "log": [],
    })
    _save(slug, data, "world/npcs.json")


def update_npc(slug, npc_id, relationship=None, description=None, faction=None):
    data = _load(slug, "world/npcs.json")
    for npc in data.get("npcs", []):
        if npc["id"] == npc_id:
            if relationship is not None:
                npc["relationship"] = relationship
            if description is not None:
                npc["description"] = description
            if faction is not None:
                npc["faction"] = faction
    _save(slug, data, "world/npcs.json")


def delete_npc(slug, npc_id):
    data = _load(slug, "world/npcs.json")
    data["npcs"] = [n for n in data.get("npcs", []) if n["id"] != npc_id]
    _save(slug, data, "world/npcs.json")


def set_npc_hidden(slug, npc_id, hidden):
    data = _load(slug, "world/npcs.json")
    for npc in data.get("npcs", []):
        if npc["id"] == npc_id:
            npc["hidden"] = hidden
    _save(slug, data, "world/npcs.json")


def delete_npc_log_entry(slug, npc_id, entry_idx):
    data = _load(slug, "world/npcs.json")
    for npc in data.get("npcs", []):
        if npc["id"] == npc_id:
            log = npc.get("log", [])
            if 0 <= entry_idx < len(log):
                log.pop(entry_idx)
    _save(slug, data, "world/npcs.json")


def log_npc(slug, npc_id, session, note, polarity=None, intensity=None, event_type=None,
            visibility="public", ripple_source=None):
    data = _load(slug, "world/npcs.json")
    event_id = "evt_" + secrets.token_hex(3)
    for npc in data.get("npcs", []):
        if npc["id"] == npc_id:
            entry = {
                "id": event_id,
                "session": session,
                "note": note,
                "visibility": visibility,
            }
            if polarity in ("positive", "neutral", "negative"):
                entry["polarity"] = polarity
                entry["intensity"] = int(intensity) if intensity in (1, 2, 3) else 1
            if event_type:
                entry["event_type"] = event_type.strip()
            if ripple_source:
                entry["ripple_source"] = ripple_source
            npc.setdefault("log", []).append(entry)
    _save(slug, data, "world/npcs.json")
    return event_id


def _entry_visibility(entry):
    """Derive visibility from an entry, handling legacy dm_only flag."""
    if "visibility" in entry:
        return entry["visibility"]
    return "dm_only" if entry.get("dm_only") else "public"


def get_visible_log(log, known_events=None, is_dm=False):
    """Filter a log list to what this viewer can see."""
    result = []
    for entry in log:
        vis = _entry_visibility(entry)
        if is_dm:
            result.append(entry)
        elif vis == "dm_only":
            pass
        elif vis == "restricted":
            if known_events and entry.get("id") in known_events:
                result.append(entry)
        else:
            result.append(entry)
    return result


def compute_npc_relationship(npc, known_events=None, is_dm=False):
    """Derive relationship, trend, and top contributors from typed log entries.
    Falls back to stored relationship if no typed entries exist."""
    all_log = get_visible_log(npc.get("log", []), known_events=known_events, is_dm=is_dm)
    typed = [e for e in all_log if e.get("polarity") in ("positive", "negative", "neutral")]
    if not typed:
        return {"relationship": npc.get("relationship", "unknown"), "trend": None,
                "contributors": [], "computed": False, "score": None}

    max_session = max(e.get("session", 0) for e in typed)
    score = 0.0
    contributors = []
    for entry in typed:
        age = max_session - entry.get("session", 0)
        decay = 0.85 ** age
        intensity = entry.get("intensity", 1)
        sign = {"positive": 1, "negative": -1, "neutral": 0}.get(entry["polarity"], 0)
        weight = sign * intensity * decay
        score += weight
        if weight != 0:
            contributors.append({**entry, "_weight": round(weight, 2)})

    contributors.sort(key=lambda x: abs(x["_weight"]), reverse=True)

    if score >= 4:
        rel = "allied"
    elif score >= 1.5:
        rel = "friendly"
    elif score >= -1.5:
        rel = "neutral"
    else:
        rel = "hostile"

    recent = sorted(typed, key=lambda e: e.get("session", 0))[-3:]
    pos = sum(1 for e in recent if e.get("polarity") == "positive")
    neg = sum(1 for e in recent if e.get("polarity") == "negative")
    trend = "up" if pos >= 2 else ("down" if neg >= 2 else "stable")

    return {"relationship": rel, "trend": trend,
            "contributors": contributors[:5], "computed": True, "score": round(score, 2)}


# ── Factions ──────────────────────────────────────────────────────────────────

def get_factions(slug, include_hidden=True):
    factions = _load(slug, "world/factions.json").get("factions", [])
    if not include_hidden:
        factions = [f for f in factions if not f.get("hidden", False)]
    return factions


def add_faction(slug, name, relationship, description, hidden=True):
    data = _load(slug, "world/factions.json")
    data.setdefault("factions", []).append({
        "id": slugify(name),
        "name": name,
        "relationship": relationship,
        "description": description,
        "hidden": hidden,
        "log": [],
    })
    _save(slug, data, "world/factions.json")


def update_faction(slug, faction_id, relationship=None, description=None):
    data = _load(slug, "world/factions.json")
    for f in data.get("factions", []):
        if f["id"] == faction_id:
            if relationship is not None:
                f["relationship"] = relationship
            if description is not None:
                f["description"] = description
    _save(slug, data, "world/factions.json")


def delete_faction(slug, faction_id):
    data = _load(slug, "world/factions.json")
    data["factions"] = [f for f in data.get("factions", []) if f["id"] != faction_id]
    _save(slug, data, "world/factions.json")


def set_faction_hidden(slug, faction_id, hidden):
    data = _load(slug, "world/factions.json")
    for f in data.get("factions", []):
        if f["id"] == faction_id:
            f["hidden"] = hidden
    _save(slug, data, "world/factions.json")


def delete_faction_log_entry(slug, faction_id, entry_idx):
    data = _load(slug, "world/factions.json")
    for f in data.get("factions", []):
        if f["id"] == faction_id:
            log = f.get("log", [])
            if 0 <= entry_idx < len(log):
                log.pop(entry_idx)
    _save(slug, data, "world/factions.json")


def log_faction(slug, faction_id, session, note, polarity=None, intensity=None, event_type=None,
                visibility="public", ripple_source=None):
    data = _load(slug, "world/factions.json")
    event_id = "evt_" + secrets.token_hex(3)
    for f in data.get("factions", []):
        if f["id"] == faction_id:
            entry = {
                "id": event_id,
                "session": session,
                "note": note,
                "visibility": visibility,
            }
            if polarity in ("positive", "neutral", "negative"):
                entry["polarity"] = polarity
                entry["intensity"] = int(intensity) if intensity in (1, 2, 3) else 1
            if event_type:
                entry["event_type"] = event_type.strip()
            if ripple_source:
                entry["ripple_source"] = ripple_source
            f.setdefault("log", []).append(entry)
    _save(slug, data, "world/factions.json")
    return event_id


# ── Quests ────────────────────────────────────────────────────────────────────

def get_quests(slug, include_hidden=True):
    quests = _load(slug, "story/quests.json").get("quests", [])
    if not include_hidden:
        quests = [q for q in quests if not q.get("hidden", False)]
    return quests


def add_quest(slug, title, description, hidden=True):
    data = _load(slug, "story/quests.json")
    data.setdefault("quests", []).append({
        "id": slugify(title),
        "title": title,
        "status": "active",
        "description": description,
        "hidden": hidden,
        "objectives": [],
        "log": [],
    })
    _save(slug, data, "story/quests.json")


def add_objective(slug, quest_id, text):
    data = _load(slug, "story/quests.json")
    for q in data.get("quests", []):
        if q["id"] == quest_id:
            q.setdefault("objectives", []).append({"text": text, "done": False})
    _save(slug, data, "story/quests.json")


def delete_objective(slug, quest_id, obj_index):
    data = _load(slug, "story/quests.json")
    for q in data.get("quests", []):
        if q["id"] == quest_id:
            objs = q.get("objectives", [])
            if 0 <= obj_index < len(objs):
                objs.pop(obj_index)
    _save(slug, data, "story/quests.json")


def edit_objective(slug, quest_id, obj_index, text):
    data = _load(slug, "story/quests.json")
    for q in data.get("quests", []):
        if q["id"] == quest_id:
            objs = q.get("objectives", [])
            if 0 <= obj_index < len(objs):
                objs[obj_index]["text"] = text
    _save(slug, data, "story/quests.json")


def edit_quest_description(slug, quest_id, description):
    data = _load(slug, "story/quests.json")
    for q in data.get("quests", []):
        if q["id"] == quest_id:
            q["description"] = description
    _save(slug, data, "story/quests.json")


def set_objective(slug, quest_id, obj_index, done):
    data = _load(slug, "story/quests.json")
    for q in data.get("quests", []):
        if q["id"] == quest_id:
            objs = q.get("objectives", [])
            if 0 <= obj_index < len(objs):
                objs[obj_index]["done"] = done
    _save(slug, data, "story/quests.json")


def set_quest_status(slug, quest_id, status):
    data = _load(slug, "story/quests.json")
    for q in data.get("quests", []):
        if q["id"] == quest_id:
            q["status"] = status
    _save(slug, data, "story/quests.json")


def delete_quest(slug, quest_id):
    data = _load(slug, "story/quests.json")
    data["quests"] = [q for q in data.get("quests", []) if q["id"] != quest_id]
    _save(slug, data, "story/quests.json")


def set_quest_hidden(slug, quest_id, hidden):
    data = _load(slug, "story/quests.json")
    for q in data.get("quests", []):
        if q["id"] == quest_id:
            q["hidden"] = hidden
    _save(slug, data, "story/quests.json")


def delete_quest_log_entry(slug, quest_id, entry_idx):
    data = _load(slug, "story/quests.json")
    for q in data.get("quests", []):
        if q["id"] == quest_id:
            log = q.get("log", [])
            if 0 <= entry_idx < len(log):
                log.pop(entry_idx)
    _save(slug, data, "story/quests.json")


def log_quest(slug, quest_id, session, note):
    data = _load(slug, "story/quests.json")
    for q in data.get("quests", []):
        if q["id"] == quest_id:
            q.setdefault("log", []).append({"session": session, "note": note})
    _save(slug, data, "story/quests.json")


# ── Party ─────────────────────────────────────────────────────────────────────

def get_party(slug, include_hidden=True):
    chars = _load(slug, "party.json").get("characters", [])
    if not include_hidden:
        chars = [c for c in chars if not c.get("hidden", False)]
    return chars


def add_character(slug, name, race, char_class, level, notes="", hidden=False):
    data = _load(slug, "party.json")
    data.setdefault("characters", []).append({
        "name": name,
        "race": race,
        "class": char_class,
        "level": int(level),
        "status": "active",
        "hidden": hidden,
        "notes": notes,
        "known_events": [],
    })
    _save(slug, data, "party.json")


def set_character_hidden(slug, char_name, hidden):
    data = _load(slug, "party.json")
    for c in data.get("characters", []):
        if c["name"] == char_name:
            c["hidden"] = hidden
    _save(slug, data, "party.json")


def delete_character(slug, char_name):
    data = _load(slug, "party.json")
    data["characters"] = [c for c in data.get("characters", []) if c["name"] != char_name]
    _save(slug, data, "party.json")


def update_character(slug, char_name, level=None, status=None, notes=None):
    data = _load(slug, "party.json")
    for char in data.get("characters", []):
        if char["name"] == char_name:
            if level is not None:
                char["level"] = int(level)
            if status is not None:
                char["status"] = status
            if notes is not None:
                char["notes"] = notes
    _save(slug, data, "party.json")


def add_npc_relation(slug, npc_id, target_id, target_type, relation, weight):
    data = _load(slug, "world/npcs.json")
    for npc in data.get("npcs", []):
        if npc["id"] == npc_id:
            npc.setdefault("relations", []).append({
                "target": target_id, "target_type": target_type,
                "relation": relation, "weight": float(weight),
            })
    _save(slug, data, "world/npcs.json")


def remove_npc_relation(slug, npc_id, rel_idx):
    data = _load(slug, "world/npcs.json")
    for npc in data.get("npcs", []):
        if npc["id"] == npc_id:
            rels = npc.get("relations", [])
            if 0 <= rel_idx < len(rels):
                rels.pop(rel_idx)
    _save(slug, data, "world/npcs.json")


def add_faction_relation(slug, faction_id, target_id, target_type, relation, weight):
    data = _load(slug, "world/factions.json")
    for f in data.get("factions", []):
        if f["id"] == faction_id:
            f.setdefault("relations", []).append({
                "target": target_id, "target_type": target_type,
                "relation": relation, "weight": float(weight),
            })
    _save(slug, data, "world/factions.json")


def remove_faction_relation(slug, faction_id, rel_idx):
    data = _load(slug, "world/factions.json")
    for f in data.get("factions", []):
        if f["id"] == faction_id:
            rels = f.get("relations", [])
            if 0 <= rel_idx < len(rels):
                rels.pop(rel_idx)
    _save(slug, data, "world/factions.json")


def apply_ripple(slug, source_id, source_type, session_n, note, polarity, intensity,
                 event_type=None, visibility="public", source_event_id=None):
    """Log derived events to entities related to the source. Ripples inherit source visibility."""
    if not polarity:
        return []
    if source_type == "npc":
        source = next((n for n in _load(slug, "world/npcs.json").get("npcs", [])
                       if n["id"] == source_id), None)
    else:
        source = next((f for f in _load(slug, "world/factions.json").get("factions", [])
                       if f["id"] == source_id), None)
    if not source or not source.get("relations"):
        return []
    FLIP = {"positive": "negative", "negative": "positive", "neutral": "neutral"}
    ripple_source = {
        "entity_id": source_id,
        "entity_type": source_type,
        "event_id": source_event_id,
    }
    rippled = []
    for rel in source["relations"]:
        target_id = rel.get("target")
        target_type = rel.get("target_type", "npc")
        weight = float(rel.get("weight", 0.5))
        rpolarity = FLIP.get(polarity, polarity) if rel["relation"] == "rival" else polarity
        rintensity = max(1, round(intensity * weight))
        relation_label = "ally" if rel["relation"] == "ally" else "rival"
        rnote = f"Consequence of {source['name']} ({relation_label}): {note}"
        if target_type == "npc":
            log_npc(slug, target_id, session_n, rnote,
                    polarity=rpolarity, intensity=rintensity,
                    event_type=event_type, visibility=visibility,
                    ripple_source=ripple_source)
        else:
            log_faction(slug, target_id, session_n, rnote,
                        polarity=rpolarity, intensity=rintensity,
                        event_type=event_type, visibility=visibility,
                        ripple_source=ripple_source)
        rippled.append({"target": target_id, "target_type": target_type, "relation": rel["relation"]})
    return rippled


def edit_log_entry(slug, entity_id, entity_type, event_id, note=None, polarity=None,
                   intensity=None, visibility=None):
    """Edit a log entry by its UUID."""
    if entity_type == "npc":
        data = _load(slug, "world/npcs.json")
        entities = data.get("npcs", [])
        file_key = "world/npcs.json"
    else:
        data = _load(slug, "world/factions.json")
        entities = data.get("factions", [])
        file_key = "world/factions.json"
    for entity in entities:
        if entity["id"] == entity_id:
            for entry in entity.get("log", []):
                if entry.get("id") == event_id:
                    if note is not None:
                        entry["note"] = note
                    if polarity in ("positive", "neutral", "negative"):
                        entry["polarity"] = polarity
                    if intensity is not None:
                        entry["intensity"] = max(1, min(3, int(intensity)))
                    if visibility in ("public", "restricted", "dm_only"):
                        entry["visibility"] = visibility
    _save(slug, data, file_key)


def undo_ripple_chain(slug, source_event_id):
    """Delete all log entries across all entities that were rippled from source_event_id."""
    for file_key, entity_key in [("world/npcs.json", "npcs"), ("world/factions.json", "factions")]:
        data = _load(slug, file_key)
        changed = False
        for entity in data.get(entity_key, []):
            before = len(entity.get("log", []))
            entity["log"] = [
                e for e in entity.get("log", [])
                if not (e.get("ripple_source") or {}).get("event_id") == source_event_id
            ]
            if len(entity.get("log", [])) != before:
                changed = True
        if changed:
            _save(slug, data, file_key)


def reveal_event(slug, event_id, char_name):
    """Add event_id to a character's known_events list."""
    data = _load(slug, "party.json")
    for c in data.get("characters", []):
        if c["name"] == char_name:
            known = c.setdefault("known_events", [])
            if event_id not in known:
                known.append(event_id)
    _save(slug, data, "party.json")


def assign_character_user(slug, char_name, username):
    data = _load(slug, "party.json")
    for c in data.get("characters", []):
        if c["name"] == char_name:
            if username:
                c["assigned_user"] = username
            else:
                c.pop("assigned_user", None)
    _save(slug, data, "party.json")


def get_player_character(slug, username):
    """Return the character assigned to this username in this campaign, or None."""
    for c in _load(slug, "party.json").get("characters", []):
        if c.get("assigned_user") == username:
            return c
    return None


# ── Assets ────────────────────────────────────────────────────────────────────

def add_property(slug, name, notes=""):
    data = _load(slug, "assets.json")
    data.setdefault("property", []).append({"name": name, "notes": notes})
    _save(slug, data, "assets.json")


def remove_property(slug, idx):
    data = _load(slug, "assets.json")
    props = data.get("property", [])
    if 0 <= idx < len(props):
        props.pop(idx)
    _save(slug, data, "assets.json")


def get_assets(slug):
    return _load(slug, "assets.json")


def set_currency(slug, key, amount):
    data = _load(slug, "assets.json")
    data.setdefault("currency", {})[key] = int(amount)
    _save(slug, data, "assets.json")


def add_item(slug, name, notes=""):
    data = _load(slug, "assets.json")
    data.setdefault("items", []).append({"name": name, "notes": notes})
    _save(slug, data, "assets.json")


def remove_item(slug, item_index):
    data = _load(slug, "assets.json")
    items = data.get("items", [])
    if 0 <= item_index < len(items):
        items.pop(item_index)
    _save(slug, data, "assets.json")


def add_ship(slug, name, ship_type, hp="", weapons=None, crew=None, cargo=None, notes=""):
    data = _load(slug, "assets.json")
    data.setdefault("ships", []).append({
        "name": name,
        "type": ship_type,
        "hp": hp,
        "weapons": weapons or [],
        "crew": crew or [],
        "cargo": cargo or [],
        "notes": notes,
    })
    _save(slug, data, "assets.json")


def update_ship(slug, ship_idx, name, kind, hp, notes):
    data = _load(slug, "assets.json")
    ships = data.get("ships", [])
    if 0 <= ship_idx < len(ships):
        s = ships[ship_idx]
        if name: s["name"] = name
        s["type"] = kind
        s["hp"] = hp
        s["notes"] = notes
    _save(slug, data, "assets.json")


def add_crew(slug, ship_idx, member):
    data = _load(slug, "assets.json")
    ships = data.get("ships", [])
    if 0 <= ship_idx < len(ships):
        ships[ship_idx].setdefault("crew", []).append(member)
    _save(slug, data, "assets.json")


def remove_crew(slug, ship_idx, crew_idx):
    data = _load(slug, "assets.json")
    ships = data.get("ships", [])
    if 0 <= ship_idx < len(ships):
        crew = ships[ship_idx].get("crew", [])
        if 0 <= crew_idx < len(crew):
            crew.pop(crew_idx)
    _save(slug, data, "assets.json")


def add_cargo(slug, ship_idx, item):
    data = _load(slug, "assets.json")
    ships = data.get("ships", [])
    if 0 <= ship_idx < len(ships):
        ships[ship_idx].setdefault("cargo", []).append(item)
    _save(slug, data, "assets.json")


def remove_cargo(slug, ship_idx, cargo_idx):
    data = _load(slug, "assets.json")
    ships = data.get("ships", [])
    if 0 <= ship_idx < len(ships):
        cargo = ships[ship_idx].get("cargo", [])
        if 0 <= cargo_idx < len(cargo):
            cargo.pop(cargo_idx)
    _save(slug, data, "assets.json")


def delete_ship(slug, ship_idx):
    data = _load(slug, "assets.json")
    ships = data.get("ships", [])
    if 0 <= ship_idx < len(ships):
        ships.pop(ship_idx)
    _save(slug, data, "assets.json")


def delete_weapon(slug, ship_idx, weapon_idx):
    data = _load(slug, "assets.json")
    ships = data.get("ships", [])
    if 0 <= ship_idx < len(ships):
        weapons = ships[ship_idx].get("weapons", [])
        if 0 <= weapon_idx < len(weapons):
            weapons.pop(weapon_idx)
    _save(slug, data, "assets.json")


def add_weapon(slug, ship_idx, name, max_hp):
    data = _load(slug, "assets.json")
    ships = data.get("ships", [])
    if 0 <= ship_idx < len(ships):
        ships[ship_idx].setdefault("weapons", []).append({
            "name": name, "hp": max_hp, "max_hp": max_hp
        })
    _save(slug, data, "assets.json")


def set_weapon_hp(slug, ship_idx, weapon_idx, hp):
    data = _load(slug, "assets.json")
    ships = data.get("ships", [])
    if 0 <= ship_idx < len(ships):
        weapons = ships[ship_idx].get("weapons", [])
        if 0 <= weapon_idx < len(weapons):
            w = weapons[weapon_idx]
            w["hp"] = max(0, min(int(hp), w.get("max_hp", int(hp))))
    _save(slug, data, "assets.json")


# ── Stronghold ───────────────────────────────────────────────────────────────

def get_stronghold(slug):
    return _load(slug, "assets.json").get("stronghold", None)


def set_stronghold(slug, name, kind, location, condition, notes):
    data = _load(slug, "assets.json")
    existing = data.get("stronghold") or {}
    existing.update({
        "name": name,
        "type": kind,
        "location": location,
        "condition": condition,
        "notes": notes,
    })
    existing.setdefault("features", [])
    existing.setdefault("upgrades", [])
    data["stronghold"] = existing
    _save(slug, data, "assets.json")


def add_stronghold_feature(slug, text):
    data = _load(slug, "assets.json")
    data.setdefault("stronghold", {"features": [], "upgrades": []})
    data["stronghold"].setdefault("features", []).append(text)
    _save(slug, data, "assets.json")


def remove_stronghold_feature(slug, idx):
    data = _load(slug, "assets.json")
    features = data.get("stronghold", {}).get("features", [])
    if 0 <= idx < len(features):
        features.pop(idx)
    _save(slug, data, "assets.json")


def add_stronghold_upgrade(slug, text):
    data = _load(slug, "assets.json")
    data.setdefault("stronghold", {"features": [], "upgrades": []})
    data["stronghold"].setdefault("upgrades", []).append(text)
    _save(slug, data, "assets.json")


def remove_stronghold_upgrade(slug, idx):
    data = _load(slug, "assets.json")
    upgrades = data.get("stronghold", {}).get("upgrades", [])
    if 0 <= idx < len(upgrades):
        upgrades.pop(idx)
    _save(slug, data, "assets.json")


def delete_stronghold(slug):
    data = _load(slug, "assets.json")
    data.pop("stronghold", None)
    _save(slug, data, "assets.json")


# ── Session Plan ─────────────────────────────────────────────────────────────

def get_session_plan(slug):
    return _load(slug, "dm/session.json").get("plan", "")


def set_session_plan(slug, plan):
    data = _load(slug, "dm/session.json")
    data["plan"] = plan
    _save(slug, data, "dm/session.json")


def append_session_plan(slug, text):
    """Append a line to the session plan, creating it if empty."""
    data = _load(slug, "dm/session.json")
    current = data.get("plan", "").rstrip()
    data["plan"] = (current + "\n\n" + text).lstrip()
    _save(slug, data, "dm/session.json")


def get_world_state_summary(slug, current_session):
    """Build a structured world context for AI futures inference."""
    npcs = _load(slug, "world/npcs.json").get("npcs", [])
    factions = _load(slug, "world/factions.json").get("factions", [])
    quests = _load(slug, "story/quests.json").get("quests", [])

    intel = get_dm_intelligence(slug, current_session)

    def recent_events(log, n=4):
        visible = [e for e in log if _entry_visibility(e) != "dm_only"]
        return sorted(visible, key=lambda e: e.get("session", 0), reverse=True)[:n]

    def fmt_events(log):
        evts = recent_events(log)
        if not evts:
            return "no events logged"
        return "; ".join(
            f"S{e.get('session','?')} [{e.get('polarity','?')}x{e.get('intensity',1)}] {e.get('note','')}"
            for e in evts
        )

    # Top pressured entities (active + at-risk)
    hot_entities = []
    seen = set()
    for e in (intel.get("pressures", []) + intel.get("risks", []))[:6]:
        if e["id"] in seen:
            continue
        seen.add(e["id"])
        if e["kind"] == "npc":
            obj = next((n for n in npcs if n["id"] == e["id"]), None)
        else:
            obj = next((f for f in factions if f["id"] == e["id"]), None)
        if not obj:
            continue
        rel = compute_npc_relationship(obj, is_dm=True)
        hot_entities.append({
            "id": e["id"],
            "kind": e["kind"],
            "name": e["name"],
            "role": e.get("role", ""),
            "relationship": rel.get("relationship", "unknown"),
            "trend": rel.get("trend"),
            "score": rel.get("score"),
            "reason": e.get("reason", ""),
            "recent_events": fmt_events(obj.get("log", [])),
            "relations": obj.get("relations", []),
            "faction": obj.get("faction", "") if e["kind"] == "npc" else None,
        })

    # Stale threads
    stale_summary = [
        {"name": e["name"], "kind": e["kind"], "id": e["id"],
         "last_session": e.get("last_session"), "reason": e.get("reason", "")}
        for e in intel.get("stale", [])[:4]
    ]

    # Faction relation map (just hostile pairs)
    hostile_pairs = []
    for f in factions:
        for rel in f.get("relations", []):
            if rel.get("relation") == "rival" and rel.get("weight", 0) >= 0.5:
                hostile_pairs.append(
                    f"{f['name']} ↔ {rel['target']} (rival {rel['weight']}×)"
                )

    # Active quests
    active_quests = [
        {"title": q["title"], "description": q.get("description", ""),
         "last_session": max((e.get("session", 0) for e in q.get("log", [])), default=None)}
        for q in quests if q.get("status") == "active" and not q.get("hidden")
    ]

    return {
        "current_session": current_session,
        "hot_entities": hot_entities,
        "stale_threads": stale_summary,
        "hostile_pairs": hostile_pairs,
        "active_quests": active_quests,
        "session_plan": get_session_plan(slug),
    }


def get_session_notes(slug):
    return _load(slug, "dm/session.json").get("notes", "")


def set_session_notes(slug, notes):
    data = _load(slug, "dm/session.json")
    data["notes"] = notes
    _save(slug, data, "dm/session.json")


def _last_entry(log):
    """Return the most recent log entry or None."""
    return max(log, key=lambda e: e.get("session", 0)) if log else None


def get_recent_entities(slug, current_session, window=2, include_hidden=True):
    """Return NPCs and factions with log entries in the last `window` sessions."""
    threshold = max(1, current_session - window)
    recent = []
    for npc in _load(slug, "world/npcs.json").get("npcs", []):
        if npc.get("hidden") and not include_hidden:
            continue
        recent_log = [e for e in npc.get("log", []) if e.get("session", 0) >= threshold]
        if recent_log:
            recent.append({
                "kind": "npc",
                "id": npc["id"],
                "name": npc["name"],
                "role": npc.get("role", ""),
                "rel_data": compute_npc_relationship(npc, is_dm=True),
                "last_session": max(e.get("session", 0) for e in recent_log),
                "last_entry": _last_entry(recent_log),
            })
    for faction in _load(slug, "world/factions.json").get("factions", []):
        if faction.get("hidden") and not include_hidden:
            continue
        recent_log = [e for e in faction.get("log", []) if e.get("session", 0) >= threshold]
        if recent_log:
            recent.append({
                "kind": "faction",
                "id": faction["id"],
                "name": faction["name"],
                "role": faction.get("role", ""),
                "rel_data": {"relationship": faction.get("relationship", "unknown"),
                             "trend": None, "computed": False},
                "last_session": max(e.get("session", 0) for e in recent_log),
                "last_entry": _last_entry(recent_log),
            })
    recent.sort(key=lambda x: x["last_session"], reverse=True)
    return recent


def get_neglected_entities(slug, current_session, cold_after=3, min_events=3):
    """Entities with significant history but no activity in last `cold_after` sessions."""
    threshold = current_session - cold_after
    neglected = []
    for npc in _load(slug, "world/npcs.json").get("npcs", []):
        log = npc.get("log", [])
        if len(log) < min_events:
            continue
        last = max(e.get("session", 0) for e in log)
        if last <= threshold:
            neglected.append({
                "kind": "npc", "id": npc["id"], "name": npc["name"],
                "role": npc.get("role", ""),
                "rel_data": compute_npc_relationship(npc, is_dm=True),
                "last_session": last, "event_count": len(log),
                "last_entry": _last_entry(log),
            })
    for faction in _load(slug, "world/factions.json").get("factions", []):
        log = faction.get("log", [])
        if len(log) < min_events:
            continue
        last = max(e.get("session", 0) for e in log)
        if last <= threshold:
            neglected.append({
                "kind": "faction", "id": faction["id"], "name": faction["name"],
                "role": faction.get("role", ""),
                "rel_data": {"relationship": faction.get("relationship", "unknown"),
                             "trend": None, "computed": False},
                "last_session": last, "event_count": len(log),
                "last_entry": _last_entry(log),
            })
    neglected.sort(key=lambda x: x["last_session"], reverse=True)
    return neglected


def get_relationship_shifts(slug, current_session, include_hidden=True):
    """NPCs whose computed relationship badge changed in the last session."""
    shifts = []
    for npc in _load(slug, "world/npcs.json").get("npcs", []):
        if npc.get("hidden") and not include_hidden:
            continue
        typed = [e for e in npc.get("log", []) if e.get("polarity") in ("positive", "negative", "neutral")]
        if not typed:
            continue
        current = compute_npc_relationship(npc, is_dm=True)
        if not current["computed"]:
            continue
        prev_entries = [e for e in typed if e.get("session", 0) < current_session]
        if not prev_entries:
            continue
        prev = compute_npc_relationship({**npc, "log": prev_entries}, is_dm=True)
        if prev["relationship"] != current["relationship"]:
            direction = "improved" if current["score"] > prev.get("score", 0) else "worsened"
            shifts.append({
                "kind": "npc", "id": npc["id"], "name": npc["name"],
                "from_rel": prev["relationship"],
                "to_rel": current["relationship"],
                "direction": direction,
                "rel_data": current,
            })
    return shifts


def get_dm_intelligence(slug, current_session):
    """Return 4 ranked attention lists for the DM intelligence layer.
    Derived purely from event history — no manual curation."""
    npcs = _load(slug, "world/npcs.json").get("npcs", [])
    factions = _load(slug, "world/factions.json").get("factions", [])
    quests = _load(slug, "story/quests.json").get("quests", [])

    pressures = []  # 🔥 heating up
    stale = []      # ⏳ forgotten
    risks = []      # ⚠️ consequence
    gaps = []       # 🧩 narrative gaps

    for entity in list(npcs) + list(factions):
        is_npc = "class" not in entity and "relationship" in entity
        kind = "npc" if entity in npcs else "faction"
        log = entity.get("log", [])
        rel = compute_npc_relationship(entity, is_dm=True) if kind == "npc" else {
            "relationship": entity.get("relationship", "unknown"),
            "trend": None, "computed": False, "score": None,
        }

        # --- Active Pressure: recent + intensity + worsening ---
        recent = [e for e in log if e.get("session", 0) >= current_session - 2]
        if recent:
            pressure = sum(
                e.get("intensity", 1) * (0.85 ** max(0, current_session - e.get("session", current_session)))
                for e in recent if e.get("polarity") in ("positive", "negative", "neutral")
            )
            if rel.get("trend") == "down":
                pressure *= 1.5
            if pressure >= 1.0:
                parts = []
                if rel.get("trend") == "down":
                    parts.append("worsening")
                parts.append(f"{len(recent)} event{'s' if len(recent) != 1 else ''} in last 2 sessions")
                pressures.append({
                    "kind": kind, "id": entity["id"], "name": entity["name"],
                    "role": entity.get("role", ""), "rel_data": rel,
                    "score": round(pressure, 2), "reason": ", ".join(parts),
                    "last_session": max(e.get("session", 0) for e in recent),
                })

        # --- Stale Threads: significant history, gone quiet ---
        typed = [e for e in log if e.get("polarity") in ("positive", "negative", "neutral")]
        if len(typed) >= 3:
            last = max(e.get("session", 0) for e in log)
            silent = current_session - last
            if silent >= 3:
                importance = sum(e.get("intensity", 1) for e in typed)
                stale.append({
                    "kind": kind, "id": entity["id"], "name": entity["name"],
                    "role": entity.get("role", ""), "rel_data": rel,
                    "score": round(importance * (silent / 3), 2),
                    "last_session": last, "sessions_silent": silent,
                    "reason": f"{silent} sessions silent — {len(typed)} past interactions",
                    "last_entry": _last_entry(log),
                })

        # --- Consequence Risk: hostile score + recent negative events ---
        if kind == "npc" and rel.get("computed") and rel.get("score", 0) < -1:
            recent_neg = [e for e in log
                          if e.get("session", 0) >= current_session - 3
                          and e.get("polarity") == "negative"]
            if recent_neg or rel.get("trend") == "down":
                multiplier = 1.4 if rel.get("trend") == "down" else 1.0
                risks.append({
                    "kind": kind, "id": entity["id"], "name": entity["name"],
                    "role": entity.get("role", ""), "rel_data": rel,
                    "score": round(abs(rel["score"]) * multiplier, 2),
                    "reason": (
                        f"Score {rel['score']:+.1f}, "
                        + ("declining" if rel.get("trend") == "down" else "hostile")
                        + (f" — {len(recent_neg)} recent negative event{'s' if len(recent_neg) != 1 else ''}" if recent_neg else "")
                    ),
                })

        # --- Narrative Gaps: visible but no public events ---
        public_log = get_visible_log(log, is_dm=False)
        if not entity.get("hidden"):
            if entity.get("description") and not public_log:
                gaps.append({
                    "kind": kind, "id": entity["id"], "name": entity["name"],
                    "role": entity.get("role", ""), "rel_data": rel, "score": 2.0,
                    "reason": "Revealed to players but no public interactions logged",
                })
            elif not log:
                gaps.append({
                    "kind": kind, "id": entity["id"], "name": entity["name"],
                    "role": entity.get("role", ""), "rel_data": rel, "score": 1.0,
                    "reason": "No interactions logged",
                })

    # --- Quest staleness and gaps ---
    for quest in quests:
        if quest.get("hidden") or quest.get("status") != "active":
            continue
        qlog = quest.get("log", [])
        if not qlog:
            gaps.append({
                "kind": "quest", "id": quest["id"], "name": quest["title"],
                "role": "Active Quest", "rel_data": None, "score": 1.5,
                "reason": "Active quest — no progress logged yet",
            })
        else:
            last_q = max(e.get("session", 0) for e in qlog)
            silent_q = current_session - last_q
            if silent_q >= 3:
                stale.append({
                    "kind": "quest", "id": quest["id"], "name": quest["title"],
                    "role": "Active Quest", "rel_data": None,
                    "score": round(silent_q * 0.8, 2),
                    "last_session": last_q, "sessions_silent": silent_q,
                    "reason": f"Active quest, {silent_q} sessions without progress",
                    "last_entry": _last_entry(qlog),
                })

    for lst in [pressures, stale, risks, gaps]:
        lst.sort(key=lambda x: x["score"], reverse=True)

    return {
        "pressures": pressures[:5],
        "stale": stale[:5],
        "risks": risks[:5],
        "gaps": gaps[:5],
    }


def get_session_delta(slug, session_n):
    """Return all events logged in a specific session, grouped by entity, for the DM."""
    groups = []
    for npc in _load(slug, "world/npcs.json").get("npcs", []):
        entries = [e for e in npc.get("log", []) if e.get("session") == session_n]
        if entries:
            groups.append({
                "kind": "npc", "id": npc["id"], "name": npc["name"],
                "role": npc.get("role", ""),
                "rel_data": compute_npc_relationship(npc, is_dm=True),
                "entries": entries,
            })
    for faction in _load(slug, "world/factions.json").get("factions", []):
        entries = [e for e in faction.get("log", []) if e.get("session") == session_n]
        if entries:
            groups.append({
                "kind": "faction", "id": faction["id"], "name": faction["name"],
                "role": faction.get("role", ""),
                "rel_data": {"relationship": faction.get("relationship", "unknown"),
                             "trend": None, "computed": False},
                "entries": entries,
            })
    groups.sort(key=lambda g: g["name"])
    return groups


def get_all_log_entries(slug):
    entries = []
    for npc in _load(slug, "world/npcs.json").get("npcs", []):
        for entry in npc.get("log", []):
            entries.append({"source": npc["name"], "type": "NPC", **entry})
    for faction in _load(slug, "world/factions.json").get("factions", []):
        for entry in faction.get("log", []):
            entries.append({"source": faction["name"], "type": "Faction", **entry})
    for quest in _load(slug, "story/quests.json").get("quests", []):
        for entry in quest.get("log", []):
            entries.append({"source": quest["title"], "type": "Quest", **entry})
    entries.sort(key=lambda e: e.get("session", 0), reverse=True)
    return entries


# ── Journal ───────────────────────────────────────────────────────────────────

def get_journal(slug):
    return _load(slug, "journal.json").get("entries", [])


def post_journal(slug, session_n, date, recap):
    data = _load(slug, "journal.json")
    data.setdefault("entries", []).append({
        "session": session_n,
        "date": date,
        "recap": recap,
    })
    data["entries"].sort(key=lambda e: e.get("session", 0))
    _save(slug, data, "journal.json")


def delete_journal_entry(slug, idx):
    data = _load(slug, "journal.json")
    entries = data.get("entries", [])
    if 0 <= idx < len(entries):
        entries.pop(idx)
    _save(slug, data, "journal.json")


# ── Session helpers ──────────────────────────────────────────────────────────

def get_current_session(slug):
    max_log = 0
    for npc in _load(slug, "world/npcs.json").get("npcs", []):
        for entry in npc.get("log", []):
            max_log = max(max_log, entry.get("session", 0))
    for f in _load(slug, "world/factions.json").get("factions", []):
        for entry in f.get("log", []):
            max_log = max(max_log, entry.get("session", 0))
    for q in _load(slug, "story/quests.json").get("quests", []):
        for entry in q.get("log", []):
            max_log = max(max_log, entry.get("session", 0))
    max_journal = max(
        (e.get("session", 0) for e in _load(slug, "journal.json").get("entries", [])),
        default=0
    )
    return max(max_log, max_journal + 1)


# ── References ────────────────────────────────────────────────────────────────

def get_references(slug):
    return _load(slug, "references.json").get("references", [])


def delete_reference(slug, ref_id):
    data = _load(slug, "references.json")
    data["references"] = [r for r in data.get("references", []) if r["id"] != ref_id]
    _save(slug, data, "references.json")


def add_reference(slug, title, source, notes, columns, rows):
    data = _load(slug, "references.json")
    data.setdefault("references", []).append({
        "id": slugify(title),
        "title": title,
        "source": source,
        "notes": notes,
        "columns": columns,
        "rows": rows,
    })
    _save(slug, data, "references.json")
