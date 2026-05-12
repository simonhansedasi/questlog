"""Seed script: The Hartstone Compact. TTRPG starter world.

A neutral border city, two kingdoms pressing claims, one paladin order keeping the peace.
Showcases all TTRPG features: party, quests, dual-axis edges, conditions, ripples,
log_character, log_party_group, hidden_factions, source_event_id.

Run:  python seeds/seed_paladins_grace.py
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
    ("Commander Aldric Vane",
     "Grace-Sworn — military leader of the compact",
     "ally", False,
     [F["The Grace-Sworn"]], None,
     "Thirty years in [[The Grace-Sworn]]. He has kept Hartstone neutral through three "
     "crises and does not intend this to be the fourth. He is building options. "
     "Some of them are things he can never tell [[The Compact Guild|the Guild]] about.",
     "Aldric sent a private rider before dinner on Session 1 — the recipient is a retired "
     "Grace-Sworn who knows where the 1187 treaty's original signatories were buried. "
     "He's been in contact with this source for three weeks, since before Vespar arrived. "
     "He knew this was coming."),

    ("Lady Ivra Malt",
     "House Vespar — envoy pressing the northern claim",
     "rival", False,
     [F["House Vespar"]], None,
     "She arrived with twelve lawyers and forty guards 'for her protection.' "
     "She is charming, specific, and never wrong about anything she can cite in writing. "
     "She wants Hartstone. She has a fallback position she has not yet revealed. "
     "She knows [[Commander Aldric Vane]] better than he would prefer.",
     "Ivra and Aldric have met twice before — once at a trade summit seven years ago, "
     "once at a border arbitration three years back. She knows he won't bend on the compact. "
     "Her fallback: if the claim fails, she will offer Aldric a personal arrangement — "
     "Grace-Sworn funding from House Vespar, permanently, in exchange for a 'favorable interpretation.'"),

    ("Guildmaster Sena Cord",
     "Compact Guild — controls trade and tariff income",
     "neutral", False,
     [F["The Compact Guild"]], None,
     "[[The Compact Guild|The Guild]] has financed [[The Grace-Sworn]] for two generations. Guildmaster Sena Cord knows this. "
     "She is not threatening — she is ensuring everyone understands the math. "
     "She will back whoever keeps the trade routes open. She has a price. "
     "She has not named it yet.",
     "Her price: the Guild wants a permanent seat on the compact's trade arbitration panel — "
     "a structural veto over any tariff disputes routed through Hartstone. "
     "She has been meeting with Dax Fell for three months. The Kelrath resolution, "
     "if it holds, gives the Guild more leverage than either Vespar outcome."),

    ("Emissary Dax Fell",
     "Kelrath Confederation — diplomatic observer",
     "rival", False,
     [F["The Kelrath Envoys"]], None,
     "He has been in Hartstone for six months before [[House Vespar]] arrived. "
     "He knows where every magistrate eats dinner and which ones have debts. "
     "He presents as reasonable and collaborative. He is. He is also winning.",
     "Dax drafted the Kelrath neutrality resolution while still at the Confederation capital — "
     "six months before he arrived. He knew Vespar's play in advance, possibly from an "
     "informant inside House Vespar's legal office. [[Osric Fell|Osric]] was at the Academy "
     "when the resolution was being drafted. He never saw Dax's name on it until now."),

    ("Brother Edmar",
     "Grace-Sworn — chaplain and keeper of founding records",
     "ally", False,
     [F["The Grace-Sworn"]], None,
     "Old enough to remember the last succession crisis. Gentle enough that people "
     "tell him things they should not. He spends his evenings in [[The City Archive|the archive]]. "
     "He knows something about [[The Underbrick]] he is deciding whether to share.",
     "Brother Edmar has found the 1187 treaty's third provision: a supersession clause "
     "that voids both the Vespar dynastic claim and the Kelrath neutrality resolution "
     "in the event of 'armed factional presence.' Both delegations are in technical violation. "
     "The clause would require the Grace-Sworn to expel both delegations and hold Hartstone "
     "independently for one year. He hasn't told Aldric yet because the clause also requires "
     "the compact to be financially self-sufficient — which it currently is not."),

    ("Petra Wynn",
     "City archivist — custodian of three generations of records",
     "neutral", True,
     [F["The Compact Guild"]], [F["The Kelrath Envoys"]],
     "The city's official archivist. She has copies of everything. She does not sell "
     "information — she trades it. She knows who owns the old tunnels under the east "
     "quarter and what has moved through [[The East Quarter Tunnels|them]] recently. (DM-only until approached)",
     "Petra sold the 1187 treaty's third provision to Dax Fell six months ago — before he "
     "arrived in Hartstone. That is why his neutrality resolution is so precisely drafted. "
     "She didn't know what he'd use it for. She knows now. She also has the tunnel map "
     "for the east quarter. She has not offered it to anyone yet."),

    ("The Loom",
     "Underbrick — faction boss, identity unknown",
     "hostile", True,
     [], [F["The Underbrick"]],
     "[[The Underbrick]]'s controller. Nobody inside the network has seen their face. "
     "They communicate through cutouts and coded drops. They have been buying weapons "
     "from both [[House Vespar|Vespar]] and [[The Kelrath Envoys|Kelrath]] suppliers simultaneously. "
     "Either they are playing both sides or they are the third side. (DM-only)",
     "The Loom sold the same weapon shipment to both Vespar and Kelrath — "
     "not by accident. They are trying to provoke a confrontation between the delegations "
     "in Hartstone while the compact's enforcement powers are degraded. "
     "In the chaos, the Underbrick becomes the only functioning authority in the east quarter. "
     "The Loom is playing a third game, not second fiddle to either delegation."),
]

N = {}
for item in npcs_to_add:
    name, role, rel, hidden, faction_ids, hidden_faction_ids, desc, dm_notes = item
    db.add_npc(SLUG, name, role, rel, desc,
               hidden=hidden, factions=faction_ids,
               hidden_factions=hidden_faction_ids,
               dm_notes=dm_notes)
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
    dm_notes="The 1187 treaty has a third provision that supersedes both the Vespar dynastic claim and the Kelrath neutrality resolution. Brother Edmar has found it. He has not told anyone yet. Petra Wynn already knows about it — she traded the information to Dax Fell six months ago.")

db.add_location(SLUG, "The Compact Hall",
    role="Hartstone's formal hearing chamber — where claims are argued",
    description="The formal chamber where [[The Grace-Sworn]] convene hearings on treaty matters. Three rows of benches face a raised platform where [[Commander Aldric Vane|the Commander]] presides. The flags of the compact hang above. [[Lady Ivra Malt]] presented her documentation here. [[Emissary Dax Fell]] produced his counter-resolution here. The session was adjourned without resolution.",
    hidden=False,
    dm_notes="The next hearing will determine whether the compact must recognize a Vespar heir. If Aldric rules wrongly, the compact breaks. The third provision of the 1187 treaty — if invoked — makes both delegations' arguments irrelevant but requires the Grace-Sworn to be financially self-sufficient. They are not.")

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
             formal_relation="rival", personal_relation="ally",   weight=0.8, dm_only=True)
add_dual_rel("npc", N["Emissary Dax Fell"],     N["Lady Ivra Malt"],        "npc",
             formal_relation="rival", personal_relation="ally",   weight=0.8, dm_only=True)

# Clean alliances
add_rel("npc", N["Commander Aldric Vane"],  N["Brother Edmar"],         "npc", "ally", 0.9)
add_rel("npc", N["Brother Edmar"],          N["Commander Aldric Vane"], "npc", "ally", 0.9)
add_rel("npc", N["Guildmaster Sena Cord"],  N["Emissary Dax Fell"],     "npc", "ally", 0.7, dm_only=True)
add_rel("npc", N["Emissary Dax Fell"],      N["Guildmaster Sena Cord"], "npc", "ally", 0.7, dm_only=True)
add_rel("npc", N["Petra Wynn"],             N["Emissary Dax Fell"],     "npc", "ally", 0.65, dm_only=True)
add_rel("npc", N["The Loom"],               N["Lady Ivra Malt"],        "npc", "ally", 0.6, dm_only=True)
add_rel("npc", N["The Loom"],               N["Emissary Dax Fell"],     "npc", "ally", 0.6, dm_only=True)

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
add_rel("faction", F["The Underbrick"],     F["The Kelrath Envoys"], "faction", "ally",  0.5, dm_only=True)

print("  Relations set")

# ── Event Log — Session 1: Both Delegations Arrive ────────────────────────────

evt = log_f(F["House Vespar"], 1,
      "[[House Vespar]]'s delegation arrives at Hartstone's north gate with forty armed guards — "
      "twenty-eight over the compact's twelve-guard limit. "
      "[[Commander Aldric Vane]] reads [[Lady Ivra Malt|her]] papers and does not invoke the clause. He is counting.",
      polarity="negative", intensity=2, event_type="politics",
      location_id=L["Hartstone North Gate"])
db.apply_ripple(SLUG, F["House Vespar"], "faction", 1,
                "Vespar delegation's forty-guard arrival puts the compact's enforcement clause in play.",
                "negative", 2, "politics", "public", source_event_id=evt)

evt = log_n(N["Lady Ivra Malt"], 1,
      "[[Lady Ivra Malt]] presents papers claiming historical title at [[Hartstone North Gate|the north gate]]. "
      "Impeccably polite, completely immovable. She thanks [[Commander Aldric Vane]] for the guest quarters "
      "before he has finished reading.",
      polarity="negative", intensity=2, event_type="politics",
      location_id=L["Hartstone North Gate"])
db.apply_ripple(SLUG, N["Lady Ivra Malt"], "npc", 1,
                "Lady Ivra's arrival — claim presented, forty guards, compact limit exceeded.",
                "negative", 2, "politics", "public", source_event_id=evt)

log_n(N["Commander Aldric Vane"], 1,
      "[[Commander Aldric Vane]] reads [[Lady Ivra Malt]]'s papers, thanks her, and invites the delegation "
      "to guest quarters without confirming the claim. He sends a private rider to [[Brother Edmar]] before dinner.",
      polarity="positive", intensity=1, event_type="politics",
      location_id=L["The Grace-Sworn Citadel"])

log_n(N["Emissary Dax Fell"], 1,
      "[[Emissary Dax Fell]] dines with [[The Compact Guild]]'s senior merchants the same evening "
      "the [[House Vespar]] delegation arrives. He has been here six months. He is not surprised.",
      polarity="neutral", intensity=1, event_type="politics", visibility="dm_only",
      location_id=L["The Guildhall"])

# Session 1 — character logs
db.log_character(SLUG, "Carran Voss", 1,
    "Carran stands at the gate when [[House Vespar]]'s column arrives — forty guards, "
    "two lawyers reading aloud from folded papers. He counts swords. He keeps counting. "
    "[[Commander Aldric Vane|Aldric]] told him the compact has held three succession crises. "
    "Carran is not sure Aldric has seen forty swords arrive at the gate before.",
    polarity="negative", intensity=2, event_type="politics",
    location_id=L["Hartstone North Gate"])

db.log_character(SLUG, "Mira Dune", 1,
    "[[Emissary Dax Fell|Dax Fell]] takes the same corner table at the Guildhall's private dining room "
    "he has used every third evening for six months. Mira has delivered messages to that table. "
    "Tonight he has [[Guildmaster Sena Cord|Sena Cord]]'s senior merchants with him "
    "and a new bottle of Kelrath red. The [[House Vespar]] delegation is still unpacking.",
    polarity="neutral", intensity=1, event_type="politics",
    location_id=L["The Guildhall"])

db.log_character(SLUG, "Sera Eld", 1,
    "Sera arrived in Hartstone two weeks ago to study [[The Grace-Sworn|Grace-Sworn]] field medicine. "
    "She did not expect to arrive in the middle of a succession crisis. "
    "[[Brother Edmar]] gave her a bed in the archive annex and apologized for the timing. "
    "She is beginning to suspect the timing is not going to improve.",
    polarity="neutral", intensity=1, event_type="other",
    location_id=L["The Grace-Sworn Citadel"])

db.log_character(SLUG, "Osric Fell", 1,
    "The name on the sealed correspondence delivered to [[Emissary Dax Fell]] this evening "
    "is written in a hand [[Osric Fell|Osric]] recognizes from the Kelrath Academy's administrative staff. "
    "The letter is dated three months ago. That is before the Kelrath Council would have voted on anything. "
    "He does not mention this to anyone tonight.",
    polarity="negative", intensity=1, event_type="discovery", visibility="dm_only")

db.log_party_group(SLUG, 1,
    "First evening in Hartstone: [[House Vespar]]'s column through the north gate, "
    "[[Lady Ivra Malt]] presenting papers before the ink on Aldric's receipt was dry, "
    "and [[Emissary Dax Fell]] already dining with the Guild's inner circle. "
    "Two delegations, one compact, and the man who holds it together is down one rider he won't explain.",
    polarity="negative", intensity=2, event_type="politics",
    location_id=L["Hartstone North Gate"])

# ── Event Log — Session 2: The Archive and the Weapons ───────────────────────

log_n(N["Brother Edmar"], 2,
      "[[Brother Edmar]] locates the succession clause in the founding compact: "
      "[[The Grace-Sworn]] must recognize the legitimate ruler of any treaty partner. "
      "Both [[House Vespar]] claimants have documentation. One set is forged — possibly both. "
      "He does not yet know which. He finds something else in the 1187 treaty he is not ready to share.",
      polarity="positive", intensity=1, event_type="discovery",
      location_id=L["The City Archive"])

evt = log_f(F["The Underbrick"], 2,
      "Three weapon shipments move through [[The East Quarter Tunnels|the east tunnels]] in two weeks — "
      "too many for street crime. Consistent with equipping a small private force. "
      "A [[The Grace-Sworn|Grace-Sworn]] border patrol filed the report. "
      "[[Commander Aldric Vane]] has not yet briefed the delegations.",
      polarity="negative", intensity=2, event_type="other",
      visibility="dm_only")
db.apply_ripple(SLUG, F["The Underbrick"], "faction", 2,
                "Military-scale weapons moving through east tunnels — Underbrick operating at new capacity.",
                "negative", 2, "other", "dm_only", source_event_id=evt)

log_n(N["Guildmaster Sena Cord"], 2,
      "[[Guildmaster Sena Cord]] requests a private meeting at [[The Guildhall]]. "
      "She confirms [[The Compact Guild]] is aware of the weapons movement — not because the watch told her. "
      "She says: 'The compact pays my tariffs. I would prefer it to continue.' "
      "She does not name her price. She pours the good wine.",
      polarity="neutral", intensity=1, event_type="dialogue",
      location_id=L["The Guildhall"])

# Session 2 — character logs
db.log_character(SLUG, "Carran Voss", 2,
    "Carran spends the afternoon in [[The City Archive|the archive]] with [[Brother Edmar]], "
    "working through succession records. The founding compact's clause is clear: "
    "[[The Grace-Sworn]] must recognize the legitimate ruler. "
    "The word 'legitimate' is not defined in the text. Edmar says that was deliberate.",
    polarity="negative", intensity=1, event_type="discovery",
    location_id=L["The City Archive"])

db.log_character(SLUG, "Mira Dune", 2,
    "Three shipments in two weeks through the east quarter drainage tunnels — "
    "[[Mira Dune|Mira]] knows those routes. She has run courier packages through two of them. "
    "Whatever is being moved is heavy: the gravel impressions are four inches deep. "
    "That is not packages. That is crates.",
    polarity="negative", intensity=2, event_type="discovery",
    location_id=L["The East Quarter Tunnels"])

db.log_character(SLUG, "Sera Eld", 2,
    "[[Guildmaster Sena Cord]] spent the first ten minutes of the meeting deciding whether "
    "to trust [[Sera Eld|Sera]]. Sera has seen that look before — in patients weighing whether "
    "to tell a healer where it actually hurts. Sena decided yes, provisionally. "
    "She mentioned the weapons before anyone asked. That was not accidental.",
    polarity="neutral", intensity=1, event_type="dialogue",
    location_id=L["The Guildhall"])

db.log_character(SLUG, "Osric Fell", 2,
    "The 1187 treaty has three provisions. Both delegations have cited the first two. "
    "[[Osric Fell|Osric]] finds the third while [[Brother Edmar]] is pulling succession records. "
    "He reads it twice. He does not mention it to Edmar. "
    "He needs to know who else has seen this before he decides what to do with it.",
    polarity="positive", intensity=2, event_type="discovery", visibility="dm_only",
    location_id=L["The City Archive"])

db.log_party_group(SLUG, 2,
    "Split run: [[Carran Voss|Carran]] and [[Osric Fell|Osric]] in [[The City Archive|the archive]], "
    "[[Mira Dune|Mira]] in the east quarter tunnels, [[Sera Eld|Sera]] at the [[The Guildhall|Guildhall]] meeting. "
    "Everyone came back with something. The succession clause requires a ruling. "
    "The weapons movement is military. The 1187 treaty has a third provision nobody is citing. "
    "[[Guildmaster Sena Cord|Sena Cord]] knows about the weapons and wants to talk terms.",
    polarity="negative", intensity=2, event_type="discovery",
    actor_id=F["The Underbrick"], actor_type="faction")

# ── Event Log — Session 3: Lady Ivra's Play ───────────────────────────────────

evt = log_n(N["Lady Ivra Malt"], 3,
      "[[Lady Ivra Malt]] presents her second claimant's documentation at a formal hearing: "
      "Lord Eddan Vespar, third cousin, with a direct treaty right to Hartstone under "
      "the Compact of 1187. The records are genuine. [[Emissary Dax Fell]] has a counter. "
      "She expected him to.",
      polarity="negative", intensity=2, event_type="politics",
      location_id=L["The Compact Hall"])
db.apply_ripple(SLUG, N["Lady Ivra Malt"], "npc", 3,
                "Lady Ivra's formal claim — Lord Eddan's documentation presented at the hearing.",
                "negative", 2, "politics", "public", source_event_id=evt)

evt = log_n(N["Emissary Dax Fell"], 3,
      "[[Emissary Dax Fell]] produces a ratified [[The Kelrath Envoys|Kelrath]] Council resolution: "
      "Hartstone's neutrality supersedes any historical treaty claim. "
      "It is dated six months ago. He drafted it before he arrived.",
      polarity="negative", intensity=2, event_type="politics",
      location_id=L["The Compact Hall"])
db.apply_ripple(SLUG, N["Emissary Dax Fell"], "npc", 3,
                "Dax Fell's neutrality resolution — dated six months ago, drafted before he arrived in Hartstone.",
                "negative", 2, "politics", "public", source_event_id=evt)

log_n(N["Commander Aldric Vane"], 3,
      "[[Commander Aldric Vane]] adjourns the hearing. Asks [[Brother Edmar]] to retrieve "
      "the 1187 treaty from the archive. Sends a second rider privately. Does not explain who. "
      "His expression does not change at any point during the session.",
      polarity="positive", intensity=1, event_type="politics", visibility="dm_only",
      location_id=L["The Compact Hall"])

# Session 3 — character logs
db.log_character(SLUG, "Carran Voss", 3,
    "The compact requires [[The Grace-Sworn]] to recognize the legitimate ruler "
    "of [[House Vespar|Vespar]]'s treaty territory. [[Lady Ivra Malt|Ivra]]'s documentation is genuine. "
    "[[Emissary Dax Fell|Dax]]'s resolution is ratified. Both are legally sound. "
    "Both cannot be honored simultaneously. [[Carran Voss|Carran]] keeps looking at [[Commander Aldric Vane|Aldric]], "
    "who is not looking back.",
    polarity="negative", intensity=2, event_type="politics",
    location_id=L["The Compact Hall"])

db.log_character(SLUG, "Mira Dune", 3,
    "[[Mira Dune|Mira]] sat in the back row and watched which documents [[Lady Ivra Malt|Lady Ivra]] "
    "kept folded. Three of them never left her lawyer's inside pocket. "
    "[[Emissary Dax Fell|Dax Fell]] watched the same pocket. He knew which documents she would present "
    "before she presented them. That is not preparation. That is advance notice.",
    polarity="negative", intensity=1, event_type="discovery",
    location_id=L["The Compact Hall"])

db.log_character(SLUG, "Sera Eld", 3,
    "[[Brother Edmar]] was quiet through the hearing. Not attentive-quiet — the silence "
    "of someone who already knows how the argument ends. "
    "[[Sera Eld|Sera]] caught him during the adjournment: 'You found something in the treaty.' "
    "He looked at her for a long moment. 'I found something I need to verify,' he said. "
    "'Before anyone else does.'",
    polarity="positive", intensity=1, event_type="dialogue",
    location_id=L["The Compact Hall"])

db.log_character(SLUG, "Osric Fell", 3,
    "[[Osric Fell|Osric]] was at the Kelrath Academy when the neutrality resolution was being drafted — "
    "not the ratification, the drafting. He remembers the policy clerks running the citations. "
    "[[Emissary Dax Fell|Dax]]'s document is word-for-word what was on that desk. "
    "The resolution was ready before the Vespar succession crisis was public knowledge. "
    "Someone told Kelrath what Vespar was planning before they announced it.",
    polarity="negative", intensity=2, event_type="discovery", visibility="dm_only",
    location_id=L["The Compact Hall"])

db.log_party_group(SLUG, 3,
    "[[The Compact Hall|The hearing]] produced no ruling and two very careful legal positions. "
    "[[Lady Ivra Malt|Ivra]]'s documentation is genuine. [[Emissary Dax Fell|Dax]]'s resolution is ratified. "
    "[[Commander Aldric Vane|Aldric]] adjourned without comment. "
    "[[Brother Edmar]] is pulling the 1187 treaty's original text for the third time. "
    "[[Osric Fell|Osric]] has said nothing about what he found in the archive yesterday.",
    polarity="negative", intensity=2, event_type="politics",
    location_id=L["The Compact Hall"])

# ── Event Log — Session 4: The Underbrick Moves ───────────────────────────────

evt = log_f(F["The Underbrick"], 4,
      "A [[The Grace-Sworn|Grace-Sworn]] patrol is ambushed in [[The East Quarter Tunnels|the east tunnels]] — "
      "non-lethal, disarmed, and blindfolded for two hours. A message is written on one guard's forearm: "
      "'Stop looking.' [[The Loom]] did not use the patrol's own weapons. They had their own.",
      polarity="negative", intensity=3, event_type="combat",
      actor_id=N["The Loom"], actor_type="npc",
      location_id=L["The East Quarter Tunnels"])
db.apply_ripple(SLUG, F["The Underbrick"], "faction", 4,
                "Underbrick attacks Grace-Sworn patrol — open confrontation, armed, organized.",
                "negative", 3, "combat", "public", source_event_id=evt)

evt = log_n(N["Commander Aldric Vane"], 4,
      "[[Commander Aldric Vane]] invokes the armed envoy clause: both delegations must reduce "
      "guards to twelve within forty-eight hours. [[Lady Ivra Malt]] protests formally. "
      "[[Emissary Dax Fell]] immediately complies and offers his excess guards to help patrol the tunnels. "
      "[[Commander Aldric Vane|Aldric]] thanks him and does not accept.",
      polarity="positive", intensity=2, event_type="politics",
      location_id=L["The Compact Hall"])
db.apply_ripple(SLUG, N["Commander Aldric Vane"], "npc", 4,
                "Aldric invokes the compact's armed envoy clause — direct enforcement action.",
                "positive", 2, "politics", "public", source_event_id=evt)

log_n(N["The Loom"], 4,
      "A cutout is captured in the market. Under questioning: [[The Underbrick]] is being paid "
      "by two clients simultaneously for the same weapon delivery — both [[House Vespar|Vespar]] "
      "and [[The Kelrath Envoys|Kelrath]] suppliers. [[The Loom]] sold the same shipment twice. "
      "One of them is about to realize they did not receive what they paid for.",
      polarity="negative", intensity=2, event_type="discovery", visibility="dm_only",
      location_id=L["The East Quarter Tunnels"])

db.log_condition(SLUG, C["Armed Envoys"], 4,
                 "Kelrath reduces guard count immediately; Vespar has 48 hours to comply. "
                 "Enforcement of the clause partially eases the armed tension in the city.",
                 polarity="positive", intensity=1)

# Session 4 — character logs
db.log_character(SLUG, "Carran Voss", 4,
    "Two of the [[The Grace-Sworn|Grace-Sworn]] guards in that patrol are initiates "
    "[[Carran Voss|Carran]] trained with. They were found in the tunnel junction, hands bound, "
    "blindfolded. One of them had a word written on his forearm in [[The Underbrick|Underbrick]] ink. "
    "Carran cleaned it off himself. He did not tell [[Commander Aldric Vane|Aldric]] about the second message "
    "in the guard's boot.",
    polarity="negative", intensity=3, event_type="combat",
    location_id=L["The East Quarter Tunnels"])

db.log_character(SLUG, "Mira Dune", 4,
    "[[Mira Dune|Mira]] went into the tunnels two hours before the patrol was supposed to. "
    "She found the ambush site, the staging area, and a second exit [[The Grace-Sworn|Grace-Sworn]] "
    "tunnel maps don't show. She marked it and came back out. "
    "She did not tell anyone she went in. She is deciding who to tell about the exit.",
    polarity="negative", intensity=2, event_type="discovery", visibility="dm_only",
    location_id=L["The East Quarter Tunnels"])

db.log_character(SLUG, "Sera Eld", 4,
    "[[Sera Eld|Sera]] healed the patrol in the citadel's lower ward. None of them could say "
    "how many people ambushed them — it was dark, it was fast, nobody spoke. "
    "The blindfolds were cut from bolt-cloth. The same bolt-cloth [[The Compact Guild|the Guild]] "
    "imports from the southern river towns. She recognized the weave.",
    polarity="negative", intensity=2, event_type="other",
    location_id=L["The Grace-Sworn Citadel"])

db.log_character(SLUG, "Osric Fell", 4,
    "The cutout's account — same weapons sold to [[House Vespar|Vespar]] and [[The Kelrath Envoys|Kelrath]] simultaneously — "
    "means [[The Loom]] is not working for either delegation. "
    "[[Osric Fell|Osric]] draws the conclusion quietly: [[The Underbrick|the Underbrick]] is trying to provoke "
    "a confrontation between two well-armed delegations inside Hartstone's walls. "
    "In the chaos, the compact's enforcement authority collapses and the east quarter "
    "becomes ungoverned territory. Someone planned this before Vespar arrived.",
    polarity="negative", intensity=3, event_type="discovery", visibility="dm_only")

db.log_party_group(SLUG, 4,
    "Ambush patrol recovered. Cutout captured. [[The Loom]] sold the same weapons to both "
    "[[House Vespar|Vespar]] and [[The Kelrath Envoys|Kelrath]]. [[Commander Aldric Vane|Aldric]] invoked the armed "
    "envoy clause — [[The Kelrath Envoys|Kelrath]] complied immediately, [[House Vespar|Vespar]] has 48 hours. "
    "The weapons cache is still in the tunnels. Two delegations are about to learn "
    "they each paid for a shipment neither of them is going to receive.",
    polarity="negative", intensity=3, event_type="combat",
    actor_id=F["The Underbrick"], actor_type="faction",
    location_id=L["The East Quarter Tunnels"])

print("  Event log complete")

# ── Location log entries ───────────────────────────────────────────────────────

log_l(L["Hartstone North Gate"], 1,
      "[[House Vespar]]'s delegation arrives with forty armed guards — twenty-eight over the compact limit. "
      "[[Lady Ivra Malt]] presents papers claiming historical title. The gate watch counts every sword. "
      "[[Commander Aldric Vane]] does not invoke the clause today.",
      polarity="negative", intensity=2, event_type="politics",
      actor_id=F["House Vespar"], actor_type="faction")

log_l(L["The City Archive"], 2,
      "[[Brother Edmar]] locates the succession clause. Both [[House Vespar|Vespar]] claimants have documentation — "
      "one set is forged, possibly both. He finds the 1187 treaty's third provision and has not told anyone. "
      "[[Osric Fell]] was here separately and found it too.",
      polarity="positive", intensity=2, event_type="discovery",
      actor_id=N["Brother Edmar"], actor_type="npc")

log_l(L["The Guildhall"], 2,
      "[[Guildmaster Sena Cord]] meets the party privately. She confirms the Guild knows about "
      "the weapon shipments through the east tunnels. She says: 'The compact pays my tariffs — "
      "I would prefer it to continue.' She does not name her price.",
      polarity="neutral", intensity=1, event_type="dialogue",
      actor_id=N["Guildmaster Sena Cord"], actor_type="npc")

log_l(L["The Compact Hall"], 3,
      "[[Lady Ivra Malt]] presents Lord Eddan Vespar's documentation. [[Emissary Dax Fell]] produces "
      "the Kelrath neutrality resolution dated six months ago. [[Commander Aldric Vane]] adjourns without ruling. "
      "He pulls the 1187 treaty and sends a private rider from the citadel's back gate.",
      polarity="neutral", intensity=2, event_type="politics")

log_l(L["The East Quarter Tunnels"], 4,
      "A [[The Grace-Sworn|Grace-Sworn]] patrol ambushed here — non-lethal, disarmed, blindfolded two hours. "
      "'Stop looking.' The weapons cache is further in. [[The Loom]] used their own arms. "
      "A second exit exists that does not appear on Grace-Sworn tunnel maps.",
      polarity="negative", intensity=3, event_type="combat",
      actor_id=N["The Loom"], actor_type="npc")

log_l(L["The Grace-Sworn Citadel"], 4,
      "Ambushed patrol brought here for treatment. [[Sera Eld]] identified Guild-import bolt-cloth "
      "used for the blindfolds. [[Commander Aldric Vane]] invoked the armed envoy clause from the "
      "citadel's command chamber. [[Kelrath Envoys|Kelrath]] complied within the hour.",
      polarity="negative", intensity=2, event_type="other",
      actor_id=F["The Underbrick"], actor_type="faction")

print("  Location logs complete")

# ── Quest log progression ──────────────────────────────────────────────────────

db.log_quest(SLUG, "authenticate_the_heir", 2,
    "Session 2: Both Vespar claimants have documentation in the archive. "
    "One set is forged — possibly both. Brother Edmar working on authentication. "
    "The succession clause requires a ruling before the compact's next formal session.")
db.log_quest(SLUG, "authenticate_the_heir", 3,
    "Session 3: Lord Eddan Vespar's documentation presented formally at the hearing — records genuine. "
    "Kelrath's neutrality resolution offered as counter. 1187 treaty pulled. "
    "Third provision located; Edmar verifying whether it supersedes both claims. "
    "Osric Fell read it separately and has said nothing.")

db.log_quest(SLUG, "the_guild_s_price", 2,
    "Session 2: Sena Cord's private meeting confirmed the Guild's support has conditions. "
    "She did not name her price. She knows about the weapons movement and did not volunteer how.")
db.log_quest(SLUG, "the_guild_s_price", 4,
    "Session 4: Dax Fell complied immediately with the guard reduction and offered his guards "
    "for tunnel patrol — Guild-favorable. Sena Cord's preference for Kelrath's resolution "
    "over Vespar's claim is becoming visible. Her price may be structural, not personal.")

db.log_quest(SLUG, "root_out_the_underbrick", 2,
    "Session 2: Three military-scale weapon shipments through east quarter tunnels in two weeks. "
    "Source unidentified. Quantities inconsistent with street crime.")
db.log_quest(SLUG, "root_out_the_underbrick", 4,
    "Session 4: Grace-Sworn patrol ambushed — armed, organized, 'Stop looking.' "
    "Cutout captured: The Loom sold the same shipment to both Vespar and Kelrath simultaneously. "
    "Two clients. One cache. Neither knows yet. Cache location still unknown.")

print("  Quest logs complete")

# ── Journal ────────────────────────────────────────────────────────────────────
db.post_journal(SLUG, 1, "Session 1 — The Delegations Arrive",
    "Both sides are here now. Vespar came in force and made their claim in writing "
    "before they'd unpacked. Kelrath's man had been here six months already. "
    "Aldric is holding the line but he's holding it alone. The compact's enforcement "
    "powers depend entirely on the Guild's continued financial support. "
    "We need to find out what Sena Cord wants before she tells us.")

db.post_journal(SLUG, 3, "Session 3 — The 1187 Treaty",
    "Dax Fell's counter is legally sound. The resolution is dated six months ago — "
    "when he arrived. He's been preparing this response since before Vespar moved. "
    "Which means he knew exactly what they were going to do. How? "
    "Brother Edmar is pulling the original treaty. There may be a third provision "
    "neither side cited. Osric got very quiet when we mentioned that.")

db.post_journal(SLUG, 4, "Session 4 — The Underbrick",
    "Attacking a Grace-Sworn patrol is a line. They crossed it. "
    "The captured cutout says The Loom sold the same weapons to two clients. "
    "Both delegations? That's either the most cynical move I've heard "
    "or The Loom is trying to start a fight between them and profit from the chaos. "
    "We need to reach the cache before either delegation realizes they both paid for it.")

print(f"\nDone. Campaign '{SLUG}' seeded at {CAMP_DIR}")
print("To deploy to Pi:  rsync -av campaigns/paladins_grace/ simonhans@raspberrypi:/mnt/serverdrive/coding/rippleforge/campaigns/paladins_grace/")
