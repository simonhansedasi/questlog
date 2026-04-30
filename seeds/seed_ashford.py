"""Seed script: The Ashcroft Vein — RippleForge's flagship TTRPG demo.

A frontier mining town extorted by a gang with deeper backing than anyone admits.
Sessions 1-5, party at level 4. Used as DEMO_SOURCE in app.py.

Run:  python seed_ashford.py
"""
import sys, json, secrets, shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from src import data as db

SLUG = "ashford"
CAMPAIGNS = Path(__file__).parent / "campaigns"
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
    "name": "The Ashcroft Vein",
    "system": "Any system",
    "owner": "demo",
    "dm_pin": "demo",
    "share_token": secrets.token_urlsafe(16),
    "demo": True,
    "public": True,
    "mode": "ttrpg",
    "observer_name": "The Party",
    "party_name": "The Vein Company",
    "description": "Session 5 — The Ironmasks are broken. Greystone Keep awaits.",
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
          event_type=None, visibility="public", ripple=False, actor_id=None, actor_type=None):
    evt = db.log_npc(SLUG, npc_id, session, note, polarity=polarity,
                     intensity=intensity, event_type=event_type, visibility=visibility,
                     actor_id=actor_id, actor_type=actor_type)
    if ripple and polarity in ("positive", "negative"):
        db.apply_ripple(SLUG, npc_id, "npc", session, note, polarity, intensity, event_type, visibility)
    return evt


def log_f(faction_id, session, note, polarity=None, intensity=1,
          event_type=None, visibility="public", ripple=False, actor_id=None, actor_type=None):
    evt = db.log_faction(SLUG, faction_id, session, note, polarity=polarity,
                         intensity=intensity, event_type=event_type, visibility=visibility,
                         actor_id=actor_id, actor_type=actor_type)
    if ripple and polarity in ("positive", "negative"):
        db.apply_ripple(SLUG, faction_id, "faction", session, note, polarity, intensity, event_type, visibility)
    return evt


# ── Party (level 4 — mid-campaign) ─────────────────────────────────────────────
db.add_character(SLUG, "Calder Voss", "Human", "Fighter", 4,
                 notes="Former Greywood Ranger scout. Knows the Greywood better than anyone. Carries a grudge against the Ironmasks that predates the party.")
db.add_character(SLUG, "Wren Ashvale", "Half-Elf", "Rogue", 4,
                 notes="Grew up in Ashford. Her father worked the Vein. The Ironmask toll drove him out. She came back to finish it.")
db.add_character(SLUG, "Sable", "Tiefling", "Warlock", 4,
                 notes="Wandering contractor. Does not explain who her patron is. Deeply effective in a crisis.")
db.add_character(SLUG, "Lira of the Dawn", "Human", "Cleric", 4,
                 notes="Travelling healer who stopped in Ashford for one night and hasn't left. She knows what 'the Factor' means but hasn't said how.")
db.add_character(SLUG, "Osric Fynt", "Gnome", "Artificer", 4,
                 notes="Trade Compact assessor who went rogue after discovering what the Compact actually knew about the Ironmasks.")
print("  Party seeded")

# ── Factions ───────────────────────────────────────────────────────────────────
factions = [
    ("The Ironmasks", "hostile", False,
     "A bandit gang turned extortion syndicate controlling Ashford's trade roads. "
     "They tax every merchant entering town, take a cut of mine payroll, and have beaten "
     "three citizens badly enough to be examples. Their boss is known as The Ledger. "
     "Their muscle comes from somewhere further up the chain."),

    ("The Trade Compact", "neutral", False,
     "The regional commercial authority that officially regulates trade in and out of Ashford. "
     "They have been paying the Ironmask toll rather than escalating. "
     "Someone in the Compact is more deeply entangled than they've admitted. "
     "Edda Sorn is their local agent — she suspects the entanglement too."),

    ("Greywood Rangers", "ally", False,
     "The regional militia patrolling the Greywood and the roads to and from Ashford. "
     "They are stretched thin — three rangers for thirty miles of road. "
     "Farlan Dusk (retired) and Sister Veyne (active) represent what they can spare."),

    ("Stonebreaker Clan", "neutral", False,
     "Orc clan occupying Greystone Keep in the hills north of Ashford. "
     "The keep controls the upper vein entrance. Warchief Durnak has no love for the "
     "Ironmasks but also no reason to help outsiders unless properly approached."),

    ("Emerald Circle", "neutral", False,
     "A druidic order with ancient claim to the Greywood. They tolerate the mine because "
     "the Ashcroft Vein is below the root line. They will not tolerate the expansion "
     "the Ironmasks have been forcing on the miners."),

    ("The Shadow Wing", "hostile", True,
     "The organization above the Ironmasks. They move rare materials out of the Vein "
     "through an unofficial channel — bypassing the Trade Compact entirely. "
     "The Factor (Corvin Ashale) coordinates them. (DM-only)"),
]

F = {}
for name, rel, hidden, desc in factions:
    db.add_faction(SLUG, name, rel, desc, hidden=hidden)
    factions_data = db._load(SLUG, "world/factions.json")
    F[name] = factions_data["factions"][-1]["id"]
    print(f"  Faction: {name}")

# ── NPCs ────────────────────────────────────────────────────────────────────────
npcs_to_add = [
    ("Edda Sorn", "Trade Compact agent — local liaison, probable whistleblower",
     "ally", False, [F["The Trade Compact"]],
     "She was sent to Ashford to oversee Compact interests and immediately started "
     "noticing things she wasn't supposed to notice. She has been quietly documenting "
     "the discrepancy between declared mine output and actual shipments for four months. "
     "She approached the party because she doesn't know who else to trust."),

    ("Bram Ketterly", "Dwarf freight merchant — prisoner at Greystone Keep",
     "ally", False, [F["The Trade Compact"]],
     "He refused to pay the Ironmask toll three months ago on principle. "
     "They took his wagon, his cargo, and him. He is currently being held at "
     "Greystone Keep as a 'debt collection.' He has information about the "
     "Shadow Wing supply route that he doesn't know he has."),

    ("Governor Harwick Denn", "Appointed Governor of Ashford — compromised",
     "neutral", False, [F["The Trade Compact"]],
     "He was appointed by the Trade Compact to run Ashford. He has been quietly "
     "paying the Ironmask toll from civic funds and recording it as road maintenance. "
     "He knows exactly what he has done and spends his evenings convincing himself "
     "it was the only reasonable option. He is not wrong that he had no other options. "
     "He is wrong that it ends there."),

    ("Nessa Crane", "Proprietor — Ashford Trading Company",
     "neutral", False, [F["The Trade Compact"]],
     "She runs the largest trading post in Ashford. She has been paying the toll "
     "and passing the cost to her suppliers. Her suppliers are starting to push back. "
     "She wants the Ironmasks gone but is not willing to be seen working against them "
     "until it is safe to do so. She is watching the party's progress carefully."),

    ("Orvyn Thatch", "Proprietor — Thatch's General Store",
     "ally", False, [],
     "The town's most reliable gossip. He knows everything that moves through Ashford "
     "because he sells everything to everyone. He has been quietly giving discounts "
     "to people the Ironmasks have victimized, which has strained his margins. "
     "He is the party's best source of local intelligence."),

    ("Petra Holt", "Proprietor — Ashford Miners' Registry",
     "ally", False, [],
     "She registers every miner, tracks shift schedules, and maintains the payroll ledger "
     "for the Vein. She has noticed that payroll deductions for 'safety equipment' "
     "don't correspond to any equipment she can see. The Ironmasks are running a "
     "payroll skim through the Registry. She has the evidence."),

    ("Farlan Dusk", "Retired Greywood Ranger scout",
     "ally", False, [F["Greywood Rangers"]],
     "Retired on a hip injury, living in Ashford for three years. He still knows "
     "the Greywood better than anyone active. He has been watching the Ironmask "
     "supply routes out of old habit and has a very good idea of where they go. "
     "He will help if asked directly. He doesn't volunteer."),

    ("Sister Veyne", "Active Greywood Ranger — cleric attached to the patrol",
     "ally", False, [F["Greywood Rangers"]],
     "The only active Ranger currently in Ashford. She has been filing incident "
     "reports about the Ironmasks for two months. The reports go nowhere because "
     "they go to the Governor. She has started filing them with the Trade Compact "
     "instead, which is how Edda Sorn found out about the payroll skim."),

    ("Maren Vosk", "The Ledger — Ironmask boss",
     "hostile", False, [F["The Ironmasks"]],
     "She runs the Ironmask operation in Ashford with ledger-perfect precision. "
     "Every toll, every payroll skim, every protection payment is documented. "
     "She does not enjoy violence but authorizes it without hesitation when the "
     "numbers require it. She knows exactly who the Factor is and considers "
     "herself insulated from any consequences. She is wrong."),

    ("Corvin Ashale", "The Factor — Shadow Wing coordinator",
     "hostile", True, [F["The Shadow Wing"]],
     "He presents as a successful independent merchant with a modest warehouse near "
     "the mine entrance. He is the Shadow Wing's operational coordinator for the "
     "Ashcroft Vein: he decides what gets skimmed from the mine output, "
     "routes it through the Ironmasks, and ships it out via a tunnel entrance "
     "the Trade Compact doesn't know exists. (DM-only)"),

    ("Thane Bergrak", "Woodsman — Emerald Circle liaison",
     "neutral", False, [F["Emerald Circle"]],
     "He lives in the Greywood and comes to Ashford once a week to sell timber rights "
     "and deliver the Circle's opinions on what the miners are doing wrong. "
     "His opinions are accurate but his delivery is confrontational. "
     "He knows a Circle-maintained passage through the Greywood that avoids the roads."),

    ("Warchief Durnak", "Stonebreaker Clan — holds Greystone Keep",
     "neutral", False, [F["Stonebreaker Clan"]],
     "His clan has held Greystone Keep for three generations. They have no interest "
     "in Ashford's problems but the Ironmasks have been using the Keep's outer "
     "courtyard as a holding area without asking. He has not acted because they "
     "haven't been worth the trouble. That calculation is changing."),

    ("The Pale Widow", "Ghost — Ruins of Coldwater",
     "neutral", False, [],
     "A spirit haunting the Coldwater ruins two miles from Ashford. The miners "
     "avoid her on superstition. The Ironmasks learned to avoid her because three "
     "of their scouts went into Coldwater and didn't come back. "
     "She has been watching the Vein for longer than the town has existed."),

    ("Serev", "Factor's courier — Shadow Wing operative",
     "hostile", True, [F["The Shadow Wing"]],
     "Corvin Ashale's main courier between the Factor's operation and the Shadow Wing's "
     "distribution network. Goes by multiple names. Was seen near the Registry "
     "two nights before the payroll skim started. (DM-only)"),
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
    "The Ironmask Toll",
    "Ashford trade roads", "supply", "all",
    "-25%",
    description="Every merchant entering Ashford pays the Ironmask toll — a flat percentage "
    "on declared cargo value. Merchants underreport. The Ironmasks know it and raise the rate. "
    "Three merchants have stopped making the Ashford run entirely. "
    "The town's supply margins are thin and getting thinner.",
    hidden=False)

db.add_condition(SLUG,
    "Vein Instability",
    "Ashcroft Vein (lower shafts)", "danger", "military",
    "structural risk",
    description="The Ironmasks have been forcing miners to work lower shafts without "
    "adequate timbering to maximize output. The Guild engineer's report from six weeks "
    "ago flagged three sections as unsafe. The report was suppressed. "
    "Miners are refusing the lower shaft shifts. The Ironmasks are threatening them.",
    hidden=False)

db.add_condition(SLUG,
    "The Factor's Net",
    "Ashford (concealed)", "access", "all",
    "covert control",
    description="Someone above Maren Vosk is coordinating the Ironmask operation as cover "
    "for a parallel extraction racket — skimming refined ore from the Vein before "
    "it reaches the Trade Compact's scales. The skim is invisible in the Registry "
    "because it leaves through a tunnel the Compact doesn't know about. (DM-only)",
    hidden=True)

conditions_data = db._load(SLUG, "world/conditions.json")
C = {c["name"]: c["id"] for c in conditions_data["conditions"]}
print(f"  Conditions: {list(C.keys())}")

# ── Quests ─────────────────────────────────────────────────────────────────────
db.add_quest(SLUG,
    "Rescue Bram Ketterly",
    "Bram Ketterly refused to pay the toll and ended up in an Ironmask cell in "
    "Greystone Keep. He's been there three months. His family thinks he's dead. "
    "The Stonebreaker Clan controls the Keep's outer walls. Getting to Bram without "
    "starting a war with Durnak's clan requires either diplomacy or creativity.",
    hidden=False)

db.add_quest(SLUG,
    "Secure the Old Vein",
    "The lower Ashcroft shafts are unsafe and the Ironmasks are forcing miners into them "
    "anyway. Stopping this requires either breaking the Ironmasks' grip on the Registry "
    "or getting the unsafe-shaft report to someone who can act on it — "
    "which means finding someone in the Trade Compact who isn't compromised.",
    hidden=False)

db.add_quest(SLUG,
    "Drive Out the Ironmasks",
    "Maren Vosk runs a tight operation. The Ironmasks are entrenched, connected, and "
    "violent enough to deter individual resistance. Breaking them requires evidence "
    "that implicates whoever is protecting them at the Compact level — "
    "without which any victory against the street operation just creates a vacancy.",
    hidden=False)

db.add_quest(SLUG,
    "The Warden's Archive",
    "The Coldwater ruins were once a garrison post. The Pale Widow guards the archive. "
    "Someone sent a Shadow Wing operative to the ruins recently — they didn't come back. "
    "The archive may contain records about the tunnels below the Vein. "
    "Approaching the Pale Widow requires respect, not force.",
    hidden=False)

db.add_quest(SLUG,
    "The Factor",
    "Maren Vosk answers to someone. Edda Sorn's shipping discrepancy records "
    "point to a warehouse near the Vein entrance that moves more weight than its "
    "declared cargo accounts for. Find the Factor. Find the tunnel. "
    "Find out who the Shadow Wing is selling to. This is the real problem.",
    hidden=True)

print(f"  Quests seeded")

# ── Relations ──────────────────────────────────────────────────────────────────

# Dual-axis: formal vs personal
add_dual_rel("npc", N["Governor Harwick Denn"], N["Edda Sorn"],  "npc",
             formal_relation="ally",  personal_relation="rival",  weight=0.75)
add_dual_rel("npc", N["Edda Sorn"],             N["Governor Harwick Denn"], "npc",
             formal_relation="ally",  personal_relation="rival",  weight=0.75)
add_dual_rel("npc", N["Edda Sorn"],             N["Maren Vosk"], "npc",
             formal_relation="neutral", personal_relation="rival", weight=0.8, dm_only=True)
add_dual_rel("npc", N["Maren Vosk"],            N["Edda Sorn"],  "npc",
             formal_relation="neutral", personal_relation="rival", weight=0.8, dm_only=True)
add_dual_rel("npc", N["Farlan Dusk"],           N["Sister Veyne"], "npc",
             formal_relation="ally",  personal_relation="rival",  weight=0.7)
add_dual_rel("npc", N["Sister Veyne"],          N["Farlan Dusk"],  "npc",
             formal_relation="ally",  personal_relation="rival",  weight=0.7)

# Clean alliances / rivalries
add_rel("npc", N["Edda Sorn"],          N["Bram Ketterly"],      "npc", "ally",   0.85)
add_rel("npc", N["Bram Ketterly"],      N["Edda Sorn"],          "npc", "ally",   0.85)
add_rel("npc", N["Maren Vosk"],         N["Corvin Ashale"],      "npc", "ally",   0.9,  dm_only=True)
add_rel("npc", N["Corvin Ashale"],      N["Maren Vosk"],         "npc", "ally",   0.9,  dm_only=True)
add_rel("npc", N["Corvin Ashale"],      N["Serev"],              "npc", "ally",   1.0,  dm_only=True)
add_rel("npc", N["Farlan Dusk"],        N["Thane Bergrak"],      "npc", "ally",   0.75)
add_rel("npc", N["Thane Bergrak"],      N["Farlan Dusk"],        "npc", "ally",   0.75)
add_rel("npc", N["Petra Holt"],         N["Sister Veyne"],       "npc", "ally",   0.8)
add_rel("npc", N["Sister Veyne"],       N["Petra Holt"],         "npc", "ally",   0.8)
add_rel("npc", N["Maren Vosk"],         N["Governor Harwick Denn"], "npc", "ally", 0.85)
add_rel("npc", N["Governor Harwick Denn"], N["Maren Vosk"],     "npc", "ally",   0.85)
add_rel("npc", N["Warchief Durnak"],    N["Maren Vosk"],         "npc", "rival",  0.7)

# Faction relations
add_rel("faction", F["The Ironmasks"],    F["The Trade Compact"],  "faction", "ally",   0.7)
add_rel("faction", F["The Trade Compact"],F["The Ironmasks"],      "faction", "ally",   0.5)
add_rel("faction", F["The Ironmasks"],    F["Greywood Rangers"],   "faction", "rival",  0.9)
add_rel("faction", F["Greywood Rangers"], F["The Ironmasks"],      "faction", "rival",  0.9)
add_rel("faction", F["The Ironmasks"],    F["Stonebreaker Clan"],  "faction", "neutral", 0.5)
add_rel("faction", F["Greywood Rangers"], F["Emerald Circle"],     "faction", "ally",   0.75)
add_rel("faction", F["Emerald Circle"],   F["Greywood Rangers"],   "faction", "ally",   0.75)
add_rel("faction", F["The Shadow Wing"],  F["The Ironmasks"],      "faction", "ally",   1.0,  dm_only=True)
add_rel("faction", F["The Shadow Wing"],  F["The Trade Compact"],  "faction", "ally",   0.6,  dm_only=True)

print("  Relations set")

# ── Event Log ──────────────────────────────────────────────────────────────────

# Session 1: Arrival in Ashford
log_n(N["Orvyn Thatch"], 1,
      "The party arrives in Ashford and stops at Thatch's General Store. "
      "Orvyn gives them a full picture without being asked: the toll, Bram's capture, "
      "the Registry situation. He's been waiting for someone to tell.",
      polarity="positive", intensity=1, event_type="dialogue")

log_n(N["Maren Vosk"], 1,
      "The Ledger's collectors approach the party within two hours of their arrival "
      "to assess whether they are merchants subject to the toll. "
      "They back down when challenged but take notes.",
      polarity="negative", intensity=1, event_type="other")

log_f(F["The Ironmasks"], 1,
      "The Ironmasks have expanded their toll operations to cover the northern road "
      "as well as the eastern approach. Farlan Dusk counted thirty-two collectors "
      "working the roads in the past week — up from eighteen a month ago.",
      polarity="negative", intensity=2, event_type="other", ripple=True)

log_n(N["Edda Sorn"], 1,
      "Edda Sorn contacts the party privately at the inn. She lays out her shipping "
      "discrepancy records: declared output versus actual weight shipped, month by month. "
      "The gap has been growing for eight months. She needs someone to take this further.",
      polarity="positive", intensity=2, event_type="dialogue")

# Session 2: The Registry and the Keep
log_n(N["Petra Holt"], 2,
      "Petra Holt shows the party the Registry payroll records. The 'safety equipment' "
      "deductions are real deductions against real miner wages. "
      "Twelve percent of the payroll is being skimmed through a fictitious expense. "
      "She has a complete ledger copy hidden under the Registry floor.",
      polarity="positive", intensity=2, event_type="discovery")

log_n(N["Governor Harwick Denn"], 2,
      "The party confronts Governor Denn with Petra's evidence. "
      "He does not deny it. He says: 'What exactly did you expect me to do?' "
      "He agrees to stop the civic fund payments going forward. He does nothing else.",
      polarity="negative", intensity=1, event_type="dialogue")

log_n(N["Warchief Durnak"], 2,
      "The party approaches Greystone Keep and requests parley. "
      "Durnak meets them at the gate. He is not hostile but he is not friendly. "
      "He will release Bram if the party removes the Ironmask presence from his outer courtyard. "
      "He gives them three days.",
      polarity="neutral", intensity=1, event_type="dialogue")

# Session 3: Taking the Courtyard
log_f(F["The Ironmasks"], 3,
      "The party drives the Ironmask holding operation out of the Keep's outer courtyard. "
      "Six Ironmasks subdued. Two escaped toward Ashford. Durnak watches from the wall "
      "without interfering.",
      polarity="negative", intensity=3, event_type="combat",
      ripple=True)

log_n(N["Bram Ketterly"], 3,
      "Bram Ketterly is released from the Keep's storage cellar, underfed but uninjured. "
      "He remembers faces. He remembers routes. He saw a Shadow Wing courier twice "
      "without knowing what they were. He will tell the party everything.",
      polarity="positive", intensity=2, event_type="other")

log_n(N["Maren Vosk"], 3,
      "The Ledger responds to the Keep incident by doubling Ironmask patrols in town "
      "and imposing a 'security surcharge' on all merchants. She is escalating, not retreating.",
      polarity="negative", intensity=2, event_type="politics", ripple=True)

db.apply_ripple(SLUG, N["Maren Vosk"], "npc", 3,
                "Ironmask escalation — doubled patrols, new surcharge on merchants.",
                "negative", 2, "politics", "public")

# Session 4: The Mine and the Pale Widow
log_n(N["Thane Bergrak"], 4,
      "Thane Bergrak approaches the party on the road to Coldwater. "
      "He knows about the unsafe shaft situation. The Emerald Circle has been "
      "monitoring the mine's structural deterioration. He shows them the Circle's "
      "own survey: three shafts will fail within sixty days. Not might. Will.",
      polarity="positive", intensity=2, event_type="dialogue")

log_n(N["The Pale Widow"], 4,
      "The party approaches Coldwater ruins respectfully. The Pale Widow does not attack. "
      "She shows them the garrison archive: maps of a tunnel system predating the mine, "
      "running beneath the Vein. One tunnel connects to an exit point near Corvin Ashale's warehouse.",
      polarity="positive", intensity=3, event_type="discovery")

log_n(N["Corvin Ashale"], 4,
      "Watching the Coldwater tunnel maps, the party realizes Corvin Ashale's warehouse "
      "sits directly above the old tunnel exit. The shipping weight discrepancy finally makes sense. "
      "He's not moving cargo out. He's moving it down.",
      polarity="negative", intensity=3, event_type="discovery",
      visibility="dm_only")

log_f(F["The Shadow Wing"], 4,
      "The Shadow Wing moves refined ore samples through the tunnel system twice a week. "
      "The operation has been running for eight months — exactly as long as the "
      "shipping discrepancy in Edda's records.",
      polarity="negative", intensity=2, event_type="other",
      visibility="dm_only", ripple=True)

db.log_condition(SLUG, C["Vein Instability"], 4,
                 "Three shafts confirmed as critical per Emerald Circle survey. "
                 "60-day window before structural failure in lower sections.",
                 polarity="negative", intensity=2)

# Session 5: The Ironmasks Break
log_n(N["Sister Veyne"], 5,
      "Sister Veyne coordinates a simultaneous ranger action on three Ironmask "
      "collection points. With the party holding the road north, the operation "
      "lands cleanly. Seventeen Ironmasks captured. Maren Vosk's records seized.",
      polarity="positive", intensity=3, event_type="combat")

log_n(N["Maren Vosk"], 5,
      "Maren Vosk is captured in the Registry during the raid. Her ledgers are complete. "
      "They name Corvin Ashale by initials — 'CA' — in seventeen separate entries "
      "as the recipient of skim payments. She will not confirm the name but she won't deny it.",
      polarity="negative", intensity=3, event_type="combat",
      actor_id=N["Sister Veyne"], actor_type="npc")

db.apply_ripple(SLUG, N["Maren Vosk"], "npc", 5,
                "The Ledger captured — Ironmask operation collapses.",
                "negative", 3, "combat", "public")

log_f(F["The Ironmasks"], 5,
      "The Ironmask street operation in Ashford is broken. The toll is ended. "
      "Remaining Ironmasks have scattered into the Greywood. "
      "Corvin Ashale's warehouse is locked from the inside.",
      polarity="positive", intensity=3, event_type="other", ripple=True)

log_n(N["Corvin Ashale"], 5,
      "Corvin Ashale barricades himself in his warehouse when the Ironmasks fall. "
      "He has already sent a coded message via Serev. The Shadow Wing knows the operation "
      "is burned. He is waiting for extraction.",
      polarity="negative", intensity=2, event_type="other",
      visibility="dm_only")

log_n(N["Edda Sorn"], 5,
      "Edda Sorn presents the shipping discrepancy records to the Trade Compact "
      "regional office, backed by Maren Vosk's seized ledgers. "
      "The Compact has opened a formal investigation. The Governor has gone quiet. "
      "The Factor hasn't been found yet.",
      polarity="positive", intensity=2, event_type="politics")

db.log_condition(SLUG, C["The Ironmask Toll"], 5,
                 "Ironmask street operation broken; toll collection ended. "
                 "Roads are open. Supply margins will recover in 2-3 weeks.",
                 polarity="positive", intensity=3)

print("  Event log complete")

# ── Journal ────────────────────────────────────────────────────────────────────
db.post_journal(SLUG, 1, "Session 1 — Ashford",
    "First night. Orvyn at the store gave us everything: the toll, Bram, the Registry, "
    "the silence from the Governor's office. Then Edda Sorn found us at the inn with "
    "her ledgers. She's been sitting on this for four months waiting for someone who "
    "could do something with it. The Compact toll discrepancy alone is worth pursuing. "
    "The question is how far up it goes.")

db.post_journal(SLUG, 3, "Session 3 — Greystone Keep",
    "Bram is out. Durnak kept his word the moment we cleared the courtyard — "
    "no ceremony, no renegotiation, just opened the cellar. Bram's in decent shape "
    "for three months in a root cellar. He saw a courier twice with Shadow Wing "
    "markings. He didn't know what they were but he described the route. "
    "That matches nothing we've seen on any road map. It goes underground.")

db.post_journal(SLUG, 4, "Session 4 — Coldwater",
    "The Pale Widow showed us the garrison maps. Nobody's been in that archive since "
    "the garrison was decommissioned — you can tell by the dust on everything except "
    "the tunnel entrance records, which are clean. Someone was here recently. "
    "The tunnel exits under Corvin Ashale's warehouse. He's not moving cargo. "
    "He's moving the mine's output before it ever reaches the Compact scales. "
    "This is the real operation. The Ironmasks were always just the noise.")

db.post_journal(SLUG, 5, "Session 5 — The Ledger",
    "The toll is done. The roads are open. Maren Vosk's in custody with her own ledgers "
    "as evidence and 'CA' in seventeen entries. She won't say his name out loud. "
    "Corvin Ashale is locked in his warehouse waiting for extraction. "
    "Serev got a message out — we don't know to who. "
    "The Ironmasks are broken but the Factor is still breathing and the Shadow Wing "
    "knows we're here. Greystone Keep is next.")

print(f"\nDone. Campaign '{SLUG}' seeded at {CAMP_DIR}")
print("To deploy to Pi:  rsync -av campaigns/ashford/ simonhans@raspberrypi:/mnt/serverdrive/coding/rippleforge/campaigns/ashford/")
print("Remember to update DEMO_SOURCE in app.py to CAMPAIGNS / 'ashford' if using as demo.")
