import json
import re
import secrets
import uuid
from pathlib import Path

CAMPAIGNS = Path(__file__).parent.parent / "campaigns"


def build_branch_chain(active_branch, all_branches):
    """Return [root_branch, ..., active_branch] ordered root-first."""
    chain = []
    b = active_branch
    while b:
        chain.insert(0, b)
        parent_id = b.get("parent_branch")
        b = next((x for x in all_branches if x["id"] == parent_id), None) if parent_id else None
    return chain


def filter_log_for_branch(log, active_branch, all_branches):
    """Return entries visible in the given branch (or main timeline if None)."""
    if not active_branch:
        return [e for e in log if not e.get("branch")]
    chain = build_branch_chain(active_branch, all_branches)
    result = []
    for e in log:
        branch_id = e.get("branch")
        sess = e.get("session", 0)
        if not branch_id:
            if sess <= chain[0]["fork_point"]:
                result.append(e)
        else:
            for i, b in enumerate(chain):
                if branch_id == b["id"]:
                    if i == len(chain) - 1:
                        result.append(e)
                    elif sess <= chain[i + 1]["fork_point"]:
                        result.append(e)
                    break
    return result


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


def _load_party(slug):
    """Load party.json, auto-migrating old flat {characters:[]} format to {parties:[...]}."""
    data = _load(slug, "party.json")
    if "characters" in data and "parties" not in data:
        data = {"parties": [{"id": "default", "name": "The Party", "characters": data["characters"]}]}
        _save(slug, data, "party.json")
    elif "parties" not in data:
        data = {"parties": [{"id": "default", "name": "The Party", "characters": []}]}
        _save(slug, data, "party.json")
    return data


def _all_chars(data):
    """Return flat list of all character dicts across all parties (references, not copies)."""
    return [c for p in data.get("parties", []) for c in p.get("characters", [])]


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


# ── NPCs ──────────────────────────────────────────────────────────────────────

def get_npcs(slug, include_hidden=True):
    npcs = _load(slug, "world/npcs.json").get("npcs", [])
    for npc in npcs:
        # normalize legacy single-faction string to list
        if "factions" not in npc:
            legacy = npc.get("faction", "")
            npc["factions"] = [legacy] if legacy else []
        npc.setdefault("hidden_factions", [])
    if not include_hidden:
        npcs = [n for n in npcs if not n.get("hidden", False)]
    return npcs


def add_npc(slug, name, role, relationship, description, hidden=True, factions=None, hidden_factions=None, image_url=None, dm_notes=None):
    data = _load(slug, "world/npcs.json")
    entry = {
        "id": slugify(name),
        "name": name,
        "role": role,
        "relationship": relationship,
        "description": description,
        "hidden": hidden,
        "factions": [f for f in (factions or []) if f],
        "hidden_factions": [f for f in (hidden_factions or []) if f],
        "log": [],
    }
    if image_url:
        entry["image_url"] = image_url
    if dm_notes:
        entry["dm_notes"] = dm_notes
    data.setdefault("npcs", []).append(entry)
    _save(slug, data, "world/npcs.json")


def update_npc(slug, npc_id, name=None, role=None, relationship=None, description=None, factions=None, hidden_factions=None, score_offset=None, dm_notes=None, image_url=None):
    data = _load(slug, "world/npcs.json")
    for npc in data.get("npcs", []):
        if npc["id"] == npc_id:
            if name:
                npc["name"] = name
            if role is not None:
                npc["role"] = role
            if relationship is not None:
                npc["relationship"] = relationship
            if description is not None:
                npc["description"] = description
            if dm_notes is not None:
                if dm_notes:
                    npc["dm_notes"] = dm_notes
                else:
                    npc.pop("dm_notes", None)
            if image_url is not None:
                npc["image_url"] = image_url
            if factions is not None:
                npc["factions"] = [f for f in factions if f]
                npc.pop("faction", None)  # remove legacy field if present
            if hidden_factions is not None:
                npc["hidden_factions"] = [f for f in hidden_factions if f]
            if score_offset is not None:
                npc["score_offset"] = score_offset
    _save(slug, data, "world/npcs.json")


def delete_npc(slug, npc_id):
    data = _load(slug, "world/npcs.json")
    data["npcs"] = [n for n in data.get("npcs", []) if n["id"] != npc_id]
    _save(slug, data, "world/npcs.json")


def npc_to_party_member(slug, npc_id):
    """Convert an NPC directly into a new party character, transferring all history.

    Creates a party character from the NPC's data, rewrites every actor_id /
    ripple_source / relation target that referenced npc_id to _char_{slug},
    then removes the NPC entry.
    """
    npc_data = _load(slug, "world/npcs.json")
    npcs = npc_data.get("npcs", [])
    source = next((n for n in npcs if n["id"] == npc_id), None)
    if not source:
        return False

    char_name = source["name"]
    char_slug = f"_char_{slugify(char_name)}"

    char = {
        "name": char_name,
        "race": "",
        "class": source.get("role", ""),
        "level": 1,
        "status": "active",
        "hidden": source.get("hidden", False),
        "notes": source.get("description", "") or "",
        "log": source.get("log", []),
        "relations": source.get("relations", []),
        "factions": source.get("factions") or [],
        "hidden_factions": source.get("hidden_factions") or [],
        "dead": source.get("dead", False),
    }
    for field in ("dead_session", "conditions", "known_events", "score_offset"):
        if source.get(field):
            char[field] = source[field]

    party_data = _load_party(slug)
    party_data["parties"][0]["characters"].append(char)

    npc_data["npcs"] = [n for n in npcs if n["id"] != npc_id]
    _save(slug, npc_data, "world/npcs.json")
    _save(slug, party_data, "party.json")

    def _rewrite_log(log):
        for e in log:
            if e.get("actor_id") == npc_id and e.get("actor_type") == "npc":
                e["actor_id"] = char_name
                e["actor_type"] = "char"
            rs = e.get("ripple_source")
            if rs and rs.get("entity_id") == npc_id and rs.get("entity_type") == "npc":
                rs["entity_id"] = char_name
                rs["entity_type"] = "char"

    def _rewrite_relations(entity):
        existing = {r.get("target") for r in entity.get("relations", []) if r.get("target") != npc_id}
        new_rels = []
        for r in entity.get("relations", []):
            if r.get("target") == npc_id:
                if char_slug not in existing:
                    r = dict(r)
                    r["target"] = char_slug
                    new_rels.append(r)
                    existing.add(char_slug)
            else:
                new_rels.append(r)
        entity["relations"] = new_rels

    npc_data2 = _load(slug, "world/npcs.json")
    for n in npc_data2.get("npcs", []):
        _rewrite_log(n.get("log", []))
        _rewrite_relations(n)
    _save(slug, npc_data2, "world/npcs.json")

    fac_data = _load(slug, "world/factions.json")
    for f in fac_data.get("factions", []):
        _rewrite_log(f.get("log", []))
        _rewrite_relations(f)
    _save(slug, fac_data, "world/factions.json")

    loc_data = _load(slug, "world/locations.json")
    for loc in loc_data.get("locations", []):
        _rewrite_log(loc.get("log", []))
    _save(slug, loc_data, "world/locations.json")

    party_data2 = _load_party(slug)
    for p in party_data2.get("parties", []):
        for c in p.get("characters", []):
            _rewrite_log(c.get("log", []))
            _rewrite_relations(c)
    _save(slug, party_data2, "party.json")

    meta = _load(slug, "campaign.json")
    _rewrite_log(meta.get("party_group_log", []))
    _save(slug, meta, "campaign.json")

    return True


def npc_join_party(slug, npc_id, char_name):
    """Merge an NPC into a party character, transferring all log/relation history.

    All log entries, relations, and factions from the NPC are absorbed into
    the party character. Every actor_id/ripple_source reference to the NPC is
    rewritten to (char_name, "char"). Relations pointing to the NPC's id are
    repointed to _char_{slug}. The NPC is then removed.
    """
    npc_data = _load(slug, "world/npcs.json")
    npcs = npc_data.get("npcs", [])
    source = next((n for n in npcs if n["id"] == npc_id), None)
    if not source:
        return False

    party_data = _load_party(slug)
    char = next(
        (c for p in party_data.get("parties", []) for c in p.get("characters", [])
         if c["name"] == char_name),
        None
    )
    if not char:
        return False

    char_slug = f"_char_{slugify(char_name)}"

    # ── 1. Merge logs ──────────────────────────────────────────────────────
    combined = char.get("log", []) + source.get("log", [])
    combined.sort(key=lambda e: e.get("session", 0))
    char["log"] = combined

    # ── 2. Merge relations (skip dupes) ────────────────────────────────────
    existing_rel_targets = {r.get("target") for r in char.get("relations", [])}
    for rel in source.get("relations", []):
        if rel.get("target") not in existing_rel_targets and rel.get("target") != char_slug:
            char.setdefault("relations", []).append(rel)
            existing_rel_targets.add(rel.get("target"))

    # ── 3. Merge factions ──────────────────────────────────────────────────
    merged = list({*char.get("factions", []), *source.get("factions", [])})
    if merged:
        char["factions"] = merged
    merged_h = list({*char.get("hidden_factions", []), *source.get("hidden_factions", [])})
    if merged_h:
        char["hidden_factions"] = merged_h

    # ── 4. Remove source NPC and save both files ───────────────────────────
    npc_data["npcs"] = [n for n in npcs if n["id"] != npc_id]
    _save(slug, npc_data, "world/npcs.json")
    _save(slug, party_data, "party.json")

    # ── 5. Rewrite cross-references ────────────────────────────────────────
    def _rewrite_log(log):
        for e in log:
            if e.get("actor_id") == npc_id and e.get("actor_type") == "npc":
                e["actor_id"] = char_name
                e["actor_type"] = "char"
            rs = e.get("ripple_source")
            if rs and rs.get("entity_id") == npc_id and rs.get("entity_type") == "npc":
                rs["entity_id"] = char_name
                rs["entity_type"] = "char"

    def _rewrite_relations(entity):
        existing = {r.get("target") for r in entity.get("relations", []) if r.get("target") != npc_id}
        new_rels = []
        for r in entity.get("relations", []):
            if r.get("target") == npc_id:
                if char_slug not in existing:
                    r = dict(r)
                    r["target"] = char_slug
                    new_rels.append(r)
                    existing.add(char_slug)
            else:
                new_rels.append(r)
        entity["relations"] = new_rels

    npc_data2 = _load(slug, "world/npcs.json")
    for n in npc_data2.get("npcs", []):
        _rewrite_log(n.get("log", []))
        _rewrite_relations(n)
    _save(slug, npc_data2, "world/npcs.json")

    fac_data = _load(slug, "world/factions.json")
    for f in fac_data.get("factions", []):
        _rewrite_log(f.get("log", []))
        _rewrite_relations(f)
    _save(slug, fac_data, "world/factions.json")

    loc_data = _load(slug, "world/locations.json")
    for loc in loc_data.get("locations", []):
        _rewrite_log(loc.get("log", []))
    _save(slug, loc_data, "world/locations.json")

    party_data2 = _load_party(slug)
    for p in party_data2.get("parties", []):
        for c in p.get("characters", []):
            _rewrite_log(c.get("log", []))
            _rewrite_relations(c)
    _save(slug, party_data2, "party.json")

    meta = _load(slug, "campaign.json")
    _rewrite_log(meta.get("party_group_log", []))
    _save(slug, meta, "campaign.json")

    return True


def collapse_npc_into(slug, source_id, target_id):
    """Merge source NPC into target NPC, then delete source.

    All log entries, relations, and factions from source are absorbed into
    target. Every actor_id / ripple_source.entity_id reference to source_id
    is rewritten to target_id across all entity files and party_group_log.
    Relations on other entities that point to source_id are repointed to
    target_id (or dropped if target already has an edge to that entity).
    """
    if source_id == target_id:
        return False

    npc_data = _load(slug, "world/npcs.json")
    npcs = npc_data.get("npcs", [])
    source = next((n for n in npcs if n["id"] == source_id), None)
    target = next((n for n in npcs if n["id"] == target_id), None)
    if not source or not target:
        return False

    # ── 1. Merge logs ──────────────────────────────────────────────────────
    combined = target.get("log", []) + source.get("log", [])
    combined.sort(key=lambda e: e.get("session", 0))
    target["log"] = combined

    # ── 2. Merge relations (skip dupes already on target) ──────────────────
    existing_rel_targets = {r.get("target") for r in target.get("relations", [])}
    for rel in source.get("relations", []):
        if rel.get("target") not in existing_rel_targets and rel.get("target") != target_id:
            target.setdefault("relations", []).append(rel)

    # ── 3. Merge factions ──────────────────────────────────────────────────
    merged_factions = list({*target.get("factions", []), *source.get("factions", [])})
    if merged_factions:
        target["factions"] = merged_factions
    merged_hfactions = list({*target.get("hidden_factions", []), *source.get("hidden_factions", [])})
    if merged_hfactions:
        target["hidden_factions"] = merged_hfactions

    # ── 4. Remove source from NPC list ────────────────────────────────────
    npc_data["npcs"] = [n for n in npcs if n["id"] != source_id]
    _save(slug, npc_data, "world/npcs.json")

    # ── 5. Rewrite all cross-references in every data file ────────────────
    def _rewrite_log(log):
        for e in log:
            if e.get("actor_id") == source_id and e.get("actor_type") == "npc":
                e["actor_id"] = target_id
            rs = e.get("ripple_source")
            if rs and rs.get("entity_id") == source_id and rs.get("entity_type") == "npc":
                rs["entity_id"] = target_id

    def _rewrite_relations(entity):
        rels = entity.get("relations", [])
        # repoint source → target; drop if target already has an edge there
        existing = {r.get("target") for r in rels if r.get("target") != source_id}
        new_rels = []
        for r in rels:
            if r.get("target") == source_id:
                if target_id not in existing:
                    r = dict(r)
                    r["target"] = target_id
                    new_rels.append(r)
                    existing.add(target_id)
            else:
                new_rels.append(r)
        entity["relations"] = new_rels

    # NPCs
    npc_data2 = _load(slug, "world/npcs.json")
    for n in npc_data2.get("npcs", []):
        _rewrite_log(n.get("log", []))
        _rewrite_relations(n)
        if n.get("id") == target_id:
            _rewrite_log(n.get("log", []))
    _save(slug, npc_data2, "world/npcs.json")

    # Factions
    fac_data = _load(slug, "world/factions.json")
    for f in fac_data.get("factions", []):
        _rewrite_log(f.get("log", []))
        _rewrite_relations(f)
    _save(slug, fac_data, "world/factions.json")

    # Locations
    loc_data = _load(slug, "world/locations.json")
    for loc in loc_data.get("locations", []):
        _rewrite_log(loc.get("log", []))
    _save(slug, loc_data, "world/locations.json")

    # Party characters
    party_data = _load(slug, "party.json")
    for pg in party_data.get("parties", party_data.get("characters", [])):
        chars = pg.get("characters", [pg]) if "characters" in pg else [pg]
        for c in chars:
            _rewrite_log(c.get("log", []))
            _rewrite_relations(c)
    _save(slug, party_data, "party.json")

    # campaign.json party_group_log
    meta = _load(slug, "campaign.json")
    _rewrite_log(meta.get("party_group_log", []))
    _save(slug, meta, "campaign.json")

    return True


def set_npc_dead(slug, npc_id, dead, dead_session=None):
    data = _load(slug, "world/npcs.json")
    for npc in data.get("npcs", []):
        if npc["id"] == npc_id:
            npc["dead"] = dead
            if dead and dead_session is not None:
                npc["dead_session"] = dead_session
            elif not dead:
                npc.pop("dead_session", None)
            break
    _save(slug, data, "world/npcs.json")


def set_npc_party_affiliate(slug, npc_id, value):
    data = _load(slug, "world/npcs.json")
    for npc in data.get("npcs", []):
        if npc["id"] == npc_id:
            if value:
                npc["party_affiliate"] = True
            else:
                npc.pop("party_affiliate", None)
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
            visibility="public", ripple_source=None, actor_id=None, actor_type=None, branch=None,
            axis=None, actor_dm_only=False, location_id=None):
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
            if actor_id:
                entry["actor_id"] = actor_id
                if actor_type:
                    entry["actor_type"] = actor_type
                if actor_dm_only:
                    entry["actor_dm_only"] = True
            if branch:
                entry["branch"] = branch
            if axis in ("formal", "personal"):
                entry["axis"] = axis
            if location_id:
                entry["location_id"] = location_id
            npc.setdefault("log", []).append(entry)
    _save(slug, data, "world/npcs.json")
    return event_id


def _entry_visibility(entry):
    """Derive visibility from an entry, handling legacy dm_only flag."""
    if "visibility" in entry:
        return entry["visibility"]
    return "dm_only" if entry.get("dm_only") else "public"


def get_visible_log(log, known_events=None, is_dm=False):
    """Filter a log list to what this viewer can see. Soft-deleted entries are never included."""
    result = []
    for entry in log:
        if entry.get("deleted"):
            continue
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


def entity_snapshot(slug, entity_id, entity_type):
    """Snapshot an entity's relationship state and log count for diff comparison."""
    if entity_type == "npc":
        for npc in get_npcs(slug, include_hidden=True):
            if npc["id"] == entity_id:
                rel = compute_npc_relationship(npc, is_dm=True)
                return {"name": npc["name"], "log_count": len(npc.get("log", [])),
                        "relationship": rel["relationship"], "score": rel.get("score")}
    elif entity_type == "condition":
        for c in get_conditions(slug, include_hidden=True, include_resolved=True):
            if c["id"] == entity_id:
                sev = compute_condition_severity(c, is_dm=True)
                return {"name": c["name"], "log_count": len(c.get("log", [])),
                        "relationship": sev["severity"], "score": sev.get("score")}
    else:
        for f in get_factions(slug, include_hidden=True):
            if f["id"] == entity_id:
                return {"name": f["name"], "log_count": len(f.get("log", [])),
                        "relationship": f.get("relationship", "unknown"), "score": None}
    return None


_TIER_MIN = {"allied": 6.0, "friendly": 3.0, "neutral": -3.0, "hostile": -6.0}


def _score_to_rel(score):
    if score >= 6:   return "allied"
    if score >= 3:   return "friendly"
    if score >= -3:  return "neutral"
    return "hostile"


def _compute_axis_score(entries, latest_session):
    """Decay-weighted score for a single axis subset of typed entries.
    No floor or offset — axis scores are raw so they can reveal contradictions."""
    if not entries:
        return None
    score = sum(
        {"positive": 1, "negative": -1, "neutral": 0}.get(e["polarity"], 0)
        * e.get("intensity", 1)
        * (0.85 ** (latest_session - e.get("session", 0)))
        for e in entries
    )
    return _score_to_rel(score)


def compute_npc_relationship(npc, known_events=None, is_dm=False, max_session=None,
                             branch_id=None, fork_point=None,
                             active_branch=None, all_branches=None):
    """Derive relationship, trend, and top contributors from typed log entries.
    Falls back to stored relationship if no typed entries exist.
    max_session: only include entries from sessions <= max_session.
    active_branch/all_branches: recursive branch chain filter (preferred over branch_id/fork_point).
    branch_id/fork_point: legacy flat-branch filter (used when active_branch not supplied)."""
    all_log = get_visible_log(npc.get("log", []), known_events=known_events, is_dm=is_dm)
    if max_session is not None:
        all_log = [e for e in all_log if e.get("session", 0) <= max_session]
    if active_branch is not None:
        all_log = filter_log_for_branch(all_log, active_branch, all_branches or [])
    elif branch_id is not None:
        all_log = [e for e in all_log if
                   (not e.get("branch") and e.get("session", 0) <= (fork_point or 0)) or
                   e.get("branch") == branch_id]
    else:
        all_log = [e for e in all_log if not e.get("branch")]
    typed = [e for e in all_log if e.get("polarity") in ("positive", "negative", "neutral")]
    if not typed:
        return {"relationship": npc.get("relationship", "unknown"), "trend": None,
                "contributors": [], "computed": False, "score": None,
                "score_natural": None, "score_offset": npc.get("score_offset", 0)}

    latest_session = max(e.get("session", 0) for e in typed)
    score = 0.0
    contributors = []
    for entry in typed:
        age = latest_session - entry.get("session", 0)
        decay = 0.85 ** age
        intensity = entry.get("intensity", 1)
        sign = {"positive": 1, "negative": -1, "neutral": 0}.get(entry["polarity"], 0)
        weight = sign * intensity * decay
        score += weight
        if weight != 0:
            contributors.append({**entry, "_weight": round(weight, 2)})

    contributors.sort(key=lambda x: abs(x["_weight"]), reverse=True)

    offset = npc.get("score_offset", 0)
    adjusted = score + offset
    # Stored relationship acts as a minimum floor — events can push higher but not below
    stored_rel = npc.get("relationship", "unknown")
    if stored_rel in _TIER_MIN:
        adjusted = max(adjusted, _TIER_MIN[stored_rel])
    rel = _score_to_rel(adjusted)

    recent = sorted(typed, key=lambda e: e.get("session", 0))[-3:]
    pos = sum(1 for e in recent if e.get("polarity") == "positive")
    neg = sum(1 for e in recent if e.get("polarity") == "negative")
    trend = "up" if pos >= 2 else ("down" if neg >= 2 else "stable")

    # Build chronological timeline with running cumulative (raw, non-decayed)
    timeline = sorted(typed, key=lambda e: e.get("session", 0))
    running = 0
    for e in timeline:
        raw = {"positive": 1, "negative": -1, "neutral": 0}.get(e["polarity"], 0) * e.get("intensity", 1)
        running += raw
        e = dict(e)
    tl = []
    running = 0
    for e in timeline:
        raw = {"positive": 1, "negative": -1, "neutral": 0}.get(e["polarity"], 0) * e.get("intensity", 1)
        running += raw
        tl.append({**e, "_raw": raw, "_cumulative": running})

    # Dual-axis: formal (institutional/structural) vs personal (emotional/sentiment)
    formal_rel = _compute_axis_score(
        [e for e in typed if e.get("axis") == "formal"], latest_session)
    personal_rel = _compute_axis_score(
        [e for e in typed if e.get("axis") == "personal"], latest_session)
    has_conflict = bool(formal_rel and personal_rel and formal_rel != personal_rel)

    return {"relationship": rel, "trend": trend,
            "contributors": contributors[:5], "timeline": tl, "computed": True,
            "score": round(adjusted, 2), "score_natural": round(score, 2),
            "score_offset": round(offset, 2),
            "formal_relationship": formal_rel,
            "personal_relationship": personal_rel,
            "has_conflict": has_conflict}


# ── Factions ──────────────────────────────────────────────────────────────────

def get_factions(slug, include_hidden=True):
    factions = _load(slug, "world/factions.json").get("factions", [])
    if not include_hidden:
        factions = [f for f in factions if not f.get("hidden", False)]
    return factions


def add_faction(slug, name, relationship, description, hidden=True, image_url=None, dm_notes=None, role=None):
    data = _load(slug, "world/factions.json")
    entry = {
        "id": slugify(name),
        "name": name,
        "relationship": relationship,
        "description": description,
        "hidden": hidden,
        "log": [],
    }
    if role:
        entry["role"] = role
    if image_url:
        entry["image_url"] = image_url
    if dm_notes:
        entry["dm_notes"] = dm_notes
    data.setdefault("factions", []).append(entry)
    _save(slug, data, "world/factions.json")


def update_faction(slug, faction_id, relationship=None, description=None, score_offset=None, dm_notes=None, image_url=None, role=None):
    data = _load(slug, "world/factions.json")
    for f in data.get("factions", []):
        if f["id"] == faction_id:
            if role is not None:
                if role:
                    f["role"] = role
                else:
                    f.pop("role", None)
            if relationship is not None:
                f["relationship"] = relationship
            if description is not None:
                f["description"] = description
            if dm_notes is not None:
                if dm_notes:
                    f["dm_notes"] = dm_notes
                else:
                    f.pop("dm_notes", None)
            if image_url is not None:
                f["image_url"] = image_url
            if score_offset is not None:
                f["score_offset"] = score_offset
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


def set_faction_party_affiliated(slug, faction_id, value):
    data = _load(slug, "world/factions.json")
    for f in data.get("factions", []):
        if f["id"] == faction_id:
            if value:
                f["party_affiliated"] = True
            else:
                f.pop("party_affiliated", None)
    _save(slug, data, "world/factions.json")


def set_faction_char_member(slug, faction_id, char_name, affiliated):
    data = _load(slug, "world/factions.json")
    for f in data.get("factions", []):
        if f["id"] == faction_id:
            members = f.setdefault("affiliated_chars", [])
            if affiliated and char_name not in members:
                members.append(char_name)
            elif not affiliated and char_name in members:
                members.remove(char_name)
            if not f["affiliated_chars"]:
                f.pop("affiliated_chars")
            break
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
                visibility="public", ripple_source=None, actor_id=None, actor_type=None, branch=None,
                axis=None, actor_dm_only=False, location_id=None):
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
            if actor_id:
                entry["actor_id"] = actor_id
                if actor_type:
                    entry["actor_type"] = actor_type
                if actor_dm_only:
                    entry["actor_dm_only"] = True
            if branch:
                entry["branch"] = branch
            if axis in ("formal", "personal"):
                entry["axis"] = axis
            if location_id:
                entry["location_id"] = location_id
            f.setdefault("log", []).append(entry)
    _save(slug, data, "world/factions.json")
    return event_id


# ── Locations ─────────────────────────────────────────────────────────────────

def get_locations(slug, include_hidden=True):
    locations = _load(slug, "world/locations.json").get("locations", [])
    if not include_hidden:
        locations = [l for l in locations if not l.get("hidden", False)]
    return locations


def get_location(slug, location_id):
    return next((l for l in get_locations(slug) if l["id"] == location_id), None)


def add_location(slug, name, role=None, description="", hidden=False, dm_notes=None):
    data = _load(slug, "world/locations.json")
    entry = {
        "id": slugify(name),
        "name": name,
        "description": description,
        "hidden": hidden,
        "log": [],
    }
    if role:
        entry["role"] = role
    if dm_notes:
        entry["dm_notes"] = dm_notes
    data.setdefault("locations", []).append(entry)
    _save(slug, data, "world/locations.json")
    return entry["id"]


def update_location(slug, location_id, name=None, role=None, description=None, dm_notes=None):
    data = _load(slug, "world/locations.json")
    for loc in data.get("locations", []):
        if loc["id"] == location_id:
            if name is not None:
                loc["name"] = name
            if role is not None:
                if role:
                    loc["role"] = role
                else:
                    loc.pop("role", None)
            if description is not None:
                loc["description"] = description
            if dm_notes is not None:
                if dm_notes:
                    loc["dm_notes"] = dm_notes
                else:
                    loc.pop("dm_notes", None)
    _save(slug, data, "world/locations.json")


def set_location_hidden(slug, location_id, hidden):
    data = _load(slug, "world/locations.json")
    for loc in data.get("locations", []):
        if loc["id"] == location_id:
            loc["hidden"] = hidden
    _save(slug, data, "world/locations.json")


def delete_location(slug, location_id):
    data = _load(slug, "world/locations.json")
    data["locations"] = [l for l in data.get("locations", []) if l["id"] != location_id]
    _save(slug, data, "world/locations.json")


def log_location(slug, location_id, session, note, visibility="public", polarity=None,
                 intensity=None, event_type=None, actor_id=None, actor_type=None):
    data = _load(slug, "world/locations.json")
    event_id = "evt_" + secrets.token_hex(3)
    for loc in data.get("locations", []):
        if loc["id"] == location_id:
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
            if actor_id:
                entry["actor_id"] = actor_id
                if actor_type:
                    entry["actor_type"] = actor_type
            loc.setdefault("log", []).append(entry)
    _save(slug, data, "world/locations.json")
    return event_id


def delete_location_log_entry(slug, location_id, entry_idx):
    data = _load(slug, "world/locations.json")
    for loc in data.get("locations", []):
        if loc["id"] == location_id:
            log = loc.get("log", [])
            if 0 <= entry_idx < len(log):
                log.pop(entry_idx)
    _save(slug, data, "world/locations.json")


# ── Inter-faction relationship tracking ──────────────────────────────────────

def compute_inter_faction_score(entries):
    """Score a faction-to-faction relationship from log entries that have actor_id set."""
    typed = [e for e in entries if e.get("polarity") in ("positive", "negative", "neutral")]
    if not typed:
        return {"relationship": "unknown", "trend": None, "computed": False, "score": None}
    max_session = max(e.get("session", 0) for e in typed)
    score = 0.0
    for entry in typed:
        age = max_session - entry.get("session", 0)
        decay = 0.85 ** age
        sign = {"positive": 1, "negative": -1, "neutral": 0}.get(entry["polarity"], 0)
        score += sign * entry.get("intensity", 1) * decay
    if score >= 4:    rel = "allied"
    elif score >= 1:  rel = "friendly"
    elif score >= -1: rel = "neutral"
    elif score >= -4: rel = "hostile"
    else:             rel = "war"
    recent = sorted(typed, key=lambda e: e.get("session", 0))[-3:]
    pos = sum(1 for e in recent if e.get("polarity") == "positive")
    neg = sum(1 for e in recent if e.get("polarity") == "negative")
    trend = "improving" if pos >= 2 else ("deteriorating" if neg >= 2 else "stable")

    def _ifrel(s):
        if s >= 4:    return "allied"
        if s >= 1:    return "friendly"
        if s >= -1:   return "neutral"
        if s >= -4:   return "hostile"
        return "war"

    def _ifaxis(entries):
        if not entries:
            return None
        s = sum(
            {"positive": 1, "negative": -1, "neutral": 0}.get(e["polarity"], 0)
            * e.get("intensity", 1)
            * (0.85 ** (max_session - e.get("session", 0)))
            for e in entries
        )
        return _ifrel(s)

    formal_rel = _ifaxis([e for e in typed if e.get("axis") == "formal"])
    personal_rel = _ifaxis([e for e in typed if e.get("axis") == "personal"])
    has_conflict = bool(formal_rel and personal_rel and formal_rel != personal_rel)

    return {"relationship": rel, "trend": trend, "computed": True, "score": round(score, 2),
            "formal_relationship": formal_rel, "personal_relationship": personal_rel,
            "has_conflict": has_conflict}


def get_inter_faction_relations(slug):
    """Scan all NPC/faction logs for entries with actor_id and return computed pairwise scores."""
    pair_entries = {}

    def _register(entity_id, entry):
        actor_id = entry.get("actor_id")
        if not actor_id or actor_id == entity_id:
            return
        key = tuple(sorted([entity_id, actor_id]))
        pair_entries.setdefault(key, []).append(entry)

    for npc in _load(slug, "world/npcs.json").get("npcs", []):
        for entry in npc.get("log", []):
            if not entry.get("deleted"):
                _register(npc["id"], entry)
    for faction in _load(slug, "world/factions.json").get("factions", []):
        for entry in faction.get("log", []):
            if not entry.get("deleted"):
                _register(faction["id"], entry)

    results = []
    for (a_id, b_id), entries in pair_entries.items():
        score_data = compute_inter_faction_score(entries)
        results.append({"a_id": a_id, "b_id": b_id, **score_data})
    return results


def get_inter_entity_relations(slug, max_session=None, branch_id=None, fork_point=None,
                               active_branch=None, all_branches=None):
    """Like get_inter_faction_relations but tracks entity types (npc/faction) for each side.
    max_session: only include entries from sessions <= max_session.
    active_branch/all_branches: recursive branch chain filter (preferred).
    branch_id/fork_point: legacy flat-branch filter."""
    pair_entries = {}
    entity_types = {}

    if active_branch is not None:
        _chain = build_branch_chain(active_branch, all_branches or [])

    def _include(entry):
        if max_session is not None and entry.get("session", 0) > max_session:
            return False
        if active_branch is not None:
            return entry in filter_log_for_branch([entry], active_branch, all_branches or [])
        if branch_id is not None:
            return ((not entry.get("branch") and entry.get("session", 0) <= (fork_point or 0)) or
                    entry.get("branch") == branch_id)
        return not entry.get("branch")

    for npc in _load(slug, "world/npcs.json").get("npcs", []):
        entity_types[npc["id"]] = "npc"
        for entry in npc.get("log", []):
            if entry.get("deleted") or not _include(entry):
                continue
            actor_id = entry.get("actor_id")
            if not actor_id or actor_id == npc["id"]:
                continue
            if entry.get("actor_type"):
                entity_types[actor_id] = entry["actor_type"]
            key = tuple(sorted([npc["id"], actor_id]))
            pair_entries.setdefault(key, []).append(entry)

    for faction in _load(slug, "world/factions.json").get("factions", []):
        entity_types[faction["id"]] = "faction"
        for entry in faction.get("log", []):
            if entry.get("deleted") or not _include(entry):
                continue
            actor_id = entry.get("actor_id")
            if not actor_id or actor_id == faction["id"]:
                continue
            if entry.get("actor_type"):
                entity_types[actor_id] = entry["actor_type"]
            key = tuple(sorted([faction["id"], actor_id]))
            pair_entries.setdefault(key, []).append(entry)

    for char in _all_chars(_load_party(slug)):
        char_id = char["name"]
        entity_types[char_id] = "char"
        for entry in char.get("log", []):
            if entry.get("deleted") or not _include(entry):
                continue
            actor_id = entry.get("actor_id")
            if not actor_id or actor_id == char_id:
                continue
            if entry.get("actor_type"):
                entity_types[actor_id] = entry["actor_type"]
            key = tuple(sorted([char_id, actor_id]))
            pair_entries.setdefault(key, []).append(entry)

    results = []
    for (a_id, b_id), entries in pair_entries.items():
        score_data = compute_inter_faction_score(entries)
        all_dm_only = all(e.get("actor_dm_only") for e in entries)
        results.append({
            "a_id": a_id, "b_id": b_id,
            "a_type": entity_types.get(a_id, "npc"),
            "b_type": entity_types.get(b_id, "npc"),
            "dm_only": all_dm_only,
            **score_data,
        })
    return results


# ── Conditions ────────────────────────────────────────────────────────────────

def get_conditions(slug, include_hidden=True, include_resolved=False):
    conditions = _load(slug, "world/conditions.json").get("conditions", [])
    if not include_hidden:
        conditions = [c for c in conditions if not c.get("hidden", False)]
    if not include_resolved:
        conditions = [c for c in conditions if c.get("status", "active") != "resolved"]
    return conditions


def add_condition(slug, name, region, effect_type, effect_scope, magnitude, description="", hidden=True):
    data = _load(slug, "world/conditions.json")
    data.setdefault("conditions", []).append({
        "id": slugify(name),
        "name": name,
        "region": region,
        "effect_type": effect_type,
        "effect_scope": effect_scope,
        "magnitude": magnitude,
        "status": "active",
        "description": description,
        "hidden": hidden,
        "relations": [],
        "log": [],
    })
    _save(slug, data, "world/conditions.json")


def update_condition(slug, condition_id, region=None, effect_type=None, effect_scope=None,
                     magnitude=None, description=None):
    data = _load(slug, "world/conditions.json")
    for c in data.get("conditions", []):
        if c["id"] == condition_id:
            if region is not None:
                c["region"] = region
            if effect_type is not None:
                c["effect_type"] = effect_type
            if effect_scope is not None:
                c["effect_scope"] = effect_scope
            if magnitude is not None:
                c["magnitude"] = magnitude
            if description is not None:
                c["description"] = description
    _save(slug, data, "world/conditions.json")


def delete_condition(slug, condition_id):
    data = _load(slug, "world/conditions.json")
    data["conditions"] = [c for c in data.get("conditions", []) if c["id"] != condition_id]
    _save(slug, data, "world/conditions.json")


def set_condition_hidden(slug, condition_id, hidden):
    data = _load(slug, "world/conditions.json")
    for c in data.get("conditions", []):
        if c["id"] == condition_id:
            c["hidden"] = hidden
    _save(slug, data, "world/conditions.json")


def set_condition_status(slug, condition_id, status):
    data = _load(slug, "world/conditions.json")
    for c in data.get("conditions", []):
        if c["id"] == condition_id:
            c["status"] = status
    _save(slug, data, "world/conditions.json")


def delete_condition_log_entry(slug, condition_id, entry_idx):
    data = _load(slug, "world/conditions.json")
    for c in data.get("conditions", []):
        if c["id"] == condition_id:
            log = c.get("log", [])
            if 0 <= entry_idx < len(log):
                log.pop(entry_idx)
    _save(slug, data, "world/conditions.json")


def log_condition(slug, condition_id, session, note, polarity=None, intensity=None,
                  event_type=None, visibility="public", ripple_source=None, location_id=None,
                  actor_id=None, actor_type=None):
    data = _load(slug, "world/conditions.json")
    event_id = "evt_" + secrets.token_hex(3)
    for c in data.get("conditions", []):
        if c["id"] == condition_id:
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
            if location_id:
                entry["location_id"] = location_id
            if actor_id:
                entry["actor_id"] = actor_id
                entry["actor_type"] = actor_type or "npc"
            c.setdefault("log", []).append(entry)
    _save(slug, data, "world/conditions.json")
    return event_id


def add_condition_relation(slug, condition_id, target_id, target_type, relation, weight):
    data = _load(slug, "world/conditions.json")
    for c in data.get("conditions", []):
        if c["id"] == condition_id:
            c.setdefault("relations", []).append({
                "target": target_id, "target_type": target_type,
                "relation": relation, "weight": float(weight),
            })
    _save(slug, data, "world/conditions.json")


def remove_condition_relation(slug, condition_id, rel_idx):
    data = _load(slug, "world/conditions.json")
    for c in data.get("conditions", []):
        if c["id"] == condition_id:
            rels = c.get("relations", [])
            if 0 <= rel_idx < len(rels):
                rels.pop(rel_idx)
    _save(slug, data, "world/conditions.json")


def compute_condition_severity(condition, known_events=None, is_dm=False):
    """Derive severity level and trend from event history.
    Negative polarity = condition intensifying; positive = condition improving."""
    all_log = get_visible_log(condition.get("log", []), known_events=known_events, is_dm=is_dm)
    typed = [e for e in all_log if e.get("polarity") in ("positive", "negative", "neutral")]
    if not typed:
        return {"severity": "unknown", "trend": None, "computed": False, "score": None}

    max_session = max(e.get("session", 0) for e in typed)
    score = 0.0
    for entry in typed:
        age = max_session - entry.get("session", 0)
        decay = 0.85 ** age
        intensity = entry.get("intensity", 1)
        sign = {"negative": 1, "positive": -1, "neutral": 0}.get(entry["polarity"], 0)
        score += sign * intensity * decay

    if score >= 3:
        severity = "critical"
    elif score >= 1:
        severity = "significant"
    elif score >= -1:
        severity = "moderate"
    else:
        severity = "subsiding"

    recent = sorted(typed, key=lambda e: e.get("session", 0))[-3:]
    neg = sum(1 for e in recent if e.get("polarity") == "negative")
    pos = sum(1 for e in recent if e.get("polarity") == "positive")
    trend = "worsening" if neg >= 2 else ("improving" if pos >= 2 else "stable")

    return {"severity": severity, "trend": trend, "computed": True, "score": round(score, 2)}


# ── Quests ────────────────────────────────────────────────────────────────────

def get_quests(slug, include_hidden=True):
    quests = _load(slug, "story/quests.json").get("quests", [])
    if not include_hidden:
        quests = [q for q in quests if not q.get("hidden", False)]
    return quests


def add_quest(slug, title, description, hidden=True, status="active"):
    data = _load(slug, "story/quests.json")
    if status not in ("active", "complete", "failed"):
        status = "active"
    data.setdefault("quests", []).append({
        "id": slugify(title),
        "title": title,
        "status": status,
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

def get_parties(slug):
    """Return list of party dicts: [{id, name, characters:[...]}, ...]."""
    return _load_party(slug)["parties"]


def get_party(slug, party_id=None, include_hidden=True):
    """Return characters for one party (first party if party_id=None)."""
    parties = get_parties(slug)
    if party_id:
        party = next((p for p in parties if p["id"] == party_id), None) or (parties[0] if parties else {"characters": []})
    else:
        party = parties[0] if parties else {"characters": []}
    chars = party.get("characters", [])
    return chars if include_hidden else [c for c in chars if not c.get("hidden", False)]


def get_all_party_characters(slug, include_hidden=True):
    """Return all characters across all parties."""
    data = _load_party(slug)
    chars = _all_chars(data)
    return chars if include_hidden else [c for c in chars if not c.get("hidden", False)]


def add_party(slug, name):
    data = _load_party(slug)
    base_id = slugify(name) or f"party_{len(data['parties'])+1}"
    party_id = base_id
    existing = {p["id"] for p in data["parties"]}
    n = 2
    while party_id in existing:
        party_id = f"{base_id}_{n}"; n += 1
    data["parties"].append({"id": party_id, "name": name, "characters": []})
    _save(slug, data, "party.json")
    return party_id


def rename_party(slug, party_id, name):
    data = _load_party(slug)
    for p in data["parties"]:
        if p["id"] == party_id:
            p["name"] = name
            break
    _save(slug, data, "party.json")


def delete_party(slug, party_id):
    data = _load_party(slug)
    data["parties"] = [p for p in data["parties"] if p["id"] != party_id]
    _save(slug, data, "party.json")


def add_character(slug, name, race, char_class, level, notes="", hidden=False, party_id=None, session=None):
    data = _load_party(slug)
    if party_id:
        target = next((p for p in data["parties"] if p["id"] == party_id), None) or data["parties"][0]
    else:
        target = data["parties"][0]
    char = {
        "name": name,
        "race": race,
        "class": char_class,
        "level": int(level),
        "status": "active",
        "hidden": hidden,
        "notes": notes,
        "known_events": [],
    }
    if session is not None:
        char["session_joined"] = int(session)
    target.setdefault("characters", []).append(char)
    _save(slug, data, "party.json")


def log_character(slug, char_name, session, note, polarity=None, intensity=None,
                  event_type=None, visibility="public", actor_id=None, actor_type=None,
                  actor_dm_only=False, location_id=None):
    data = _load_party(slug)
    event_id = "evt_" + secrets.token_hex(3)
    for char in _all_chars(data):
        if char["name"] == char_name:
            entry = {"id": event_id, "session": session, "note": note, "visibility": visibility}
            if polarity in ("positive", "neutral", "negative"):
                entry["polarity"] = polarity
                entry["intensity"] = int(intensity) if intensity in (1, 2, 3) else 1
            if event_type:
                entry["event_type"] = event_type.strip()
            if actor_id:
                entry["actor_id"] = actor_id
                if actor_type:
                    entry["actor_type"] = actor_type
                if actor_dm_only:
                    entry["actor_dm_only"] = True
            if location_id:
                entry["location_id"] = location_id
            char.setdefault("log", []).append(entry)
    _save(slug, data, "party.json")
    return event_id


def log_party_group(slug, session, note, polarity=None, intensity=None, event_type=None,
                    visibility="public", actor_id=None, actor_type=None, actor_dm_only=False,
                    location_id=None, party_name=None):
    data = _load(slug, "campaign.json")
    event_id = "evt_" + secrets.token_hex(3)
    entry = {"id": event_id, "session": session, "note": note, "visibility": visibility}
    if party_name:
        entry["party_name"] = party_name
    if polarity in ("positive", "neutral", "negative"):
        entry["polarity"] = polarity
        entry["intensity"] = int(intensity) if intensity in (1, 2, 3) else 1
    if event_type:
        entry["event_type"] = event_type.strip()
    if actor_id:
        entry["actor_id"] = actor_id
        if actor_type:
            entry["actor_type"] = actor_type
        if actor_dm_only:
            entry["actor_dm_only"] = True
    if location_id:
        entry["location_id"] = location_id
    data.setdefault("party_group_log", []).append(entry)
    _save(slug, data, "campaign.json")
    return event_id


def set_character_hidden(slug, char_name, hidden):
    data = _load_party(slug)
    for c in _all_chars(data):
        if c["name"] == char_name:
            c["hidden"] = hidden
    _save(slug, data, "party.json")


def set_character_dead(slug, char_name, dead):
    data = _load_party(slug)
    for c in _all_chars(data):
        if c["name"] == char_name:
            c["dead"] = dead
            if not dead and c.get("status") == "dead":
                c["status"] = "active"
    _save(slug, data, "party.json")


def delete_character(slug, char_name):
    data = _load_party(slug)
    for p in data["parties"]:
        p["characters"] = [c for c in p.get("characters", []) if c["name"] != char_name]
    _save(slug, data, "party.json")


def update_character(slug, char_name, level=None, status=None, notes=None, new_name=None, factions=None):
    data = _load_party(slug)
    for char in _all_chars(data):
        if char["name"] == char_name:
            if level is not None:
                char["level"] = int(level)
            if status is not None:
                char["status"] = status
            if notes is not None:
                char["notes"] = notes
            if factions is not None:
                char["factions"] = [f for f in factions if f]
            if new_name and new_name != char_name:
                char["name"] = new_name
    _save(slug, data, "party.json")
    if new_name and new_name != char_name:
        old_id = f"_char_{slugify(char_name)}"
        new_id = f"_char_{slugify(new_name)}"
        for fname in ("world/npcs.json", "world/factions.json"):
            wdata = _load(slug, fname)
            key = "npcs" if "npcs" in wdata else "factions"
            for entity in wdata.get(key, []):
                for rel in entity.get("relations", []):
                    if rel.get("target") == old_id:
                        rel["target"] = new_id
            _save(slug, wdata, fname)


def add_npc_relation(slug, npc_id, target_id, target_type, relation, weight, dm_only=False):
    data = _load(slug, "world/npcs.json")
    for npc in data.get("npcs", []):
        if npc["id"] == npc_id:
            rels = [r for r in npc.get("relations", []) if r.get("target") != target_id]
            entry = {"target": target_id, "target_type": target_type,
                     "relation": relation, "weight": float(weight)}
            if dm_only:
                entry["dm_only"] = True
            rels.append(entry)
            npc["relations"] = rels
    _save(slug, data, "world/npcs.json")


def remove_npc_relation(slug, npc_id, rel_idx):
    data = _load(slug, "world/npcs.json")
    for npc in data.get("npcs", []):
        if npc["id"] == npc_id:
            rels = npc.get("relations", [])
            if 0 <= rel_idx < len(rels):
                rels.pop(rel_idx)
    _save(slug, data, "world/npcs.json")


def add_faction_relation(slug, faction_id, target_id, target_type, relation, weight, dm_only=False):
    data = _load(slug, "world/factions.json")
    for f in data.get("factions", []):
        if f["id"] == faction_id:
            entry = {"target": target_id, "target_type": target_type,
                     "relation": relation, "weight": float(weight)}
            if dm_only:
                entry["dm_only"] = True
            f.setdefault("relations", []).append(entry)
    _save(slug, data, "world/factions.json")


def remove_faction_relation(slug, faction_id, rel_idx):
    data = _load(slug, "world/factions.json")
    for f in data.get("factions", []):
        if f["id"] == faction_id:
            rels = f.get("relations", [])
            if 0 <= rel_idx < len(rels):
                rels.pop(rel_idx)
    _save(slug, data, "world/factions.json")


def get_branches(slug):
    return _load(slug, "campaign.json").get("branches", [])


def create_branch(slug, name, fork_point, parent_branch=None):
    import datetime
    data = _load(slug, "campaign.json")
    branch_id = "br_" + secrets.token_hex(3)
    entry = {
        "id": branch_id,
        "name": name,
        "fork_point": int(fork_point),
        "created": datetime.date.today().isoformat(),
    }
    if parent_branch:
        entry["parent_branch"] = parent_branch
    data.setdefault("branches", []).append(entry)
    _save(slug, data, "campaign.json")
    return branch_id


def delete_branch(slug, branch_id):
    data = _load(slug, "campaign.json")
    data["branches"] = [b for b in data.get("branches", []) if b["id"] != branch_id]
    _save(slug, data, "campaign.json")
    npc_data = _load(slug, "world/npcs.json")
    for npc in npc_data.get("npcs", []):
        npc["log"] = [e for e in npc.get("log", []) if e.get("branch") != branch_id]
    _save(slug, npc_data, "world/npcs.json")
    faction_data = _load(slug, "world/factions.json")
    for f in faction_data.get("factions", []):
        f["log"] = [e for e in f.get("log", []) if e.get("branch") != branch_id]
    _save(slug, faction_data, "world/factions.json")


def add_party_relation(slug, target_id, target_type, relation, weight):
    data = _load(slug, "campaign.json")
    data.setdefault("party_relations", []).append({
        "target": target_id, "target_type": target_type,
        "relation": relation, "weight": float(weight),
    })
    _save(slug, data, "campaign.json")


def remove_party_relation(slug, rel_idx):
    data = _load(slug, "campaign.json")
    rels = data.get("party_relations", [])
    if 0 <= rel_idx < len(rels):
        rels.pop(rel_idx)
        data["party_relations"] = rels
    _save(slug, data, "campaign.json")


def apply_ripple(slug, source_id, source_type, session_n, note, polarity, intensity,
                 event_type=None, visibility="public", source_event_id=None, branch=None,
                 actor_id=None, actor_type=None):
    """Log derived events to entities related to the source. Ripples inherit source visibility.

    Fires in two passes:
    1. Outbound — entities listed in source's own relations (source declared them relevant).
    2. Inbound — entities that listed source in THEIR relations (they declared source relevant),
       skipping any already hit by the outbound pass to avoid double-firing.
    """
    if not polarity:
        return []
    if source_type == "npc":
        source = next((n for n in _load(slug, "world/npcs.json").get("npcs", [])
                       if n["id"] == source_id), None)
    elif source_type == "condition":
        source = next((c for c in _load(slug, "world/conditions.json").get("conditions", [])
                       if c["id"] == source_id), None)
    else:
        source = next((f for f in _load(slug, "world/factions.json").get("factions", [])
                       if f["id"] == source_id), None)
    if not source:
        return []
    _dead_npc_ids = {n["id"] for n in _load(slug, "world/npcs.json").get("npcs", []) if n.get("dead")}
    FLIP = {"positive": "negative", "negative": "positive", "neutral": "neutral"}
    ripple_source = {
        "entity_id": source_id,
        "entity_type": source_type,
        "event_id": source_event_id,
    }
    rippled = []
    already_fired = set()

    def _fire(target_id, target_type, rel_type, weight):
        if target_type == "npc" and target_id in _dead_npc_ids:
            return
        if actor_id and target_id == actor_id:
            return  # target caused the original event — they already have it, don't fire back
        if rel_type == "rival":
            return  # rival ripples inflate the general score in wrong direction — skip
        rpolarity = FLIP.get(polarity, polarity) if rel_type == "rival" else polarity
        rintensity = max(1, round(intensity * weight))
        relation_label = "ally" if rel_type == "ally" else "rival"
        rnote = f"Consequence of {source['name']} ({relation_label}): {note}"
        if target_type == "npc":
            log_npc(slug, target_id, session_n, rnote,
                    polarity=rpolarity, intensity=rintensity,
                    event_type=event_type, visibility=visibility,
                    ripple_source=ripple_source,
                    actor_id=actor_id, actor_type=actor_type,
                    branch=branch)
        elif target_type == "condition":
            log_condition(slug, target_id, session_n, rnote,
                          polarity=rpolarity, intensity=rintensity,
                          event_type=event_type, visibility=visibility,
                          ripple_source=ripple_source)
        elif target_type in ("char", "party"):
            log_party_group(slug, session_n, rnote,
                            polarity=rpolarity, intensity=rintensity,
                            event_type=event_type, visibility=visibility,
                            actor_id=source_id, actor_type=source_type)
        else:
            log_faction(slug, target_id, session_n, rnote,
                        polarity=rpolarity, intensity=rintensity,
                        event_type=event_type, visibility=visibility,
                        ripple_source=ripple_source,
                        actor_id=actor_id, actor_type=actor_type,
                        branch=branch)
        rippled.append({"target": target_id, "target_type": target_type, "relation": rel_type})

    def _rel_type(rel):
        """Get the effective relation type; dual-axis edges use formal_relation."""
        return rel.get("relation") or rel.get("formal_relation") or "ally"

    # Pass 1: outbound — source declared these targets relevant
    for rel in source.get("relations", []):
        target_id = rel.get("target")
        target_type = rel.get("target_type", "npc")
        if not target_id:
            continue
        _fire(target_id, target_type, _rel_type(rel), float(rel.get("weight", 0.5)))
        already_fired.add(target_id)

    # Pass 2: inbound — other entities declared source as their target
    for npc in _load(slug, "world/npcs.json").get("npcs", []):
        if npc["id"] == source_id or npc["id"] in already_fired:
            continue
        if npc.get("dead"):
            continue
        for rel in npc.get("relations", []):
            if rel.get("target") == source_id:
                _fire(npc["id"], "npc", _rel_type(rel), float(rel.get("weight", 0.5)))
                already_fired.add(npc["id"])
                break
    for faction in _load(slug, "world/factions.json").get("factions", []):
        if faction["id"] == source_id or faction["id"] in already_fired:
            continue
        for rel in faction.get("relations", []):
            if rel.get("target") == source_id:
                _fire(faction["id"], "faction", _rel_type(rel), float(rel.get("weight", 0.5)))
                already_fired.add(faction["id"])
                break

    return rippled


# ── Pending ripples ────────────────────────────────────────────────────────────

def get_pending_ripples(slug):
    return _load(slug, "dm/pending_ripples.json").get("ripples", [])


def add_pending_ripple(slug, source_entity_id, source_entity_type, source_entity_name,
                       source_event_id, session_n, note, polarity, intensity, event_type, visibility):
    import datetime
    data = _load(slug, "dm/pending_ripples.json")
    ripples = data.get("ripples", [])
    ripples.append({
        "id": str(uuid.uuid4()),
        "created_at": datetime.datetime.utcnow().isoformat(),
        "session_n": session_n,
        "source_entity_id": source_entity_id,
        "source_entity_type": source_entity_type,
        "source_entity_name": source_entity_name,
        "source_event_id": source_event_id,
        "note": note,
        "polarity": polarity,
        "intensity": intensity,
        "event_type": event_type,
        "visibility": visibility,
    })
    _save(slug, {"ripples": ripples}, "dm/pending_ripples.json")


def resolve_pending_ripple(slug, ripple_id):
    data = _load(slug, "dm/pending_ripples.json")
    ripples = [r for r in data.get("ripples", []) if r["id"] != ripple_id]
    _save(slug, {"ripples": ripples}, "dm/pending_ripples.json")


def apply_ripple_scoped(slug, source_id, source_type, session_n, note, polarity, intensity,
                        event_type=None, visibility="public", source_event_id=None,
                        depth=1, extra_entities=None):
    """BFS ripple with configurable depth.
    depth=1: direct relations only. depth=2: +1 hop (intensity halved each hop beyond first).
    depth=None: full graph BFS. extra_entities: [{id, type}] receive a direct witness ripple.
    """
    if not polarity:
        return []

    FLIP = {"positive": "negative", "negative": "positive", "neutral": "neutral"}
    ripple_source = {"entity_id": source_id, "entity_type": source_type, "event_id": source_event_id}

    def _get_rels(eid, etype):
        if etype == "npc":
            ents = _load(slug, "world/npcs.json").get("npcs", [])
        elif etype == "faction":
            ents = _load(slug, "world/factions.json").get("factions", [])
        else:
            return []
        e = next((x for x in ents if x["id"] == eid), None)
        return e.get("relations", []) if e else []

    def _get_name(eid, etype):
        if etype == "npc":
            ents = _load(slug, "world/npcs.json").get("npcs", [])
        elif etype == "faction":
            ents = _load(slug, "world/factions.json").get("factions", [])
        else:
            return eid
        e = next((x for x in ents if x["id"] == eid), None)
        return e["name"] if e else eid

    def _log(eid, etype, rnote, rpol, rint):
        if etype == "npc":
            log_npc(slug, eid, session_n, rnote, polarity=rpol, intensity=rint,
                    event_type=event_type, visibility=visibility, ripple_source=ripple_source)
        elif etype == "condition":
            log_condition(slug, eid, session_n, rnote, polarity=rpol, intensity=rint,
                          event_type=event_type, visibility=visibility, ripple_source=ripple_source)
        elif etype in ("char", "party"):
            log_party_group(slug, session_n, rnote, polarity=rpol, intensity=rint,
                            event_type=event_type, visibility=visibility)
        else:
            log_faction(slug, eid, session_n, rnote, polarity=rpol, intensity=rint,
                        event_type=event_type, visibility=visibility, ripple_source=ripple_source)

    source_name = _get_name(source_id, source_type)
    _dead_npc_ids_scoped = {n["id"] for n in _load(slug, "world/npcs.json").get("npcs", []) if n.get("dead")}
    visited = {(source_id, source_type)}
    rippled = []

    # BFS queue: (entity_id, entity_type, hop, broadcast_intensity, broadcast_polarity)
    # broadcast_intensity is what this entity "sends" to its neighbours
    queue = [(source_id, source_type, 0, intensity, polarity)]

    while queue:
        eid, etype, hop, cur_int, cur_pol = queue.pop(0)
        if depth is not None and hop >= depth:
            continue

        for rel in _get_rels(eid, etype):
            tid = rel.get("target")
            ttype = rel.get("target_type", "npc")
            if not tid or (tid, ttype) in visited:
                continue
            if ttype == "npc" and tid in _dead_npc_ids_scoped:
                continue
            visited.add((tid, ttype))

            weight = float(rel.get("weight", 0.5))
            rel_type = rel.get("relation") or rel.get("formal_relation") or "ally"
            rpolarity = FLIP.get(cur_pol, cur_pol) if rel_type == "rival" else cur_pol
            rintensity = max(1, round(cur_int * weight))

            if hop == 0:
                relation_label = "ally" if rel_type == "ally" else "rival"
                rnote = f"Consequence of {source_name} ({relation_label}): {note}"
            else:
                rnote = f"Word of {source_name}'s fate reaches you: {note}"

            _log(tid, ttype, rnote, rpolarity, rintensity)
            rippled.append({"target": tid, "target_type": ttype, "relation": rel_type, "hop": hop + 1})
            # Intensity halves at each subsequent hop
            queue.append((tid, ttype, hop + 1, max(1, round(rintensity * 0.5)), rpolarity))

    # Witness entities — fire direct ripple regardless of graph position
    for extra in (extra_entities or []):
        eid = extra.get("id")
        etype = extra.get("type", "npc")
        if not eid or (eid, etype) in visited:
            continue
        _log(eid, etype, f"Witnessed: {source_name}: {note}",
             polarity, max(1, round(intensity * 0.5)))
        rippled.append({"target": eid, "target_type": etype, "relation": "witness", "hop": 0})

    return rippled


def backfill_relation_ripples(slug, source_id, source_type, target_id, target_type, relation, weight):
    """Fire ripples to a newly connected entity for all historical polarity entries on the source.
    Only targets the new relation — existing relations are not re-rippled."""
    if source_type == "npc":
        source = next((n for n in _load(slug, "world/npcs.json").get("npcs", []) if n["id"] == source_id), None)
    else:
        source = next((f for f in _load(slug, "world/factions.json").get("factions", []) if f["id"] == source_id), None)
    if not source:
        return 0
    # Build set of source event IDs already rippled to target (prevents duplicate backfill)
    if target_type == "npc":
        target_ent = next((n for n in _load(slug, "world/npcs.json").get("npcs", []) if n["id"] == target_id), None)
    else:
        target_ent = next((f for f in _load(slug, "world/factions.json").get("factions", []) if f["id"] == target_id), None)
    already_rippled = set()
    if target_ent:
        for e in target_ent.get("log", []):
            rs = e.get("ripple_source", {})
            if rs.get("entity_id") == source_id and rs.get("event_id"):
                already_rippled.add(rs["event_id"])
    if relation == "rival":
        return 0  # rival backfill inflates general score in wrong direction — skip
    relation_label = "ally"
    count = 0
    for entry in source.get("log", []):
        if not entry.get("polarity"):
            continue
        if entry.get("ripple_source"):
            continue  # never cascade ripples — only backfill directly-logged events
        if entry.get("id") in already_rippled:
            continue  # already backfilled this event to this target
        orig_actor_id = entry.get("actor_id")
        orig_actor_type = entry.get("actor_type")
        if orig_actor_id and orig_actor_id == target_id:
            continue  # target caused this entry — skip, they already have it
        rpolarity = entry["polarity"]
        rintensity = max(1, round(int(entry.get("intensity", 1)) * float(weight)))
        rnote = f"Retroactive ripple from {source['name']} ({relation_label}): {entry['note']}"
        ripple_source = {"entity_id": source_id, "entity_type": source_type, "event_id": entry.get("id")}
        if target_type == "npc":
            log_npc(slug, target_id, entry.get("session", 1), rnote,
                    polarity=rpolarity, intensity=rintensity,
                    event_type=entry.get("event_type"), visibility=entry.get("visibility", "public"),
                    ripple_source=ripple_source,
                    actor_id=orig_actor_id, actor_type=orig_actor_type)
        else:
            log_faction(slug, target_id, entry.get("session", 1), rnote,
                        polarity=rpolarity, intensity=rintensity,
                        event_type=entry.get("event_type"), visibility=entry.get("visibility", "public"),
                        ripple_source=ripple_source,
                        actor_id=orig_actor_id, actor_type=orig_actor_type)
        count += 1
    return count


def edit_log_entry(slug, entity_id, entity_type, event_id, note=None, polarity=None,
                   intensity=None, visibility=None, actor_id=None, actor_type=None,
                   location_id=None, clear_actor=False, clear_location=False):
    """Edit a log entry by its UUID."""
    def _apply(entry):
        if note is not None:
            entry["note"] = note
        if polarity in ("positive", "neutral", "negative"):
            entry["polarity"] = polarity
            if intensity is not None:
                entry["intensity"] = max(1, min(3, int(intensity)))
        elif polarity == "":
            entry.pop("polarity", None)
            entry.pop("intensity", None)
        if visibility in ("public", "restricted", "dm_only"):
            entry["visibility"] = visibility
        if actor_id:
            entry["actor_id"] = actor_id
            if actor_type:
                entry["actor_type"] = actor_type
        elif clear_actor:
            entry.pop("actor_id", None)
            entry.pop("actor_type", None)
        if location_id:
            entry["location_id"] = location_id
        elif clear_location:
            entry.pop("location_id", None)

    if entity_type == "party":
        data = _load(slug, "campaign.json")
        for entry in data.get("party_group_log", []):
            if entry.get("id") == event_id:
                _apply(entry)
        _save(slug, data, "campaign.json")
        return
    if entity_type == "character":
        data = _load_party(slug)
        for char in _all_chars(data):
            if char["name"] == entity_id:
                for entry in char.get("log", []):
                    if entry.get("id") == event_id:
                        _apply(entry)
        _save(slug, data, "party.json")
        return
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
                    _apply(entry)
    _save(slug, data, file_key)


def delete_log_entry_by_id(slug, entity_id, entity_type, event_id):
    """Soft-delete a log entry by event_id — sets deleted=True so it can be restored."""
    if entity_type == "party":
        data = _load(slug, "campaign.json")
        for entry in data.get("party_group_log", []):
            if entry.get("id") == event_id:
                entry["deleted"] = True
                _save(slug, data, "campaign.json")
                return True
        return False
    if entity_type == "character":
        data = _load_party(slug)
        for char in _all_chars(data):
            if char["name"] == entity_id:
                for entry in char.get("log", []):
                    if entry.get("id") == event_id:
                        entry["deleted"] = True
                        _save(slug, data, "party.json")
                        return True
        return False
    file_map = {
        "npc": ("world/npcs.json", "npcs"),
        "faction": ("world/factions.json", "factions"),
        "condition": ("world/conditions.json", "conditions"),
    }
    if entity_type not in file_map:
        return False
    file_key, entity_key = file_map[entity_type]
    data = _load(slug, file_key)
    for entity in data.get(entity_key, []):
        if entity["id"] == entity_id:
            for entry in entity.get("log", []):
                if entry.get("id") == event_id:
                    entry["deleted"] = True
                    _save(slug, data, file_key)
                    return True
    return False


def restore_log_entry_by_id(slug, entity_id, entity_type, event_id):
    """Restore a soft-deleted log entry by event_id."""
    file_map = {
        "npc": ("world/npcs.json", "npcs"),
        "faction": ("world/factions.json", "factions"),
        "condition": ("world/conditions.json", "conditions"),
    }
    if entity_type not in file_map:
        return False
    file_key, entity_key = file_map[entity_type]
    data = _load(slug, file_key)
    for entity in data.get(entity_key, []):
        if entity["id"] == entity_id:
            for entry in entity.get("log", []):
                if entry.get("id") == event_id:
                    entry.pop("deleted", None)
                    _save(slug, data, file_key)
                    return True
    return False


def get_ripple_chains(slug, source_event_ids):
    """Return {source_event_id: [{entity_name, entity_id, entity_type, event_id, deleted}]} for all ripple children."""
    if not source_event_ids:
        return {}
    chains = {eid: [] for eid in source_event_ids}
    id_set = set(source_event_ids)
    for file_key, entity_key, etype in [
        ("world/npcs.json", "npcs", "npc"),
        ("world/factions.json", "factions", "faction"),
    ]:
        data = _load(slug, file_key)
        for entity in data.get(entity_key, []):
            for entry in entity.get("log", []):
                src = (entry.get("ripple_source") or {}).get("event_id")
                if src in id_set:
                    chains[src].append({
                        "entity_name": entity["name"],
                        "entity_id": entity["id"],
                        "entity_type": etype,
                        "event_id": entry.get("id"),
                        "deleted": bool(entry.get("deleted")),
                    })
    return chains


def move_log_entry(slug, source_entity_id, source_entity_type, event_id, target_entity_id, target_entity_type):
    """Move a log entry from one entity to another by event_id, preserving all metadata."""
    file_map = {
        "npc": ("world/npcs.json", "npcs"),
        "faction": ("world/factions.json", "factions"),
    }
    if source_entity_type not in file_map or target_entity_type not in file_map:
        return False
    src_file, src_key = file_map[source_entity_type]
    tgt_file, tgt_key = file_map[target_entity_type]
    src_data = _load(slug, src_file)
    entry = None
    for entity in src_data.get(src_key, []):
        if entity["id"] == source_entity_id:
            for i, e in enumerate(entity.get("log", [])):
                if e.get("id") == event_id:
                    entry = entity["log"].pop(i)
                    break
            break
    if not entry:
        return False
    _save(slug, src_data, src_file)
    tgt_data = _load(slug, tgt_file)
    for entity in tgt_data.get(tgt_key, []):
        if entity["id"] == target_entity_id:
            entity.setdefault("log", []).append(entry)
            break
    _save(slug, tgt_data, tgt_file)
    return True


def undo_ripple_chain(slug, source_event_id):
    """Soft-delete all log entries rippled from source_event_id. Returns count soft-deleted."""
    removed = 0
    for file_key, entity_key in [
        ("world/npcs.json", "npcs"),
        ("world/factions.json", "factions"),
        ("world/conditions.json", "conditions"),
    ]:
        data = _load(slug, file_key)
        changed = False
        for entity in data.get(entity_key, []):
            for entry in entity.get("log", []):
                if (entry.get("ripple_source") or {}).get("event_id") == source_event_id \
                        and not entry.get("deleted"):
                    entry["deleted"] = True
                    removed += 1
                    changed = True
        if changed:
            _save(slug, data, file_key)
    return removed


def reveal_event(slug, event_id, char_name):
    """Add event_id to a character's known_events list."""
    data = _load_party(slug)
    for c in _all_chars(data):
        if c["name"] == char_name:
            known = c.setdefault("known_events", [])
            if event_id not in known:
                known.append(event_id)
    _save(slug, data, "party.json")


def add_character_relation(slug, char_name, target_id, target_type, relation, weight,
                           formal_relation=None, personal_relation=None):
    data = _load_party(slug)
    for c in _all_chars(data):
        if c["name"] == char_name:
            rels = [r for r in c.get("relations", []) if r.get("target") != target_id]
            entry = {"target": target_id, "target_type": target_type, "weight": float(weight)}
            if formal_relation and personal_relation and formal_relation != personal_relation:
                entry["formal_relation"] = formal_relation
                entry["personal_relation"] = personal_relation
            else:
                entry["relation"] = formal_relation or relation
            rels.append(entry)
            c["relations"] = rels
    _save(slug, data, "party.json")


def remove_character_relation(slug, char_name, target_id):
    data = _load_party(slug)
    for c in _all_chars(data):
        if c["name"] == char_name:
            c["relations"] = [r for r in c.get("relations", []) if r.get("target") != target_id]
    _save(slug, data, "party.json")


def unreveal_event(slug, event_id, char_name):
    """Remove event_id from a character's known_events list."""
    data = _load_party(slug)
    for c in _all_chars(data):
        if c["name"] == char_name:
            known = c.get("known_events", [])
            if event_id in known:
                known.remove(event_id)
    _save(slug, data, "party.json")


def assign_character_user(slug, char_name, email):
    data = _load_party(slug)
    for c in _all_chars(data):
        if c["name"] == char_name:
            if email:
                c["assigned_email"] = email.lower().strip()
                c.pop("assigned_user", None)
            else:
                c.pop("assigned_email", None)
                c.pop("assigned_user", None)
    _save(slug, data, "party.json")


def get_player_character(slug, username, user_email=None):
    """Return the character assigned to this user in this campaign, or None.

    Matches on assigned_email (new) or legacy assigned_user (username).
    """
    email_lower = user_email.lower() if user_email else None
    for c in _all_chars(_load_party(slug)):
        if email_lower and c.get("assigned_email") == email_lower:
            return c
        if c.get("assigned_user") == username:
            return c
    return None


# ── Character Conditions ──────────────────────────────────────────────────────

def get_character_conditions(slug, char_name, include_hidden=True, include_resolved=False):
    for char in _all_chars(_load_party(slug)):
        if char["name"] == char_name:
            conds = char.get("conditions", [])
            if not include_hidden:
                conds = [c for c in conds if not c.get("hidden", False)]
            if not include_resolved:
                conds = [c for c in conds if not c.get("resolved", False)]
            return conds
    return []


def add_character_condition(slug, char_name, name, category, description,
                            acquired_session, linked_npc_id=None, linked_faction_id=None,
                            hidden=False):
    data = _load_party(slug)
    for char in _all_chars(data):
        if char["name"] == char_name:
            cond = {
                "id": str(uuid.uuid4())[:8],
                "name": name,
                "category": category,
                "description": description,
                "acquired_session": int(acquired_session) if acquired_session else 1,
                "hidden": hidden,
                "resolved": False,
            }
            if linked_npc_id:
                cond["linked_npc_id"] = linked_npc_id
            if linked_faction_id:
                cond["linked_faction_id"] = linked_faction_id
            char.setdefault("conditions", []).append(cond)
    _save(slug, data, "party.json")


def resolve_character_condition(slug, char_name, cond_id):
    data = _load_party(slug)
    for char in _all_chars(data):
        if char["name"] == char_name:
            for cond in char.get("conditions", []):
                if cond["id"] == cond_id:
                    cond["resolved"] = True
    _save(slug, data, "party.json")


def toggle_character_condition_hidden(slug, char_name, cond_id):
    data = _load_party(slug)
    for char in _all_chars(data):
        if char["name"] == char_name:
            for cond in char.get("conditions", []):
                if cond["id"] == cond_id:
                    cond["hidden"] = not cond.get("hidden", False)
    _save(slug, data, "party.json")


def delete_character_condition(slug, char_name, cond_id):
    data = _load_party(slug)
    for char in _all_chars(data):
        if char["name"] == char_name:
            char["conditions"] = [c for c in char.get("conditions", []) if c["id"] != cond_id]
    _save(slug, data, "party.json")


def get_conditions_for_npc(slug, npc_id):
    """Returns [(char_name, condition)] for all active conditions linked to this NPC."""
    results = []
    for char in _all_chars(_load_party(slug)):
        for cond in char.get("conditions", []):
            if cond.get("linked_npc_id") == npc_id and not cond.get("resolved", False):
                results.append((char["name"], cond))
    return results


def get_conditions_for_faction(slug, faction_id):
    """Returns [(char_name, condition)] for all active conditions linked to this faction."""
    results = []
    for char in _all_chars(_load_party(slug)):
        for cond in char.get("conditions", []):
            if cond.get("linked_faction_id") == faction_id and not cond.get("resolved", False):
                results.append((char["name"], cond))
    return results


def get_condition_alerts(slug, is_dm=True):
    """For each active character condition linked to an NPC/faction that has log entries,
    return the condition + linked entity + its most recent log entry. Sorted most-recent first."""
    npcs = {n["id"]: n for n in get_npcs(slug, include_hidden=is_dm)}
    factions = {f["id"]: f for f in get_factions(slug, include_hidden=is_dm)}
    alerts = []
    for char in _all_chars(_load_party(slug)):
        for cond in char.get("conditions", []):
            if cond.get("resolved") or cond.get("hidden"):
                continue
            entity = entity_type = entity_id = None
            if cond.get("linked_npc_id"):
                entity = npcs.get(cond["linked_npc_id"])
                entity_type = "npc"
                entity_id = cond["linked_npc_id"]
            elif cond.get("linked_faction_id"):
                entity = factions.get(cond["linked_faction_id"])
                entity_type = "faction"
                entity_id = cond["linked_faction_id"]
            if not entity or not entity.get("log"):
                continue
            recent = entity["log"][-1]
            alerts.append({
                "char_name": char["name"],
                "condition": cond,
                "entity_id": entity_id,
                "entity_type": entity_type,
                "entity_name": entity["name"],
                "recent_entry": recent,
            })
    alerts.sort(key=lambda a: a["recent_entry"].get("session", 0), reverse=True)
    return alerts


def get_condition_alerts_for_entities(slug, entity_ids):
    """Given a set of entity_ids, return condition alerts whose linked entity is in that set."""
    all_alerts = get_condition_alerts(slug, is_dm=True)
    return [a for a in all_alerts if a["entity_id"] in entity_ids]


# ── Pending Projections ───────────────────────────────────────────────────────

def get_pending_projections(slug):
    """All projected log entries not yet confirmed or dismissed, across NPCs and factions."""
    pending = []
    npc_names = {n["id"]: n["name"] for n in _load(slug, "world/npcs.json").get("npcs", [])}
    faction_names = {f["id"]: f["name"] for f in _load(slug, "world/factions.json").get("factions", [])}
    for npc in _load(slug, "world/npcs.json").get("npcs", []):
        for entry in npc.get("log", []):
            if entry.get("event_type") == "projected" and not entry.get("confirmed") and not entry.get("dismissed"):
                pending.append({
                    "entity_id": npc["id"],
                    "entity_type": "npc",
                    "entity_name": npc["name"],
                    "event_id": entry["id"],
                    "note": entry["note"],
                    "session": entry.get("session", 1),
                    "polarity": entry.get("polarity"),
                    "intensity": entry.get("intensity", 1),
                    "visibility": entry.get("visibility", "public"),
                })
    for faction in _load(slug, "world/factions.json").get("factions", []):
        for entry in faction.get("log", []):
            if entry.get("event_type") == "projected" and not entry.get("confirmed") and not entry.get("dismissed"):
                pending.append({
                    "entity_id": faction["id"],
                    "entity_type": "faction",
                    "entity_name": faction["name"],
                    "event_id": entry["id"],
                    "note": entry["note"],
                    "session": entry.get("session", 1),
                    "polarity": entry.get("polarity"),
                    "intensity": entry.get("intensity", 1),
                    "visibility": entry.get("visibility", "public"),
                })
    pending.sort(key=lambda x: x["session"], reverse=True)
    return pending


def confirm_projection(slug, entity_id, entity_type, event_id, new_event_type, current_session):
    """Promote a projected entry to a real event and fire ripples."""
    if entity_type == "npc":
        data = _load(slug, "world/npcs.json")
        entities = data.get("npcs", [])
        file_key = "world/npcs.json"
    else:
        data = _load(slug, "world/factions.json")
        entities = data.get("factions", [])
        file_key = "world/factions.json"
    entry = None
    for e in entities:
        if e["id"] == entity_id:
            for log_entry in e.get("log", []):
                if log_entry.get("id") == event_id:
                    log_entry["event_type"] = new_event_type or "other"
                    log_entry["confirmed"] = True
                    log_entry["session"] = current_session
                    entry = log_entry
                    break
    _save(slug, data, file_key)
    if entry:
        apply_ripple(slug, entity_id, entity_type, current_session,
                     entry["note"], entry.get("polarity"), entry.get("intensity", 1),
                     event_type=entry["event_type"], visibility=entry.get("visibility", "public"),
                     source_event_id=event_id,
                     actor_id=entry.get("actor_id"), actor_type=entry.get("actor_type"))
    return entry


def dismiss_projection(slug, entity_id, entity_type, event_id):
    """Mark a projected entry as dismissed (party intervened)."""
    if entity_type == "npc":
        data = _load(slug, "world/npcs.json")
        entities = data.get("npcs", [])
        file_key = "world/npcs.json"
    else:
        data = _load(slug, "world/factions.json")
        entities = data.get("factions", [])
        file_key = "world/factions.json"
    for e in entities:
        if e["id"] == entity_id:
            for entry in e.get("log", []):
                if entry.get("id") == event_id:
                    entry["dismissed"] = True
    _save(slug, data, file_key)


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


def edit_item(slug, item_index, name, notes=""):
    data = _load(slug, "assets.json")
    items = data.get("items", [])
    if 0 <= item_index < len(items):
        items[item_index]["name"] = name
        items[item_index]["notes"] = notes
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


def log_ship(slug, ship_name, session, note, event_type=None, visibility="public"):
    data = _load(slug, "assets.json")
    name_lower = ship_name.strip().lower()
    for ship in data.get("ships", []):
        if ship.get("name", "").lower() == name_lower:
            entry = {"session": session, "note": note, "visibility": visibility}
            if event_type:
                entry["event_type"] = event_type.strip()
            ship.setdefault("log", []).append(entry)
            _save(slug, data, "assets.json")
            return True
    return False


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


def generate_session_brief(slug):
    """Build a markdown session prep brief from current world state. No AI call."""
    current_session = get_current_session(slug)
    lines = [f"## Session Brief — Session {current_session}", ""]

    # Open threads — uncommitted futures
    futures = get_futures(slug).get("futures", [])
    pending = [f for f in futures if not f.get("committed")]
    if pending:
        lines.append("### Open Threads")
        for f in pending:
            conf = f.get("confidence", "")
            conf_tag = f" _{conf}_" if conf and conf != "high" else ""
            lines.append(f"- **{f.get('entity_name', '?')}** — {f.get('hypothesis', '')} {conf_tag}".rstrip())
        lines.append("")

    # Active quests
    quests = [q for q in get_quests(slug, include_hidden=False) if q.get("status") == "active"]
    if quests:
        lines.append("### Active Quests")
        for q in quests:
            lines.append(f"- **{q['title']}**{' — ' + q['description'] if q.get('description') else ''}")
            for obj in q.get("objectives", []):
                mark = "x" if obj.get("done") else " "
                lines.append(f"  - [{mark}] {obj['text']}")
        lines.append("")

    # Party stakes — active character conditions
    npcs = {n["id"]: n["name"] for n in get_npcs(slug, include_hidden=True)}
    factions = {f["id"]: f["name"] for f in get_factions(slug, include_hidden=True)}
    party = _all_chars(_load_party(slug))
    stake_lines = []
    for char in party:
        for cond in char.get("conditions", []):
            if cond.get("resolved") or cond.get("hidden"):
                continue
            linked = ""
            if cond.get("linked_npc_id"):
                linked = f" → {npcs.get(cond['linked_npc_id'], '?')}"
            elif cond.get("linked_faction_id"):
                linked = f" → {factions.get(cond['linked_faction_id'], '?')}"
            cat = cond.get("category", "")
            stake_lines.append(
                f"- **{char['name']}** [{cat}] {cond['name']}{linked} — {cond.get('description', '')}"
            )
    if stake_lines:
        lines.append("### Party Stakes")
        lines.extend(stake_lines)
        lines.append("")

    # Hot entities — active last 2 sessions
    recent = get_recent_entities(slug, current_session, window=2, include_hidden=True)
    if recent:
        lines.append("### Hot Entities")
        for e in recent[:8]:
            last = e.get("last_entry", {})
            note = last.get("note", "")
            sess = last.get("session", "")
            rel = e.get("rel_data", {}).get("relationship", "")
            rel_tag = f" ({rel})" if rel and rel != "unknown" else ""
            lines.append(f"- **{e['name']}**{rel_tag} — {note} [S{sess}]")
        lines.append("")

    return "\n".join(lines).rstrip()


def save_futures(slug, futures, session_n):
    data = _load(slug, "dm/session.json")
    data["futures"] = futures
    data["futures_session"] = session_n
    _save(slug, data, "dm/session.json")


def get_futures(slug):
    data = _load(slug, "dm/session.json")
    return {
        "futures": data.get("futures", []),
        "session": data.get("futures_session"),
    }


def save_proposals(slug, proposals, session_n, parse_cursor=None):
    data = _load(slug, "dm/session.json")
    data["proposals"] = proposals
    data["proposals_session"] = session_n
    if parse_cursor is not None:
        data["proposals_parse_cursor"] = parse_cursor
    _save(slug, data, "dm/session.json")


def get_proposals(slug):
    data = _load(slug, "dm/session.json")
    return {
        "proposals": data.get("proposals", []),
        "session": data.get("proposals_session"),
        "parse_cursor": data.get("proposals_parse_cursor"),
    }


def clear_proposals(slug):
    data = _load(slug, "dm/session.json")
    data.pop("proposals", None)
    data.pop("proposals_session", None)
    data.pop("proposals_parse_cursor", None)
    data.pop("proposals_status", None)
    data.pop("proposals_error", None)
    _save(slug, data, "dm/session.json")


def set_proposals_status(slug, status, error=None):
    data = _load(slug, "dm/session.json")
    data["proposals_status"] = status
    if error:
        data["proposals_error"] = error
    else:
        data.pop("proposals_error", None)
    _save(slug, data, "dm/session.json")


def get_proposals_status(slug):
    data = _load(slug, "dm/session.json")
    return {
        "status": data.get("proposals_status"),
        "error": data.get("proposals_error"),
    }


def save_relation_suggestions(slug, suggestions):
    data = _load(slug, "dm/session.json")
    data["relation_suggestions"] = suggestions
    _save(slug, data, "dm/session.json")


def get_relation_suggestions(slug):
    return _load(slug, "dm/session.json").get("relation_suggestions", [])


def dismiss_relation_suggestion(slug, source_id, target_id):
    data = _load(slug, "dm/session.json")
    data["relation_suggestions"] = [
        s for s in data.get("relation_suggestions", [])
        if not (s["source_id"] == source_id and s["target_id"] == target_id)
    ]
    _save(slug, data, "dm/session.json")


def build_causal_context(slug, session_n):
    """Serialize the causal chain into a compact string for AI prompt injection.

    Covers: dead entities, relationship scores with their event-level drivers,
    and event-driven inter-entity tensions derived from actor_id history.
    """
    npcs = get_npcs(slug, include_hidden=True)
    factions = get_factions(slug, include_hidden=True)

    npc_ids = {n["id"] for n in npcs}
    name_lookup = {n["id"]: n["name"] for n in npcs}
    name_lookup.update({f["id"]: f["name"] for f in factions})

    dead = [n["name"] for n in npcs if n.get("dead")]

    entity_rows = []
    for entity in list(npcs) + list(factions):
        kind = "npc" if entity["id"] in npc_ids else "faction"
        log = entity.get("log", [])
        rel_data = compute_npc_relationship(entity, is_dm=True)
        contributors = rel_data.get("contributors", [])
        if not contributors:
            continue

        last_session = max((e.get("session", 0) for e in log), default=0)
        score_str = f" score:{rel_data['score']:+.1f}" if rel_data.get("computed") else ""
        trend_str = f" trend:{rel_data['trend']}" if rel_data.get("trend") else ""
        dead_str = " [DEAD]" if entity.get("dead") else ""
        header = f"{entity['name']} ({kind}){dead_str} — {rel_data['relationship']}{score_str}{trend_str}"

        driver_lines = []
        for c in contributors[:3]:
            note_preview = c.get("note", "")[:72]
            driver_lines.append(f"  [S{c.get('session', 0)}] {c['_weight']:+.1f} \"{note_preview}\"")

        static = [
            f"{r['relation']}:{name_lookup.get(r['target'], r['target'])}"
            for r in entity.get("relations", [])[:3]
        ]
        if static:
            driver_lines.append(f"  Links: {', '.join(static)}")

        entity_rows.append((last_session, header + "\n" + "\n".join(driver_lines)))

    entity_rows.sort(key=lambda x: x[0], reverse=True)

    inter = get_inter_entity_relations(slug)
    inter_notable = sorted(
        [r for r in inter if r.get("computed") and abs(r.get("score") or 0) > 0.5],
        key=lambda r: abs(r.get("score") or 0),
        reverse=True
    )[:12]

    parts = [f"=== CAUSAL CONTEXT — Session {session_n} ==="]
    if dead:
        parts.append(f"DEAD (cannot act or be acted upon by others): {', '.join(dead)}")
    if entity_rows:
        parts.append("\nRELATIONSHIP CHAINS & CAUSAL DRIVERS:")
        for _, block in entity_rows[:25]:
            parts.append(block)
    if inter_notable:
        parts.append("\nEVENT-DRIVEN INTER-ENTITY TENSIONS (from actor_id history):")
        for r in inter_notable:
            a_name = name_lookup.get(r["a_id"], r["a_id"])
            b_name = name_lookup.get(r["b_id"], r["b_id"])
            parts.append(
                f"  {a_name} ↔ {b_name}: {r['relationship']} score:{r['score']:+.1f}"
            )
    parts.append("=== END CAUSAL CONTEXT ===")
    return "\n".join(parts)


def get_world_state_summary(slug, current_session):
    """Build a structured world context for AI futures inference."""
    npcs = _load(slug, "world/npcs.json").get("npcs", [])
    factions = _load(slug, "world/factions.json").get("factions", [])
    conditions = get_conditions(slug, include_hidden=False, include_resolved=False)
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
            "factions": obj.get("factions", []) if e["kind"] == "npc" else None,
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

    active_conditions = [
        {
            "id": c["id"],
            "name": c["name"],
            "region": c.get("region", ""),
            "effect_type": c.get("effect_type", ""),
            "effect_scope": c.get("effect_scope", ""),
            "magnitude": c.get("magnitude", ""),
            "severity": compute_condition_severity(c, is_dm=True),
        }
        for c in conditions
    ]

    return {
        "current_session": current_session,
        "hot_entities": hot_entities,
        "stale_threads": stale_summary,
        "hostile_pairs": hostile_pairs,
        "active_quests": active_quests,
        "active_conditions": active_conditions,
        "session_plan": get_session_plan(slug),
    }


def get_session_notes(slug):
    return _load(slug, "dm/session.json").get("notes", "")


def set_session_notes(slug, notes):
    data = _load(slug, "dm/session.json")
    data["notes"] = notes
    _save(slug, data, "dm/session.json")


def get_notes_parse_cursor(slug):
    """Character offset up to which notes have already been parsed and committed."""
    return _load(slug, "dm/session.json").get("notes_parse_cursor", 0)


def set_notes_parse_cursor(slug, cursor):
    data = _load(slug, "dm/session.json")
    data["notes_parse_cursor"] = cursor
    _save(slug, data, "dm/session.json")


def reset_notes_parse_cursor(slug):
    data = _load(slug, "dm/session.json")
    data.pop("notes_parse_cursor", None)
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


def get_dm_intelligence(slug, current_session, active_branch=None, all_branches=None):
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
        log = [e for e in filter_log_for_branch(entity.get("log", []), active_branch, all_branches or []) if not e.get("deleted")]
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


def get_session_delta(slug, session_n, active_branch=None, all_branches=None):
    """Return all events logged in a specific session, grouped by entity, for the DM."""
    groups = []
    for npc in _load(slug, "world/npcs.json").get("npcs", []):
        visible = filter_log_for_branch(npc.get("log", []), active_branch, all_branches or [])
        entries = [e for e in visible if e.get("session") == session_n and not e.get("deleted")]
        if entries:
            groups.append({
                "kind": "npc", "id": npc["id"], "name": npc["name"],
                "role": npc.get("role", ""),
                "rel_data": compute_npc_relationship(npc, is_dm=True,
                                                     active_branch=active_branch, all_branches=all_branches),
                "entries": entries,
            })
    for faction in _load(slug, "world/factions.json").get("factions", []):
        visible = filter_log_for_branch(faction.get("log", []), active_branch, all_branches or [])
        entries = [e for e in visible if e.get("session") == session_n and not e.get("deleted")]
        if entries:
            groups.append({
                "kind": "faction", "id": faction["id"], "name": faction["name"],
                "role": faction.get("role", ""),
                "rel_data": {"relationship": faction.get("relationship", "unknown"),
                             "trend": None, "computed": False},
                "entries": entries,
            })
    for condition in _load(slug, "world/conditions.json").get("conditions", []):
        entries = [e for e in condition.get("log", []) if e.get("session") == session_n and not e.get("deleted")]
        if entries:
            groups.append({
                "kind": "condition", "id": condition["id"], "name": condition["name"],
                "role": f"{condition.get('effect_type', '')} — {condition.get('region', '')}",
                "rel_data": compute_condition_severity(condition, is_dm=True),
                "entries": entries,
            })
    for location in _load(slug, "world/locations.json").get("locations", []):
        entries = [e for e in location.get("log", []) if e.get("session") == session_n and not e.get("deleted")]
        if entries:
            groups.append({
                "kind": "location", "id": location["id"], "name": location["name"],
                "role": location.get("role", ""),
                "rel_data": {"relationship": "neutral", "trend": None, "computed": False},
                "entries": entries,
            })
    meta = _load(slug, "campaign.json")
    party_name = meta.get("party_name") or "The Party"
    party_entries = [e for e in meta.get("party_group_log", [])
                     if e.get("session") == session_n and not e.get("deleted")]
    if party_entries:
        groups.append({
            "kind": "party", "id": "_party", "name": party_name,
            "role": "",
            "rel_data": {"relationship": "ally", "trend": None, "computed": False},
            "entries": party_entries,
        })
    groups.sort(key=lambda g: g["name"])
    return groups


def get_all_log_entries(slug):
    entries = []
    for npc in _load(slug, "world/npcs.json").get("npcs", []):
        for entry in npc.get("log", []):
            if not entry.get("deleted"):
                entries.append({"source": npc["name"], "type": "NPC", "entity_id": npc["id"], **entry})
    for faction in _load(slug, "world/factions.json").get("factions", []):
        for entry in faction.get("log", []):
            if not entry.get("deleted"):
                entries.append({"source": faction["name"], "type": "Faction", "entity_id": faction["id"], **entry})
    for quest in _load(slug, "story/quests.json").get("quests", []):
        for entry in quest.get("log", []):
            if not entry.get("deleted"):
                entries.append({"source": quest["title"], "type": "Quest", "entity_id": quest.get("id",""), **entry})
    for condition in _load(slug, "world/conditions.json").get("conditions", []):
        for entry in condition.get("log", []):
            if not entry.get("deleted"):
                entries.append({"source": condition["name"], "type": "Condition", "entity_id": condition.get("id",""), **entry})
    for char in _all_chars(_load_party(slug)):
        for entry in char.get("log", []):
            if not entry.get("deleted"):
                entries.append({"source": char["name"], "type": "Character", "entity_id": char["name"], **entry})
    meta = _load(slug, "campaign.json")
    party_name = meta.get("party_name") or "The Party"
    for entry in meta.get("party_group_log", []):
        if not entry.get("deleted"):
            entries.append({"source": party_name, "type": "Party", "entity_id": "_party", "entity_type": "party_group", **entry})
    entries.sort(key=lambda e: e.get("session", 0), reverse=True)
    return entries


# ── Journal ───────────────────────────────────────────────────────────────────

def get_journal(slug, include_deleted=False):
    entries = _load(slug, "journal.json").get("entries", [])
    result = []
    for i, e in enumerate(entries):
        if not include_deleted and e.get("deleted"):
            continue
        result.append({**e, "_raw_idx": i})
    return result


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
        entries[idx]["deleted"] = True
    _save(slug, data, "journal.json")


def restore_journal_entry(slug, idx):
    data = _load(slug, "journal.json")
    entries = data.get("entries", [])
    if 0 <= idx < len(entries):
        entries[idx].pop("deleted", None)
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
    for c in _load(slug, "world/conditions.json").get("conditions", []):
        for entry in c.get("log", []):
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


def format_magnitude(magnitude):
    """Render a structured magnitude object as a display string."""
    if not magnitude or not isinstance(magnitude, dict):
        return str(magnitude) if magnitude else ""
    t = magnitude.get("type", "custom")
    if t == "percent":
        v = magnitude.get("value", 0)
        return f"+{v}%" if v >= 0 else f"{v}%"
    if t == "multiplier":
        return f"{magnitude.get('value', 1)}x"
    if t == "blocked":
        return "blocked"
    if t == "restricted":
        return "restricted"
    return magnitude.get("label", "")


def get_async_campaign(slug):
    return _load(slug, "dm/async_campaign.json")


def save_async_campaign(slug, data):
    _save(slug, data, "dm/async_campaign.json")


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
