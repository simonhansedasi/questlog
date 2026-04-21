import os
import json
import anthropic
from dotenv import load_dotenv

load_dotenv()
_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def _parse_json(raw):
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)


def generate_recap(session_notes, campaign_name, quests, npcs):
    active_quests = [q for q in quests if q.get("status") == "active"]
    visible_npcs = [n for n in npcs if not n.get("hidden")]

    quest_lines = "\n".join(f"- {q['title']}: {q.get('description','')}" for q in active_quests) or "None"
    npc_lines = "\n".join(f"- {n['name']} ({n.get('role','')})" for n in visible_npcs) or "None"

    system = f"""You are a session scribe for a tabletop RPG campaign called "{campaign_name}".

Write player-facing session recaps — 2 to 4 short paragraphs, past tense, written like an in-world chronicle. Focus on what happened, decisions made, and consequences that unfolded. Do not invent events not implied by the notes. Do not reference game mechanics or rules. Keep it vivid but concise."""

    user = f"""Active quests:
{quest_lines}

Key NPCs:
{npc_lines}

DM's session notes:
{session_notes}

Write the recap now:"""

    message = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user}]
    )
    return message.content[0].text.strip()


def propose_log_entries(session_notes, campaign_name, session_n, npcs, factions, party=None, ships=None):
    """Parse session notes into proposed structured log entries for DM review."""
    npc_lines = "\n".join(
        f"  - id: {n['id']} | name: {n['name']} | role: {n.get('role','')}"
        for n in npcs
    ) or "  (none)"
    faction_lines = "\n".join(
        f"  - id: {f['id']} | name: {f['name']}"
        for f in factions
    ) or "  (none)"
    party_lines = "\n".join(
        f"  - {c['name']}"
        for c in (party or [])
    ) or "  (none)"
    ship_lines = "\n".join(
        f"  - {s['name']} ({s.get('type', 'ship')})"
        for s in (ships or [])
    ) or "  (none)"

    system = """You are a campaign tracking assistant for tabletop RPGs. You are completely system-agnostic — you do not inject genre, rules, stats, or game mechanics. You track narrative events only.

Your job: extract discrete world events from a DM's raw session notes and return them as a JSON array.

Core rules:
- Extract only events explicitly stated or directly implied in the notes. Do not invent events, future states, or downstream consequences — ripple propagation is handled separately.
- Entity disambiguation: if a name closely resembles an existing known entity (different title, nickname, minor spelling variation, e.g. "Guard Milo" vs "Milo the Guard"), use the known entity_id rather than treating it as a new entity.
- Logic of the latest: if a note describes a state that seems to contradict a known entity's current state (e.g., location changed, alliance shifted), trust the new note. Do not create a duplicate entry.
- Conflict detection: if a note describes something fundamentally impossible given known state (e.g., killing an NPC already known to be dead), still write the entry but set "conflict": true — it will be surfaced for DM review.
- Party members are never entry subjects. Log events from the perspective of the NPC, faction, or ship they interact with.
- Notes must describe what concretely happened — past tense, one sentence. Not predictions, not future consequences, not interpretations."""

    user = f"""Campaign: "{campaign_name}" — Session {session_n}

Party members (never entry subjects — do NOT create entries where entity_name is a party member):
{party_lines}

Known NPCs:
{npc_lines}

Known Factions:
{faction_lines}

Known Ships:
{ship_lines}

DM's session notes:
{session_notes}

Return ONLY a JSON array. No prose before or after. Each element:
{{
  "entity_id": "<id from NPC/faction lists above, or null for ships and genuinely new entities>",
  "entity_type": "npc" | "faction" | "ship",
  "entity_name": "<name as it appears in notes>",
  "faction_name": "<faction this NPC belongs to, if apparent — NPC entries only, else null>",
  "note": "<one sentence, past tense: what concretely happened>",
  "polarity": "positive" | "neutral" | "negative" | null,
  "intensity": 1 | 2 | 3,
  "event_type": "<combat|dialogue|politics|discovery|betrayal|movement|other>",
  "visibility": "public" | "dm_only",
  "conflict": false
}}

- polarity null = event has no relationship significance
- intensity 1=minor, 2=moderate, 3=major
- dm_only if players should not know about this yet
- conflict true if this entry seems to contradict the entity's known state
- Ships always use entity_id: null (matched by name at commit time)
- Return [] if nothing meaningful happened

JSON array:"""

    message = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user}]
    )
    return _parse_json(message.content[0].text)


def propose_futures(campaign_name, session_n, world_summary):
    """Given current world state, generate 2-3 plausible near-future narrative consequences."""
    hot = world_summary.get("hot_entities", [])
    stale = world_summary.get("stale_threads", [])
    hostile = world_summary.get("hostile_pairs", [])
    quests = world_summary.get("active_quests", [])
    plan = world_summary.get("session_plan", "")

    hot_lines = "\n".join(
        f"  - {e['name']} ({e['kind']}, {e['relationship']}{', '+e['trend'] if e.get('trend') else ''}): {e['recent_events']}"
        for e in hot
    ) or "  (none)"
    stale_lines = "\n".join(
        f"  - {e['name']} ({e['kind']}) — last seen S{e['last_session']}: {e['reason']}"
        for e in stale
    ) or "  (none)"
    hostile_lines = "\n".join(f"  - {p}" for p in hostile) or "  (none)"
    quest_lines = "\n".join(
        f"  - {q['title']}: {q['description']}"
        for q in quests
    ) or "  (none)"

    system = """You are a narrative consequence engine for tabletop RPGs. You are completely system-agnostic — you do not reference rules, stats, or mechanics.

Your job: given the current state of the world, project what concretely happens in the next 1-2 sessions if the party does nothing to intervene.

Core rules:
- Every consequence must be caused by a specific, named tension already present in the provided world state. Do not invent new actors, factions, or events from outside this context.
- Be concrete and gameable: name the specific entity, describe the specific action they take, make it something a DM can turn into a scene or an encounter.
- Direct causation only: trace the cause explicitly in your reasoning. "X does Y because Z happened."
- State consequences as if they are happening, not as possibilities. These are projections, not suggestions.
- 2-3 consequences only. Prioritize the highest-pressure, most imminent tensions.
- Do not invent dramatic chaos unrelated to the current tensions — the world moves predictably from known forces."""

    user = f"""Campaign: "{campaign_name}" — Current session: {session_n}

Hot entities (under active pressure or shifting fast):
{hot_lines}

Stale threads (unresolved tensions building in the background):
{stale_lines}

Hostile relationships:
{hostile_lines}

Active quests:
{quest_lines}

DM's session plan hint:
{plan or "(none)"}

Return ONLY a JSON array. No prose before or after. Each element:
{{
  "entity_name": "<primary entity driving this consequence>",
  "entity_kind": "npc" | "faction" | "quest",
  "hypothesis": "<what concretely happens — 1-2 sentences, stated as fact not possibility>",
  "reasoning": "<which specific tension or event causes this — 1 sentence>",
  "confidence": "high" | "medium" | "low"
}}

JSON array:"""

    message = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user}]
    )
    return _parse_json(message.content[0].text)
