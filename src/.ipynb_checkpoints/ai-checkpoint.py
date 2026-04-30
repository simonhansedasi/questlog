import os
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
