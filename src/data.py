import json
import re
from pathlib import Path

CAMPAIGNS = Path(__file__).parent.parent / "campaigns"


def _path(slug, *parts):
    return CAMPAIGNS / slug / Path(*parts)


def _load(slug, *parts):
    p = _path(slug, *parts)
    if not p.exists():
        return {}
    return json.loads(p.read_text())


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


def add_npc(slug, name, role, relationship, description, hidden=True):
    data = _load(slug, "world/npcs.json")
    data.setdefault("npcs", []).append({
        "id": slugify(name),
        "name": name,
        "role": role,
        "relationship": relationship,
        "description": description,
        "hidden": hidden,
        "log": [],
    })
    _save(slug, data, "world/npcs.json")


def update_npc(slug, npc_id, relationship=None, description=None):
    data = _load(slug, "world/npcs.json")
    for npc in data.get("npcs", []):
        if npc["id"] == npc_id:
            if relationship is not None:
                npc["relationship"] = relationship
            if description is not None:
                npc["description"] = description
    _save(slug, data, "world/npcs.json")


def set_npc_hidden(slug, npc_id, hidden):
    data = _load(slug, "world/npcs.json")
    for npc in data.get("npcs", []):
        if npc["id"] == npc_id:
            npc["hidden"] = hidden
    _save(slug, data, "world/npcs.json")


def log_npc(slug, npc_id, session, note):
    data = _load(slug, "world/npcs.json")
    for npc in data.get("npcs", []):
        if npc["id"] == npc_id:
            npc.setdefault("log", []).append({"session": session, "note": note})
    _save(slug, data, "world/npcs.json")


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


def set_faction_hidden(slug, faction_id, hidden):
    data = _load(slug, "world/factions.json")
    for f in data.get("factions", []):
        if f["id"] == faction_id:
            f["hidden"] = hidden
    _save(slug, data, "world/factions.json")


def log_faction(slug, faction_id, session, note):
    data = _load(slug, "world/factions.json")
    for f in data.get("factions", []):
        if f["id"] == faction_id:
            f.setdefault("log", []).append({"session": session, "note": note})
    _save(slug, data, "world/factions.json")


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


def set_quest_hidden(slug, quest_id, hidden):
    data = _load(slug, "story/quests.json")
    for q in data.get("quests", []):
        if q["id"] == quest_id:
            q["hidden"] = hidden
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
    })
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


# ── Assets ────────────────────────────────────────────────────────────────────

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


# ── Session Plan ─────────────────────────────────────────────────────────────

def get_session_plan(slug):
    return _load(slug, "dm/session.json").get("plan", "")


def set_session_plan(slug, plan):
    data = _load(slug, "dm/session.json")
    data["plan"] = plan
    _save(slug, data, "dm/session.json")


def get_session_notes(slug):
    return _load(slug, "dm/session.json").get("notes", "")


def set_session_notes(slug, notes):
    data = _load(slug, "dm/session.json")
    data["notes"] = notes
    _save(slug, data, "dm/session.json")


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


# ── References ────────────────────────────────────────────────────────────────

def get_references(slug):
    return _load(slug, "references.json").get("references", [])


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
