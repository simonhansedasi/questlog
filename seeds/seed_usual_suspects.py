"""Seed script: The Usual Suspects — pre-reveal state for Collapse & Migrate demo.

Verbal Kint and Kaiser Soze exist as two separate NPCs. The demo:
  Open Verbal Kint → Advanced → Collapse & Migrate → Kaiser Soze → confirm.
The graph snaps: one node carries both the cooperative witness's benign history
and the criminal mastermind's terror network, connected to Kujan's investigation
through the same person.

Fiction mode. Observer: The Investigation. 5 sessions (Nights 0-5).
Showcases: hidden entities, dm_only logs, actor_id causation chains, dual-axis
relations, location_id on all events, party characters with log_character,
party_group_log, dead NPCs with dead_session, wikilinks in all notes.

Run:  python seeds/seed_usual_suspects.py
"""
import sys, json, secrets, shutil
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from src import data as db

SLUG = "usual_suspects"
CAMPAIGNS = ROOT / "campaigns"
CAMP_DIR  = CAMPAIGNS / SLUG

if CAMP_DIR.exists():
    shutil.rmtree(CAMP_DIR)
for d in ["world", "story", "dm"]:
    (CAMP_DIR / d).mkdir(parents=True, exist_ok=True)

def _w(rel, content):
    (CAMP_DIR / rel).write_text(json.dumps(content, indent=2))

_w("campaign.json", {
    "name": "The Usual Suspects",
    "slug": SLUG,
    "system": "Film — Bryan Singer / Christopher McQuarrie, 1995",
    "owner": "demo",
    "dm_pin": "1995",
    "share_token": secrets.token_urlsafe(16),
    "demo": True,
    "public": True,
    "mode": "fiction",
    "observer_name": "The Investigation",
    "terminology": {
        "npc": "Character", "npcs": "Characters",
        "session": "Night", "sessions": "Nights",
        "dm": "Director", "party": "The Investigation",
        "faction": "Organization", "factions": "Organizations",
        "cast_label": "Cast",
        "assets_label": "Evidence",
        "story_label": "Threads",
        "journal_label": "Case File",
        "brief_nav": "Briefing",
        "quest_label": "Thread",
        "quests_label": "Threads",
        "log_verb": "Record",
        "quick_log_label": "Quick Record",
        "notes_label": "Director Notes",
        "session_tools_label": "Write & Parse",
        "parse_cta": "Extract Events",
        "recap_cta": "Generate Night Summary",
        "brief_cta": "Case Brief",
        "dm_controls": "Director Controls",
        "recap_section_label": "Night Summary",
        "share_label": "Reader Share Link",
        "players_label": "Collaborators",
    },
})
_w("party.json",                   {"characters": []})
_w("assets.json",                  {"ships": []})
_w("journal.json",                 {"entries": []})
_w("references.json",              {"references": []})
_w("world/npcs.json",              {"npcs": []})
_w("world/factions.json",          {"factions": []})
_w("world/conditions.json",        {"conditions": []})
_w("story/quests.json",            {"quests": []})
_w("dm/session.json",              {})
_w("dm/relation_suggestions.json", [])
_w("world/locations.json",         {"locations": []})

print(f"Seeding {CAMP_DIR} ...")

# ── Helpers ────────────────────────────────────────────────────────────────────

def log_n(npc_id, session, note, polarity=None, intensity=1, event_type=None,
          visibility="public", actor_id=None, actor_type=None, location_id=None, ripple=False):
    evt = db.log_npc(SLUG, npc_id, session, note, polarity=polarity, intensity=intensity,
                     event_type=event_type, visibility=visibility,
                     actor_id=actor_id, actor_type=actor_type, location_id=location_id)
    if ripple and polarity in ("positive", "negative"):
        db.apply_ripple(SLUG, npc_id, "npc", session, note, polarity, intensity,
                        event_type, visibility, source_event_id=evt)
    return evt

def log_f(faction_id, session, note, polarity=None, intensity=1, event_type=None,
          visibility="public", actor_id=None, actor_type=None, location_id=None, ripple=False):
    evt = db.log_faction(SLUG, faction_id, session, note, polarity=polarity, intensity=intensity,
                         event_type=event_type, visibility=visibility,
                         actor_id=actor_id, actor_type=actor_type, location_id=location_id)
    if ripple and polarity in ("positive", "negative"):
        db.apply_ripple(SLUG, faction_id, "faction", session, note, polarity, intensity,
                        event_type, visibility, source_event_id=evt)
    return evt

def log_l(loc_id, session, note, polarity=None, intensity=1, event_type=None,
          visibility="public", actor_id=None, actor_type=None):
    db.log_location(SLUG, loc_id, session, note, polarity=polarity, intensity=intensity,
                    event_type=event_type, visibility=visibility,
                    actor_id=actor_id, actor_type=actor_type)

def log_c(char_name, session, note, polarity=None, intensity=1, event_type=None,
          visibility="public", actor_id=None, actor_type=None, location_id=None):
    db.log_character(SLUG, char_name, session, note, polarity=polarity, intensity=intensity,
                     event_type=event_type, visibility=visibility,
                     actor_id=actor_id, actor_type=actor_type, location_id=location_id)

def log_pg(session, note, polarity=None, intensity=1, event_type=None,
           visibility="public", actor_id=None, actor_type=None, location_id=None, party_name=None):
    db.log_party_group(SLUG, session, note, polarity=polarity, intensity=intensity,
                       event_type=event_type, visibility=visibility,
                       actor_id=actor_id, actor_type=actor_type,
                       location_id=location_id, party_name=party_name)

def add_rel(src_type, src_id, tgt_id, tgt_type, relation, weight=0.8, dm_only=False):
    fname = "world/npcs.json" if src_type == "npc" else "world/factions.json"
    key   = "npcs"            if src_type == "npc" else "factions"
    data  = db._load(SLUG, fname)
    for e in data[key]:
        if e["id"] == src_id:
            rels = e.setdefault("relations", [])
            if not any(r["target"] == tgt_id for r in rels):
                r = {"target": tgt_id, "target_type": tgt_type, "relation": relation, "weight": weight}
                if dm_only:
                    r["dm_only"] = True
                rels.append(r)
    db._save(SLUG, data, fname)

def add_dual_rel(src_type, src_id, tgt_id, tgt_type, formal, personal, weight=0.85, dm_only=False):
    fname = "world/npcs.json" if src_type == "npc" else "world/factions.json"
    key   = "npcs"            if src_type == "npc" else "factions"
    data  = db._load(SLUG, fname)
    for e in data[key]:
        if e["id"] == src_id:
            rels = e.setdefault("relations", [])
            if not any(r["target"] == tgt_id for r in rels):
                r = {"target": tgt_id, "target_type": tgt_type,
                     "formal_relation": formal, "personal_relation": personal, "weight": weight}
                if dm_only:
                    r["dm_only"] = True
                rels.append(r)
    db._save(SLUG, data, fname)

# ── Locations ──────────────────────────────────────────────────────────────────
print("  locations ...")
L = {}
L["introom"] = db.add_location(SLUG, "The Interrogation Room",
    role="US Customs Office, San Pedro",
    description="A beige federal office. A coffee-ringed table. A window that looks into a parking structure. "
                "[[Agent Dave Kujan]] has been in this room for six hours and he still has nothing. "
                "On the bulletin board behind him: names, faces, shipping manifests — everything [[Verbal Kint]] needed.")
L["osttex"] = db.add_location(SLUG, "The Osttex",
    role="Argentine freighter, San Pedro Docks — Pier 17",
    description="A rusted Argentine freighter carrying what was claimed to be 91 million dollars in cocaine. "
                "Whatever it carried, 27 men died here on a Thursday morning. The ship burned to the waterline.")
L["lineup"] = db.add_location(SLUG, "New York Lineup Room",
    role="NYPD 21st Precinct — Manhattan",
    description="A bare room with height markings on the wall. Five men who had never met stood here and read numbers. "
                "They made each other laugh. That was the beginning.")
L["kob_ofc"] = db.add_location(SLUG, "Kobayashi's Office",
    role="Attorney's Office, Downtown Los Angeles",
    description="A glass tower. A very expensive suit. Files on every man in the room — criminal records, "
                "family addresses, crimes never prosecuted. [[Kobayashi]] said [[Kaiser Soze]] sends his regards.")
L["safehouse"] = db.add_location(SLUG, "The Safe House",
    role="San Pedro — one mile from the docks",
    description="A rented property used for planning. [[McManus]] said it smelled like a dead cat. "
                "Nobody disagreed. [[Dean Keaton]] spread the dock maps on the kitchen table.")

# ── Factions ───────────────────────────────────────────────────────────────────
print("  factions ...")
db.add_faction(SLUG, "The Five", relationship="neutral", hidden=False,
    role="The Crew",
    description="Five criminals brought together in a New York police lineup on a weapons charge. "
                "A gun charge that went nowhere. Five men who had no reason to know each other "
                "and every reason not to. [[Dean Keaton]] didn't want to be there. "
                "[[Verbal Kint]] was just happy to survive.")

db.add_faction(SLUG, "Soze's Organization", relationship="hostile", hidden=True,
    role="Criminal Empire",
    description="No one has ever seen [[Kaiser Soze]] and lived to tell about it in a way that was believed. "
                "His organization moves money, men, and information across three continents. "
                "It doesn't have a name. It doesn't need one.",
    dm_notes="[[Verbal Kint]] IS [[Kaiser Soze]]. Every event logged here was executed under his direct control. "
             "The organization is the man. Demo: collapse Verbal into Soze to reveal the unified node.")

db.add_faction(SLUG, "US Customs", relationship="ally", hidden=False,
    role="Federal Law Enforcement",
    description="[[Agent Dave Kujan]]'s organization. They want [[Kaiser Soze]] badly enough to give immunity "
                "to a man who witnessed 27 murders and walked away without a scratch.")

db.add_faction(SLUG, "The Hungarians", relationship="hostile", hidden=True,
    role="Criminal Organization — destroyed",
    description="[[Arkosh Kovash]]'s people. They came to San Pedro to identify [[Kaiser Soze]] to [[US Customs]]. "
                "[[Kaiser Soze]] learned about the meeting and sent [[The Five]] to the docks. "
                "Every Hungarian died on the [[The Osttex|Osttex]].")

# ── NPCs ───────────────────────────────────────────────────────────────────────
print("  characters ...")

db.add_npc(SLUG, "Verbal Kint", role="Cooperative Witness",
    relationship="neutral", hidden=False,
    factions=["the_five"],
    hidden_factions=["sozes_organization"],
    description="Small. Polite. A slight limp from childhood. [[Agent Dave Kujan]] called him a gimp "
                "and offered him coffee. He gave five hours of testimony, accepted immunity, and walked out. "
                "He knew everything.",
    dm_notes="He is [[Kaiser Soze]]. The limp is an affectation he has maintained for years. "
             "The cooperation was a calculated performance. Every word of his testimony was either true, "
             "a lie, or something he read off the bulletin board behind Agent Kujan. "
             "DEMO: collapse Verbal Kint into Kaiser Soze to reveal the unified entity.")

db.add_npc(SLUG, "Kaiser Soze", role="Ghost — Criminal Architect",
    relationship="hostile", hidden=True,
    factions=["sozes_organization"],
    description="A man. A myth. A Turk. He killed his own family rather than let the Hungarians use them "
                "as leverage — then killed the Hungarians, their families, and everyone who had ever done "
                "business with them. Then he disappeared. The legend is the security system.",
    dm_notes="This entity and [[Verbal Kint]] are the same person. "
             "DEMO: open Verbal Kint → Advanced → Collapse & Migrate → Kaiser Soze. "
             "All log entries and relations merge. One unified node shows the full picture.")

db.add_npc(SLUG, "Kobayashi", role="Soze's Attorney and Fixer",
    relationship="hostile", hidden=False,
    factions=["sozes_organization"],
    description="Impeccable English. A Savile Row suit. He knew every family member's address, "
                "every uncharged crime, every vulnerability in the room. He wasn't threatening them. "
                "He was demonstrating capability.")

db.add_npc(SLUG, "Dean Keaton", role="Former Dirty Cop — Reluctant Leader",
    relationship="neutral", hidden=False,
    factions=["the_five"],
    description="Corrupt detective who went straight. Three times indicted, never convicted. "
                "He had a restaurant. He had [[Edie Finneran]]. [[McManus]] pulled him back in. "
                "[[Verbal Kint]] watched him die.")

db.add_npc(SLUG, "McManus", role="The Hothead — Crew Planner",
    relationship="neutral", hidden=False,
    factions=["the_five"],
    description="The best thief [[Dean Keaton]] had ever seen. Ran the lineup job. "
                "Ran the taxi job. Ran his mouth constantly. On the [[The Osttex|Osttex]] he ran out of luck.")

db.add_npc(SLUG, "Fenster", role="McManus's Partner",
    relationship="neutral", hidden=False,
    factions=["the_five"],
    description="[[McManus]]'s right hand. Spoke in a way that made people lean in — "
                "they always left more confused. He tried to run when he understood the situation. "
                "He was the first to go.")

db.add_npc(SLUG, "Hockney", role="The Professional",
    relationship="neutral", hidden=False,
    factions=["the_five"],
    description="Quiet. Competent. Had been in Attica. Nobody asked about it. "
                "He came for the score, did the work, and died next to [[McManus]] on a burning dock.")

db.add_npc(SLUG, "Arkosh Kovash", role="Hungarian Survivor — Key Witness",
    relationship="hostile", hidden=True,
    factions=["the_hungarians"],
    description="The only Hungarian who survived the [[The Osttex|Osttex]] fire. Badly burned. "
                "Spoke only to Agent [[Baer]]. Said one name. The sketch took three days.")

db.add_npc(SLUG, "Agent Baer", role="US Customs — San Pedro Field Office",
    relationship="ally", hidden=False,
    factions=["us_customs"],
    description="[[Agent Dave Kujan]]'s colleague in San Pedro. Handled the [[Arkosh Kovash]] interview. "
                "Faxed the sketch. By the time the fax reached [[Agent Dave Kujan|Kujan]]'s hand, "
                "[[Verbal Kint]] was already in a black car rounding the corner.")

# ── Party ──────────────────────────────────────────────────────────────────────
print("  party ...")
db.add_character(SLUG, "Agent Dave Kujan", race="", char_class="US Customs Special Agent", level=1,
    notes="He had [[Verbal Kint]] in that room for six hours. He was certain [[Dean Keaton]] ran "
          "everything. He was right that Keaton was involved. He was wrong about everything else.")
db.set_npc_party_affiliate(SLUG, "agent_baer", True)

# ── Relations ──────────────────────────────────────────────────────────────────
print("  relations ...")

# The Five — crew bonds
add_rel("npc", "dean_keaton", "the_five",    "faction", "ally",  0.9)
add_rel("npc", "mcmanus",     "the_five",    "faction", "ally",  0.9)
add_rel("npc", "fenster",     "the_five",    "faction", "ally",  0.9)
add_rel("npc", "hockney",     "the_five",    "faction", "ally",  0.9)
add_rel("npc", "verbal_kint", "the_five",    "faction", "ally",  0.7)
add_rel("npc", "mcmanus",     "dean_keaton", "npc",     "ally",  0.9)
add_rel("npc", "fenster",     "mcmanus",     "npc",     "ally",  0.95)
add_rel("npc", "hockney",     "mcmanus",     "npc",     "ally",  0.8)

# Verbal → Keaton: publicly cooperative, but Soze is using Keaton as a tool
add_dual_rel("npc", "verbal_kint", "dean_keaton", "npc",
             formal="ally", personal="rival", weight=0.75)

# Soze's network
add_rel("npc", "kaiser_soze", "sozes_organization", "faction", "ally",  1.0)
add_rel("npc", "kobayashi",   "sozes_organization", "faction", "ally",  0.95)
add_rel("npc", "kaiser_soze", "kobayashi",          "npc",     "ally",  0.95)
# Verbal's hidden allegiance — the key dm_only link
add_rel("npc", "verbal_kint", "sozes_organization", "faction", "ally",  1.0, dm_only=True)

# Soze vs the world
add_rel("npc", "kaiser_soze", "the_hungarians", "faction", "rival", 1.0)
add_rel("npc", "kaiser_soze", "the_five",       "faction", "rival", 0.9,  dm_only=True)
add_dual_rel("npc", "kaiser_soze", "dean_keaton", "npc",
             formal="ally", personal="rival", weight=0.9, dm_only=True)

# Kobayashi coerces the crew
add_rel("npc", "kobayashi", "the_five", "faction", "rival", 0.8)

# Arkosh
add_rel("npc", "arkosh_kovash", "the_hungarians", "faction", "ally",  0.9)
add_rel("npc", "arkosh_kovash", "kaiser_soze",    "npc",     "rival", 1.0)

# Faction-level
add_rel("faction", "the_five",           "sozes_organization", "faction", "rival", 0.9)
add_rel("faction", "sozes_organization", "the_hungarians",     "faction", "rival", 1.0)
add_rel("faction", "sozes_organization", "us_customs",         "faction", "rival", 0.8)
add_rel("faction", "us_customs",         "the_five",           "faction", "ally",  0.5)
add_rel("faction", "us_customs",         "sozes_organization", "faction", "rival", 0.9)
add_rel("faction", "the_hungarians",     "sozes_organization", "faction", "rival", 1.0)

print("  relations set")

# ── Threads (Quests) ───────────────────────────────────────────────────────────
print("  threads ...")
db.add_quest(SLUG, "Identify Kaiser Soze",
    description="27 men died on a burning freighter in San Pedro. One badly burned Hungarian survivor "
                "whispered a name to [[Agent Baer]]. US Customs has been hunting this man for fifteen years. "
                "Every lead ends with dead witnesses.",
    hidden=False, status="active")
db.add_quest(SLUG, "The Osttex Massacre",
    description="What actually happened on [[The Osttex|Pier 17]]? The official story is a drug deal gone wrong. "
                "[[Arkosh Kovash]] says something else. The five suspects from the lineup are the only "
                "witnesses. Four of them are dead.",
    hidden=False, status="active")
db.add_quest(SLUG, "The Testimony of Verbal Kint",
    description="[[Verbal Kint]] spent six hours telling [[Agent Dave Kujan]] everything — the lineup, "
                "[[Kobayashi]], [[Dean Keaton]]'s plan, the Osttex. Every detail checked out. "
                "Every name was verifiable. The question is what he left out.",
    hidden=False, status="active")

# ── Night 0 — Origin (dm_only backstory) ──────────────────────────────────────
print("  Night 0 (backstory) ...")

log_n("kaiser_soze", 0,
    "The Hungarians took [[Kaiser Soze]]'s family and held them at gunpoint to send a message. "
    "[[Kaiser Soze]] came home, looked at each of them, and shot his wife and children himself "
    "before the Hungarians could use them further. Then he killed every Hungarian in the room.",
    polarity="negative", intensity=3, event_type="combat", visibility="dm_only",
    actor_id="the_hungarians", actor_type="faction")

log_n("kaiser_soze", 0,
    "[[Kaiser Soze]] spent the next two years tracking down every associate, family member, "
    "and business contact of the Hungarians who had come for him. He killed them all. "
    "Then he burned the businesses. Then he vanished into legend.",
    polarity="negative", intensity=3, event_type="combat", visibility="dm_only")

log_f("the_hungarians", 0,
    "The men who moved against [[Kaiser Soze]] did not survive the encounter. "
    "The organization that remained understood that Soze existed beyond the normal logic of retaliation. "
    "His name became a warning told in the dark.",
    polarity="negative", intensity=3, event_type="combat", visibility="dm_only",
    actor_id="kaiser_soze", actor_type="npc", ripple=True)

# ── Night 1 — The Lineup ───────────────────────────────────────────────────────
print("  Night 1 (the lineup) ...")

log_pg(1,
    "Five men — [[Dean Keaton]], [[McManus]], [[Fenster]], [[Hockney]], and [[Verbal Kint]] — "
    "were arrested in New York on a weapons charge and placed together in a holding cell. "
    "The charges went nowhere. The five men did not go nowhere.",
    polarity="neutral", intensity=2, event_type="politics",
    actor_id="us_customs", actor_type="faction",
    location_id=L["lineup"], party_name="The Investigation")

log_n("verbal_kint", 1,
    "[[Verbal Kint]] cooperated completely with the weapons charge, signed everything, "
    "and said nothing memorable. [[Agent Dave Kujan|Kujan]] barely noticed him.",
    polarity="neutral", intensity=1, event_type="dialogue",
    actor_id="agent_baer", actor_type="npc",
    location_id=L["lineup"])

log_n("dean_keaton", 1,
    "[[Dean Keaton]] resisted the arrest. His lawyer had him out in four hours. "
    "He told [[McManus]] he was done with this life. [[McManus]] had heard this before.",
    polarity="negative", intensity=2, event_type="politics",
    actor_id="us_customs", actor_type="faction",
    location_id=L["lineup"])

log_n("mcmanus", 1,
    "[[McManus]] read the lineup number aloud as if it were a bad audition, made [[Fenster]] laugh, "
    "and got them all made to do it three more times. He had a plan by the end of the night.",
    polarity="neutral", intensity=1, event_type="dialogue",
    location_id=L["lineup"])

log_n("fenster", 1,
    "[[Fenster]] spent the holding cell night explaining [[McManus]]'s taxi company plan "
    "in a way that somehow made it clearer and more confusing simultaneously. "
    "[[McManus]] didn't care. The numbers worked.",
    polarity="neutral", intensity=1, event_type="dialogue",
    location_id=L["lineup"])

log_n("hockney", 1,
    "[[Hockney]] said four words during the entire lineup. Two were to the lawyer. "
    "He had done this before and knew which four words mattered.",
    polarity="neutral", intensity=1, event_type="dialogue",
    location_id=L["lineup"])

log_l(L["lineup"], 1,
    "The [[New York Lineup Room|lineup room]] processed five men with no prior connection. "
    "They left with a plan for the Taxi job, and something harder to name.",
    polarity="neutral", intensity=2, event_type="politics")

# Soze identifies the assets (dm_only)
log_n("kaiser_soze", 1,
    "[[Kaiser Soze]] had the lineup report within hours of the arrests. "
    "Five talented, unconnected criminals with no knowledge of him and no loyalty to each other. "
    "Exactly the profile he needed for [[The Osttex|Pier 17]].",
    polarity="positive", intensity=2, event_type="politics", visibility="dm_only")

log_f("sozes_organization", 1,
    "[[Soze's Organization]] began compiling full dossiers on all five suspects: "
    "known associates, family members, prior arrests, outstanding uncharged crimes, "
    "personal vulnerabilities. Everything [[Kobayashi]] would need.",
    polarity="positive", intensity=2, event_type="politics", visibility="dm_only",
    actor_id="kaiser_soze", actor_type="npc")

# The taxi job
evt = log_n("mcmanus", 1,
    "[[McManus]] organized the crew to rob a taxi company's cash drop — "
    "three million dollars, minimal risk, guards on a predictable schedule. "
    "[[Dean Keaton]] ran the job. It went perfectly.",
    polarity="positive", intensity=2, event_type="combat")
db.apply_ripple(SLUG, "mcmanus", "npc", 1,
    "The taxi job ran clean — three million split five ways, no shots fired.",
    "positive", 2, "combat", source_event_id=evt)

log_f("the_five", 1,
    "The taxi job went perfectly. The five men who were strangers in a lineup "
    "became something harder to describe — not friends, not a crew exactly, "
    "but people who had seen each other work.",
    polarity="positive", intensity=2, event_type="combat",
    actor_id="mcmanus", actor_type="npc")

log_c("Agent Dave Kujan", 1,
    "[[Agent Dave Kujan|Kujan]] received the weapons charge report and filed it. "
    "Five separate men, no common motive. He didn't connect the names for another six months.",
    polarity="neutral", intensity=1, event_type="politics",
    actor_id="agent_baer", actor_type="npc",
    location_id=L["introom"])

# ── Night 2 — The Ultimatum ────────────────────────────────────────────────────
print("  Night 2 (the ultimatum) ...")

evt = log_n("kobayashi", 2,
    "[[Kobayashi]] met the five in a parking garage in Los Angeles. He had files on every man — "
    "criminal records, home addresses, the names of their families, crimes never prosecuted. "
    "He said [[Kaiser Soze]] sends his regards and placed the files on the hood of the car.",
    polarity="negative", intensity=3, event_type="dialogue",
    actor_id="kaiser_soze", actor_type="npc",
    location_id=L["kob_ofc"])
db.apply_ripple(SLUG, "kobayashi", "npc", 2,
    "Kobayashi delivered Soze's ultimatum — compliance or consequences for everyone they loved.",
    "negative", 3, "dialogue", source_event_id=evt)

log_f("the_five", 2,
    "[[Kobayashi]] informed the crew they had unknowingly robbed a truck belonging to "
    "[[Soze's Organization]]. The price of that error was one job. "
    "[[Dean Keaton]] said no. [[Kobayashi]] slid a photograph across the hood.",
    polarity="negative", intensity=3, event_type="politics",
    actor_id="kobayashi", actor_type="npc",
    location_id=L["kob_ofc"])

log_n("dean_keaton", 2,
    "[[Dean Keaton]] told [[Kobayashi]] they weren't interested. [[Kobayashi]] produced a photograph "
    "of [[Edie Finneran]]. [[Dean Keaton|Keaton]] looked at it for a long time before he sat back down.",
    polarity="negative", intensity=3, event_type="dialogue",
    actor_id="kobayashi", actor_type="npc",
    location_id=L["kob_ofc"])

log_n("verbal_kint", 2,
    "[[Verbal Kint]] sat quietly through the entire meeting at [[Kobayashi's Office|Kobayashi's office]], "
    "asked no questions, signed nothing, and was the first to say he would do the job.",
    polarity="neutral", intensity=1, event_type="dialogue",
    location_id=L["kob_ofc"])

log_n("fenster", 2,
    "[[Fenster]] told [[McManus]] he was going to run. He had a contact in Arizona. "
    "He would be gone by Thursday. He was right about the timeline.",
    polarity="negative", intensity=2, event_type="dialogue",
    actor_id="kobayashi", actor_type="npc")

# Fenster dies
log_n("fenster", 2,
    "[[Fenster]] was found dead in a drainage ditch outside San Pedro. "
    "Cause of death was never officially determined. He was the first.",
    polarity="negative", intensity=3, event_type="other", visibility="public")

log_n("kaiser_soze", 2,
    "[[Fenster]] attempted to flee to Arizona. [[Kaiser Soze]] tracked him in eleven hours "
    "and killed him personally. The body was placed where the remaining four would find it. "
    "A demonstration, not a disposal.",
    polarity="negative", intensity=3, event_type="combat", visibility="dm_only",
    location_id=L["safehouse"])

db.set_npc_dead(SLUG, "fenster", True, dead_session=2)

log_n("mcmanus", 2,
    "[[McManus]] identified [[Fenster]]'s body. He didn't say anything for two days. "
    "Then he started studying the dock maps.",
    polarity="negative", intensity=3, event_type="other",
    actor_id="kaiser_soze", actor_type="npc")

log_n("dean_keaton", 2,
    "[[Dean Keaton]] began planning the Osttex operation the night [[Fenster]] was found. "
    "He stopped talking about quitting. He called [[Edie Finneran]] and told her nothing.",
    polarity="negative", intensity=2, event_type="politics",
    actor_id="kaiser_soze", actor_type="npc")

log_l(L["kob_ofc"], 2,
    "[[Kobayashi]] delivered the ultimatum. Five files. One photograph of [[Edie Finneran]]. "
    "The meeting ended when [[Dean Keaton]] sat back down.",
    polarity="negative", intensity=3, event_type="dialogue",
    actor_id="kaiser_soze", actor_type="npc")

# ── Night 3 — The Planning ─────────────────────────────────────────────────────
print("  Night 3 (planning the job) ...")

log_pg(3,
    "The crew cased the San Pedro docks for three days from the safe house. "
    "They had the guard rotations, the cargo manifest, the shift change timing. "
    "[[Dean Keaton]] ran the operation planning like a professional with nothing left to lose.",
    polarity="neutral", intensity=2, event_type="politics",
    location_id=L["safehouse"], party_name="The Investigation")

log_n("dean_keaton", 3,
    "[[Dean Keaton]] laid out the operation at [[The Safe House|the safe house]]: board the [[The Osttex|Osttex]] at 0200, "
    "secure the cocaine, transfer to a second vessel before Customs arrived. "
    "Clean. Fast. No loose ends.",
    polarity="neutral", intensity=2, event_type="dialogue",
    location_id=L["safehouse"])

log_n("verbal_kint", 3,
    "[[Verbal Kint]] observed the planning from the corner of the room. He asked careful questions. "
    "He contributed a detail about the guard schedule that no one else had noticed. "
    "[[McManus]] told [[Dean Keaton|Keaton]] he was smarter than he looked.",
    polarity="neutral", intensity=1, event_type="dialogue",
    location_id=L["safehouse"])

log_n("kaiser_soze", 3,
    "[[Kaiser Soze]] knew there was no cocaine aboard the [[The Osttex|Osttex]]. "
    "The true target was [[Arkosh Kovash]] — a Hungarian cooperating with [[US Customs]] "
    "who could identify Soze by sight. The crew were assassins who believed they were thieves.",
    polarity="neutral", intensity=3, event_type="politics", visibility="dm_only",
    location_id=L["safehouse"])

log_n("arkosh_kovash", 3,
    "[[Arkosh Kovash]] arrived in San Pedro aboard the [[The Osttex|Osttex]] under [[US Customs]] protection. "
    "He was scheduled to provide formal identification testimony regarding [[Kaiser Soze]] "
    "to federal investigators the following week.",
    polarity="neutral", intensity=2, event_type="politics", visibility="dm_only",
    actor_id="us_customs", actor_type="faction",
    location_id=L["osttex"])

log_f("us_customs", 3,
    "[[US Customs]] arranged secure transport and housing for [[Arkosh Kovash]]'s testimony. "
    "The operation was considered secure. No one on the team knew about the five men "
    "watching the docks from a rented house one mile away.",
    polarity="positive", intensity=2, event_type="politics",
    location_id=L["osttex"])

log_l(L["safehouse"], 3,
    "The dock maps covered the kitchen table for three days. The crew knew the [[The Osttex|Osttex]] "
    "better than the crew that worked it. [[Dean Keaton]] said it would take twenty minutes.",
    polarity="neutral", intensity=2, event_type="politics",
    actor_id="dean_keaton", actor_type="npc")

# ── Night 4 — The Massacre ─────────────────────────────────────────────────────
print("  Night 4 (the Osttex) ...")

log_l(L["osttex"], 4,
    "At 0200 on Thursday the [[The Osttex|Osttex]] was boarded by an unknown number of men. "
    "Twenty-seven people died. The ship burned to the waterline. "
    "US Customs arrived forty minutes later.",
    polarity="negative", intensity=3, event_type="combat",
    actor_id="kaiser_soze", actor_type="npc")

log_pg(4,
    "The crew boarded the [[The Osttex|Osttex]] at 0200 and immediately encountered armed resistance. "
    "The intel was wrong. There was no cocaine. There were men waiting for them in the dark.",
    polarity="negative", intensity=3, event_type="combat",
    location_id=L["osttex"], party_name="The Investigation")

log_n("mcmanus", 4,
    "[[McManus]] was killed in the firefight on the deck of the [[The Osttex|Osttex]]. "
    "He was the best thief [[Dean Keaton]] had ever seen.",
    polarity="negative", intensity=3, event_type="combat",
    location_id=L["osttex"])
db.set_npc_dead(SLUG, "mcmanus", True, dead_session=4)

log_n("hockney", 4,
    "[[Hockney]] was killed alongside [[McManus]] on the burning deck. "
    "He had done the work and taken the money and died next to the only man he trusted.",
    polarity="negative", intensity=3, event_type="combat",
    location_id=L["osttex"])
db.set_npc_dead(SLUG, "hockney", True, dead_session=4)

log_n("arkosh_kovash", 4,
    "[[Arkosh Kovash]] survived the [[The Osttex|Osttex]] fire with severe burns to his hands and face. "
    "He was the only Hungarian alive. He kept repeating one name to the paramedics.",
    polarity="negative", intensity=3, event_type="combat",
    actor_id="kaiser_soze", actor_type="npc",
    location_id=L["osttex"])

log_n("kaiser_soze", 4,
    "[[Kaiser Soze]] killed [[Dean Keaton]] personally at the end of the [[The Osttex|Osttex]] operation — "
    "a shot to the chest and one to verify. Keaton was the one man from the lineup "
    "who had seen his face and understood what he had seen.",
    polarity="negative", intensity=3, event_type="combat", visibility="dm_only",
    location_id=L["osttex"])

log_n("dean_keaton", 4,
    "[[Dean Keaton]] was shot on the dock and left burning. [[Verbal Kint]] said he watched him die. "
    "He was telling the truth about that part.",
    polarity="negative", intensity=3, event_type="combat",
    actor_id="kaiser_soze", actor_type="npc",
    location_id=L["osttex"])
db.set_npc_dead(SLUG, "dean_keaton", True, dead_session=4)

log_n("verbal_kint", 4,
    "[[Verbal Kint]] was the only member of the crew to survive the [[The Osttex|Osttex]] without injury. "
    "He was found sitting on a piling half a mile from the fire, hands folded in his lap.",
    polarity="neutral", intensity=2, event_type="other",
    location_id=L["osttex"])

evt = log_f("the_five", 4,
    "Of the five men from the lineup: [[McManus]] dead on the [[The Osttex|Osttex]] deck, "
    "[[Hockney]] dead beside him, [[Dean Keaton]] shot on the dock, [[Fenster]] dead in a drainage ditch. "
    "[[Verbal Kint]] sits on a piling and waits for the police.",
    polarity="negative", intensity=3, event_type="combat",
    actor_id="kaiser_soze", actor_type="npc",
    location_id=L["osttex"])
db.apply_ripple(SLUG, "the_five", "faction", 4,
    "The crew is destroyed — four dead, one witness.",
    "negative", 3, "combat", source_event_id=evt)

log_f("the_hungarians", 4,
    "Every Hungarian on the [[The Osttex|Osttex]] died in the operation. "
    "[[Arkosh Kovash]] alone survived. [[Kaiser Soze]]'s primary objective — "
    "eliminating the witness who could identify him — was not achieved.",
    polarity="negative", intensity=3, event_type="combat",
    actor_id="kaiser_soze", actor_type="npc",
    location_id=L["osttex"])

log_c("Agent Dave Kujan", 4,
    "[[Agent Dave Kujan|Kujan]] arrived at [[The Osttex|Pier 17]] forty minutes after the fire started. "
    "Twenty-seven bodies. One surviving crew member sitting on a piling. "
    "He recognized the name from a weapons charge six months ago.",
    polarity="negative", intensity=3, event_type="discovery",
    location_id=L["osttex"])

# ── Night 5 — The Interrogation ────────────────────────────────────────────────
print("  Night 5 (the interrogation) ...")

log_c("Agent Dave Kujan", 5,
    "[[Agent Dave Kujan|Kujan]] interrogated [[Verbal Kint]] for six hours. "
    "Verbal gave him everything — the lineup, [[Kobayashi]], [[Dean Keaton]]'s plan, "
    "the Osttex. Kujan became certain [[Dean Keaton|Keaton]] had orchestrated everything. "
    "He was wrong about the direction.",
    polarity="neutral", intensity=2, event_type="dialogue",
    actor_id="verbal_kint", actor_type="npc",
    location_id=L["introom"])

log_n("verbal_kint", 5,
    "[[Verbal Kint]] gave [[Agent Dave Kujan|Agent Kujan]] a complete and coherent account "
    "of everything leading to the [[The Osttex|Osttex]]. Every detail checked out. "
    "Every name was verifiable. He accepted immunity and signed the papers without hesitation.",
    polarity="neutral", intensity=1, event_type="dialogue",
    actor_id="agent_baer", actor_type="npc",
    location_id=L["introom"])

log_n("verbal_kint", 5,
    "[[Verbal Kint]] walked out of the US Customs office into the San Pedro sunlight. "
    "[[Kobayashi]]'s car was waiting at the curb. Everything had been arranged.",
    polarity="positive", intensity=1, event_type="movement",
    location_id=L["introom"])

log_n("verbal_kint", 5,
    "Outside the building, [[Verbal Kint]]'s limp gradually disappeared. "
    "His curled fingers straightened. His posture changed. By the time the car reached the corner, "
    "a different man was sitting in it.",
    polarity="neutral", intensity=3, event_type="other", visibility="dm_only",
    location_id=L["introom"])

log_n("arkosh_kovash", 5,
    "[[Arkosh Kovash]] gave [[Agent Baer]] a full physical description of the man who had killed "
    "everyone on the [[The Osttex|Osttex]]. The composite sketch took three days to complete.",
    polarity="neutral", intensity=2, event_type="dialogue",
    actor_id="agent_baer", actor_type="npc")

log_n("kaiser_soze", 5,
    "[[Kaiser Soze]] spent six hours in that room directing [[Agent Dave Kujan|Kujan]]'s attention "
    "toward a dead man. He answered every question truthfully, in a way that pointed to "
    "[[Dean Keaton|Keaton]] as the architect. He walked out with immunity and a car waiting. "
    "And like that — he was gone.",
    polarity="positive", intensity=3, event_type="politics", visibility="dm_only",
    location_id=L["introom"])

log_c("Agent Dave Kujan", 5,
    "[[Agent Dave Kujan|Kujan]] looked at the bulletin board. He started reading the names aloud. "
    "Kobayashi. Redfoot. Skokie. McManus. Every name in [[Verbal Kint|Verbal's]] testimony "
    "was on that wall. He ran. The parking lot was empty.",
    polarity="negative", intensity=3, event_type="discovery",
    location_id=L["introom"])

evt = log_f("us_customs", 5,
    "[[US Customs]] received the composite sketch of [[Kaiser Soze]] from [[Arkosh Kovash]] "
    "after [[Verbal Kint]] had already been released. The description matched no one in their files. "
    "The black car was never traced.",
    polarity="negative", intensity=3, event_type="politics",
    actor_id="kaiser_soze", actor_type="npc",
    location_id=L["introom"])

log_l(L["introom"], 5,
    "Six hours. A table. Two coffees. A complete and coherent account of everything. "
    "When [[Agent Dave Kujan|Kujan]] ran to the window the parking lot was empty "
    "and the fax from [[Agent Baer]] was still warm in his hand.",
    polarity="negative", intensity=3, event_type="discovery",
    actor_id="kaiser_soze", actor_type="npc")

# ── Conditions ─────────────────────────────────────────────────────────────────
print("  conditions ...")
db.add_condition(SLUG, "Verbal's Immunity Agreement",
    region="Federal Jurisdiction — San Pedro",
    effect_type="legal", effect_scope="single", magnitude=3,
    description="[[Verbal Kint]] cannot be prosecuted for any crimes described in his testimony. "
                "[[Agent Dave Kujan|Agent Kujan]] believes this was a mistake in retrospect. "
                "He is correct, but not in the way he currently understands.",
    hidden=False)
db.set_condition_hidden(SLUG, "verbals_immunity_agreement", False)
db.log_condition(SLUG, "verbals_immunity_agreement", 5,
    "The immunity agreement was signed, notarized, and witnessed by [[Agent Baer]]. "
    "[[Verbal Kint]] signed without reading it. He already knew what it said.",
    polarity="positive", intensity=2, event_type="politics",
    actor_id="agent_baer", actor_type="npc")

db.add_condition(SLUG, "The Soze Composite Sketch",
    region="US Customs — San Pedro Field Office",
    effect_type="intelligence", effect_scope="investigation", magnitude=3,
    description="[[Arkosh Kovash]]'s description of the man who killed everyone on the [[The Osttex|Osttex]]. "
                "Three days in the making. It arrived on [[Agent Dave Kujan|Agent Kujan]]'s desk "
                "the moment [[Verbal Kint]] walked out the door.",
    hidden=True)
db.log_condition(SLUG, "the_soze_composite_sketch", 5,
    "The sketch arrived via fax from [[Agent Baer]] while [[Agent Dave Kujan|Kujan]] was still "
    "processing [[Verbal Kint]]'s release. He read it. Then he read it again. Then he ran.",
    polarity="negative", intensity=3, event_type="discovery",
    actor_id="arkosh_kovash", actor_type="npc")

# ── Journal ────────────────────────────────────────────────────────────────────
print("  journal ...")
db.post_journal(SLUG, 1,
    "Night 1 — The Lineup",
    "A weapons charge that went nowhere. Five men. A holding cell. By the time they were released "
    "they had a plan and a shared vocabulary. The taxi job worked perfectly. Three million, no shots fired. "
    "None of us knew that the lineup was where it started — not with the arrest, but with whoever "
    "pulled the report an hour after it was filed.")

db.post_journal(SLUG, 2,
    "Night 2 — The Ultimatum",
    "Kobayashi knew everything. Every uncharged crime, every family address, every vulnerability. "
    "He said Kaiser Soze sends his regards like it was a pleasantry. "
    "Fenster tried to run. They found him in a ditch two days later. Nobody tried to run again. "
    "Keaton stopped talking about the restaurant.")

db.post_journal(SLUG, 4,
    "Night 4 — The Osttex",
    "There was no cocaine. There were men waiting in the dark with automatic weapons. "
    "McManus and Hockney died on the deck. Keaton was shot on the dock. "
    "I sat on a piling and watched the ship burn and waited for the police. "
    "I was the only one without a scratch.")

db.post_journal(SLUG, 5,
    "Night 5 — The Testimony",
    "Six hours. He asked good questions. He wanted Keaton to be the answer "
    "and I gave him Keaton, because Keaton was dead and dead men make excellent answers. "
    "Every word I said was true. The shape of it was the lie. "
    "The car was waiting when I walked out. Everything had been arranged.")

print(f"\nDone. Campaign '{SLUG}' seeded at {CAMP_DIR}")
print("DEMO: Verbal Kint page → Advanced → Collapse & Migrate → Kaiser Soze")
print("The graph will show a unified node with the full cooperative + criminal history.")
