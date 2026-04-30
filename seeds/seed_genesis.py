"""Seed script: Book of Genesis — Hebrew Bible, from Creation to Joseph in Egypt.

Showcases: dual-axis edges (Jacob/Esau, Sarah/Hagar, Joseph/brothers),
world conditions (East of Eden, The Flood, The Great Famine), fiction mode,
observer_name, story arcs.

Run:  python seed_genesis.py
"""
import sys, json, secrets, shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from src import data as db

SLUG = "genesis"
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
    "name": "Book of Genesis",
    "slug": "genesis",
    "system": "Sacred Text — Hebrew Bible",
    "owner": "demo",
    "dm_pin": "1234",
    "share_token": secrets.token_urlsafe(16),
    "demo": True,
    "public": True,
    "mode": "fiction",
    "observer_name": "The Reader",
    "terminology": {
        "npc": "Character", "npcs": "Characters",
        "session": "Chapter", "sessions": "Chapters",
        "dm": "Author", "party": "Reader",
        "faction": "House", "factions": "Houses",
        "cast_label": "Cast",
        "notes_label": "Chapter Notes",
        "session_tools_label": "Write & Parse",
        "parse_cta": "Extract Story Events",
        "recap_cta": "Generate Chapter Summary",
        "quick_log_label": "Quick Event",
        "dm_controls": "Author Controls",
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


# ── Factions ───────────────────────────────────────────────────────────────────
factions = [
    ("The Heavenly Court", "ally", True,
     "YHWH and the divine assembly — angels, messengers, the sons of God. "
     "They execute God's will: announce births, destroy cities, wrestle with patriarchs, "
     "guard Eden. In Genesis, God is the primary actor, not an absent observer. "
     "Every human story unfolds within this frame."),

    ("House of Israel", "ally", False,
     "The covenant family: Abraham, Isaac, Jacob, and the twelve sons who become "
     "the twelve tribes. Not yet a nation — a family, a promise, a genealogy God "
     "has staked his reputation on. Their survival across famine and fratricide "
     "is the spine of the narrative."),

    ("The Nations", "neutral", False,
     "Egypt, Canaan, and all the peoples surrounding the covenant family. "
     "They are not enemies by default — Pharaoh shelters Abraham, Melchizedek blesses him, "
     "and the Canaanites trade with Isaac. The covenant does not yet mean conquest. "
     "That comes later."),
]

F = {}
for name, rel, hidden, desc in factions:
    db.add_faction(SLUG, name, rel, desc, hidden=hidden)
    factions_data = db._load(SLUG, "world/factions.json")
    F[name] = factions_data["factions"][-1]["id"]
    print(f"  Faction: {name}")

# ── NPCs ────────────────────────────────────────────────────────────────────────
npcs_to_add = [
    # The Primordial Arc
    ("The LORD", "Creator and Covenant-Maker",
     "ally", True, [F["The Heavenly Court"]],
     "YHWH acts directly in Genesis: creating, judging, promising, relenting. "
     "He makes covenants he then tests. He destroys the world and regrets it. "
     "He chooses Jacob over Esau before either is born. He wrestles with Jacob "
     "in the dark. He is not distant or symbolic — he is present and surprising."),

    ("Adam", "The First Man, keeper of the garden",
     "neutral", False, [F["House of Israel"]],
     "Made from dust, given breath, placed in a garden with one prohibition. "
     "He names every creature. He receives the woman and joins her in the one "
     "thing they were told not to do. He blames her when caught. He is every man."),

    ("Eve", "The First Woman, mother of all living",
     "neutral", False, [F["House of Israel"]],
     "She hears the serpent's argument and finds it compelling — the fruit will "
     "make them wise, like God. She eats. She gives to Adam. She names herself "
     "Eve, 'mother of all living,' after the curse. The naming is an act of defiance "
     "and hope in the same breath."),

    # Cain and Abel
    ("Cain", "The First Murderer, keeper of the earth",
     "negative", False, [F["House of Israel"]],
     "He offers the fruits of the ground; Abel offers fat portions of his flock. "
     "God regards Abel's offering and not his. The text never explains why. Cain's "
     "rage at the injustice is understandable. What he does with it is not. "
     "He is marked but not destroyed — God protects the first murderer."),

    ("Abel", "Shepherd and first martyr",
     "ally", False, [F["House of Israel"]],
     "He exists in the story for three verses and then he is dead. His blood "
     "cries from the ground. He has no voice in the text but God hears him. "
     "He is the first of many younger brothers the story loves better."),

    # The Flood
    ("Noah", "Righteous survivor, builder of the ark",
     "ally", False, [F["House of Israel"]],
     "God finds one righteous man in a generation given to violence, and tells "
     "him to build a boat. Noah does exactly what he is told, nothing more. "
     "After the flood he plants a vineyard, drinks too much, and curses his son Ham. "
     "The first act after survival is often embarrassing."),

    # Abraham cycle
    ("Abraham", "Father of Nations, friend of God",
     "ally", False, [F["House of Israel"]],
     "He leaves everything at seventy-five on the strength of a promise. "
     "He passes his wife off as his sister twice to save his own skin. "
     "He laughs when God promises a son at ninety-nine. He rises at dawn to "
     "take Isaac to Moriah without a word to Sarah. He is the central figure "
     "of Genesis: brave, flawed, chosen."),

    ("Sarah", "Matriarch, mother of the promise",
     "ally", False, [F["House of Israel"]],
     "She laughs at the angel's announcement — a ninety-year-old woman bearing a son. "
     "She laughed, God notes. She says she didn't laugh. God says she did. "
     "The argument is never resolved. She named her son Isaac: laughter. "
     "She is fiercer and harder than Abraham in protecting her line."),

    ("Hagar", "Egyptian servant, mother of Ishmael",
     "neutral", False, [F["The Nations"]],
     "Sarah gives her to Abraham as a surrogate and then treats her with cruelty "
     "when Hagar grows proud of her pregnancy. She flees into the desert. "
     "An angel finds her at a spring. God sees her — the text emphasizes this: "
     "she is the only person in the Bible to name God. She calls him El-roi: "
     "the God who sees me."),

    ("Ishmael", "Son of Abraham and Hagar, father of twelve princes",
     "neutral", False, [F["The Nations"]],
     "The first son, the not-chosen one. He and his mother are sent into the "
     "desert with bread and a skin of water when Isaac is weaned. The water runs "
     "out. Hagar sets the boy under a bush and walks away so she won't watch him "
     "die. God hears the boy crying. He will be a great nation too — just not "
     "this story's nation."),

    ("Melchizedek", "Priest-King of Salem, man of mystery",
     "ally", False, [F["The Nations"]],
     "He appears from nowhere to bless Abraham after battle, brings bread and wine, "
     "and disappears. He is priest of El-Elyon — God Most High — before Abraham "
     "ever hears that name. He has no genealogy in the text, no beginning or end. "
     "He becomes a type: priesthood outside the bloodline."),

    ("Lot", "Abraham's nephew, survivor of Sodom",
     "neutral", False, [F["House of Israel"]],
     "He chooses the well-watered plain of Jordan and pitches his tent near Sodom. "
     "When the city is destroyed he escapes with his daughters. His wife looks back "
     "and becomes a pillar of salt. His daughters get him drunk on successive nights "
     "and conceive Moab and Ammon. Lot is the character to whom things happen."),

    ("Isaac", "Son of Promise, quiet patriarch",
     "ally", False, [F["House of Israel"]],
     "He is bound on the altar at Moriah and unmade. He is the passive center "
     "of his own story: the sacrifice that doesn't happen. He grows up, marries "
     "Rebekah, fathers twins he cannot see clearly — literally or otherwise. "
     "He blesses Jacob thinking he is Esau. He is deceived by his own family."),

    ("Rebekah", "Matriarch, planner of the deception",
     "ally", False, [F["House of Israel"]],
     "She waters ten camels unasked when Abraham's servant arrives at her family's well — "
     "an act of extraordinary generosity. She leaves everything to marry a stranger. "
     "She hears the oracle: the elder will serve the younger. She makes it happen, "
     "using her husband's blindness. She never sees Jacob again after she saves him."),

    # Jacob cycle — the heart of Genesis
    ("Jacob", "Patriarch of Israel, heel-grabber and wrestler",
     "ally", False, [F["House of Israel"]],
     "He is born grabbing his twin's heel. He buys Esau's birthright for stew. "
     "He steals Isaac's blessing. He flees, dreams of a ladder, bargains with God. "
     "He works seven years for Rachel and is given Leah instead. He works seven "
     "more. He wrestles God at the ford of Jabbok and refuses to let go. "
     "His name becomes Israel. He is the ancestor of everyone."),

    ("Esau", "The elder twin, man of the field",
     "neutral", False, [F["House of Israel"]],
     "He sells his birthright for a bowl of red stew because he is starving "
     "and cannot see past the moment. He weeps when he finds the blessing stolen "
     "— a sound that tears the reader in two. He forgives Jacob decades later "
     "and runs to meet him. His mercy is greater than his loss."),

    ("Laban", "Jacob's uncle and adversary",
     "negative", False, [F["The Nations"]],
     "He substitutes Leah for Rachel on the wedding night and explains it away "
     "with local custom. He changes Jacob's wages ten times over fourteen years. "
     "He pursues Jacob when he finally leaves and finds his household gods missing. "
     "He is the mirror Jacob needed: he meets a manipulator who out-manipulates him."),

    ("Rachel", "Beloved wife of Jacob",
     "ally", False, [F["House of Israel"]],
     "Jacob sees her at the well and weeps. He works seven years for her. "
     "He works seven more. She steals her father's household gods when they leave — "
     "the text never explains why. She dies giving birth to Benjamin, naming him "
     "Son of My Sorrow with her last breath. Jacob renames him Son of My Right Hand."),

    ("Leah", "Elder wife of Jacob, unseen and fertile",
     "neutral", False, [F["House of Israel"]],
     "She was substituted for her sister. The text says Jacob loved Rachel more. "
     "God sees Leah's unloved condition and opens her womb. She names her sons "
     "with prayers: Reuben — God has seen my affliction. Simeon — God heard "
     "I am unloved. Her naming of her children is a theology of pain acknowledged."),

    # Joseph cycle
    ("Joseph", "Dreamer and Vizier of Egypt",
     "ally", False, [F["House of Israel"]],
     "Jacob's favorite son, given a coat of many colors. His dreams say his "
     "brothers will bow to him. His brothers throw him in a pit and sell him to "
     "Ishmaelite traders for twenty pieces of silver. In Egypt he rises to the top "
     "of every system he enters — Potiphar's house, the prison, Pharaoh's court. "
     "He weeps when he finally sees his brothers again. He forgives them."),

    ("Judah", "Fourth son of Jacob, the unexpected leader",
     "neutral", False, [F["House of Israel"]],
     "He suggests selling Joseph instead of killing him. He fails his daughter-in-law "
     "Tamar. He stands surety for Benjamin before Jacob. In Egypt, when Pharaoh's "
     "vizier threatens to keep Benjamin, it is Judah — not Reuben — who steps forward "
     "and offers himself as a substitute. That speech changes Joseph. The line of Judah "
     "becomes the royal line."),

    ("Pharaoh", "King of Egypt, Joseph's patron",
     "neutral", False, [F["The Nations"]],
     "He dreams of seven fat cows and seven lean cows, and Joseph interprets it: "
     "seven years of plenty, then seven years of famine. He makes a Hebrew slave "
     "and prisoner second-in-command of all Egypt before breakfast. He is "
     "pragmatic, powerful, and — in Genesis — not yet an enemy."),
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
    "East of Eden",
    "The World", "access", "all",
    {"type": "blocked"},
    description="The garden is closed. Cherubim with a flaming sword guard the way back. "
    "Adam and Eve work the ground by the sweat of their faces. Cain kills Abel. "
    "The world outside Eden is a world of consequence without mercy — until the flood, "
    "until the covenant, until something changes.",
    hidden=False)

db.add_condition(SLUG,
    "The Flood",
    "The World", "danger", "all",
    {"label": "total catastrophe"},
    description="God sees that every inclination of the human heart is only evil continually "
    "and regrets making humanity. The rain falls for forty days. Every high mountain is covered. "
    "Only what is in the ark survives. After, God sets a rainbow in the clouds: "
    "never again. The covenant of the rainbow.",
    hidden=False)

db.add_condition(SLUG,
    "The Great Famine",
    "All the known world", "supply", "all",
    {"type": "percent", "value": -70},
    description="Seven years of plenty have ended. The famine covers all the earth — "
    "Egypt, Canaan, everywhere. People come to Egypt from surrounding lands because "
    "Joseph has stored grain during the years of plenty. "
    "The famine that nearly destroys Jacob's family will reunite it.",
    hidden=False)

conditions_data = db._load(SLUG, "world/conditions.json")
C = {c["name"]: c["id"] for c in conditions_data["conditions"]}
print(f"  Conditions: {list(C.keys())}")

# ── Story Arcs ─────────────────────────────────────────────────────────────────
db.add_quest(SLUG,
    "The Primordial History",
    "Creation, the garden, the fall, Cain's murder of Abel, the flood, and the tower of Babel. "
    "In eleven chapters Genesis runs through the whole disaster of human history — "
    "each generation worse than the last — until God chooses one man and starts over with a family.",
    hidden=False)

db.add_quest(SLUG,
    "The Abraham Covenant",
    "God calls Abram out of Ur with a promise: land, descendants, blessing to all nations. "
    "Abram follows without knowing where he is going. For twenty-five years the promise "
    "waits. Then Isaac is born. Then God asks for him back. The binding on Moriah is the "
    "hinge of the covenant: God provides.",
    hidden=False)

db.add_quest(SLUG,
    "Jacob and the Twelve Tribes",
    "Jacob steals the blessing, flees, works for Laban, wrestles God, and becomes Israel. "
    "Twelve sons from four women become twelve tribes. The family is held together by "
    "conflict, favoritism, and a God who refuses to let any of them go.",
    hidden=False)

db.add_quest(SLUG,
    "Joseph in Egypt",
    "Sold by his brothers for twenty silver coins. Enslaved. Falsely accused. Imprisoned. "
    "Then elevated to second-in-command of Egypt by Pharaoh's dream. "
    "When famine drives his brothers to Egypt and they bow before the vizier, "
    "Joseph's first dream comes true. He weeps. He forgives them. "
    "What they meant for evil, God meant for good.",
    hidden=False)

print(f"  Story arcs seeded")

# ── Relations ──────────────────────────────────────────────────────────────────

# Dual-axis: formal bond vs personal rupture
add_dual_rel("npc", N["Cain"],    N["Abel"],   "npc", formal_relation="ally",  personal_relation="rival",   weight=0.9)
add_dual_rel("npc", N["Jacob"],   N["Esau"],   "npc", formal_relation="ally", personal_relation="rival",   weight=0.9)
add_dual_rel("npc", N["Esau"],    N["Jacob"],  "npc", formal_relation="ally", personal_relation="rival",   weight=0.9)
add_dual_rel("npc", N["Sarah"],   N["Hagar"],  "npc", formal_relation="ally",  personal_relation="rival",  weight=0.8)
add_dual_rel("npc", N["Hagar"],   N["Sarah"],  "npc", formal_relation="ally",  personal_relation="rival",  weight=0.8)
add_dual_rel("npc", N["Joseph"],  N["Judah"],  "npc", formal_relation="ally", personal_relation="rival",    weight=0.85)
add_dual_rel("npc", N["Judah"],   N["Joseph"], "npc", formal_relation="ally", personal_relation="rival",    weight=0.85)
add_dual_rel("npc", N["Jacob"],   N["Laban"],  "npc", formal_relation="ally",  personal_relation="rival",    weight=0.75)
add_dual_rel("npc", N["Laban"],   N["Jacob"],  "npc", formal_relation="ally",  personal_relation="rival",    weight=0.75)
add_dual_rel("npc", N["Jacob"],   N["Rachel"], "npc", formal_relation="ally",  personal_relation="ally",  weight=1.0)
add_dual_rel("npc", N["Jacob"],   N["Leah"],   "npc", formal_relation="ally",  personal_relation="rival",  weight=0.7)

# Clean bonds
add_rel("npc", N["The LORD"],   N["Abraham"],  "npc", "ally", 1.0, dm_only=True)
add_rel("npc", N["Abraham"],    N["Sarah"],    "npc", "ally", 0.95)
add_rel("npc", N["Sarah"],      N["Abraham"],  "npc", "ally", 0.95)
add_rel("npc", N["Abraham"],    N["Isaac"],    "npc", "ally", 1.0)
add_rel("npc", N["Isaac"],      N["Abraham"],  "npc", "ally", 1.0)
add_rel("npc", N["Abraham"],    N["Lot"],      "npc", "ally", 0.8)
add_rel("npc", N["Abraham"],    N["Ishmael"],  "npc", "ally", 0.85)
add_rel("npc", N["Isaac"],      N["Rebekah"],  "npc", "ally", 0.9)
add_rel("npc", N["Rebekah"],    N["Isaac"],    "npc", "ally", 0.9)
add_rel("npc", N["Jacob"],      N["Joseph"],   "npc", "ally", 1.0)
add_rel("npc", N["Joseph"],     N["Jacob"],    "npc", "ally", 1.0)
add_rel("npc", N["Rachel"],     N["Joseph"],   "npc", "ally", 1.0)
add_rel("npc", N["Joseph"],     N["Pharaoh"],  "npc", "ally", 0.85)
add_rel("npc", N["The LORD"],   N["Jacob"],    "npc", "ally", 1.0, dm_only=True)
add_rel("npc", N["The LORD"],   N["Joseph"],   "npc", "ally", 1.0, dm_only=True)
add_rel("npc", N["Hagar"],      N["Ishmael"],  "npc", "ally", 1.0)
add_rel("npc", N["Abraham"],    N["Melchizedek"], "npc", "ally", 0.7)

# Faction edges
add_rel("faction", F["House of Israel"], F["The Heavenly Court"], "faction", "ally", 0.9)
add_rel("faction", F["House of Israel"], F["The Nations"],        "faction", "neutral", 0.5)

print("  Relations set")

# ── Event Log ──────────────────────────────────────────────────────────────────

# Chapters 1-3: The Primordial History
log_n(N["Adam"], 1,
      "Adam and Eve eat the fruit of the tree of knowledge of good and evil; "
      "they hide from God among the trees of the garden.",
      polarity="negative", intensity=2, event_type="other", ripple=True)

log_n(N["Cain"], 1,
      "Cain kills his brother Abel in the field; when God asks where Abel is, "
      "Cain says: am I my brother's keeper?",
      polarity="negative", intensity=3, event_type="combat")

db.apply_ripple(SLUG, N["Cain"], "npc", 1,
                "Cain kills Abel — the first violence in the world.",
                "negative", 3, "combat", "public")

log_n(N["Noah"], 2,
      "God tells Noah to build an ark; Noah does exactly what God commands "
      "without a word of protest or a question.",
      polarity="positive", intensity=1, event_type="other")

log_f(F["The Nations"], 2,
      "The flood covers the earth for forty days; every living thing outside "
      "the ark dies. The world is unmade and remade.",
      polarity="negative", intensity=3, event_type="other")

log_n(N["Noah"], 2,
      "Noah plants a vineyard, drinks too much, and lies uncovered in his tent; "
      "Ham sees him and tells his brothers. Shem and Japheth walk in backward "
      "with a garment and cover him.",
      polarity="negative", intensity=1, event_type="other")

# Chapter 4: Abraham
log_n(N["Abraham"], 3,
      "God tells Abram to leave his country, his kindred, and his father's house "
      "for a land he will be shown. Abram leaves. He is seventy-five years old.",
      polarity="positive", intensity=2, event_type="other")

log_n(N["Abraham"], 3,
      "Entering Egypt during famine, Abram tells Sarai to say she is his sister "
      "to protect himself from men who would kill him for her. She is taken into "
      "Pharaoh's house. God strikes the household with plagues.",
      polarity="negative", intensity=2, event_type="politics")

log_n(N["Melchizedek"], 4,
      "After Abraham's victory over the kings, Melchizedek king of Salem "
      "brings bread and wine and blesses him: blessed be Abram by God Most High, "
      "creator of heaven and earth.",
      polarity="positive", intensity=2, event_type="dialogue")

log_n(N["Hagar"], 4,
      "Hagar flees into the desert after Sarah mistreats her; "
      "the angel of the LORD finds her at a spring on the way to Shur and tells her "
      "to return. She names God El-roi: the one who sees me.",
      polarity="positive", intensity=3, event_type="other")

log_n(N["Abraham"], 5,
      "God appears to Abraham at age ninety-nine and promises a son from Sarah; "
      "Abraham falls on his face and laughs. He says: shall Sarah, at ninety, bear a child?",
      polarity="positive", intensity=2, event_type="dialogue")

log_n(N["Sarah"], 5,
      "Sarah listens from the tent entrance when the angels announce she will bear "
      "a son in a year. She laughs to herself. God asks: is anything too hard for the LORD?",
      polarity="positive", intensity=2, event_type="dialogue")

log_n(N["Abraham"], 5,
      "Abraham rises early in the morning and takes Isaac to Mount Moriah. "
      "He builds the altar, binds his son, and raises the knife. "
      "God stops him: now I know you fear God, for you have not withheld your son.",
      polarity="positive", intensity=3, event_type="other", ripple=True)

# Chapter 5: Jacob and Esau
log_n(N["Esau"], 5,
      "Esau comes in from the field famished and sells his birthright to Jacob "
      "for bread and a bowl of red lentil stew. He eats, rises, and goes away, "
      "having despised his birthright.",
      polarity="negative", intensity=2, event_type="dialogue")

log_n(N["Rebekah"], 5,
      "Rebekah hears that Isaac intends to bless Esau; she dresses Jacob in goat skins "
      "so blind Isaac will mistake him for his hairy brother, "
      "and sends Jacob to steal the blessing.",
      polarity="neutral", intensity=2, event_type="other")

log_n(N["Jacob"], 5,
      "Jacob deceives his blind father and receives the blessing of the firstborn; "
      "Esau arrives minutes later and weeps: is he not rightly named Jacob? "
      "He has supplanted me twice. He plans to kill Jacob after Isaac's death.",
      polarity="negative", intensity=3, event_type="dialogue", ripple=True)

log_n(N["Jacob"], 6,
      "Jacob flees to Laban's house and dreams of a ladder reaching to heaven "
      "with angels ascending and descending; God speaks from above and renews "
      "the covenant of Abraham. Jacob wakes: surely the LORD is in this place.",
      polarity="positive", intensity=3, event_type="other")

log_n(N["Laban"], 6,
      "On the wedding night Laban substitutes Leah for Rachel; Jacob wakes "
      "to find the wrong wife. Laban explains: it is not done to give the younger "
      "before the firstborn. Jacob must work seven more years for Rachel.",
      polarity="negative", intensity=3, event_type="other", ripple=True)

log_n(N["Jacob"], 7,
      "At the ford of Jabbok, Jacob wrestles with a man until daybreak; "
      "the man strikes Jacob's hip but cannot pin him. Jacob refuses to release him "
      "without a blessing. The man asks his name. Then renames him: Israel.",
      polarity="positive", intensity=3, event_type="combat")

log_n(N["Esau"], 7,
      "Esau runs to meet Jacob returning with his family and embraces him; "
      "Jacob had sent gifts ahead expecting violence and found forgiveness instead. "
      "Esau says: I have enough, my brother. Keep what you have.",
      polarity="positive", intensity=3, event_type="dialogue")

# Chapter 6: Joseph
log_n(N["Joseph"], 8,
      "Joseph tells his dreams — sheaves bowing, stars bowing — to his father "
      "and brothers. His brothers hate him and cannot speak peaceably to him.",
      polarity="negative", intensity=1, event_type="dialogue")

log_n(N["Judah"], 8,
      "Judah persuades his brothers not to kill Joseph but to sell him to Ishmaelite "
      "traders for twenty pieces of silver. They dip his coat in goat's blood "
      "and bring it to Jacob: we found this. Is it your son's robe?",
      polarity="negative", intensity=3, event_type="other",
      actor_id=N["Joseph"], actor_type="npc")

db.apply_ripple(SLUG, N["Joseph"], "npc", 8,
                "Joseph is sold into Egypt by his own brothers.",
                "negative", 3, "other", "public")

log_n(N["Joseph"], 9,
      "In Egypt Joseph rises to oversee Potiphar's household; "
      "Potiphar's wife falsely accuses him of assault when he rejects her; "
      "he is thrown into prison.",
      polarity="negative", intensity=2, event_type="other")

log_n(N["Joseph"], 9,
      "In prison Joseph correctly interprets the dreams of Pharaoh's cupbearer "
      "and baker; the cupbearer forgets him for two years.",
      polarity="neutral", intensity=1, event_type="other")

log_n(N["Pharaoh"], 10,
      "Pharaoh dreams of seven fat cows and seven lean cows; Joseph interprets "
      "the dream: seven years of plenty, then seven years of famine. "
      "Pharaoh makes Joseph second in command of all Egypt.",
      polarity="positive", intensity=3, event_type="dialogue")

log_f(F["House of Israel"], 10,
      "The famine strikes Canaan; Jacob sends his sons to Egypt to buy grain, "
      "keeping Benjamin at home. They bow before the vizier without recognizing Joseph.",
      polarity="negative", intensity=3, event_type="other")

log_n(N["Joseph"], 10,
      "Joseph recognizes his brothers but does not reveal himself; he tests them, "
      "accuses them of spying, keeps Simeon, and demands Benjamin be brought. "
      "He turns away and weeps.",
      polarity="positive", intensity=2, event_type="dialogue")

log_n(N["Judah"], 10,
      "When Joseph threatens to keep Benjamin, Judah steps forward and offers "
      "himself as a substitute: let me remain as your servant in place of the boy. "
      "How can I go back to my father if the boy is not with me?",
      polarity="positive", intensity=3, event_type="dialogue")

log_n(N["Joseph"], 10,
      "Joseph can control himself no longer; he clears the room and weeps aloud. "
      "He says: I am Joseph. Is my father still alive? He cannot stop weeping. "
      "He kisses all his brothers and they talk together.",
      polarity="positive", intensity=3, event_type="dialogue", ripple=True)

db.log_condition(SLUG, C["The Great Famine"], 10,
                 "Joseph's grain stores sustain Egypt and Canaan through the seven lean years; "
                 "the family of Jacob survives. What was meant for evil was meant for good.",
                 polarity="positive", intensity=3)

print("  Event log complete")

# ── Journal entries ─────────────────────────────────────────────────────────────
db.post_journal(SLUG, 1, "The Garden",
    "The text takes eleven chapters to get from creation to Abraham. In those eleven chapters: "
    "the fall, fratricide, the flood, Babel. Every generation compounds the last. "
    "God does not destroy humanity again, but the covenant with Noah is thin — "
    "barely a promise not to repeat the flood. Something different is needed.")

db.post_journal(SLUG, 5, "The Binding of Isaac",
    "Abraham rises early in the morning. He saddles his donkey himself — "
    "doesn't wake a servant for this. He takes two young men and Isaac. "
    "He splits the wood himself. Three days to Moriah. "
    "The boy asks: here is the fire and the wood, but where is the lamb? "
    "Abraham says: God will provide. The text does not say whether he believes it.")

db.post_journal(SLUG, 7, "Jabbok",
    "Jacob wrestles until daybreak and refuses to let go without a blessing. "
    "His name is changed to Israel: he who strives with God. "
    "He limps away. He calls the place Peniel: I have seen God face to face and lived. "
    "The covenant family is named for a wrestling match. That is the point.")

db.post_journal(SLUG, 10, "Joseph Weeps",
    "Joseph is second in command of Egypt. His brothers are bowing before him. "
    "Every dream has come true. And he weeps so loudly the Egyptians hear it, "
    "and Pharaoh's household hears it. "
    "You meant it for evil. God meant it for good. He says this without bitterness. "
    "That is the most extraordinary thing in the book.")

print(f"\nDone. Campaign '{SLUG}' seeded at {CAMP_DIR}")
print("To deploy to Pi:  rsync -av campaigns/genesis/ simonhans@raspberrypi:/mnt/serverdrive/coding/questbook/campaigns/genesis/")
