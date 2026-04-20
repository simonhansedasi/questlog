import os
import json
import anthropic
from dotenv import load_dotenv

load_dotenv()
_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def generate_recap(session_notes, campaign_name, quests, npcs):
    active_quests = [q for q in quests if q.get("status") == "active"]
    visible_npcs = [n for n in npcs if not n.get("hidden")]

    quest_lines = "\n".join(f"- {q['title']}: {q.get('description','')}" for q in active_quests) or "None"
    npc_lines = "\n".join(f"- {n['name']} ({n.get('role','')})" for n in visible_npcs) or "None"

    prompt = f"""You are a session scribe for a tabletop RPG campaign called "{campaign_name}".

The DM's raw session notes are below. Write a player-facing session recap — 2 to 4 short paragraphs, past tense, written like an in-world chronicle. Focus on what happened, decisions made, and consequences. Do not invent events not implied by the notes. Keep it vivid but concise.

Active quests for context:
{quest_lines}

Key NPCs for context:
{npc_lines}

DM's session notes:
{session_notes}

Write the recap now:"""

    message = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text.strip()


def propose_log_entries(session_notes, campaign_name, session_n, npcs, factions):
    """Parse session notes into proposed structured log entries for DM review."""
    npc_lines = "\n".join(
        f"  - id: {n['id']} | name: {n['name']} | role: {n.get('role','')}"
        for n in npcs
    ) or "  (none)"
    faction_lines = "\n".join(
        f"  - id: {f['id']} | name: {f['name']}"
        for f in factions
    ) or "  (none)"

    prompt = f"""You are a campaign tracking assistant for a TTRPG campaign called "{campaign_name}".

Parse the DM's session notes and extract discrete world events — one entry per meaningful interaction between the party and an NPC or faction. Each entry should be a single factual sentence about what happened.

Session number: {session_n}

Known NPCs:
{npc_lines}

Known Factions:
{faction_lines}

DM's session notes:
{session_notes}

Return ONLY a JSON array. No prose before or after. Each element:
{{
  "entity_id": "<id from the lists above, or null if entity not listed>",
  "entity_type": "npc" or "faction",
  "entity_name": "<name as written in notes>",
  "note": "<one sentence: what happened>",
  "polarity": "positive" | "neutral" | "negative" | null,
  "intensity": 1 | 2 | 3,
  "event_type": "<combat|dialogue|politics|discovery|betrayal|etc or null>",
  "visibility": "public" | "dm_only"
}}

Rules:
- Only include entities that appear in the notes
- If an entity isn't in the known lists, still include it with entity_id: null
- polarity null means the event has no relationship significance
- intensity 1=minor, 2=moderate, 3=major
- dm_only if the event is something players shouldn't know yet
- Return an empty array [] if nothing meaningful happened

JSON array:"""

    message = _client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = message.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return json.loads(raw)
