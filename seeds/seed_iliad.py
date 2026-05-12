"""Seed script: The Iliad — Homer's fifty-one days in year ten of the Trojan War.

Showcases: dual-axis conflict edges, world conditions, story arcs, observer_name,
fiction mode terminology, ripple chains across a full event log, set_npc_dead,
source_event_id on all apply_ripple calls.

Run:  python seeds/seed_iliad.py
"""
import sys, json, secrets, shutil
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from src import data as db

SLUG = "iliad"
CAMPAIGNS = ROOT / "campaigns"
CAMP_DIR = CAMPAIGNS / SLUG

# ── Wipe and recreate ──────────────────────────────────────────────────────────
if CAMP_DIR.exists():
    shutil.rmtree(CAMP_DIR)
for d in ["world", "story", "dm"]:
    (CAMP_DIR / d).mkdir(parents=True, exist_ok=True)

def _w(rel_path, content):
    (CAMP_DIR / rel_path).write_text(json.dumps(content, indent=2))

# ── Campaign metadata ──────────────────────────────────────────────────────────
_w("campaign.json", {
    "name": "The Iliad",
    "slug": "iliad",
    "system": "Greek Epic — Homer",
    "owner": "demo",
    "dm_pin": "1234",
    "share_token": secrets.token_urlsafe(16),
    "demo": True,
    "public": True,
    "mode": "fiction",
    "observer_name": "The Chorus",
    "terminology": {
        "npc": "Character", "npcs": "Characters",
        "session": "Book", "sessions": "Books",
        "dm": "Narrator", "party": "Chorus",
        "faction": "Group", "factions": "Groups",
        "cast_label": "Cast",
        "notes_label": "Book Notes",
        "session_tools_label": "Write & Parse",
        "parse_cta": "Extract Story Events",
        "recap_cta": "Generate Book Summary",
        "quick_log_label": "Quick Event",
        "dm_controls": "Narrator Controls",
        "log_verb": "Log",
        "brief_nav": "Outline",
        "journal_label": "Journal",
        "quest_label": "Arc",
        "quests_label": "Story Arcs",
        "share_label": "Reader Share Link",
        "players_label": "Collaborators",
    },
})
_w("party.json",                     {"characters": []})
_w("assets.json",                    {"ships": []})
_w("journal.json",                   {"entries": []})
_w("references.json",                {"references": []})
_w("world/npcs.json",                {"npcs": []})
_w("world/factions.json",            {"factions": []})
_w("world/conditions.json",          {"conditions": []})
_w("story/quests.json",              {"quests": []})
_w("dm/session.json",                {})
_w("dm/relation_suggestions.json",   [])
_w("world/locations.json",           {"locations": []})

print(f"Seeding {CAMP_DIR} …")

# ── Helpers ────────────────────────────────────────────────────────────────────

def add_dual_rel(src_type, src_id, tgt_id, tgt_type,
                 formal_relation, personal_relation, weight=0.85, dm_only=False):
    fname = "world/npcs.json" if src_type == "npc" else "world/factions.json"
    key   = "npcs"            if src_type == "npc" else "factions"
    data  = db._load(SLUG, fname)
    for e in data[key]:
        if e["id"] == src_id:
            rels = e.setdefault("relations", [])
            if not any(r["target"] == tgt_id for r in rels):
                entry = {
                    "target": tgt_id, "target_type": tgt_type,
                    "formal_relation": formal_relation,
                    "personal_relation": personal_relation,
                    "weight": weight,
                }
                if dm_only:
                    entry["dm_only"] = True
                rels.append(entry)
    db._save(SLUG, data, fname)


def add_rel(src_type, src_id, tgt_id, tgt_type, relation, weight=0.8, dm_only=False):
    fname = "world/npcs.json" if src_type == "npc" else "world/factions.json"
    key   = "npcs"            if src_type == "npc" else "factions"
    data  = db._load(SLUG, fname)
    for e in data[key]:
        if e["id"] == src_id:
            rels = e.setdefault("relations", [])
            if not any(r["target"] == tgt_id for r in rels):
                entry = {"target": tgt_id, "target_type": tgt_type,
                         "relation": relation, "weight": weight}
                if dm_only:
                    entry["dm_only"] = True
                rels.append(entry)
    db._save(SLUG, data, fname)


def log_n(npc_id, session, note, polarity=None, intensity=1,
          event_type=None, visibility="public", actor_id=None, actor_type=None, location_id=None):
    return db.log_npc(SLUG, npc_id, session, note, polarity=polarity,
                      intensity=intensity, event_type=event_type, visibility=visibility,
                      actor_id=actor_id, actor_type=actor_type, location_id=location_id)


def log_f(faction_id, session, note, polarity=None, intensity=1,
          event_type=None, visibility="public", actor_id=None, actor_type=None, location_id=None):
    return db.log_faction(SLUG, faction_id, session, note, polarity=polarity,
                          intensity=intensity, event_type=event_type, visibility=visibility,
                          actor_id=actor_id, actor_type=actor_type, location_id=location_id)


def log_l(loc_id, session, note, polarity=None, intensity=1,
          event_type=None, visibility="public", actor_id=None, actor_type=None):
    db.log_location(SLUG, loc_id, session, note, visibility=visibility,
                    polarity=polarity, intensity=intensity, event_type=event_type,
                    actor_id=actor_id, actor_type=actor_type)


# ── Factions ───────────────────────────────────────────────────────────────────
factions = [
    ("The Achaean Host", "ally", False,
     "The coalition of Greek city-states besieging Troy. One hundred thousand men "
     "under [[Agamemnon]]'s nominal command, held together by oaths and ambition. "
     "Their unity is their weakness: the kings quarrel, the soldiers grow weary, "
     "and without [[Achilles]] they bleed against the Trojan walls."),

    ("The City of Troy", "neutral", False,
     "[[Priam]]'s city — rich, walled, and ten years under siege. The Trojans fight "
     "not for glory but for survival. Their greatest strength is [[Hector]]; their "
     "original wound is [[Paris]]. Troy is beloved of [[Apollo]] and Aphrodite, which "
     "keeps it standing long past reason."),

    ("The Divine Council", "neutral", True,
     "The Olympian gods, who treat the Trojan War as their own theater. Zeus "
     "holds the scales of fate; Hera and [[Athena]] back the Achaeans; [[Apollo]] and "
     "Aphrodite shield Troy. Their interventions decide what human valor alone "
     "cannot. Hidden to mortal eyes."),
]

F = {}
for name, rel, hidden, desc in factions:
    db.add_faction(SLUG, name, rel, desc, hidden=hidden)
    factions_data = db._load(SLUG, "world/factions.json")
    F[name] = factions_data["factions"][-1]["id"]
    print(f"  Faction: {name}")

# ── NPCs ────────────────────────────────────────────────────────────────────────
npcs_to_add = [
    # Achaean heroes
    ("Achilles", "Prince of Phthia, son of Thetis — the greatest warrior of the age",
     "neutral", False, [F["The Achaean Host"]],
     "Son of the sea-nymph [[Thetis]] and mortal king Peleus. He was given a choice "
     "at birth: a long, obscure life or a short, glorious one. He chose glory. "
     "Now in his rage at [[Agamemnon]] he may choose wrong again — and take the "
     "[[The Achaean Host|Achaeans]] down with him. His grief at [[Patroclus]]'s death will shake heaven."),

    ("Agamemnon", "High King of Mycenae, commander of the Achaean forces",
     "negative", False, [F["The Achaean Host"]],
     "King of kings by wealth and bloodline, not merit. He started this war to "
     "reclaim his brother's wife and has kept one hundred thousand men from home "
     "for a decade. He is capable of grandeur and of pettiness in equal measure. "
     "Stripping Briseis from [[Achilles]] is the worst decision of the war."),

    ("Patroclus", "Companion of Achilles, the gentlest of the Greeks",
     "ally", False, [F["The Achaean Host"]],
     "[[Achilles]]' closest friend — some say his soul's other half. He killed a boy "
     "in a quarrel as a child and was sent to [[Achilles]]' father's court in exile, "
     "where the two grew up together. He is braver than he should be and more "
     "compassionate than the war deserves. He will die wearing [[Achilles]]' armor."),

    ("Odysseus", "King of Ithaca, the Cunning",
     "ally", False, [F["The Achaean Host"]],
     "The wiliest man in the Greek world. He argued against joining the expedition "
     "and was tricked into going. Now he serves as strategist, diplomat, and the "
     "voice of cold reason in a war run on hot pride. He survives everything by "
     "thinking three moves ahead."),

    ("Ajax", "Prince of Salamis, bulwark of the Greeks",
     "ally", False, [F["The Achaean Host"]],
     "The largest and second-strongest of the Greeks. Where [[Achilles]] is a force "
     "of nature, Ajax is a wall — steadfast, immovable, the last man standing "
     "when others break. He will hold the ships against [[Hector]] alone. He carries "
     "a shield like a tower and feels the weight of every man he cannot save."),

    ("Menelaus", "King of Sparta, wronged husband",
     "neutral", False, [F["The Achaean Host"]],
     "This war was nominally fought to bring back his wife. He is brave but "
     "outclassed by the war his brother [[Agamemnon]]'s armies waged in his name. When he "
     "finally duels [[Paris]] — the man who stole [[Helen]] — he nearly wins. Aphrodite "
     "saves [[Paris]] and Menelaus is left holding nothing but his anger."),

    ("Diomedes", "King of Argos, the most fearless fighter",
     "ally", False, [F["The Achaean Host"]],
     "The most effective Achaean fighter during [[Achilles]]' absence. He wounds "
     "Aphrodite. He wounds Ares. He does things no mortal should do and survives "
     "them. [[Athena]] walks beside him, unseen, during his aristeia. He is what "
     "heroism looks like without the tragic weight."),

    ("Nestor", "King of Pylos, elder counselor",
     "ally", False, [F["The Achaean Host"]],
     "The oldest of the Greek kings, full of stories about wars he fought in his "
     "youth that dwarf this one. His advice is almost always right; it is almost "
     "never followed fast enough. He is the institutional memory of what honor "
     "requires and what it costs."),

    # Trojan royals and their circle
    ("Hector", "Prince of Troy, champion of the Trojans",
     "ally", False, [F["The City of Troy"]],
     "[[Priam]]'s eldest son and Troy's defender. He fights not for glory but for "
     "his city, his wife, his infant son. He knows Troy will fall. He goes out "
     "each morning anyway. The Iliad's moral center — the poem loves him even as "
     "it kills him. His farewell to [[Andromache]] at [[The Scaean Gate]] is everything."),

    ("Andromache", "Wife of Hector, voice of grief",
     "ally", False, [F["The City of Troy"]],
     "Her father and seven brothers were killed by [[Achilles]] before the poem "
     "begins. She has no one left but [[Hector]]. She begs him not to fight; she "
     "knows exactly how this ends. Her lament over his body is among the most "
     "devastating passages in Western literature."),

    ("Priam", "King of Troy, father of fifty sons",
     "neutral", False, [F["The City of Troy"]],
     "He has watched his city become a prison and his sons die one by one. "
     "His dignity is extraordinary — he walks alone into [[Achilles]]' camp to beg "
     "for [[Hector]]'s body, and [[Achilles]] weeps with him. The poem's final act is "
     "between these two men who have every reason to be enemies."),

    ("Paris", "Prince of Troy, the cause of everything",
     "negative", False, [F["The City of Troy"]],
     "[[Hector]]'s younger brother. He was given a choice by the gods — wisdom, "
     "power, or beauty — and chose beauty: Aphrodite and [[Helen]]. Now a hundred "
     "thousand men are dead for his decision and he fights the consequences with "
     "a bow, at a distance, never quite accepting blame. He kills [[Achilles]] in "
     "the end. He never deserves to."),

    ("Helen", "Most beautiful woman in the world, unwilling prize",
     "neutral", False, [F["The City of Troy"]],
     "She watches the war from [[The Walls of Troy|the walls of Troy]], naming Greek heroes for [[Priam]]. "
     "Did she choose to go with [[Paris]] or was she taken? Homer leaves it "
     "deliberately unclear. She hates herself, or says she does. [[Priam]] is kind "
     "to her. She is not the cause of the war — she is its most visible wound."),

    # Hidden: divine figures
    ("Apollo", "God of sun and plague, champion of Troy",
     "neutral", True, [F["The Divine Council"]], [],
     "The archer god. He sent the plague that opened the poem and has sheltered "
     "Troy throughout. He fights on the Trojan side openly, deflects spears from "
     "[[Hector]], and finally guides [[Paris]]'s arrow into [[Achilles]]' heel. "
     "The gods play by rules that are not human rules."),

    ("Athena", "Goddess of wisdom and war, patron of the Greeks",
     "ally", True, [F["The Divine Council"]], [],
     "She appears to [[Achilles]] in Book 1 to stop him from killing [[Agamemnon]]. "
     "She walks beside [[Diomedes]] during his aristeia. She tricks [[Hector]] into "
     "standing to face [[Achilles]] by disguising herself as his brother. "
     "She is the most active divine presence in the poem."),

    ("Thetis", "Sea-nymph, mother of Achilles",
     "ally", True, [F["The Divine Council"]], [],
     "[[Achilles]]' divine mother. She knows he is fated to die young and has spent "
     "his life trying to delay it. She persuades Zeus to favor the Trojans while "
     "[[Achilles]] withdraws, which leads to [[Patroclus]]'s death. Her grief and "
     "[[Achilles]]' grief mirror each other across the poem."),
]

N = {}
for item in npcs_to_add:
    if len(item) == 6:
        name, role, rel, hidden, faction_ids, desc = item
        hidden_factions = []
    else:
        name, role, rel, hidden, faction_ids, hidden_factions, desc = item
    db.add_npc(SLUG, name, role, rel, desc, hidden=hidden,
               factions=faction_ids, hidden_factions=hidden_factions if hidden_factions else None)
    npcs_data = db._load(SLUG, "world/npcs.json")
    N[name] = npcs_data["npcs"][-1]["id"]
    print(f"  NPC: {name}")

# ── Conditions ─────────────────────────────────────────────────────────────────
db.add_condition(SLUG,
    "The Siege of Troy — Year Ten",
    "All of Troy", "danger", "all",
    {"label": "decade-long stalemate"},
    description="Ten years of war. The walls of Troy remain unbroken. Supply "
    "lines on both sides strain. Men have grown old, had sons, buried fathers "
    "while camped on this plain. Every day costs lives. Neither side can end it.",
    hidden=False)

db.add_condition(SLUG,
    "Apollo's Plague",
    "Achaean Camp", "danger", "military",
    {"type": "percent", "value": -30},
    description="Apollo looses plague arrows into the Achaean camp for nine days "
    "after Agamemnon dishonors his priest Chryses. Men and mules die. The fires "
    "of cremation never go out. The camp smells of death.",
    hidden=False)

db.add_condition(SLUG,
    "Achilles Withdraws",
    "Achaean Camp", "access", "military",
    {"type": "blocked"},
    description="After Agamemnon strips him of Briseis, Achilles refuses to "
    "fight. The greatest warrior of the age sits idle on the beach. Without him "
    "the Achaeans lose ground with every engagement. The Trojans can feel it.",
    hidden=False)

conditions_data = db._load(SLUG, "world/conditions.json")
C = {c["name"]: c["id"] for c in conditions_data["conditions"]}
print(f"  Conditions: {list(C.keys())}")

# ── Story Arcs ─────────────────────────────────────────────────────────────────
db.add_quest(SLUG,
    "The Wrath of Achilles",
    "Agamemnon seizes Briseis. Achilles withdraws. The Achaeans, robbed of their "
    "champion, begin to lose. Thetis persuades Zeus to let them suffer. Everything "
    "that follows flows from one king's pride and one hero's rage.",
    hidden=False)

db.add_quest(SLUG,
    "The Death of Patroclus",
    "Patroclus cannot watch his friends die. He borrows Achilles' armor and leads "
    "the Myrmidons back to battle. He drives the Trojans from the ships — and then, "
    "ignoring his friend's command, presses too far. Apollo stuns him. Hector "
    "kills him. The armor is stripped. Achilles' rage turns inside out.",
    hidden=False)

db.add_quest(SLUG,
    "The Ransom of Hector",
    "Achilles kills Hector. He drags the body behind his chariot for twelve days. "
    "Priam, guided by Hermes, walks alone into the enemy camp at night to beg for "
    "his son. Achilles weeps with the old man. He returns the body. The poem ends "
    "with Hector's funeral — not Troy's fall. That is the point.",
    hidden=False)

print(f"  Story arcs seeded")

# ── Locations ──────────────────────────────────────────────────────────────────
db.add_location(SLUG, "The Achaean Camp",
    role="Greek military encampment on the Trojan shore",
    description="Ten years of siege have turned a beachhead into a city of tents, ships, and fires. The camp stretches along the shore from [[The Ships of Achilles|the ships of Achilles]] on one end to the ships of [[Ajax]] on the other. The assembly is held here. The plague burned through here for nine days. [[Agamemnon]]'s tent is at the center.",
    hidden=False,
    dm_notes="The plague that opens the poem originates here when Agamemnon dishonors Chryses. Achilles withdraws to the ships on the camp's edge — his separation from the main body is physical as well as symbolic. The embassy to Achilles comes to him here in Book 4. Patroclus borrows the armor here.")

db.add_location(SLUG, "The Ships of Achilles",
    role="Where Achilles withdraws — the edge of the war",
    description="[[Achilles]]' black ships are beached at the far end of the Achaean line. When he withdraws from battle, he comes here and stays — singing of the deeds of men, playing his lyre, with [[Patroclus]] beside him. The rest of the army bleeds against [[The Walls of Troy|the Trojan walls]] while the greatest warrior of the age sits idle at his ships.",
    hidden=False,
    dm_notes="This is the emotional center of the Iliad's first half. Thetis rises from the sea here. The embassy (Odysseus, Ajax, Phoenix) comes here. Patroclus comes here weeping to beg for the armor. The ships represent both Achilles' withdrawal and his eventual return — when he finally arms again, it is here.")

db.add_location(SLUG, "The Scaean Gate",
    role="Troy's western gate — the farewell place",
    description="The great gate on Troy's western wall, the entrance most used in battle. [[Hector]] passes through it every morning to fight. [[Andromache]] waits for him here. It is at this gate that [[Hector]] bids her farewell — lifting his son Astyanax, who recoils from the horsehair crest of his helmet. [[Hector]] removes it. He holds the boy. He goes back through the gate.",
    hidden=False,
    dm_notes="The Scaean Gate farewell is the poem's moral center. Hector knows Troy will fall. He goes anyway. The scene is constructed to break the reader: the baby who fears the helmet, the prayer for the son to surpass the father, Andromache watching him walk away knowing she will never see him again.")

db.add_location(SLUG, "The Walls of Troy",
    role="Troy's ramparts — where the Trojans watch and fall",
    description="The walls of Troy are the boundary between survival and destruction. The Trojan elders sit here and watch [[Helen]] name the Greek heroes on [[The Plain of Troy|the plain]] below. [[Andromache]] runs to these walls when she hears [[Hector]] is dead. [[Priam]] tears his white hair here watching his son die. The walls have held for ten years. They will not hold forever.",
    hidden=False,
    dm_notes="The wall scenes give the Trojans their domestic humanity — we see them watching the war rather than fighting it. Andromache's collapse on the wall when Hector's body is dragged by Achilles is among the most devastating moments in the poem.")

db.add_location(SLUG, "Priam's Palace",
    role="Troy's royal halls — grief and counsel",
    description="The palace of King [[Priam]] within [[The Walls of Troy|Troy's walls]]. His fifty sons and their wives are housed here. It is to this palace that [[Hector]] goes to find [[Paris]] idle with [[Helen]] when he should be fighting. Here Hecuba tears her robes. Here [[Priam]] prepares the wagon of treasure that he will take, alone, into the enemy camp.",
    hidden=False,
    dm_notes="The palace is where Troy's private grief is held. Hector's body is mourned here by Andromache, Hecuba, and Helen, each in turn, with different forms of lament. Priam's departure from the palace with the treasure — alone, at night — is the poem's final act of courage.")

db.add_location(SLUG, "Achilles' Hut",
    role="Where Priam ransoms Hector's body",
    description="[[Achilles]]' dwelling in [[The Achaean Camp|the Achaean camp]] — larger than a tent, a shelter built for the siege's duration. It is here that [[Priam]] comes at midnight, guided by Hermes, to kneel before the man who killed his son. [[Achilles]] weeps with him. He promises twelve days of truce. He returns [[Hector]]'s body without ransom. The poem ends here, in this act of grace in an enemy's dwelling.",
    hidden=False,
    dm_notes="The final scene of the Iliad takes place in this hut. Two men weeping together — each for what they have lost. Achilles sees his own father in Priam. He lifts the old king from the ground. He returns the body. He does not have to. That is Homer's answer to the question of what heroism is.")

db.add_location(SLUG, "The Plain of Troy",
    role="The battlefield — where the war is fought and decided",
    description="The broad plain before [[The Walls of Troy|Troy's walls]], between [[The Scaean Gate]] and [[The Achaean Camp]]. Ten years of war have been fought here. The River Scamander crosses it. This is where [[Diomedes]] wounds Aphrodite and Ares. Where the Trojans breach the wall. Where [[Patroclus]] drives the Trojans back and then presses too far. Where [[Hector]] and [[Achilles]] fight their last fight.",
    hidden=False,
    dm_notes="The plain is the theater of the war's action. Hector runs three circuits of Troy on this plain pursued by Achilles. Patroclus's overreach happens here — he drives the Trojans from the ships and then cannot stop. Apollo stuns him at the walls of Troy on the plain's far edge.")

locations_data = db._load(SLUG, "world/locations.json")
L = {loc["name"]: loc["id"] for loc in locations_data["locations"]}
print(f"  Locations: {list(L.keys())}")

# ── Relations ──────────────────────────────────────────────────────────────────

# Dual-axis: formal alliance vs personal enmity
add_dual_rel("npc", N["Achilles"],   N["Agamemnon"],  "npc", formal_relation="ally",   personal_relation="rival", weight=0.9)
add_dual_rel("npc", N["Agamemnon"],  N["Achilles"],   "npc", formal_relation="ally",   personal_relation="rival", weight=0.9)
add_dual_rel("npc", N["Hector"],     N["Paris"],      "npc", formal_relation="ally",   personal_relation="rival", weight=0.85)
add_dual_rel("npc", N["Paris"],      N["Hector"],     "npc", formal_relation="ally",   personal_relation="rival", weight=0.8)
add_dual_rel("npc", N["Menelaus"],   N["Helen"],      "npc", formal_relation="ally",   personal_relation="rival", weight=0.7)
add_dual_rel("npc", N["Achilles"],   N["Hector"],     "npc", formal_relation="rival",  personal_relation="ally",  weight=0.95)
add_dual_rel("npc", N["Hector"],     N["Achilles"],   "npc", formal_relation="rival",  personal_relation="ally",  weight=0.9)

# Clean alliances
add_rel("npc", N["Achilles"],    N["Patroclus"],  "npc", "ally", 1.0)
add_rel("npc", N["Patroclus"],   N["Achilles"],   "npc", "ally", 1.0)
add_rel("npc", N["Agamemnon"],   N["Menelaus"],   "npc", "ally", 0.95)
add_rel("npc", N["Menelaus"],    N["Agamemnon"],  "npc", "ally", 0.95)
add_rel("npc", N["Odysseus"],    N["Agamemnon"],  "npc", "ally", 0.75)
add_rel("npc", N["Agamemnon"],   N["Odysseus"],   "npc", "ally", 0.75)
add_rel("npc", N["Odysseus"],    N["Diomedes"],   "npc", "ally", 0.85)
add_rel("npc", N["Diomedes"],    N["Odysseus"],   "npc", "ally", 0.85)
add_rel("npc", N["Ajax"],        N["Achilles"],   "npc", "ally", 0.8)
add_rel("npc", N["Hector"],      N["Priam"],      "npc", "ally", 1.0)
add_rel("npc", N["Priam"],       N["Hector"],     "npc", "ally", 1.0)
add_rel("npc", N["Hector"],      N["Andromache"], "npc", "ally", 1.0)
add_rel("npc", N["Andromache"],  N["Hector"],     "npc", "ally", 1.0)
add_rel("npc", N["Paris"],       N["Helen"],      "npc", "ally", 0.85)
add_rel("npc", N["Priam"],       N["Helen"],      "npc", "ally", 0.7)
add_rel("npc", N["Thetis"],      N["Achilles"],   "npc", "ally", 1.0)
add_rel("npc", N["Achilles"],    N["Thetis"],     "npc", "ally", 1.0)

# Divine favor (DM only)
add_rel("npc", N["Athena"],  N["Achilles"],  "npc", "ally",  0.9, dm_only=True)
add_rel("npc", N["Athena"],  N["Odysseus"],  "npc", "ally",  0.85, dm_only=True)
add_rel("npc", N["Apollo"],  N["Hector"],    "npc", "ally",  0.9, dm_only=True)
add_rel("npc", N["Apollo"],  N["Agamemnon"], "npc", "rival", 1.0, dm_only=True)
add_rel("npc", N["Thetis"],  N["Athena"],    "npc", "ally",  0.6, dm_only=True)

# Faction relations
add_rel("faction", F["The Achaean Host"], F["The City of Troy"],    "faction", "rival", 1.0)
add_rel("faction", F["The City of Troy"], F["The Achaean Host"],    "faction", "rival", 1.0)
add_rel("faction", F["The Divine Council"], F["The Achaean Host"],  "faction", "ally",  0.5, dm_only=True)
add_rel("faction", F["The Divine Council"], F["The City of Troy"],  "faction", "ally",  0.5, dm_only=True)

print("  Relations set")

# ── Event Log ──────────────────────────────────────────────────────────────────
# Book 1 — The Plague and the Quarrel

evt = log_n(N["Agamemnon"], 1,
      "Chryses, priest of [[Apollo]], comes to ransom his daughter Chryseis; "
      "[[Agamemnon]] dismisses him with contempt and threats, dishonoring [[Apollo]]'s servant.",
      polarity="negative", intensity=2, event_type="dialogue",
      location_id=L["The Achaean Camp"])
db.apply_ripple(SLUG, N["Agamemnon"], "npc", 1,
                "Agamemnon dishonors Apollo's priest — the god's anger follows.",
                "negative", 2, "dialogue", "public", source_event_id=evt)

log_n(N["Apollo"], 1,
      "[[Apollo]] descends from Olympus and looses plague arrows into the Achaean camp; "
      "for nine days the pyres burn without ceasing as men and mules die.",
      polarity="negative", intensity=3, event_type="other",
      actor_id=N["Agamemnon"], actor_type="npc",
      location_id=L["The Achaean Camp"])

log_f(F["The Achaean Host"], 1,
      "Nine days of plague devastate the camp; the army demands answers. "
      "The seer Calchas reveals the cause: [[Agamemnon]]'s insult to Chryses.",
      polarity="negative", intensity=3, event_type="other",
      location_id=L["The Achaean Camp"])

log_n(N["Achilles"], 1,
      "[[Achilles]] calls an assembly and demands [[Agamemnon]] explain the plague; "
      "he is the only one willing to name what everyone knows.",
      polarity="positive", intensity=1, event_type="dialogue",
      location_id=L["The Achaean Camp"])

evt = log_n(N["Agamemnon"], 1,
      "[[Agamemnon]] returns Chryseis but seizes Briseis from [[Achilles]] as compensation; "
      "a calculated humiliation of the man he most needs and most resents.",
      polarity="negative", intensity=3, event_type="other",
      location_id=L["The Achaean Camp"])
db.apply_ripple(SLUG, N["Agamemnon"], "npc", 1,
                "Agamemnon seizes Briseis from Achilles — the rupture that turns the war.",
                "negative", 3, "other", "public", source_event_id=evt)

log_n(N["Achilles"], 1,
      "[[Achilles]] nearly kills [[Agamemnon]]; [[Athena]] stops him. He withdraws from battle, "
      "prays to [[Thetis]] to beg Zeus to let the Achaeans suffer, and retreats to his ships.",
      polarity="positive", intensity=2, event_type="other",
      location_id=L["The Ships of Achilles"])

log_n(N["Thetis"], 1,
      "[[Thetis]] rises from the sea and holds her weeping son; she promises to go to Zeus. "
      "She knows he will die young. She grants his wish anyway.",
      polarity="positive", intensity=2, event_type="other", visibility="dm_only")

# Book 2 — The Duel of Paris and Menelaus

log_n(N["Paris"], 2,
      "[[Paris]] challenges the assembled Greeks to single combat; he nearly flees "
      "when [[Menelaus]] actually steps forward — [[Hector]] shames him back.",
      polarity="negative", intensity=1, event_type="dialogue",
      location_id=L["The Plain of Troy"])

log_n(N["Menelaus"], 2,
      "[[Menelaus]] fights [[Paris]] in single combat; he seizes [[Paris]] by the helmet and "
      "is about to drag him to death when Aphrodite snaps the chin-strap and spirits [[Paris]] away.",
      polarity="positive", intensity=2, event_type="combat",
      location_id=L["The Plain of Troy"])

log_n(N["Paris"], 2,
      "Aphrodite deposits [[Paris]] in [[Helen]]'s bedroom, unharmed and unrepentant; "
      "he does not understand why the world is angry with him.",
      polarity="negative", intensity=2, event_type="other",
      actor_id=N["Menelaus"], actor_type="npc")

log_n(N["Helen"], 2,
      "[[Helen]] is furious at Aphrodite for saving [[Paris]]; she knows she should go back "
      "to [[Menelaus]] and cannot; the goddess will not let her. She is trapped by beauty and by god.",
      polarity="positive", intensity=1, event_type="dialogue")

# Book 3 — Diomedes' Aristeia and the Farewell at the Scaean Gate

log_n(N["Diomedes"], 3,
      "With [[Athena]] beside him [[Diomedes]] tears through the Trojan line, wounding "
      "Aphrodite's wrist and driving his spear into Ares' flank. He is doing the impossible.",
      polarity="positive", intensity=3, event_type="combat",
      location_id=L["The Plain of Troy"])

log_n(N["Hector"], 3,
      "[[Hector]] enters Troy to arrange sacrifice; he finds [[Paris]] idle at home with [[Helen]] "
      "and shames him back to battle. He goes to find [[Andromache]].",
      polarity="positive", intensity=1, event_type="other",
      location_id=L["Priam's Palace"])

log_n(N["Hector"], 3,
      "At [[The Scaean Gate]] [[Hector]] bids [[Andromache]] farewell; she begs him to stay. "
      "He lifts their son Astyanax, who recoils from the great shining helmet. "
      "He prays the boy will be greater than his father. He goes back to war.",
      polarity="positive", intensity=3, event_type="dialogue",
      location_id=L["The Scaean Gate"])

log_n(N["Andromache"], 3,
      "[[Andromache]] tells [[Hector]] he is her father, her mother, her brothers — "
      "everyone she has left. She watches him walk away knowing it is the last time.",
      polarity="positive", intensity=3, event_type="dialogue",
      location_id=L["The Scaean Gate"])

# Book 4 — Embassy to Achilles

log_n(N["Odysseus"], 4,
      "[[Odysseus]], [[Ajax]], and Phoenix carry [[Agamemnon]]'s offer to [[Achilles]]: "
      "treasure, Briseis returned, [[Agamemnon]]'s daughter in marriage. "
      "[[Odysseus]] presents it brilliantly. [[Achilles]] sees the pride beneath the gifts.",
      polarity="positive", intensity=1, event_type="dialogue",
      location_id=L["The Ships of Achilles"])

log_n(N["Achilles"], 4,
      "[[Achilles]] refuses everything. He says: two fates await him — return home "
      "and live long, or stay and die young with glory. He is choosing neither "
      "right now. He will decide when [[Hector]] burns the ships.",
      polarity="positive", intensity=2, event_type="dialogue",
      location_id=L["The Ships of Achilles"])

log_n(N["Agamemnon"], 4,
      "[[Agamemnon]]'s offer is enormous in treasure and zero in apology; "
      "[[Achilles]] reads the pride beneath the gifts and says no to all of it.",
      polarity="negative", intensity=1, event_type="other")

# Book 5 — Trojans Break Through

evt = log_f(F["The Achaean Host"], 5,
      "[[The City of Troy|The Trojans]] breach the great wall of the Greek camp; [[Hector]] hurls a boulder "
      "through the gate and leads the charge toward the ships.",
      polarity="negative", intensity=3, event_type="combat",
      actor_id=N["Hector"], actor_type="npc",
      location_id=L["The Achaean Camp"])
db.apply_ripple(SLUG, F["The Achaean Host"], "faction", 5,
                "Trojans breach the camp wall — Hector leads the charge to the ships.",
                "negative", 3, "combat", "public", source_event_id=evt)

log_n(N["Ajax"], 5,
      "[[Ajax]] stands alone at the ships and drives off [[Hector]]'s assault; "
      "he is the last thing between the fleet and fire.",
      polarity="positive", intensity=3, event_type="combat",
      location_id=L["The Ships of Achilles"])

evt = log_f(F["The City of Troy"], 5,
      "For the first time in ten years [[The City of Troy|Trojans]] fight on the beach beside Achaean ships; "
      "the tide of the war shifts.",
      polarity="positive", intensity=2, event_type="combat")
db.apply_ripple(SLUG, F["The City of Troy"], "faction", 5,
                "Trojans fight on the Achaean beach for the first time in ten years.",
                "positive", 2, "combat", "public", source_event_id=evt)

# Book 6 — The Death of Patroclus

log_n(N["Patroclus"], 6,
      "[[Patroclus]] comes to [[Achilles]] with tears and begs to fight in his armor; "
      "[[Achilles]] relents, giving the Myrmidons and his divine horses, "
      "but warns him: drive [[The City of Troy|the Trojans]] back and then return.",
      polarity="positive", intensity=2, event_type="dialogue",
      location_id=L["The Ships of Achilles"])

log_n(N["Patroclus"], 6,
      "[[Patroclus]] fights brilliantly in [[Achilles]]' armor, driving [[The City of Troy|Trojans]] back from "
      "the ships; then, ignoring his friend's command, he presses on toward Troy's walls.",
      polarity="positive", intensity=2, event_type="combat",
      location_id=L["The Plain of Troy"])

log_n(N["Apollo"], 6,
      "[[Apollo]] strikes [[Patroclus]] from behind on the battlefield, knocking away "
      "his helmet and snapping his spear; Euphorbus wounds him from behind; "
      "[[Hector]] drives in the killing blow.",
      polarity="negative", intensity=3, event_type="combat",
      actor_id=N["Hector"], actor_type="npc", visibility="dm_only")

evt = log_n(N["Patroclus"], 6,
      "[[Patroclus]] dies. His last words to [[Hector]]: death is coming for you too, "
      "and it is not far off. [[Hector]] strips [[Achilles]]' divine armor from the body.",
      polarity="negative", intensity=3, event_type="combat",
      actor_id=N["Hector"], actor_type="npc",
      location_id=L["The Plain of Troy"])
db.set_npc_dead(SLUG, N["Patroclus"], True, dead_session=6)
db.apply_ripple(SLUG, N["Patroclus"], "npc", 6,
                "Patroclus is killed by Hector — Achilles' armor stripped, the bond severed.",
                "negative", 3, "combat", "public", source_event_id=evt)

log_n(N["Hector"], 6,
      "[[Hector]] kills [[Patroclus]] in single combat and strips [[Achilles]]' divine armor; "
      "he puts it on himself, not knowing what the act will cost him.",
      polarity="negative", intensity=3, event_type="combat",
      location_id=L["The Plain of Troy"])

log_f(F["The Achaean Host"], 6,
      "Word of [[Patroclus]]'s death spreads through the Achaean camp; "
      "[[Achilles]]' cry of grief shakes the battlefield. Everyone knows what comes next.",
      polarity="negative", intensity=2, event_type="other")

# Book 7 — The Return of Achilles, The Death of Hector

log_n(N["Achilles"], 7,
      "[[Achilles]] learns [[Patroclus]] is dead. He collapses. His grief is absolute. "
      "[[Thetis]] rises from the sea to hold him. He tells her: I will kill [[Hector]] "
      "and then I will die.",
      polarity="positive", intensity=3, event_type="other",
      location_id=L["The Ships of Achilles"])

log_n(N["Thetis"], 7,
      "[[Thetis]] goes to Hephaestus and commissions new armor for her son; "
      "she knows she is equipping him for his death.",
      polarity="negative", intensity=2, event_type="other", visibility="dm_only")

evt = log_n(N["Achilles"], 7,
      "[[Achilles]] returns to battle in new divine armor; [[The City of Troy|the Trojans]] rout at the sight of him. "
      "He kills everything in his path. The river Scamander runs red.",
      polarity="positive", intensity=3, event_type="combat",
      location_id=L["The Plain of Troy"])
db.apply_ripple(SLUG, N["Achilles"], "npc", 7,
                "Achilles returns to battle — divine armor, Patroclus unavenged, the Trojans route.",
                "positive", 3, "combat", "public", source_event_id=evt)

log_n(N["Hector"], 7,
      "[[Hector]] stands outside the gates as all of Troy flees inside. "
      "His father [[Priam]] begs from the walls; his mother tears her robes. "
      "He waits for [[Achilles]].",
      polarity="positive", intensity=3, event_type="other",
      location_id=L["The Walls of Troy"])

log_n(N["Hector"], 7,
      "[[Hector]] runs three circuits of Troy pursued by [[Achilles]]; "
      "[[Athena]] takes Deiphobus's form to stop him. He turns and faces his death with full knowledge. "
      "He asks only to be given back for burial. [[Achilles]] refuses.",
      polarity="positive", intensity=3, event_type="combat",
      location_id=L["The Plain of Troy"])

evt = log_n(N["Achilles"], 7,
      "[[Achilles]] kills [[Hector]]. He drags the body behind his chariot around Troy's walls "
      "for twelve days, visiting [[Patroclus]]'s tomb. The gods watch in pain. "
      "[[Priam]] watches from the walls.",
      polarity="negative", intensity=3, event_type="combat",
      location_id=L["The Plain of Troy"])
db.set_npc_dead(SLUG, N["Hector"], True, dead_session=7)
db.apply_ripple(SLUG, N["Hector"], "npc", 7,
                "Hector is killed by Achilles — his body desecrated, Troy's future severed.",
                "negative", 3, "combat", "public", source_event_id=evt)

log_n(N["Priam"], 7,
      "[[Priam]] watches his greatest son [[Hector]] die from the walls. "
      "He tears his white hair and weeps in the dust. Troy's fathers watch with him.",
      polarity="negative", intensity=3, event_type="other",
      location_id=L["The Walls of Troy"])

log_n(N["Andromache"], 7,
      "[[Andromache]] faints upon the wall when she sees [[Hector]]'s body dragged behind [[Achilles]]' chariot. "
      "She weeps not for Troy but for their son Astyanax, who will grow up fatherless in a fallen city.",
      polarity="negative", intensity=3, event_type="other",
      location_id=L["The Walls of Troy"])

# Book 8 — The Ransom

log_n(N["Priam"], 8,
      "[[Priam]] loads a wagon with treasure, guided by Hermes, and walks alone into "
      "the enemy camp at night. He kneels before [[Achilles]] and asks him to remember "
      "his own father. He kisses the hands that killed his son.",
      polarity="positive", intensity=3, event_type="dialogue",
      location_id=L["Achilles' Hut"])

log_n(N["Achilles"], 8,
      "[[Achilles]] weeps with [[Priam]] — each man weeping for what he has lost. "
      "He lifts the old king from the ground. He promises twelve days of truce. "
      "He returns [[Hector]]'s body without ransom.",
      polarity="positive", intensity=3, event_type="dialogue",
      location_id=L["Achilles' Hut"])

log_f(F["The City of Troy"], 8,
      "[[Hector]] is brought home. [[Andromache]], Hecuba, and [[Helen]] lead the lament. "
      "The poem ends here — not at Troy's fall, but at a funeral. "
      "That is Homer's answer to the question of what war is.",
      polarity="neutral", intensity=1, event_type="other",
      location_id=L["Priam's Palace"])

# Resolve conditions
db.log_condition(SLUG, C["Achilles Withdraws"], 7,
                 "Achilles returns to battle after Patroclus's death. The condition ends.",
                 polarity="positive", intensity=3)
db.log_condition(SLUG, C["Apollo's Plague"], 1,
                 "Apollo's plague ends when Agamemnon returns Chryseis. The pyres stop burning.",
                 polarity="positive", intensity=3)

print("  Event log complete")

# ── Location log entries ───────────────────────────────────────────────────────

log_l(L["The Achaean Camp"], 1,
      "[[Apollo]]'s plague burns through the camp for nine days after [[Agamemnon]] dishonors his priest. Men and mules die. The fires of cremation never go out. [[Achilles]] forces the assembly. [[Agamemnon]] returns Chryseis and takes [[Achilles]]' prize instead.",
      polarity="negative", intensity=3, event_type="other",
      actor_id=N["Agamemnon"], actor_type="npc")

log_l(L["The Ships of Achilles"], 1,
      "[[Achilles]] withdraws here after [[Agamemnon]] seizes Briseis. He sits at his ships, plays his lyre, and sings of the deeds of men. [[Patroclus]] sits beside him. The Achaean army bleeds against the walls of Troy.",
      polarity="negative", intensity=2, event_type="other",
      actor_id=N["Agamemnon"], actor_type="npc")

log_l(L["The Scaean Gate"], 3,
      "[[Hector]] bids [[Andromache]] farewell at the gate. He lifts [[Astyanax]], who recoils from the horsehair crest. [[Hector]] removes the helmet and holds his son. He prays: let him be greater than his father. He goes back through the gate. [[Andromache]] watches him until he is out of sight.",
      polarity="positive", intensity=3, event_type="dialogue")

log_l(L["The Ships of Achilles"], 4,
      "[[Odysseus]], [[Ajax]], and Phoenix come with [[Agamemnon]]'s offer: treasure, Briseis returned, a daughter in marriage. [[Achilles]] sees the pride beneath the gifts. He refuses. Two fates await him — long life or short glory. He is choosing neither yet.",
      polarity="neutral", intensity=2, event_type="dialogue")

log_l(L["The Plain of Troy"], 6,
      "[[Patroclus]] fights brilliantly in [[Achilles]]' armor and drives the [[The City of Troy|Trojans]] from the ships. Then he presses on toward [[The Walls of Troy|the walls]]. [[Apollo]] stuns him from behind. [[Hector]] drives in the killing blow. The armor is stripped.",
      polarity="negative", intensity=3, event_type="combat",
      actor_id=N["Hector"], actor_type="npc")

log_l(L["The Walls of Troy"], 7,
      "[[Priam]] watches [[Hector]] die from the walls. He tears his white hair and weeps in the dust. He begged [[Hector]] not to face [[Achilles]]. [[Hector]] waited anyway. Troy's walls still stand. Everything behind them is changed.",
      polarity="negative", intensity=3, event_type="other",
      actor_id=N["Achilles"], actor_type="npc")

log_l(L["Achilles' Hut"], 8,
      "[[Priam]] comes at midnight, guided by Hermes, and kneels before [[Achilles]]. He asks him to remember his own father. He kisses the hands that killed his son. [[Achilles]] weeps. He lifts the old king. He promises twelve days of truce and returns [[Hector]]'s body.",
      polarity="positive", intensity=3, event_type="dialogue",
      actor_id=N["Priam"], actor_type="npc")

log_l(L["Priam's Palace"], 8,
      "[[Hector]] is brought home. [[Andromache]] leads the lament. [[Hecuba]] mourns her son. [[Helen]] mourns the only man in Troy who was kind to her. The poem ends at a funeral, not a victory. That is Homer's point.",
      polarity="neutral", intensity=1, event_type="other")

print("  Location logs complete")

# ── Arc progression log ────────────────────────────────────────────────────────

db.log_quest(SLUG, "the_wrath_of_achilles", 1,
    "Book 1: Agamemnon seizes Briseis. Achilles withdraws. Thetis persuades Zeus "
    "to let the Achaeans suffer. Apollo's plague ends but the rupture does not.")
db.log_quest(SLUG, "the_wrath_of_achilles", 4,
    "Book 4: Embassy fails. Achilles refuses treasure, honor, a king's daughter. "
    "Two fates await him. He is choosing neither yet. The army keeps dying.")
db.log_quest(SLUG, "the_wrath_of_achilles", 5,
    "Book 5: Trojans breach the camp wall and fight on the Achaean beach. "
    "Ajax holds alone. Achilles watches from the shore.")
db.log_quest(SLUG, "the_wrath_of_achilles", 7,
    "Book 7: Achilles returns. The rage has its target. Hector is dead. "
    "The wrath consumed everything it needed to — and more than that.")

db.log_quest(SLUG, "the_death_of_patroclus", 6,
    "Book 6: Patroclus borrows the armor. Drives the Trojans from the ships. "
    "Cannot stop. Apollo stuns him at the walls. Hector kills him. The armor stripped. "
    "Achilles' world ends on the plain of Troy.")

db.log_quest(SLUG, "the_ransom_of_hector", 7,
    "Book 7: Achilles kills Hector. Drags the body for twelve days. "
    "The gods watch in distress. Priam watches from the walls.")
db.log_quest(SLUG, "the_ransom_of_hector", 8,
    "Book 8: Priam walks alone into the enemy camp at night. Kneels before Achilles. "
    "Achilles weeps. Returns the body. Twelve days of truce. "
    "The poem ends at a funeral. That is the point.")

print("  Arc progression logs complete")

# ── Journal entries ─────────────────────────────────────────────────────────────
db.post_journal(SLUG, 1, "Book 1: The Plague and the Quarrel",
    "The poem opens in disaster. Apollo's plague has already been burning through the camp "
    "for nine days when Achilles forces the assembly. Agamemnon returns Chryseis but takes "
    "Briseis. Achilles withdraws. The greatest warrior of the age sits idle on the beach "
    "while his friends die. Thetis begs Zeus to let the Achaeans suffer.")

db.post_journal(SLUG, 3, "Book 3 note: Hector and Andromache",
    "The farewell at the Scaean Gate. This is why the Iliad survives. Hector knows Troy "
    "will fall. He lifts Astyanax. The baby recoils from the helmet's horsehair crest. "
    "Hector removes it and holds his son and prays: let him be greater than his father. "
    "He walks back to the war. Andromache watches him go.")

db.post_journal(SLUG, 6, "Book 6: Patroclus",
    "He warned him. Drive the Trojans back and then return — do not press to Troy's walls. "
    "Patroclus could not do it. He saved the ships. He just couldn't stop. Apollo hit him "
    "from behind on the walls of Troy. He was wearing Achilles' armor. "
    "He was not Achilles. Hector knew the difference.")

db.post_journal(SLUG, 7, "Book 7: Priam's Embassy",
    "This is the hinge. Two men weeping together in an enemy camp at midnight — one grieving "
    "his dead friend, one grieving his dead son. Achilles sees in Priam his own father, Peleus, "
    "who will soon receive news of his son's death. He returns the body. He doesn't have to. "
    "That's the point. The Iliad is not a poem about winning.")

print(f"\nDone. Campaign '{SLUG}' seeded at {CAMP_DIR}")
print("To deploy to Pi:  rsync -av campaigns/iliad/ simonhans@raspberrypi:/mnt/serverdrive/coding/rippleforge/campaigns/iliad/")
