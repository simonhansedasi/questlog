"""Seed script: The Wars of the Roses for RippleForge. 1455–1485.

Showcases: shifting alliances (Warwick switches sides twice), dual-axis edges
(brothers who are enemies, enemies who become allies), dynastic collapse,
historical mode, observer_name: Posterity.

Run:  python seed_roses.py
"""
import sys, os, json, secrets, shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from src import data as db

SLUG = "roses"
CAMPAIGNS = Path(__file__).parent / "campaigns"
CAMP_DIR = CAMPAIGNS / SLUG

if CAMP_DIR.exists():
    shutil.rmtree(CAMP_DIR)
for d in ["world", "story", "dm"]:
    (CAMP_DIR / d).mkdir(parents=True, exist_ok=True)

def _w(rel_path, content):
    (CAMP_DIR / rel_path).write_text(json.dumps(content, indent=2))

_w("campaign.json", {
    "name": "Wars of the Roses",
    "system": "History — 1455–1485",
    "owner": "demo",
    "dm_pin": "1234",
    "share_token": secrets.token_urlsafe(16),
    "demo": True,
    "public": True,
    "mode": "historical",
    "observer_name": "Posterity",
    "terminology": {
        "npc": "Figure", "npcs": "Figures",
        "session": "Period", "sessions": "Periods",
        "dm": "Historian", "party": "Posterity",
        "faction": "House", "factions": "Houses",
        "cast_label": "Principals",
        "notes_label": "Source Notes",
        "session_tools_label": "Write & Extract Records",
        "parse_cta": "Extract Historical Records",
        "recap_cta": "Generate Chronicle Entry",
        "quick_log_label": "Quick Record",
        "dm_controls": "Archivist Controls",
        "log_verb": "Record",
        "brief_nav": "Brief",
        "journal_label": "Chronicle",
        "quest_label": "Thread",
        "quests_label": "Threads",
        "share_label": "Researcher Share Link",
        "players_label": "Collaborators",
    },
})
_w("party.json",           {"characters": []})
_w("assets.json",          {"ships": []})
_w("journal.json",         {"entries": []})
_w("references.json",      {"references": []})
_w("world/npcs.json",      {"npcs": []})
_w("world/factions.json",  {"factions": []})
_w("world/conditions.json",{"conditions": []})
_w("story/quests.json",    {"quests": []})
_w("dm/session.json",      {})
_w("dm/relation_suggestions.json", [])

print(f"Campaign directory: {CAMP_DIR}")

# ── Factions ───────────────────────────────────────────────────────────────────
factions_to_add = [
    ("House of Lancaster", "neutral", False,
     "The red rose. The ruling house of England for three generations — "
     "Henry IV, Henry V, Henry VI. Their claim derives from John of Gaunt, "
     "fourth son of Edward III, but passes through an illegitimate line. "
     "Their strength is legitimacy; their weakness is Henry VI himself — "
     "a pious, gentle, occasionally catatonic king who cannot govern. "
     "The real Lancastrian force is his queen, Margaret of Anjou, "
     "whose ferocity and political will hold the cause together long "
     "after the cause should have collapsed. The red rose is finally "
     "extinguished at Bosworth Field in 1485."),

    ("House of York", "neutral", False,
     "The white rose. Their claim descends from Edward III through two lines "
     "— both stronger than Lancaster's if inheritance is traced honestly. "
     "Richard Duke of York asserts this claim not by ambition alone "
     "but by the specific failure of Lancastrian governance. "
     "His son Edward IV is everything Henry VI is not: physically imposing, "
     "politically shrewd, militarily devastating. York wins the crown twice. "
     "It is a Yorkist internal collapse — Richard III — that ends their dynasty."),

    ("House of Neville", "neutral", False,
     "The kingmakers. The Nevilles are the most powerful noble family in England "
     "— wealthier than most kings, connected to both York and Lancaster by blood. "
     "Richard Neville, Earl of Warwick, is the central figure: he makes Edward IV king, "
     "then unmakes him, then dies trying to restore Lancaster. "
     "His nickname — the Kingmaker — is earned. No single magnate in English history "
     "holds more political and military power for longer. His fatal flaw: "
     "he cannot accept that the king he made does not need him anymore."),

    ("House of Tudor", "neutral", True,
     "The red dragon. An obscure Welsh dynasty with a tenuous Lancastrian bloodline "
     "through an illegitimate line — Henry Tudor's claim is weak on paper. "
     "What Henry VII has instead of legitimacy is patience, timing, and French backing. "
     "He waits in Brittany and France for fourteen years. "
     "When Richard III's support collapses in 1485, he lands in Wales, "
     "gathers an army of Welsh and English defectors, and kills Richard at Bosworth. "
     "He then marries Elizabeth of York — uniting the roses — and rules for twenty-four years. "
     "Every English monarch since has been a Tudor or a Tudor descendant."),

    ("Kingdom of France", "neutral", True,
     "Louis XI — 'the Spider King' — watches the English tear themselves apart "
     "with quiet satisfaction. An England consumed by civil war cannot threaten France. "
     "Louis funds Warwick when Warwick switches sides. He harbors Henry Tudor in exile. "
     "He is not England's enemy so much as England's opportunist: "
     "wherever the English conflict creates leverage, Louis applies it. "
     "His backing of Tudor at the critical moment in 1485 is the margin "
     "that makes Bosworth possible."),
]

for name, rel, hidden, desc in factions_to_add:
    db.add_faction(SLUG, name=name, relationship=rel, description=desc, hidden=hidden)
    print(f"  + faction: {name}")

F = {f["name"]: f["id"] for f in db.get_factions(SLUG, include_hidden=True)}

# ── NPCs ───────────────────────────────────────────────────────────────────────
npcs_to_add = [
    # ── Lancaster ─────────────────────────────────────────────────────────────
    ("Henry VI", "King of England — House of Lancaster", "neutral", False,
     "The least warlike king England has ever had at the worst possible moment. "
     "Devout, gentle, and subject to complete mental collapses — possibly "
     "catatonic schizophrenia — during which he cannot speak, move, or rule. "
     "His first episode (1453–1454) is what gives Richard of York his opening. "
     "He does not want the crown in any active sense; he wants to found Eton "
     "and King's College Cambridge, which he does. "
     "He is deposed twice, restored once, and almost certainly murdered "
     "in the Tower of London in May 1471, probably on Edward IV's orders. "
     "He never understands why any of this is happening to him.",
     [F["House of Lancaster"]], []),

    ("Margaret of Anjou", "Queen of England — The She-Wolf of France", "neutral", False,
     "The most formidable political operator of the entire conflict. "
     "She marries Henry VI at fifteen and quickly understands that she is "
     "the effective ruler of England — her husband cannot govern. "
     "She fights for the Lancastrian cause with a ferocity Henry never possesses, "
     "raising armies, negotiating alliances, and leading forces personally. "
     "Her alliance with Warwick — her former enemy — to restore Henry in 1470 "
     "is a masterpiece of pragmatic politics. "
     "After Tewkesbury (1471) kills her son and destroys her cause, "
     "she is imprisoned, ransomed by Louis XI, and dies in France in 1482. "
     "She outlives the cause she kept alive by force of will alone.",
     [F["House of Lancaster"]], []),

    ("Edward Prince of Wales", "Heir to Lancaster — Killed at Tewkesbury", "neutral", True,
     "Margaret's son, the Lancastrian heir. Unlike his father, he is reported "
     "to speak of nothing but war and the cutting-off of heads — the opposite "
     "temperament to Henry VI. He represents Lancaster's future: "
     "if he lives, the dynasty can recover. "
     "He is killed at the Battle of Tewkesbury on May 4, 1471 — "
     "reportedly after the battle, captured and executed in Edward IV's presence. "
     "He is seventeen years old. His death effectively ends the Lancastrian line.",
     [F["House of Lancaster"]], []),

    # ── York ───────────────────────────────────────────────────────────────────
    ("Richard Duke of York", "Protector of England — Yorkist Patriarch", "neutral", False,
     "The father of the Yorkist cause. He is not initially a rebel — "
     "he is appointed Protector of England during Henry VI's first mental breakdown "
     "and governs competently. But the restoration of Henry's favor to Somerset "
     "(York's rival) and the birth of the Lancastrian heir end any hope "
     "of peaceful accommodation. York presses his own dynastic claim. "
     "He is killed at the Battle of Wakefield on December 30, 1460, "
     "ambushed outside his castle. His head is mounted on the gates of York "
     "wearing a paper crown. His son becomes Edward IV. "
     "York's cause outlives him entirely.",
     [F["House of York"]], []),

    ("Edward IV", "King of England — The Sun in Splendour", "neutral", False,
     "The most physically impressive English king since Henry V — "
     "six feet four inches, handsome, charismatic, an exceptional battlefield commander. "
     "He wins the crown at nineteen by destroying the Lancastrian army at Towton "
     "(1461), the bloodiest battle ever fought on English soil. "
     "His secret marriage to Elizabeth Woodville alienates Warwick irreparably "
     "and nearly destroys him — Warwick deposes him briefly in 1470. "
     "He recovers, kills Warwick at Barnet, destroys Lancaster at Tewkesbury, "
     "and rules stably for twelve years. "
     "He dies unexpectedly in April 1483 at age forty, likely of a fever "
     "worsened by years of campaigning and excess. His death hands England to Richard III.",
     [F["House of York"]], []),

    ("Richard Duke of Gloucester", "Lord Protector — Richard III", "neutral", False,
     "Edward IV's youngest brother. Loyal to Edward throughout the wars — "
     "a capable military commander who fights at Barnet and Tewkesbury. "
     "His loyalty to Edward is unquestioned. His behavior after Edward's death is not. "
     "He takes custody of the young Edward V, declares him illegitimate, "
     "and has himself crowned Richard III in June 1483. "
     "The two young princes — Edward V and his brother — disappear in the Tower. "
     "Their fate is unknown; almost everyone assumes Richard killed them. "
     "He is killed at Bosworth Field on August 22, 1485 — "
     "abandoned mid-battle by allies who switched sides — "
     "the last English king to die in combat. "
     "His body is buried without ceremony. His reputation never recovers.",
     [F["House of York"]], []),

    ("George Duke of Clarence", "Treacherous Brother — Drowned in Malmsey Wine", "neutral", False,
     "Edward IV's middle brother, and the most unreliable man in England. "
     "He switches sides to Warwick in 1469, returns to Edward in 1471, "
     "and schemes against Edward for the rest of his life. "
     "He is attainted of treason in 1478 — with Edward's consent — "
     "and executed privately in the Tower. "
     "The tradition that he was drowned in a barrel of Malmsey wine "
     "comes from contemporary sources. Whether it is literally true or "
     "a dark joke about his famous love of wine, no one knows. "
     "He is the only sibling Edward has executed.",
     [F["House of York"]], []),

    # ── Neville ────────────────────────────────────────────────────────────────
    ("Richard Neville, Earl of Warwick", "The Kingmaker", "neutral", False,
     "The most powerful subject in English history. "
     "His combined landholdings and revenues exceed any other noble and rival the crown. "
     "He is Edward IV's cousin, his chief military commander, and the architect "
     "of Yorkist victory in the early years. He expects to run foreign policy; "
     "Edward's secret marriage to Elizabeth Woodville — bypassing Warwick's "
     "diplomatic negotiations entirely — is the wound that never heals. "
     "He rebels in 1469, captures Edward IV, rules briefly in his name, "
     "switches to Lancaster in 1470, restores Henry VI, and is killed "
     "at the Battle of Barnet on April 14, 1471. "
     "His death removes the only man capable of keeping the Lancaster-York "
     "conflict permanently unresolved. It is his absence, not his presence, "
     "that allows Edward IV to finally stabilize his rule.",
     [F["House of Neville"]], []),

    # ── Tudor ──────────────────────────────────────────────────────────────────
    ("Henry Tudor", "Earl of Richmond — The Pretender", "neutral", True,
     "The last Lancastrian hope — and a thin one. "
     "His claim to the throne runs through an illegitimate descent from John of Gaunt "
     "and an uneasy reading of inheritance law. He is not the obvious claimant. "
     "But he is the only claimant alive after 1471, he is patient, "
     "and he has the backing of France. "
     "He spends fourteen years in Brittany and Normandy watching England implode. "
     "When he lands at Milford Haven in August 1485 with a French army, "
     "he has never met most of the men fighting under his banner. "
     "He wins because Richard III's allies switch sides mid-battle. "
     "He marries Elizabeth of York and calls himself the end of the wars. "
     "He is right.",
     [F["House of Tudor"]], [F["Kingdom of France"]]),

    ("Jasper Tudor", "Earl of Pembroke — Henry's Protector", "neutral", True,
     "Henry Tudor's uncle and the man who keeps him alive. "
     "He shelters the young Henry when the Yorkists take power in 1461, "
     "flees to Brittany with him in 1471, and maintains the Lancastrian network "
     "in Wales throughout the long years of exile. "
     "Without Jasper Tudor there is no Henry Tudor. "
     "He outlives the war, is restored to his earldom, and dies in 1495.",
     [F["House of Tudor"]], []),

    # ── Woodville ──────────────────────────────────────────────────────────────
    ("Elizabeth Woodville", "Queen of England — The Grey Mare", "neutral", False,
     "A widow of a Lancastrian knight who catches Edward IV's eye in 1464. "
     "Their secret marriage is the single most destabilizing act of Edward's reign: "
     "it humiliates Warwick, who was negotiating Edward's marriage to a French princess; "
     "it floods the court with Woodville relatives seeking patronage; "
     "and it creates the factional tension that Richard III exploits in 1483. "
     "After Edward's death she takes sanctuary in Westminster Abbey, "
     "watches her son deposed and imprisoned, and is forced to make terms with Richard. "
     "After Bosworth she sees her daughter Elizabeth marry Henry VII — "
     "and becomes the grandmother of Henry VIII.",
     [F["House of York"]], []),
]

for name, role, rel, hidden, desc, visible_fids, hidden_fids in npcs_to_add:
    db.add_npc(SLUG, name=name, role=role, relationship=rel, description=desc,
               hidden=hidden, factions=visible_fids, hidden_factions=hidden_fids)
    print(f"  + npc: {name}")

N = {n["name"]: n["id"] for n in db.get_npcs(SLUG, include_hidden=True)}

# ── Relations ──────────────────────────────────────────────────────────────────
def add_rel(src_type, src_id, tgt_id, tgt_type, relation, weight):
    fname = "world/npcs.json" if src_type == "npc" else "world/factions.json"
    key   = "npcs"            if src_type == "npc" else "factions"
    data  = db._load(SLUG, fname)
    for e in data[key]:
        if e["id"] == src_id:
            rels = e.setdefault("relations", [])
            if not any(r["target"] == tgt_id for r in rels):
                rels.append({"target": tgt_id, "target_type": tgt_type,
                             "relation": relation, "weight": weight})
    db._save(SLUG, data, fname)

def add_dual_rel(src_type, src_id, tgt_id, tgt_type,
                 formal_relation, personal_relation, weight=0.8):
    fname = "world/npcs.json" if src_type == "npc" else "world/factions.json"
    key   = "npcs"            if src_type == "npc" else "factions"
    data  = db._load(SLUG, fname)
    for e in data[key]:
        if e["id"] == src_id:
            rels = e.setdefault("relations", [])
            if not any(r["target"] == tgt_id for r in rels):
                rels.append({
                    "target": tgt_id, "target_type": tgt_type,
                    "formal_relation": formal_relation,
                    "personal_relation": personal_relation,
                    "weight": weight,
                })
    db._save(SLUG, data, fname)

# Lancaster internal
add_rel("npc", N["Henry VI"],              N["Margaret of Anjou"],           "npc", "ally",  1.0)
add_rel("npc", N["Margaret of Anjou"],     N["Henry VI"],                    "npc", "ally",  1.0)
add_rel("npc", N["Margaret of Anjou"],     N["Edward Prince of Wales"],      "npc", "ally",  1.0)
add_rel("npc", N["Henry VI"],              N["Edward Prince of Wales"],      "npc", "ally",  1.0)

# York internal
add_rel("npc", N["Richard Duke of York"],  N["Edward IV"],                   "npc", "ally",  1.0)
add_rel("npc", N["Edward IV"],             N["Richard Duke of York"],        "npc", "ally",  1.0)
add_rel("npc", N["Edward IV"],             N["Richard Duke of Gloucester"],  "npc", "ally",  1.0)
add_rel("npc", N["Richard Duke of Gloucester"], N["Edward IV"],              "npc", "ally",  1.0)

# George of Clarence — formally York's brother, personally unreliable
add_dual_rel("npc", N["Edward IV"],          N["George Duke of Clarence"], "npc",
             formal_relation="ally", personal_relation="rival", weight=0.8)
add_dual_rel("npc", N["George Duke of Clarence"], N["Edward IV"],          "npc",
             formal_relation="ally", personal_relation="rival", weight=0.8)

# Warwick — formally York's greatest ally, then enemy
add_rel("npc", N["Richard Neville, Earl of Warwick"], N["Edward IV"],      "npc", "ally",  1.0)
add_rel("npc", N["Edward IV"],  N["Richard Neville, Earl of Warwick"],     "npc", "ally",  0.9)
# Warwick and Margaret — enemies who become allies of necessity
add_dual_rel("npc", N["Richard Neville, Earl of Warwick"], N["Margaret of Anjou"], "npc",
             formal_relation="ally", personal_relation="rival", weight=0.75)
add_dual_rel("npc", N["Margaret of Anjou"], N["Richard Neville, Earl of Warwick"], "npc",
             formal_relation="ally", personal_relation="rival", weight=0.75)
# Warwick and George — co-conspirators
add_rel("npc", N["Richard Neville, Earl of Warwick"], N["George Duke of Clarence"], "npc", "ally", 0.9)

# Cross-faction rivals
add_rel("npc", N["Margaret of Anjou"],     N["Richard Duke of York"],        "npc", "rival", 1.0)
add_rel("npc", N["Richard Duke of York"],  N["Margaret of Anjou"],           "npc", "rival", 1.0)
add_rel("npc", N["Margaret of Anjou"],     N["Edward IV"],                   "npc", "rival", 1.0)
add_rel("npc", N["Edward IV"],             N["Margaret of Anjou"],           "npc", "rival", 1.0)
add_rel("npc", N["Edward IV"],             N["Richard Duke of Gloucester"],  "npc", "ally",  1.0)
add_rel("npc", N["Henry VI"],              N["Richard Duke of York"],        "npc", "rival", 0.9)
add_rel("npc", N["Richard Duke of York"],  N["Henry VI"],                    "npc", "rival", 0.9)

# Tudor connections
add_rel("npc", N["Henry Tudor"],           N["Jasper Tudor"],                "npc", "ally",  1.0)
add_rel("npc", N["Jasper Tudor"],          N["Henry Tudor"],                 "npc", "ally",  1.0)
add_rel("npc", N["Henry Tudor"],           N["Richard Duke of Gloucester"],  "npc", "rival", 1.0)
add_rel("npc", N["Richard Duke of Gloucester"], N["Henry Tudor"],            "npc", "rival", 1.0)

# Elizabeth Woodville — Warwick's nemesis
add_rel("npc", N["Elizabeth Woodville"],   N["Richard Neville, Earl of Warwick"], "npc", "rival", 0.9)
add_rel("npc", N["Richard Neville, Earl of Warwick"], N["Elizabeth Woodville"],   "npc", "rival", 0.9)
# Richard III and Elizabeth — complicated
add_dual_rel("npc", N["Richard Duke of Gloucester"], N["Elizabeth Woodville"], "npc",
             formal_relation="ally", personal_relation="rival", weight=0.7)

# Faction relations
add_rel("faction", F["House of Lancaster"], F["House of York"],     "faction", "rival", 1.0)
add_rel("faction", F["House of York"],      F["House of Lancaster"],"faction", "rival", 1.0)
add_rel("faction", F["House of Neville"],   F["House of York"],     "faction", "ally",  0.9)
add_rel("faction", F["House of York"],      F["House of Neville"],  "faction", "ally",  0.9)
add_rel("faction", F["House of Tudor"],     F["House of Lancaster"],"faction", "ally",  0.8)
add_rel("faction", F["House of Lancaster"], F["House of Tudor"],    "faction", "ally",  0.8)
add_rel("faction", F["House of Tudor"],     F["House of York"],     "faction", "rival", 0.9)
add_rel("faction", F["House of York"],      F["House of Tudor"],    "faction", "rival", 0.9)
add_rel("faction", F["Kingdom of France"],  F["House of Tudor"],    "faction", "ally",  0.7)
add_rel("faction", F["Kingdom of France"],  F["House of Lancaster"],"faction", "ally",  0.6)
add_rel("faction", F["Kingdom of France"],  F["House of York"],     "faction", "rival", 0.5)

print("Relations set.")

# ── Conditions ─────────────────────────────────────────────────────────────────
db.add_condition(SLUG,
    "The Royal Madness",
    "England", "danger", "governance",
    "total collapse of royal authority",
    description="Henry VI's first complete mental collapse begins in August 1453 "
    "and lasts eighteen months. He cannot speak, move, or recognise his newborn son. "
    "England has a king who is not there. Richard of York is appointed Protector. "
    "Henry's recovery in December 1454 ends York's protectorate and restores "
    "the Lancastrian court faction — but the damage is done. "
    "Every magnate in England now knows the throne can be taken.",
    hidden=False)

db.add_condition(SLUG,
    "The Attainder Spiral",
    "England", "danger", "nobility",
    "estates and titles stripped by act of parliament",
    description="Both sides use acts of attainder — parliamentary declarations of treason — "
    "to strip their enemies of land and title without trial. "
    "Hundreds of noble families are attainted, restored, and attainted again "
    "as the political winds shift. The practice destroys the stable property rights "
    "that underpin noble loyalty to any dynasty. "
    "Lords fight not only for principle but to recover what they have already lost.",
    hidden=False)

db.add_condition(SLUG,
    "French Interference",
    "Channel Ports", "politics", "diplomacy",
    "active foreign backing of pretenders",
    description="Louis XI of France — the Spider King — consistently backs "
    "whichever English faction is most likely to keep England divided and weak. "
    "He funds Warwick's switch to Lancaster in 1470. "
    "He harbours Henry Tudor in exile for fourteen years. "
    "He provides ships and soldiers for the Tudor invasion of 1485. "
    "England's civil war is partly sustained by French interest in its continuation.",
    hidden=True)

db.add_condition(SLUG,
    "The Missing Princes",
    "Tower of London", "danger", "succession",
    "heirs imprisoned and presumed dead",
    description="Edward V (age 12) and his brother Richard Duke of York (age 9) "
    "are placed in the Tower of London in the spring of 1483 by their uncle Richard. "
    "They are seen less and less frequently. After the summer of 1483 they are not seen at all. "
    "No bodies are found in their lifetimes. "
    "Richard III never explains their absence. "
    "Their disappearance delegitimises his reign and drives defections to Henry Tudor. "
    "Whether Richard ordered their deaths is the most debated mystery in English history.",
    hidden=True)

print("Conditions seeded.")

# ── Historical Threads ─────────────────────────────────────────────────────────
db.add_quest(SLUG,
    "The Legitimacy Question",
    "Who has the right to rule England? "
    "The Yorkist claim through Philippa of Clarence — Edward III's third son — "
    "is genealogically stronger than the Lancastrian claim through John of Gaunt's "
    "illegitimate line. But the Lancastrians have ruled for fifty years. "
    "Legitimacy is not just genealogy: it is also possession, precedent, and force. "
    "Each side argues law; each side wins with armies. "
    "Henry VII settles the question by winning and then marrying the other side.",
    hidden=False)

db.add_quest(SLUG,
    "Warwick's Gamble",
    "Richard Neville made Edward IV king. He expected to run the kingdom. "
    "Edward's secret marriage to a Woodville widow in 1464 ends this arrangement. "
    "Warwick's response — rebellion, capture of the king, restoration of Lancaster, "
    "alliance with the queen he spent years fighting — is the most dramatic "
    "political reversal of the entire conflict. "
    "Whether he could have succeeded is unanswerable: he is killed at Barnet "
    "before the alliance with Margaret can be tested at full strength.",
    hidden=False)

db.add_quest(SLUG,
    "The Princes in the Tower",
    "Edward IV dies in April 1483. His heir is twelve years old. "
    "Within two months his brother Richard has declared the boy illegitimate, "
    "imprisoned him and his brother in the Tower, and crowned himself. "
    "The two boys are never seen in public again. "
    "Richard's reign lasts twenty-six months. "
    "Every defection that ultimately kills him at Bosworth "
    "is driven at least partly by the question of what he did to his nephews.",
    hidden=False)

db.add_quest(SLUG,
    "The Tudor Settlement",
    "Henry Tudor has no real claim to the throne beyond survival and opportunity. "
    "He wins it by killing Richard III and immediately marries Elizabeth of York "
    "— uniting the two roses and ending the dynastic argument. "
    "His victory is not inevitable: it requires French money, Welsh loyalty, "
    "and the Stanley family's last-minute betrayal of Richard mid-battle. "
    "The Wars of the Roses end not because someone wins decisively "
    "but because Henry VII proves impossible to dislodge.",
    hidden=False)

print("Historical threads seeded.")

# ── Helpers ───────────────────────────────────────────────────────────────────
def log_n(npc_id, session, note, polarity=None, intensity=1,
          event_type=None, visibility="public", ripple=False):
    evt = db.log_npc(SLUG, npc_id, session, note, polarity=polarity,
                     intensity=intensity, event_type=event_type, visibility=visibility)
    if ripple and polarity:
        db.apply_ripple(SLUG, npc_id, "npc", session, note, polarity, intensity,
                        event_type, visibility=visibility, source_event_id=evt)
    return evt

def log_f(fid, session, note, polarity=None, intensity=1,
          event_type=None, visibility="public", ripple=False):
    evt = db.log_faction(SLUG, fid, session, note, polarity=polarity,
                         intensity=intensity, event_type=event_type, visibility=visibility)
    if ripple and polarity:
        db.apply_ripple(SLUG, fid, "faction", session, note, polarity, intensity,
                        event_type, visibility=visibility, source_event_id=evt)
    return evt

# ── Period 1: First Blood (1455) ───────────────────────────────────────────────
log_n(N["Henry VI"], 1,
    "Henry VI suffers his first complete mental collapse in August 1453 — "
    "eighteen months of total incapacity. He sits immobile, unable to speak "
    "or recognise his newborn son. Richard of York is appointed Protector of England. "
    "Henry's recovery in December 1454 restores the Lancastrian court faction "
    "and strips York of his protectorate. The confrontation is now inevitable.",
    polarity="negative", intensity=3, event_type="other", ripple=True)

log_n(N["Richard Duke of York"], 1,
    "The First Battle of St. Albans, May 22, 1455: York intercepts the royal "
    "army on a market street. The battle lasts less than an hour. "
    "The Lancastrian commander Somerset is killed. Henry VI is found sitting "
    "alone in a tanner's cottage, wounded by an arrow in the neck. "
    "York kneels before him and blames the dead Somerset for everything. "
    "It is the first blood of the war. It is presented as a misunderstanding.",
    polarity="negative", intensity=2, event_type="combat", ripple=True)

log_f(F["House of Lancaster"], 1,
    "The Lancastrian court loses its chief military commander at St. Albans. "
    "Margaret of Anjou, excluded from formal power because she is a woman, "
    "begins building her own political network — writing to nobles, "
    "controlling access to the king, accumulating influence outside "
    "the structures that exclude her. She will not be excluded for long.",
    polarity="negative", intensity=2, event_type="politics", ripple=True)

db.post_journal(SLUG, 1, "2024-01-01",
    "**Period 1 — First Blood (1455)**\n\n"
    "The war begins with a misunderstanding that both sides pretend is a misunderstanding. "
    "Henry's mental collapse is the enabling condition: it creates a power vacuum "
    "that York fills legitimately, then is expelled from, then reclaims by force.\n\n"
    "**Causal chain:** The rival edge between York and Lancaster activates at St. Albans — "
    "not at full intensity yet, but present. Margaret's response to exclusion "
    "is the engine's most interesting register: her score relative to Posterity "
    "begins to build as she becomes the real Lancastrian force."
)

# ── Period 2: The Act of Accord (1460) ────────────────────────────────────────
log_n(N["Margaret of Anjou"], 2,
    "Margaret assembles a Lancastrian army in the north and defeats the Yorkists "
    "at the Battle of Wakefield on December 30, 1460. "
    "Richard Duke of York is killed — ambushed outside his castle. "
    "His head is mounted on the gates of York wearing a paper crown. "
    "Margaret's forces show no restraint. The brutality radicalises "
    "York's surviving son Edward, who is now the Yorkist claimant.",
    polarity="negative", intensity=3, event_type="combat", ripple=True)

log_n(N["Richard Duke of York"], 2,
    "Before his death, York had achieved his greatest political success: "
    "the Act of Accord (October 1460) — a parliamentary settlement making "
    "him heir to Henry VI and disinheriting the Lancastrian prince. "
    "Henry VI signs it. Margaret refuses to accept it on behalf of her son. "
    "York dies at Wakefield two months later. "
    "His son inherits the claim, the crown, and the war.",
    polarity="negative", intensity=3, event_type="politics", ripple=True)

log_n(N["Richard Neville, Earl of Warwick"], 2,
    "Warwick holds London for York throughout this period — "
    "a crucial strategic contribution. He controls the city's resources, "
    "the financial networks, and the propaganda apparatus. "
    "When Edward IV marches south after Wakefield, Warwick's London "
    "is the foundation he builds the next campaign on. "
    "Their partnership is at its peak.",
    polarity="positive", intensity=2, event_type="politics", ripple=True)

db.post_journal(SLUG, 2, "2024-01-01",
    "**Period 2 — The Act of Accord (1460)**\n\n"
    "York's greatest triumph and his death occur in the same two months. "
    "The Act of Accord is a real constitutional settlement — it might have held. "
    "Margaret's refusal and the Wakefield ambush end that possibility.\n\n"
    "**Causal chain:** York's death removes the moderate Yorkist voice "
    "and replaces him with Edward — younger, angrier, less interested "
    "in settlement. Margaret's score peaks at her most effective moment "
    "politically. The rival edge between Lancaster and York intensifies."
)

# ── Period 3: Towton (March 1461) ─────────────────────────────────────────────
log_n(N["Edward IV"], 3,
    "Edward IV enters London in February 1461 and is acclaimed king. "
    "He immediately marches north to end the war. "
    "The Battle of Towton, March 29, 1461: fought in a blizzard on Palm Sunday. "
    "An estimated 28,000 dead — the bloodiest battle ever fought on English soil. "
    "The Lancastrian army is destroyed. Henry VI and Margaret flee to Scotland. "
    "Edward IV is king. He is nineteen years old.",
    polarity="positive", intensity=3, event_type="combat", ripple=True)

log_n(N["Henry VI"], 3,
    "Henry VI flees north after Towton with Margaret and the Lancastrian court. "
    "He spends three years as a fugitive in Scotland and northern England. "
    "He is captured in Lancashire in 1465 and imprisoned in the Tower of London. "
    "He prays. He is content, by some accounts, in a way he never was as a king. "
    "He is not executed — Edward finds him more useful as a symbol "
    "of Lancastrian incompetence than as a martyr.",
    polarity="negative", intensity=3, event_type="other", ripple=True)

log_f(F["House of Lancaster"], 3,
    "The Lancastrian cause after Towton is a rump: "
    "a fugitive king, an exile queen, and a handful of northern castles "
    "that hold out until 1464. Margaret leads fruitless campaigns "
    "from France and Scotland, burning through political capital "
    "and receiving less each time. The red rose is not extinguished — "
    "but it is very nearly so.",
    polarity="negative", intensity=3, event_type="combat", ripple=True)

db.post_journal(SLUG, 3, "2024-01-01",
    "**Period 3 — Towton (1461)**\n\n"
    "The war's bloodiest day produces a decisive result for the first time. "
    "Edward IV is king in a way that cannot be easily undone — "
    "he has won by force, with London's support, against a full Lancastrian army.\n\n"
    "**Causal chain:** The engine's Yorkist scores improve across the board. "
    "Lancaster's scores collapse — Henry VI is captured; Margaret is in exile. "
    "The rival edges are at maximum intensity. "
    "Warwick's score peaks as Edward's enabler and enforcer."
)

# ── Period 4: The Kingmaker Rebels (1469–1470) ────────────────────────────────
log_n(N["Edward IV"], 4,
    "Edward's secret marriage to Elizabeth Woodville in 1464 is announced "
    "while Warwick is in France negotiating Edward's marriage to a French princess. "
    "Warwick returns to find the deal done and himself humiliated. "
    "The Woodville family floods the court with appointments. "
    "Warwick's influence over foreign policy evaporates. "
    "The wound does not heal.",
    polarity="negative", intensity=2, event_type="politics", ripple=True)

log_n(N["Richard Neville, Earl of Warwick"], 4,
    "Warwick rebels in 1469 in alliance with George of Clarence — "
    "Edward's own brother. They defeat a royal army at Edgecote, "
    "capture Edward IV, and govern briefly in his name. "
    "It does not hold: Edward is released when the nobility refuses "
    "to support a king held prisoner by his own subject. "
    "Warwick and Clarence flee to France. "
    "Warwick approaches Margaret of Anjou — his former enemy — "
    "and offers to restore Henry VI if she will ally with him.",
    polarity="negative", intensity=3, event_type="betrayal", ripple=True)

log_n(N["Margaret of Anjou"], 4,
    "Margaret receives Warwick's offer in France. "
    "He was her greatest enemy for fifteen years. "
    "She makes him wait on his knees for a quarter of an hour "
    "before agreeing. "
    "The price: Warwick's daughter Anne will marry her son Edward, "
    "Prince of Wales, securing the alliance with a dynastic bond. "
    "It is the most extraordinary political agreement of the entire war — "
    "the Kingmaker and the She-Wolf, united by shared hatred of Edward IV.",
    polarity="positive", intensity=3, event_type="politics", ripple=True)

db.post_journal(SLUG, 4, "2024-01-01",
    "**Period 4 — The Kingmaker Rebels (1469–1470)**\n\n"
    "This is the engine's showcase: the dual-axis edge between Warwick and Margaret "
    "is formally ally, personally rival — they despise each other and need each other.\n\n"
    "**Causal chain:** Edward's Woodville marriage is the inflection point. "
    "It is not a military mistake but a personal one — and it costs him the "
    "most powerful subject in England. Warwick's rebel edge with Edward is "
    "now active. George of Clarence — the unreliable brother — "
    "demonstrates exactly the dual-axis formal/personal pattern "
    "the engine was built to capture."
)

# ── Period 5: The Re-adoption of Henry VI (1470–1471) ─────────────────────────
log_n(N["Richard Neville, Earl of Warwick"], 5,
    "Warwick invades England with French backing in September 1470. "
    "Edward IV, caught off guard, flees to Burgundy with Richard of Gloucester. "
    "Warwick releases Henry VI from the Tower and restores him as king — "
    "the 'Re-adeption' of Henry VI. "
    "Henry is paraded through London. He is described as dazed and confused, "
    "wearing a long blue velvet gown, repeating 'My kingdom, my kingdom.' "
    "It lasts six months.",
    polarity="negative", intensity=3, event_type="politics", ripple=True)

log_n(N["Edward IV"], 5,
    "Edward IV returns from Burgundy in March 1471 with a small army and "
    "reclaims England town by town, battle by battle. "
    "George of Clarence, characteristically, switches back to Edward "
    "mid-campaign — he meets his brother on the road and they reconcile. "
    "Warwick is killed at the Battle of Barnet on April 14, 1471, "
    "in thick fog, partly by friendly fire from his own Lancastrian allies. "
    "Edward weeps over his cousin's body and has it displayed publicly "
    "to prevent rumours that Warwick survived.",
    polarity="positive", intensity=3, event_type="combat", ripple=True)

log_n(N["Henry VI"], 5,
    "Henry VI is returned to the Tower after Barnet. "
    "He is murdered there on May 21, 1471 — "
    "on the same night Edward IV returns to London after Tewkesbury. "
    "The official cause of death is 'pure displeasure and melancholy.' "
    "No one believes this. Edward needs the Lancastrian line ended; "
    "Henry is the last legitimate adult male claimant. "
    "He is buried without ceremony. He is later venerated as a saint.",
    polarity="negative", intensity=3, event_type="other",
    visibility="dm_only", ripple=True)

db.post_journal(SLUG, 5, "2024-01-01",
    "**Period 5 — The Re-adoption (1470–1471)**\n\n"
    "Six months of Lancastrian restoration that demonstrates exactly why "
    "Henry VI cannot rule: he is installed as a figurehead by Warwick "
    "and has no idea what to do with it.\n\n"
    "**Causal chain:** Warwick's death at Barnet is the turning point. "
    "He is killed by fog and friendly fire — the battle's outcome depends "
    "on a misidentified banner in poor visibility. "
    "His absence removes the only man who could sustain Lancaster-York division "
    "indefinitely. Henry VI's murder closes the Lancastrian main line. "
    "The engine correctly shows a complete collapse in Lancastrian scores."
)

# ── Period 6: Tewkesbury — The Last Lancaster (May 1471) ──────────────────────
log_n(N["Margaret of Anjou"], 6,
    "Margaret lands in England on the same day as Barnet — "
    "she does not yet know Warwick is dead. "
    "She raises a new army in Wales, marching to join with Welsh allies. "
    "Edward IV intercepts her at Tewkesbury on May 4, 1471. "
    "The Lancastrian army is destroyed. Her son Edward, Prince of Wales, "
    "is killed — captured after the battle and executed. He is seventeen. "
    "Margaret herself is captured. She is imprisoned in the Tower "
    "and later ransomed back to France by Louis XI. "
    "She never returns to England. She dies in poverty in 1482.",
    polarity="negative", intensity=3, event_type="combat", ripple=True)

log_n(N["Edward Prince of Wales"], 6,
    "The Lancastrian Prince of Wales is killed at Tewkesbury at seventeen. "
    "He is the last male heir of the Lancastrian line in England. "
    "His death is the true end of the first phase of the wars: "
    "there is no legitimate Lancaster left to fight for. "
    "The cause Margaret sustained for two decades dies with her son.",
    polarity="negative", intensity=3, event_type="combat", ripple=True)

log_f(F["House of Lancaster"], 6,
    "The red rose is finished. Henry VI murdered in the Tower, "
    "the Prince of Wales killed at Tewkesbury, Margaret in exile. "
    "There is no Lancastrian heir. The cause has no rallying point. "
    "The only remaining Lancastrian bloodline passes through Henry Tudor — "
    "a fourteen-year-old exile in Brittany with a questionable claim "
    "who no one takes seriously yet.",
    polarity="negative", intensity=3, event_type="other", ripple=True)

db.post_journal(SLUG, 6, "2024-01-01",
    "**Period 6 — Tewkesbury (1471)**\n\n"
    "The engine's Lancaster scores hit their floor. "
    "The main line is extinguished. Margaret's score collapses "
    "because her cause is gone — not because she is defeated militarily, "
    "but because the person she was fighting for is dead.\n\n"
    "**Causal chain:** Tewkesbury and Henry VI's murder on the same night "
    "complete what Towton began. Edward IV is now secure — "
    "no Lancastrian heir, no Warwick, his brother Clarence back in the fold. "
    "The only future threat is one he cannot see: the Yorkist family itself."
)

# ── Period 7: The Stable Reign and Its End (1471–1483) ────────────────────────
log_n(N["Edward IV"], 7,
    "Edward IV rules England for twelve years after Tewkesbury — "
    "the longest stable period of the entire conflict. "
    "He is an effective king: he reforms royal finances, cultivates the "
    "merchant classes, and keeps the nobility in check. "
    "He has George of Clarence executed in 1478 — privately, in the Tower — "
    "for treason that is real, and for being an irredeemable liability. "
    "He grows fat and dissolute in his middle years, though he remains capable "
    "of bursts of decisive energy. He dies in April 1483 at forty, "
    "of a fever — unexpected, sudden, too soon.",
    polarity="positive", intensity=2, event_type="other", ripple=True)

log_n(N["George Duke of Clarence"], 7,
    "George is attainted of treason in 1478 and privately executed in the Tower. "
    "The Malmsey wine tradition — that he was drowned in a butt of his favorite wine "
    "at his own request — comes from contemporary sources. "
    "Whether literally true or darkly symbolic, it captures something real "
    "about how England viewed him: even his death had a theatrical quality. "
    "Edward weeps at his execution. He executes him anyway.",
    polarity="negative", intensity=2, event_type="betrayal", ripple=True)

log_n(N["Richard Duke of Gloucester"], 7,
    "Richard of Gloucester is Edward's loyal lieutenant throughout the stable years — "
    "governing the north of England, fighting Scotland, administering justice. "
    "He is considered the most reliable of the three York brothers. "
    "He is present at Barnet and Tewkesbury. He may have participated in Henry VI's murder. "
    "He is thirty years old when Edward dies and the world changes around him.",
    polarity="positive", intensity=1, event_type="other")

db.post_journal(SLUG, 7, "2024-01-01",
    "**Period 7 — The Stable Reign (1471–1483)**\n\n"
    "The engine records twelve years of positive drift for York — "
    "the closest thing to resolution the war produces before Tudor. "
    "George of Clarence's execution is the dark note: "
    "the dual-axis edge between him and Edward terminates here.\n\n"
    "**Causal chain:** Edward's death in 1483 is the enabling catastrophe "
    "for the final act. His heir is twelve. His most loyal brother "
    "is about to make a decision that will destroy the York dynasty "
    "from within — not because he lacks capability, but because "
    "the nobility will not forgive what he does to his nephews."
)

# ── Period 8: The Usurpation (April–June 1483) ────────────────────────────────
log_n(N["Richard Duke of Gloucester"], 8,
    "Edward IV dies in April 1483. Richard intercepts his nephew Edward V "
    "on the road to London, takes custody of him, and arrests his Woodville escorts. "
    "He is appointed Lord Protector. Within weeks he has imprisoned the boy king "
    "and his brother in the Tower 'for their safety.' "
    "He declares both boys illegitimate on the grounds that Edward IV's "
    "marriage to Elizabeth Woodville was invalid. "
    "He is crowned Richard III on July 6, 1483. "
    "He is efficient, thorough, and hated for it.",
    polarity="negative", intensity=3, event_type="betrayal", ripple=True)

log_n(N["Elizabeth Woodville"], 8,
    "Elizabeth Woodville takes sanctuary in Westminster Abbey with her daughters "
    "when Richard moves against the Woodvilles. "
    "She is powerless: her son is Richard's prisoner; her relatives are arrested. "
    "She is eventually persuaded to release her younger son Richard "
    "into his uncle's custody — a decision she will spend the rest of her life "
    "regretting or justifying, depending on the source. "
    "Both boys are never seen publicly again.",
    polarity="negative", intensity=3, event_type="politics", ripple=True)

log_f(F["House of York"], 8,
    "Richard III's usurpation fractures the Yorkist coalition. "
    "Lord Hastings — Edward IV's closest friend — is arrested and executed "
    "on Richard's orders within minutes, on a council table in the Tower, "
    "without trial. The message is clear: loyalty to Edward's memory "
    "is a threat. Many former Yorkists begin corresponding with Henry Tudor.",
    polarity="negative", intensity=3, event_type="betrayal", ripple=True)

db.post_journal(SLUG, 8, "2024-01-01",
    "**Period 8 — The Usurpation (1483)**\n\n"
    "Richard's usurpation is swift, efficient, and self-defeating. "
    "He acquires the crown and loses the political coalition that would have "
    "defended it. The missing princes are the engine's condition card: "
    "their absence drives defection without requiring proof.\n\n"
    "**Causal chain:** Richard III's rival edge with Henry Tudor is now active. "
    "The faction score for House of York begins to decline as defectors "
    "shift their correspondence to Richmond. Elizabeth Woodville's score "
    "against Richard is now at maximum hostility — she has nothing left to lose."
)

# ── Period 9: Bosworth Field (August 22, 1485) ────────────────────────────────
log_n(N["Henry Tudor"], 9,
    "Henry Tudor lands at Milford Haven in Wales on August 7, 1485 "
    "with 2,000 French soldiers and growing Welsh support. "
    "He marches through Wales gathering men under the red dragon banner. "
    "By the time he reaches Bosworth, he has perhaps 5,000 men. "
    "Richard III has twice that. But the Stanley family — "
    "controlling 6,000 men — hovers at the battlefield's edge, uncommitted.",
    polarity="positive", intensity=2, event_type="combat", ripple=True)

log_n(N["Richard Duke of Gloucester"], 9,
    "The Battle of Bosworth Field, August 22, 1485. "
    "Richard III sees Henry Tudor exposed away from his main force "
    "and charges personally with his household cavalry to kill him directly — "
    "a bold, desperate, and strategically sound gamble. "
    "The Stanley family, watching from the flank, makes their decision: "
    "they charge into Richard's flank as he reaches Tudor's position. "
    "Richard is unhorsed, surrounded, and killed. "
    "'A horse, a horse, my kingdom for a horse.' "
    "Whether he said it is unknown. He is the last English king to die in battle. "
    "His crown is found in a hawthorn bush and placed on Henry Tudor's head.",
    polarity="negative", intensity=3, event_type="combat", ripple=True)

log_n(N["Henry Tudor"], 9,
    "Henry VII is crowned on the battlefield. "
    "He imprisons Elizabeth of York, Edward IV's daughter, "
    "and then marries her — the union of the roses that ends thirty years of war. "
    "He rules for twenty-four years. He never faces a serious dynastic challenge "
    "that he cannot defeat. He is cold, careful, and extraordinarily competent. "
    "Everything that follows — the English Reformation, the British Empire, "
    "Shakespeare's history plays — begins here, in a Leicestershire field, "
    "on a summer morning in 1485.",
    polarity="positive", intensity=3, event_type="other", ripple=True)

log_f(F["House of Tudor"], 9,
    "Henry VII marries Elizabeth of York on January 18, 1486 — "
    "the union of the red and white roses. "
    "He does not adopt the combined Tudor rose as his symbol until the marriage is done: "
    "he is careful to make clear he holds the crown by conquest, "
    "not by right of his wife. "
    "The Tudor dynasty rules England for 118 years. "
    "The Wars of the Roses are over.",
    polarity="positive", intensity=3, event_type="politics", ripple=True)

db.post_journal(SLUG, 9, "2024-01-01",
    "**Period 9 — Bosworth Field (August 22, 1485)**\n\n"
    "The war ends not with a comprehensive Yorkist defeat but with a betrayal. "
    "The Stanleys choose the moment to switch sides and Richard — outnumbered "
    "in that instant — is killed. Henry Tudor's victory is contingent, narrow, "
    "and almost accidental. His genius is what he does with it afterward.\n\n"
    "**Causal chain:** The rival edge between Richard III and Henry Tudor terminates "
    "in a Leicestershire field. Every defection Richard suffered — driven by "
    "the missing princes, by Hastings' execution, by the Woodville alienation — "
    "ripples forward into this moment. The engine's final state: "
    "House of Tudor at its highest score; House of York collapsed; "
    "House of Lancaster restored through the Tudor marriage. "
    "Thirty years of war, settled by a cavalry charge and a hawthorn crown."
)

print("\nWars of the Roses campaign seeded successfully.")
print("To deploy to Pi:  rsync -av campaigns/roses/ simonhans@raspberrypi:/mnt/serverdrive/coding/questbook/campaigns/roses/")
