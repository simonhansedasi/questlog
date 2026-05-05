"""Seed script: The Hartstone Compact. TTRPG starter world.

A neutral border city, two kingdoms pressing claims, one paladin order keeping the peace.
Showcases all TTRPG features: party, quests, dual-axis edges, conditions, ripples.

Run:  python seed_paladins_grace.py
"""
import sys, json, secrets, shutil
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from src import data as db

SLUG = "paladins_grace"
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
    "slug": SLUG,
    "name": "The Hartstone Compact",
    "system": "TTRPG — any system",
    "owner": "demo",
    "dm_pin": "1234",
    "share_token": secrets.token_urlsafe(16),
    "demo": True,
    "public": True,
    "mode": "ttrpg",
    "observer_name": "The Party",
    "party_name": "The Party",
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
                 formal_relation, personal_relation, weight=0.8, dm_only=False):
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
          event_type=None, visibility="public", ripple=False, actor_id=None, actor_type=None, location_id=None):
    evt = db.log_npc(SLUG, npc_id, session, note, polarity=polarity,
                     intensity=intensity, event_type=event_type, visibility=visibility,
                     actor_id=actor_id, actor_type=actor_type, location_id=location_id)
    if ripple and polarity in ("positive", "negative"):
        db.apply_ripple(SLUG, npc_id, "npc", session, note, polarity, intensity, event_type, visibility)
    return evt


def log_f(faction_id, session, note, polarity=None, intensity=1,
          event_type=None, visibility="public", ripple=False, actor_id=None, actor_type=None, location_id=None):
    evt = db.log_faction(SLUG, faction_id, session, note, polarity=polarity,
                         intensity=intensity, event_type=event_type, visibility=visibility,
                         actor_id=actor_id, actor_type=actor_type, location_id=location_id)
    if ripple and polarity in ("positive", "negative"):
        db.apply_ripple(SLUG, faction_id, "faction", session, note, polarity, intensity, event_type, visibility)
    return evt


def log_l(loc_id, session, note, polarity=None, intensity=1,
          event_type=None, visibility="public", actor_id=None, actor_type=None):
    db.log_location(SLUG, loc_id, session, note, visibility=visibility,
                    polarity=polarity, intensity=intensity, event_type=event_type,
                    actor_id=actor_id, actor_type=actor_type)


# ── Party ──────────────────────────────────────────────────────────────────────
db.add_character(SLUG, "Carran Voss", "Human", "Paladin", 1,
                 notes="Grace-Sworn initiate. Earnest. Believes in the compact harder than anyone born to it.")
db.add_character(SLUG, "Mira Dune", "Half-Elf", "Rogue", 1,
                 notes="Compact Guild courier. Knows every back street in Hartstone. Loyalties unclear.")
db.add_character(SLUG, "Sera Eld", "Dwarf", "Cleric", 1,
                 notes="Temple healer from outside Hartstone. Came to study the Grace-Sworn. Stayed.")
db.add_character(SLUG, "Osric Fell", "Human", "Wizard", 1,
                 notes="Kelrath Academy scholar. Officially studying civic law. Unofficially watching everything.")
print("  Party seeded")

# ── Factions ───────────────────────────────────────────────────────────────────
factions = [
    ("The Grace-Sworn", "ally", False,
     "The paladin order that has kept Hartstone neutral for three generations. "
     "They serve no king and take no side — only the compact. Their numbers are "
     "dwindling and their resources thin, but their reputation is the only "
     "thing stopping Hartstone from becoming a battlefield. [[Commander Aldric Vane]] leads them."),

    ("House Vespar", "rival", False,
     "A powerful northern noble house pressing its claim to Hartstone with lawyers "
     "and armed escorts, in that order. [[Lady Ivra Malt]] speaks for the house with "
     "silk gloves and iron intent. They believe Hartstone is historically theirs."),

    ("The Compact Guild", "neutral", False,
     "Hartstone's merchant class has thrived precisely because the city is neutral — "
     "both kingdoms trade through it, pay its tariffs, and need its roads. "
     "The Guild will back whoever keeps the trade routes open. Right now that is "
     "the compact. [[Guildmaster Sena Cord]] has a price she has not yet named."),

    ("The Kelrath Envoys", "rival", False,
     "The southern Confederation sends diplomats instead of armies — so far. "
     "[[Emissary Dax Fell]] has been in Hartstone six months before [[House Vespar|Vespar's]] delegation "
     "arrived. He knows where every magistrate eats dinner and which ones have debts."),

    ("The Underbrick", "hostile", True,
     "Hartstone's criminal network operates in [[The East Quarter Tunnels|tunnels below the east quarter]]. "
     "They have survived every political change by being useful to whoever is winning. "
     "Someone is paying them very well right now. Nobody knows for what. (DM-only)"),
]

F = {}
for name, rel, hidden, desc in factions:
    db.add_faction(SLUG, name, rel, desc, hidden=hidden)
    factions_data = db._load(SLUG, "world/factions.json")
    F[name] = factions_data["factions"][-1]["id"]
    print(f"  Faction: {name}")

# ── NPCs ────────────────────────────────────────────────────────────────────────
npcs_to_add = [
    ("Commander Aldric Vane", "Grace-Sworn — military leader of the compact",
     "ally", False, [F["The Grace-Sworn"]],
     "Thirty years in [[The Grace-Sworn]]. He has kept Hartstone neutral through three "
     "crises and does not intend this to be the fourth. He is building options. "
     "Some of them are things he can never tell [[The Compact Guild|the Guild]] about."),

    ("Lady Ivra Malt", "House Vespar — envoy pressing the northern claim",
     "rival", False, [F["House Vespar"]],
     "She arrived with twelve lawyers and forty guards 'for her protection.' "
     "She is charming, specific, and never wrong about anything she can cite in writing. "
     "She wants Hartstone. She has a fallback position she has not yet revealed. "
     "She knows [[Commander Aldric Vane]] better than he would prefer."),

    ("Guildmaster Sena Cord", "Compact Guild — controls trade and tariff income",
     "neutral", False, [F["The Compact Guild"]],
     "[[The Compact Guild|The Guild]] has financed [[The Grace-Sworn]] for two generations. Guildmaster Sena Cord knows this. "
     "She is not threatening — she is ensuring everyone understands the math. "
     "She will back whoever keeps the trade routes open. She has a price. "
     "She has not named it yet."),

    ("Emissary Dax Fell", "Kelrath Confederation — diplomatic observer",
     "rival", False, [F["The Kelrath Envoys"]],
     "He has been in Hartstone for six months before [[House Vespar]] arrived. "
     "He knows where every magistrate eats dinner and which ones have debts. "
     "He presents as reasonable and collaborative. He is. He is also winning."),

    ("Brother Edmar", "Grace-Sworn — chaplain and keeper of founding records",
     "ally", False, [F["The Grace-Sworn"]],
     "Old enough to remember the last succession crisis. Gentle enough that people "
     "tell him things they should not. He spends his evenings in [[The City Archive|the archive]]. "
     "He knows something about [[The Underbrick]] he is deciding whether to share."),

    ("Petra Wynn", "City archivist — custodian of three generations of records",
     "neutral", True, [F["The Compact Guild"]],
     "The city's official archivist. She has copies of everything. She does not sell "
     "information — she trades it. She knows who owns the old tunnels under the east "
     "quarter and what has moved through [[The East Quarter Tunnels|them]] recently. (DM-only until approached)"),

    ("The Loom", "Underbrick — faction boss, identity unknown",
     "hostile", True, [F["The Underbrick"]],
     "[[The Underbrick]]'s controller. Nobody inside the network has seen their face. "
     "They communicate through cutouts and coded drops. They have been buying weapons "
     "from both [[House Vespar|Vespar]] and [[The Kelrath Envoys|Kelrath]] suppliers simultaneously. "
     "Either they are playing both sides or they are the third side. (DM-only)"),
]

N = {}
for item in npcs_to_add:
    name, role, rel, hidden, faction_ids, desc = item
    db.add_npc(SLUG, name, role, rel, desc, hidden=hidden, factions=faction_ids)
    npcs_data = db._load(SLUG, "world/npcs.json")
    N[name] = npcs_data["npcs"][-1]["id"]
    print(f"  NPC: {name}")

# ── Conditions ─────────────────────────────────────────────────────────────────
db.add_condition(SLUG,
    "The Succession Vacuum",
    "Hartstone", "danger", "all",
    {"label": "political instability"},
    description="House Vespar's lord died six weeks ago without a clear named heir. "
    "Both claimants and Kelrath agents are in Hartstone simultaneously. "
    "Every faction is in a holding pattern that could collapse into action at any moment.",
    hidden=False)

db.add_condition(SLUG,
    "Armed Envoys",
    "Hartstone", "danger", "all",
    {"type": "percent", "value": -20},
    description="House Vespar arrived with forty armed guards; Kelrath matched them. "
    "The compact limits armed retinues to twelve. Both sides are in technical violation. "
    "Aldric has not yet enforced the limit. One incident in the market triggers the clause.",
    hidden=False)

db.add_condition(SLUG,
    "The Underbrick Cache",
    "East Quarter tunnels", "supply", "military",
    {"label": "unknown weapons stockpile"},
    description="City watch found evidence of large weapon shipments moving through "
    "the tunnel network under the east quarter. Origin and destination unknown. "
    "Too many for street crime — consistent with equipping a small private force.",
    hidden=True)

conditions_data = db._load(SLUG, "world/conditions.json")
C = {c["name"]: c["id"] for c in conditions_data["conditions"]}
print(f"  Conditions: {list(C.keys())}")

# ── Quests ─────────────────────────────────────────────────────────────────────
db.add_quest(SLUG,
    "Authenticate the Heir",
    "House Vespar's two claimants both have documentation. One is forged — possibly both. "
    "The Grace-Sworn's founding compact requires them to recognize the legitimate ruler "
    "of Hartstone's treaty partners. Authenticate the wrong heir and the compact breaks. "
    "The records are in the city archive. So is Petra Wynn.",
    hidden=False)

db.add_quest(SLUG,
    "The Guild's Price",
    "Sena Cord has indicated — obliquely — that the Guild's financial support for "
    "the Grace-Sworn has a condition attached. She hasn't named it. "
    "Whatever it is, it's either something Aldric cannot give or something he should not. "
    "Find out before the Guild decides not to wait.",
    hidden=False)

db.add_quest(SLUG,
    "Root Out the Underbrick",
    "Someone is arming the Underbrick at scale. The quantities are military. "
    "Find The Loom, trace the supply line, and determine whether this is a third "
    "faction moving against both delegations — or one of the delegations moving "
    "against the compact itself.",
    hidden=False)

print(f"  Quests seeded")

# ── Locations ──────────────────────────────────────────────────────────────────
db.add_location(SLUG, "Hartstone North Gate",
    role="The city's main northern entrance — where the delegations arrived",
    description="The primary gate into Hartstone from the northern road. Two delegations have passed through this gate in recent weeks — both with armed escorts well above the compact's twelve-guard limit. The gate watch counts swords. [[Commander Aldric Vane]] has not yet invoked the clause.",
    hidden=False,
    dm_notes="House Vespar's forty armed guards entered here. The violation of the twelve-guard compact limit is documented by the gate watch. Aldric chose not to enforce it on arrival — enforcing it now requires a formal confrontation he wants to choose the timing for.")

db.add_location(SLUG, "The Grace-Sworn Citadel",
    role="Headquarters of the paladin order and Hartstone's military command",
    description="The stone fortress at Hartstone's center where [[The Grace-Sworn]] have kept their watch for three generations. [[Commander Aldric Vane]] commands from here. [[Brother Edmar]] keeps the founding compact records in [[The City Archive|the archive]] below. The citadel is the physical expression of Hartstone's neutrality — it belongs to no kingdom.",
    hidden=False,
    dm_notes="Aldric's private rider — the one he sent without explaining who it was to — left from the citadel's back gate. The archive holds the original 1187 treaty. Edmar has been in the archive every evening for a week.")

db.add_location(SLUG, "The City Archive",
    role="Hartstone's official records repository, keeper of the compact",
    description="The archive holds three generations of civic records, treaty texts, succession documents, and trade agreements. [[Petra Wynn]] is the custodian. She does not sell information — she trades it. The founding compact lives here, alongside the 1187 treaty whose third provision neither delegation has cited.",
    hidden=False,
    dm_notes="The 1187 treaty has a third provision that supersedes both the Vespar dynastic claim and the Kelrath neutrality resolution. Brother Edmar has found it. He has not told anyone yet. Petra Wynn already knows about it — she traded the information to someone six months ago.")

db.add_location(SLUG, "The Compact Hall",
    role="Hartstone's formal hearing chamber — where claims are argued",
    description="The formal chamber where [[The Grace-Sworn]] convene hearings on treaty matters. Three rows of benches face a raised platform where [[Commander Aldric Vane|the Commander]] presides. The flags of the compact hang above. [[Lady Ivra Malt]] presented her documentation here. [[Emissary Dax Fell]] produced his counter-resolution here. The session was adjourned without resolution.",
    hidden=False,
    dm_notes="The next hearing will determine whether the compact must recognize a Vespar heir. If Aldric rules wrongly, the compact breaks. The third provision of the 1187 treaty — if it is what Edmar thinks it is — could make both delegations' arguments irrelevant.")

db.add_location(SLUG, "The East Quarter Tunnels",
    role="Underbrick territory — weapons cache and ambush site",
    description="A network of tunnels beneath the east quarter of Hartstone, in use since the city's founding for drainage and storage. The city watch found evidence of recent heavy traffic. A [[The Grace-Sworn|Grace-Sworn]] patrol was ambushed here in Session 4 — disarmed, blindfolded, left a message. The source of the weapon shipments moving through these tunnels has not been found.",
    hidden=False,
    dm_notes="The Underbrick has been using these tunnels to move weapon shipments from both Vespar and Kelrath suppliers simultaneously. The Loom sold the same shipment to both clients. The cache is somewhere below the east quarter — Petra Wynn knows where the old tunnel map is. The ambush site is about forty meters in from the market entrance.")

db.add_location(SLUG, "The Guildhall",
    role="Headquarters of the Compact Guild and Hartstone's merchant class",
    description="The Guildhall stands at the intersection of Hartstone's two main trade roads, a deliberate statement about who actually runs the city's economy. [[Guildmaster Sena Cord]] receives visitors here. The upper floor has a private dining room where she meets with people she is deciding whether to trust.",
    hidden=False,
    dm_notes="The meeting where Sena Cord told the party 'the compact pays my tariffs — I would prefer it to continue' happened in the private dining room. She knows more about the weapons shipments than she said. She has been meeting with Dax Fell for three months. The guild has its own reasons for preferring Kelrath's resolution to Vespar's dynastic claim.")

locations_data = db._load(SLUG, "world/locations.json")
L = {loc["name"]: loc["id"] for loc in locations_data["locations"]}
print(f"  Locations: {list(L.keys())}")

# ── Relations ──────────────────────────────────────────────────────────────────

# Dual-axis: formal role vs personal reality
add_dual_rel("npc", N["Commander Aldric Vane"], N["Lady Ivra Malt"],   "npc",
             formal_relation="rival", personal_relation="ally",   weight=0.8, dm_only=True)
add_dual_rel("npc", N["Lady Ivra Malt"],        N["Commander Aldric Vane"], "npc",
             formal_relation="rival", personal_relation="ally",   weight=0.8, dm_only=True)
add_dual_rel("npc", N["Commander Aldric Vane"], N["Guildmaster Sena Cord"], "npc",
             formal_relation="ally",  personal_relation="rival",  weight=0.75)
add_dual_rel("npc", N["Guildmaster Sena Cord"], N["Commander Aldric Vane"], "npc",
             formal_relation="ally",  personal_relation="rival",  weight=0.75)
add_dual_rel("npc", N["Lady Ivra Malt"],        N["Emissary Dax Fell"],     "npc",
             formal_relation="rival", personal_relation="neutral", weight=0.8)
add_dual_rel("npc", N["Emissary Dax Fell"],     N["Lady Ivra Malt"],        "npc",
             formal_relation="rival", personal_relation="neutral", weight=0.8)

# Clean alliances
add_rel("npc", N["Commander Aldric Vane"],  N["Brother Edmar"],         "npc", "ally", 0.9)
add_rel("npc", N["Brother Edmar"],          N["Commander Aldric Vane"], "npc", "ally", 0.9)
add_rel("npc", N["Guildmaster Sena Cord"],  N["Emissary Dax Fell"],     "npc", "ally", 0.7)
add_rel("npc", N["Emissary Dax Fell"],      N["Guildmaster Sena Cord"], "npc", "ally", 0.7)
add_rel("npc", N["Petra Wynn"],             N["Guildmaster Sena Cord"], "npc", "ally", 0.65, dm_only=True)
add_rel("npc", N["The Loom"],               N["Lady Ivra Malt"],        "npc", "ally", 0.6, dm_only=True)

# Faction edges
add_rel("faction", F["The Grace-Sworn"],    F["The Compact Guild"],  "faction", "ally",  0.85)
add_rel("faction", F["The Compact Guild"],  F["The Grace-Sworn"],    "faction", "ally",  0.85)
add_rel("faction", F["House Vespar"],       F["The Kelrath Envoys"], "faction", "rival", 1.0)
add_rel("faction", F["The Kelrath Envoys"], F["House Vespar"],       "faction", "rival", 1.0)
add_rel("faction", F["House Vespar"],       F["The Grace-Sworn"],    "faction", "rival", 0.7)
add_rel("faction", F["The Kelrath Envoys"], F["The Grace-Sworn"],    "faction", "rival", 0.6)
add_rel("faction", F["The Grace-Sworn"],    F["House Vespar"],       "faction", "rival", 0.7)
add_rel("faction", F["The Grace-Sworn"],    F["The Kelrath Envoys"], "faction", "rival", 0.6)
add_rel("faction", F["The Underbrick"],     F["House Vespar"],       "faction", "ally",  0.5, dm_only=True)

print("  Relations set")

# ── Event Log ──────────────────────────────────────────────────────────────────

# Session 1: Both Delegations Arrive
log_n(N["Lady Ivra Malt"], 1,
      "[[House Vespar]]'s delegation arrives at Hartstone's north gate with forty armed guards. "
      "[[Lady Ivra Malt]] presents papers claiming historical title. Impeccably polite, completely immovable.",
      polarity="negative", intensity=2, event_type="politics", ripple=True,
      location_id=L["Hartstone North Gate"])

log_n(N["Commander Aldric Vane"], 1,
      "[[Commander Aldric Vane]] reads [[Lady Ivra Malt]]'s papers carefully, thanks her, and invites the delegation "
      "to guest quarters without confirming the claim. He sends a rider to [[Brother Edmar]] before dinner.",
      polarity="positive", intensity=1, event_type="politics",
      location_id=L["The Grace-Sworn Citadel"])

log_f(F["House Vespar"], 1,
      "[[House Vespar]]'s delegation exceeds the twelve-guard compact limit by twenty-eight. "
      "[[The Grace-Sworn]] are counting swords. [[Commander Aldric Vane]] has not yet invoked the clause.",
      polarity="negative", intensity=2, event_type="politics",
      location_id=L["Hartstone North Gate"])

log_n(N["Emissary Dax Fell"], 1,
      "[[Emissary Dax Fell]] dines with [[The Compact Guild]]'s senior merchants the same evening the [[House Vespar]] delegation "
      "arrives. He is already here. He has been here six months.",
      polarity="neutral", intensity=1, event_type="politics", visibility="dm_only",
      location_id=L["The Guildhall"])

# Session 2: The Archive and the Weapons
log_n(N["Brother Edmar"], 2,
      "[[Brother Edmar]] locates the succession clause in the founding compact: "
      "[[The Grace-Sworn]] must recognize the legitimate ruler of any treaty partner. "
      "Both [[House Vespar]] claimants have documentation. One set is forged. He does not yet know which.",
      polarity="positive", intensity=1, event_type="discovery",
      location_id=L["The City Archive"])

log_f(F["The Underbrick"], 2,
      "Three shipments of weapons have moved through the east tunnels in two weeks — "
      "too many for street crime. Consistent with equipping a small private force.",
      polarity="negative", intensity=2, event_type="other",
      visibility="dm_only", ripple=True)

log_n(N["Guildmaster Sena Cord"], 2,
      "[[Guildmaster Sena Cord]] requests a private meeting. She confirms [[The Compact Guild]] is aware of the "
      "weapons movement. She says: 'The compact pays my tariffs. I would prefer it to continue.' "
      "She does not say what she knows about the source.",
      polarity="neutral", intensity=1, event_type="dialogue",
      location_id=L["The Guildhall"])

# Session 3: Lady Ivra's Play
log_n(N["Lady Ivra Malt"], 3,
      "[[Lady Ivra Malt]] presents her second claimant's documentation at a formal hearing: "
      "Lord Eddan Vespar, third cousin, with a direct treaty right to Hartstone under "
      "the Compact of 1187. The records are genuine. [[Emissary Dax Fell]] has a counter.",
      polarity="negative", intensity=2, event_type="politics", ripple=True,
      location_id=L["The Compact Hall"])

log_n(N["Emissary Dax Fell"], 3,
      "[[Emissary Dax Fell]] produces a ratified [[The Kelrath Envoys|Kelrath]] Council resolution: Hartstone's neutrality "
      "supersedes any historical treaty claim. It is dated six months ago. "
      "He has been planning this longer than that.",
      polarity="negative", intensity=2, event_type="politics", ripple=True,
      location_id=L["The Compact Hall"])

log_n(N["Commander Aldric Vane"], 3,
      "[[Commander Aldric Vane]] adjourns the hearing. Asks [[Brother Edmar]] to retrieve the 1187 treaty from the archive. "
      "Sends a second rider, privately, to someone outside the city. Does not explain who.",
      polarity="positive", intensity=1, event_type="politics", visibility="dm_only",
      location_id=L["The Compact Hall"])

# Session 4: The Underbrick Moves
log_f(F["The Underbrick"], 4,
      "A [[The Grace-Sworn|Grace-Sworn]] patrol is ambushed in the east tunnels — non-lethal, but disarmed "
      "and blindfolded for two hours. A message is left: 'Stop looking.'",
      polarity="negative", intensity=3, event_type="combat",
      actor_id=N["The Loom"], actor_type="npc",
      location_id=L["The East Quarter Tunnels"])

db.apply_ripple(SLUG, F["The Underbrick"], "faction", 4,
                "Underbrick attacks Grace-Sworn patrol — open confrontation.",
                "negative", 3, "combat", "public")

log_n(N["Commander Aldric Vane"], 4,
      "[[Commander Aldric Vane]] invokes the armed envoy clause: both delegations must reduce guards to twelve "
      "within forty-eight hours. [[Lady Ivra Malt]] protests. [[Emissary Dax Fell]] immediately complies "
      "and offers his excess guards to help patrol the tunnels.",
      polarity="positive", intensity=2, event_type="politics", ripple=True,
      location_id=L["The Compact Hall"])

log_n(N["The Loom"], 4,
      "A cutout is captured in the market. Under questioning: [[The Underbrick]] is being paid "
      "by two clients simultaneously for the same weapon delivery. "
      "[[The Loom]] has sold the same shipment twice. Someone is about to be very angry.",
      polarity="negative", intensity=2, event_type="discovery", visibility="dm_only",
      location_id=L["The East Quarter Tunnels"])

db.log_condition(SLUG, C["Armed Envoys"], 4,
                 "Kelrath reduces guard count immediately; Vespar has 48 hours. "
                 "Enforcement of the clause partially eases tension.",
                 polarity="positive", intensity=1)

print("  Event log complete")

# ── Location log entries ───────────────────────────────────────────────────────

log_l(L["Hartstone North Gate"], 1,
      "[[House Vespar]]'s delegation arrives with forty armed guards — twenty-eight over the compact limit. [[Lady Ivra Malt]] presents papers claiming historical title. The gate watch counts every sword. [[Commander Aldric Vane]] does not invoke the clause today.",
      polarity="negative", intensity=2, event_type="politics")

log_l(L["The City Archive"], 2,
      "[[Brother Edmar]] locates the succession clause in the founding compact. Both [[House Vespar|Vespar]] claimants have documentation. One set is forged — possibly both. He also finds something in the 1187 treaty that neither delegation has cited. He has not told anyone yet.",
      polarity="positive", intensity=2, event_type="discovery",
      actor_id=N["Brother Edmar"], actor_type="npc")

log_l(L["The Compact Hall"], 3,
      "[[Lady Ivra Malt]] presents Lord Eddan Vespar's documentation. [[Emissary Dax Fell]] produces the Kelrath resolution dated six months ago. [[Commander Aldric Vane]] adjourns without ruling. He sends a private rider from the citadel's back gate. He does not explain to whom.",
      polarity="neutral", intensity=2, event_type="politics")

log_l(L["The East Quarter Tunnels"], 4,
      "A [[The Grace-Sworn|Grace-Sworn]] patrol is ambushed here — non-lethal, disarmed, blindfolded for two hours. A message is left: 'Stop looking.' The weapons cache is somewhere further in. [[The Loom]] knows the patrol found the outer staging area.",
      polarity="negative", intensity=3, event_type="combat",
      actor_id=N["The Loom"], actor_type="npc")

log_l(L["The Guildhall"], 2,
      "[[Guildmaster Sena Cord]] meets the party privately. She confirms the Guild knows about the weapon shipments. She says: 'The compact pays my tariffs. I would prefer it to continue.' She does not name her price. She does not say what she knows about the source.",
      polarity="neutral", intensity=1, event_type="dialogue",
      actor_id=N["Guildmaster Sena Cord"], actor_type="npc")

print("  Location logs complete")

# ── Journal ────────────────────────────────────────────────────────────────────
db.post_journal(SLUG, 1, "Session 1 — The Delegations Arrive",
    "Both sides are here now. House Vespar came in force and made their claim in writing "
    "before they'd unpacked. Kelrath's man had been here six months already. "
    "Aldric is holding the line but he's holding it alone. The compact's enforcement "
    "powers depend entirely on the Guild's continued financial support. "
    "We need to find out what Sena Cord wants before she tells us.")

db.post_journal(SLUG, 3, "Session 3 — The 1187 Treaty",
    "Dax Fell's counter is legally sound. The resolution is dated six months ago — "
    "when he arrived. He's been preparing this response since before Vespar moved. "
    "Which means he knew exactly what they were going to do. How? "
    "Brother Edmar is pulling the original treaty. There may be a third provision neither side cited.")

db.post_journal(SLUG, 4, "Session 4 — The Underbrick",
    "Attacking a Grace-Sworn patrol is a line. They crossed it. "
    "The captured cutout says The Loom sold the same weapons to two clients. "
    "Both delegations? That's either the most cynical move I've heard "
    "or The Loom is trying to start a fight between them and profit from the chaos. "
    "We need to reach the cache before either delegation realizes they both paid for it.")

print(f"\nDone. Campaign '{SLUG}' seeded at {CAMP_DIR}")
print("To deploy to Pi:  rsync -av campaigns/paladins_grace/ simonhans@raspberrypi:/mnt/serverdrive/coding/rippleforge/campaigns/paladins_grace/")
