"""Seed script: World War II campaign for RippleForge. 1933–1945.

Showcases: dual-axis edges (allied-but-rival commanders), world conditions
(The Blitz, U-boat Blockade, Holocaust, Soviet Winter), historical mode,
observer_name: Posterity, story threads.

Run:  python seed_ww2.py
"""
import sys, os, json, secrets, shutil
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from src import data as db

SLUG = "ww2"
CAMPAIGNS = ROOT / "campaigns"
CAMP_DIR = CAMPAIGNS / SLUG

if CAMP_DIR.exists():
    shutil.rmtree(CAMP_DIR)
for d in ["world", "story", "dm"]:
    (CAMP_DIR / d).mkdir(parents=True, exist_ok=True)

def _w(rel_path, content):
    (CAMP_DIR / rel_path).write_text(json.dumps(content, indent=2))

_w("campaign.json", {
    "slug": SLUG,
    "name": "World War II",
    "system": "History — 1933–1945",
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
        "faction": "Power", "factions": "Powers",
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
_w("world/locations.json",           {"locations": []})

print(f"Campaign directory: {CAMP_DIR}")

# ── Factions ───────────────────────────────────────────────────────────────────
factions_to_add = [
    ("Nazi Germany", "hostile", False,
     "The Third Reich under [[Adolf Hitler]]. The dominant European aggressor: "
     "it remilitarizes, annexes Austria and Czechoslovakia, invades [[Poland]], "
     "conquers France, and launches the largest land invasion in history against "
     "the [[Soviet Union]]. Its industrial and military capacity is matched only by "
     "its ideological machinery of racial extermination. Peak territorial control "
     "in 1942. Defeated May 1945."),

    ("Imperial Japan", "hostile", False,
     "The Empire of Japan under [[Emperor Hirohito]] and the militarist government. "
     "At war with [[Nationalist China|China]] since 1937, it expands into Southeast Asia and the Pacific "
     "in 1941–1942, seizing an empire from Burma to Guadalcanal. "
     "The attack on [[Pearl Harbor]] brings the [[United States]] fully into the war. "
     "Japan's industrial capacity cannot sustain the war of attrition that follows. "
     "Surrenders September 2, 1945."),

    ("Fascist Italy", "hostile", False,
     "[[Benito Mussolini|Mussolini's]] Italy — the original fascist state, ally to [[Nazi Germany|Germany]] via the "
     "Pact of Steel. Italy's military performance disappoints: failures in Greece "
     "force German intervention, and North Africa is lost by 1943. "
     "[[Benito Mussolini|Mussolini]] is deposed by his own Grand Council in July 1943. "
     "Italy surrenders in September. A German-backed puppet state "
     "holds northern Italy until April 1945."),

    ("Soviet Union", "neutral", False,
     "The USSR under [[Joseph Stalin|Stalin]]. Signs the Molotov–Ribbentrop non-aggression pact "
     "with [[Nazi Germany|Germany]] in 1939, enabling the invasion of [[Poland]]. "
     "[[Nazi Germany|Germany's]] Operation Barbarossa in June 1941 reverses this completely: "
     "the Soviets suffer catastrophic early losses, then stabilize, then push back. "
     "[[Stalingrad]] is the turning point. The Red Army drives west from 1943, "
     "taking Berlin in April 1945. The Soviet contribution to defeating [[Nazi Germany|Germany]] "
     "is larger than all other Allied contributions combined."),

    ("United States", "ally", False,
     "The Arsenal of Democracy. Formally neutral until [[Pearl Harbor]] (December 7, 1941), "
     "though Lend-Lease arms [[Great Britain|Britain]] and the [[Soviet Union|USSR]] from 1941. "
     "American industrial capacity — untouched by bombing — is the decisive material "
     "factor in Allied victory. Fights in North Africa (1942), Italy (1943), "
     "Western Europe (1944–45), and the Pacific throughout. "
     "The Manhattan Project produces the atomic bombs that end the Pacific War."),

    ("Great Britain", "ally", False,
     "The island that held. [[Winston Churchill|Churchill]] becomes Prime Minister in May 1940, "
     "the same week [[Nazi Germany|Germany]] begins its western offensive. "
     "Britain stands alone from June 1940 through December 1941, "
     "surviving the Blitz and winning the Battle of Britain. "
     "The British Empire's global resources, combined with [[Winston Churchill|Churchill's]] alliance "
     "management, make Britain the indispensable link between American power "
     "and the [[Soviet Union|Soviet]] eastern front."),

    ("Free France", "ally", False,
     "[[Charles de Gaulle|De Gaulle's]] government-in-exile, operating from [[London and Whitehall|London]]. "
     "After France's armistice, [[Charles de Gaulle|de Gaulle]] broadcasts from the BBC on June 18, 1940: "
     "'Whatever happens, the flame of French resistance must not and shall not die.' "
     "The Free French forces fight in North Africa, Italy, and eventually liberate "
     "Paris alongside the Allies in August 1944. "
     "[[Charles de Gaulle|De Gaulle]] enters Paris on foot. The legitimacy of Free France is contested "
     "by both Vichy and, at times, by Allied leadership who find [[Charles de Gaulle|de Gaulle]] difficult."),

    ("Nationalist China", "ally", False,
     "The Republic of China under Chiang Kai-shek, at war with [[Imperial Japan|Japan]] since 1937. "
     "China absorbs enormous Japanese manpower throughout the war — "
     "the China theater ties down more Japanese troops than any other front. "
     "Chiang's government is plagued by corruption and a parallel civil war "
     "with Mao's Communists. The Allies send aid via the Hump airlift over the Himalayas. "
     "China's war is the longest and most costly of any Allied nation."),

    ("Occupied Europe", "hostile", True,
     "The peoples living under [[Nazi Germany|Nazi]] occupation: France, [[Poland]], Netherlands, Belgium, "
     "Norway, Denmark, Yugoslavia, Greece, and the conquered [[Soviet Union|Soviet]] territories. "
     "The occupied populations range from collaboration to resistance. "
     "The Jews of Europe, along with Roma, disabled people, political prisoners, "
     "and others targeted by [[Nazi Germany|Nazi]] racial ideology, are systematically murdered "
     "in what becomes the Holocaust — six million Jews killed. "
     "This is the largest criminal enterprise in recorded history, "
     "conducted bureaucratically, industrially, and in deliberate secrecy."),

    ("Poland", "ally", False,
     "The first nation to fight back: Poland resists the [[Nazi Germany|German]] invasion from "
     "September 1, 1939, and when the [[Soviet Union|Soviets]] invade from the east on September 17, "
     "Polish resistance collapses within weeks. "
     "The Polish government-in-exile operates from [[London and Whitehall|London]] throughout the war. "
     "The Polish armed forces — reconstituted in [[Great Britain|Britain]] — fight at Narvik, "
     "Tobruk, Monte Cassino, and Arnhem. "
     "Poland is liberated in 1945 by [[Soviet Union|Soviet]] forces — and then remains under "
     "Soviet domination. The country that started the war ends it having lost "
     "more than a fifth of its population."),
]

for name, rel, hidden, desc in factions_to_add:
    db.add_faction(SLUG, name=name, relationship=rel, description=desc, hidden=hidden)
    print(f"  + faction: {name}")

F = {f["name"]: f["id"] for f in db.get_factions(SLUG, include_hidden=True)}

# ── NPCs ───────────────────────────────────────────────────────────────────────
npcs_to_add = [
    # ── Axis leaders ──────────────────────────────────────────────────────────
    ("Adolf Hitler", "Führer of the Third Reich", "hostile", False,
     "Austrian-born failed artist who becomes the most destructive political "
     "leader of the twentieth century. His political genius is real: he reads "
     "mass psychology correctly, exploits the humiliation of Versailles, "
     "and outmaneuvers every opponent in the 1930s. His military instincts "
     "are erratic — brilliant in 1939–1941, catastrophic from 1942 onward "
     "as he refuses to retreat, relieves competent generals, and increasingly "
     "substitutes ideology for strategy. Dies by suicide in [[The Berlin Bunker]] "
     "on April 30, 1945.",
     [F["Nazi Germany"]], []),

    ("Benito Mussolini", "Duce of Fascist Italy", "hostile", False,
     "The original fascist, in power in Italy since 1922. "
     "[[Adolf Hitler|Hitler]] models himself partly on Mussolini. But Italy's military is "
     "underequipped and poorly led, and [[Benito Mussolini|Mussolini's]] strategic judgment "
     "is poor. He invades Greece without telling [[Adolf Hitler|Hitler]]; the resulting "
     "disaster requires German rescue and delays Barbarossa. "
     "He is deposed by his own Grand Council on July 25, 1943, "
     "rescued by German commandos, and installed as puppet ruler "
     "of northern Italy until Italian partisans capture and execute him "
     "on April 28, 1945 — two days before [[Adolf Hitler|Hitler's]] death.",
     [F["Fascist Italy"]], []),

    ("Hideki Tojo", "Prime Minister and War Minister of Japan", "hostile", False,
     "Army general who becomes Prime Minister in October 1941 and drives "
     "Japan's decision to attack the [[United States]]. He believes Japan must "
     "strike before American rearmament makes war impossible to win. "
     "He is right about the window and wrong about the outcome. "
     "He is the dominant figure of Japanese war policy until July 1944, "
     "when the fall of Saipan forces his resignation. "
     "He survives the war, is tried as a war criminal, and is executed in 1948.",
     [F["Imperial Japan"]], []),

    ("Emperor Hirohito", "Emperor of Japan — Divine Sovereign", "hostile", True,
     "The 124th Emperor of Japan, theoretically divine, practically constrained. "
     "His role in Japan's war decisions is historically disputed. "
     "He does not stop the war in 1944 or early 1945 despite catastrophic losses. "
     "He does end it in 1945: after the atomic bombs and the [[Soviet Union|Soviet]] declaration "
     "of war, he makes the unprecedented decision to broadcast to his people "
     "in a recorded radio address on August 15, 1945. "
     "His voice has never been heard publicly before. "
     "He speaks in classical Japanese that most Japanese cannot understand. "
     "He does not use the word 'surrender.'",
     [F["Imperial Japan"]], []),

    ("Heinrich Himmler", "Reichsführer-SS — Architect of the Holocaust", "hostile", True,
     "The second most powerful man in [[Nazi Germany]] after [[Adolf Hitler|Hitler]]. "
     "Head of the SS, the Gestapo, and the entire apparatus of Nazi terror. "
     "He is the primary architect of the Holocaust — the systematic, "
     "industrial murder of six million Jews and millions of others. "
     "A former chicken farmer who implements genocide with bureaucratic precision. "
     "In the war's final months he makes secret contact with Allied representatives, "
     "trying to negotiate a separate peace. [[Adolf Hitler|Hitler]], learning of this, strips him "
     "of all offices. Himmler is captured by [[Great Britain|British]] forces in May 1945 "
     "and bites down on a cyanide capsule before he can be tried.",
     [F["Nazi Germany"]], []),

    ("Erwin Rommel", "Field Marshal — The Desert Fox", "neutral", False,
     "The Wehrmacht's most celebrated general. His tank command in France (1940) "
     "is a masterclass in armored warfare. In North Africa his Afrika Korps "
     "performs feats of operational brilliance against larger forces. "
     "He is also the most humane of the senior German commanders — "
     "he ignores [[Adolf Hitler|Hitler's]] orders to execute prisoners and Jewish civilians. "
     "By 1944 he privately believes [[Nazi Germany|Germany]] cannot win and is connected "
     "to the July 20 assassination plot. He does not detonate the bomb. "
     "After the plot's failure, he is given the choice: public trial "
     "or private suicide. He takes poison on October 14, 1944. "
     "[[Nazi Germany|Germany]] announces he died of his wounds. He is given a state funeral.",
     [F["Nazi Germany"]], []),

    # ── Allied leaders ─────────────────────────────────────────────────────────
    ("Winston Churchill", "Prime Minister of Great Britain", "ally", False,
     "The right man for the worst moment. Becomes PM on May 10, 1940 — "
     "the same day [[Nazi Germany|Germany]] launches its western offensive. "
     "He has been warning about [[Adolf Hitler|Hitler]] since 1933; no one listened. "
     "His value in 1940–1941 is not military but psychological: "
     "he convinces [[Great Britain|Britain]] and the watching world that this is survivable "
     "and worth surviving. 'We shall fight on the beaches.' "
     "He is also difficult: stubborn, Mediterranean-strategy-obsessed, "
     "condescending to Americans, and prone to operational interference. "
     "But the alliance holds, partly because of and partly despite him.",
     [F["Great Britain"]], []),

    ("Franklin D. Roosevelt", "President of the United States — 1933–1945", "ally", False,
     "Serves an unprecedented four terms. Leads the US out of the Depression "
     "and into the war. His strategic instincts are sound: he identifies "
     "[[Nazi Germany|Germany]] as the primary threat, institutes Lend-Lease before America "
     "enters the war, and builds the coalition that wins it. "
     "He manages [[Winston Churchill|Churchill's]] stubbornness and [[Joseph Stalin|Stalin's]] paranoia without "
     "fully satisfying either. He dies on April 12, 1945 — "
     "three weeks before [[Nazi Germany|Germany's]] surrender — of a cerebral hemorrhage "
     "at Warm Springs, Georgia. He does not live to see victory.",
     [F["United States"]], []),

    ("Harry S. Truman", "President of the United States — 1945", "ally", False,
     "Vice President for 82 days before [[Franklin D. Roosevelt|Roosevelt's]] death. "
     "He is told about the Manhattan Project only after becoming president. "
     "He has to decide, within months of taking office, whether to use "
     "atomic weapons on [[Imperial Japan|Japan]]. He decides yes: he believes an invasion "
     "of the Japanese home islands would cost more lives — American and Japanese — "
     "than the bombs. He orders the destruction of [[Hiroshima]] on August 6, 1945. "
     "He orders Nagasaki on August 9. Japan surrenders August 15.",
     [F["United States"]], []),

    ("Dwight D. Eisenhower", "Supreme Allied Commander — Europe", "ally", False,
     "The coalition builder. Not the most tactically gifted Allied general — "
     "[[Bernard Montgomery|Montgomery]] and [[George S. Patton|Patton]] both outperform him in pure battlefield terms — "
     "but the one who can hold the alliance together. "
     "He commands the North Africa landings, the Sicily invasion, "
     "and Operation Overlord (D-Day). He manages the egos of [[Winston Churchill|Churchill]], "
     "[[Bernard Montgomery|Montgomery]], and [[George S. Patton|Patton]] simultaneously without losing any of them "
     "irreparably. After the war he becomes the 34th President of the [[United States]].",
     [F["United States"]], []),

    ("Douglas MacArthur", "Supreme Commander — Pacific (Southwest)", "ally", False,
     "Brilliant, theatrical, and difficult. Escapes the Philippines by PT boat "
     "in March 1942 under orders, leaving his men to the Bataan Death March. "
     "'I shall return' — and he does, wading ashore at Leyte in October 1944. "
     "He commands the island-hopping campaign that brings the war to [[Imperial Japan|Japan's]] doorstep. "
     "He accepts [[Imperial Japan|Japan's]] formal surrender on the deck of the USS Missouri "
     "on September 2, 1945, and then personally oversees [[Imperial Japan|Japan's]] postwar reconstruction.",
     [F["United States"]], []),

    ("George S. Patton", "Commanding General — Third Army", "ally", False,
     "The most aggressive Allied commander and the one the Germans most feared. "
     "His Third Army's breakout from [[Normandy — Omaha Beach|Normandy]] (August 1944) covers ground "
     "faster than any army in the history of warfare. "
     "He slaps a shell-shocked soldier in a field hospital in Sicily "
     "and is nearly relieved of command by [[Dwight D. Eisenhower|Eisenhower]] — his value as a threat "
     "to German planning exceeds his personal conduct. "
     "He dies in December 1945 in a car accident in occupied Germany.",
     [F["United States"]], []),

    ("Bernard Montgomery", "Field Marshal — 8th Army and 21st Army Group", "friendly", False,
     "The British general who defeats [[Erwin Rommel|Rommel]] at El Alamein — the first "
     "major Allied land victory of the war. Meticulous, cautious, and convinced "
     "of his own genius. His rivalry with [[George S. Patton|Patton]] is real: they compete for "
     "fuel, glory, and [[Dwight D. Eisenhower|Eisenhower's]] approval throughout the 1944 campaign. "
     "His Operation Market Garden (September 1944) — a bold airdrop into "
     "the Netherlands — fails at Arnhem, the bridge too far. "
     "He accepts [[Nazi Germany|Germany's]] surrender at Lüneburg Heath on May 4, 1945.",
     [F["Great Britain"]], []),

    ("Charles de Gaulle", "Leader of Free France", "friendly", False,
     "A two-star brigadier general who refuses to accept France's armistice "
     "and broadcasts from [[London and Whitehall|London]] on June 18, 1940. "
     "He has no army, no government, no territory, and no recognition. "
     "He builds all of these through sheer will and the force of a single "
     "argument: France has not lost, only its government has surrendered. "
     "He is difficult to work with — [[Winston Churchill|Churchill]] calls him the heaviest cross "
     "he has to bear — and he is right about almost everything. "
     "He walks down the Champs-Élysées in August 1944 under sniper fire "
     "because the scene requires it.",
     [F["Free France"]], []),

    # ── Soviet commanders ──────────────────────────────────────────────────────
    ("Joseph Stalin", "General Secretary — Soviet Union", "neutral", False,
     "The man who industrialized the [[Soviet Union]] by force and killed millions "
     "doing it. His purge of the Red Army's officer corps in 1937–1938 "
     "removes most of his best military minds — they are shot, or imprisoned, "
     "or broken — and this is why Barbarossa's early months are catastrophic. "
     "He recovers. He learns to let his generals fight. "
     "By 1943 the Soviet military machine is the most powerful on earth. "
     "He extracts maximum territorial concessions from the Allies at Yalta "
     "and leaves the war controlling [[Occupied Europe|Eastern Europe]].",
     [F["Soviet Union"]], []),

    ("Georgy Zhukov", "Marshal of the Soviet Union — Defender of Moscow, Berlin", "friendly", False,
     "The greatest general of World War II by almost any measure. "
     "He is recalled to defend Moscow in October 1941 when German forces "
     "are within sight of the Kremlin's spires — and he holds. "
     "He commands at [[Stalingrad]], Kursk, the destruction of Army Group Centre, "
     "the Vistula-Oder Offensive, and the final assault on Berlin. "
     "He accepts [[Nazi Germany|Germany's]] unconditional surrender in Berlin on May 8, 1945. "
     "[[Joseph Stalin|Stalin]], jealous of his reputation, sidelines him after the war.",
     [F["Soviet Union"]], []),

    # ── Japanese commanders ────────────────────────────────────────────────────
    ("Isoroku Yamamoto", "Fleet Admiral — Architect of Pearl Harbor", "hostile", False,
     "The most sophisticated Japanese strategic thinker. He has lived in America, "
     "studied at Harvard, and knows that [[Imperial Japan|Japan]] cannot win a long war with the [[United States|US]]. "
     "He proposes [[Pearl Harbor]] as a way to buy time — not as a path to victory. "
     "'I fear we have awakened a sleeping giant,' he allegedly says afterward. "
     "He plans the Midway operation, which fails catastrophically when [[United States|US]] "
     "code-breakers read the Japanese naval codes. "
     "He is killed on April 18, 1943, when [[United States|US]] fighters intercept his transport "
     "over Bougainville — his flight schedule decoded from an intercepted message.",
     [F["Imperial Japan"]], []),
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

# Axis leaders — inter-allied
add_rel("npc", N["Adolf Hitler"],    N["Benito Mussolini"],  "npc", "ally",  0.9)
add_rel("npc", N["Benito Mussolini"],N["Adolf Hitler"],      "npc", "ally",  0.9)
add_rel("npc", N["Adolf Hitler"],    N["Hideki Tojo"],       "npc", "ally",  0.6)
add_rel("npc", N["Adolf Hitler"],    N["Heinrich Himmler"],  "npc", "ally",  1.0)
add_rel("npc", N["Heinrich Himmler"],N["Adolf Hitler"],      "npc", "ally",  1.0)
add_rel("npc", N["Adolf Hitler"],    N["Erwin Rommel"],      "npc", "ally",  0.85)
add_rel("npc", N["Erwin Rommel"],    N["Adolf Hitler"],      "npc", "ally",  0.85)
add_rel("npc", N["Hideki Tojo"],     N["Isoroku Yamamoto"],  "npc", "ally",  0.9)
add_rel("npc", N["Isoroku Yamamoto"],N["Hideki Tojo"],       "npc", "ally",  0.9)
add_rel("npc", N["Hideki Tojo"],     N["Emperor Hirohito"],  "npc", "ally",  0.75)

# Axis vs Allies (key rival edges)
add_rel("npc", N["Adolf Hitler"],    N["Winston Churchill"], "npc", "rival", 1.0)
add_rel("npc", N["Winston Churchill"],N["Adolf Hitler"],     "npc", "rival", 1.0)
add_rel("npc", N["Adolf Hitler"],    N["Franklin D. Roosevelt"], "npc", "rival", 0.9)
add_rel("npc", N["Adolf Hitler"],    N["Joseph Stalin"],     "npc", "rival", 1.0)
add_rel("npc", N["Joseph Stalin"],   N["Adolf Hitler"],      "npc", "rival", 1.0)
add_rel("npc", N["Erwin Rommel"],    N["Bernard Montgomery"],"npc", "rival", 0.9)
add_rel("npc", N["Bernard Montgomery"],N["Erwin Rommel"],    "npc", "rival", 0.9)
add_rel("npc", N["Isoroku Yamamoto"],N["Franklin D. Roosevelt"],"npc","rival",0.9)
add_rel("npc", N["Georgy Zhukov"],   N["Adolf Hitler"],      "npc", "rival", 1.0)

# Allied leaders — coalition
add_rel("npc", N["Winston Churchill"],      N["Franklin D. Roosevelt"], "npc", "ally", 1.0)
add_rel("npc", N["Franklin D. Roosevelt"], N["Winston Churchill"],      "npc", "ally", 1.0)
add_rel("npc", N["Winston Churchill"],      N["Joseph Stalin"],          "npc", "ally", 0.7)
add_rel("npc", N["Joseph Stalin"],          N["Winston Churchill"],      "npc", "ally", 0.7)
add_rel("npc", N["Franklin D. Roosevelt"], N["Joseph Stalin"],           "npc", "ally", 0.75)
add_rel("npc", N["Joseph Stalin"],          N["Franklin D. Roosevelt"],  "npc", "ally", 0.75)
add_rel("npc", N["Franklin D. Roosevelt"], N["Harry S. Truman"],         "npc", "ally", 0.9)
add_rel("npc", N["Dwight D. Eisenhower"],  N["George S. Patton"],        "npc", "ally", 0.85)
add_rel("npc", N["George S. Patton"],      N["Dwight D. Eisenhower"],    "npc", "ally", 0.85)
add_rel("npc", N["Dwight D. Eisenhower"],  N["Bernard Montgomery"],      "npc", "ally", 0.75)
add_rel("npc", N["Bernard Montgomery"],    N["Dwight D. Eisenhower"],    "npc", "ally", 0.75)
# Patton and Montgomery: formally allied officers, personally contemptuous rivals
add_dual_rel("npc", N["George S. Patton"],   N["Bernard Montgomery"], "npc",
             formal_relation="ally", personal_relation="rival", weight=0.75)
add_dual_rel("npc", N["Bernard Montgomery"], N["George S. Patton"],   "npc",
             formal_relation="ally", personal_relation="rival", weight=0.75)
# Churchill and de Gaulle: essential alliance, deeply strained personal relationship
add_dual_rel("npc", N["Winston Churchill"],  N["Charles de Gaulle"],  "npc",
             formal_relation="ally", personal_relation="rival", weight=0.7)
add_dual_rel("npc", N["Charles de Gaulle"], N["Winston Churchill"],   "npc",
             formal_relation="ally", personal_relation="rival", weight=0.7)
add_rel("npc", N["Dwight D. Eisenhower"], N["Douglas MacArthur"],        "npc", "ally", 0.7)
add_rel("npc", N["Joseph Stalin"],         N["Georgy Zhukov"],            "npc", "ally", 0.9)
add_rel("npc", N["Georgy Zhukov"],         N["Joseph Stalin"],            "npc", "ally", 0.9)

# Faction relations
add_rel("faction", F["Nazi Germany"],    F["Fascist Italy"],     "faction", "ally",  0.85)
add_rel("faction", F["Fascist Italy"],   F["Nazi Germany"],      "faction", "ally",  0.85)
add_rel("faction", F["Nazi Germany"],    F["Imperial Japan"],    "faction", "ally",  0.7)
add_rel("faction", F["Imperial Japan"],  F["Nazi Germany"],      "faction", "ally",  0.7)
add_rel("faction", F["Nazi Germany"],    F["Great Britain"],     "faction", "rival", 1.0)
add_rel("faction", F["Great Britain"],   F["Nazi Germany"],      "faction", "rival", 1.0)
add_rel("faction", F["Nazi Germany"],    F["Soviet Union"],      "faction", "rival", 1.0)
add_rel("faction", F["Soviet Union"],    F["Nazi Germany"],      "faction", "rival", 1.0)
add_rel("faction", F["Nazi Germany"],    F["United States"],     "faction", "rival", 1.0)
add_rel("faction", F["United States"],   F["Nazi Germany"],      "faction", "rival", 1.0)
add_rel("faction", F["Nazi Germany"],    F["Poland"],            "faction", "rival", 1.0)
add_rel("faction", F["Nazi Germany"],    F["Occupied Europe"],   "faction", "rival", 1.0)
add_rel("faction", F["Imperial Japan"],  F["United States"],     "faction", "rival", 1.0)
add_rel("faction", F["United States"],   F["Imperial Japan"],    "faction", "rival", 1.0)
add_rel("faction", F["Imperial Japan"],  F["Nationalist China"], "faction", "rival", 1.0)
add_rel("faction", F["Nationalist China"],F["Imperial Japan"],   "faction", "rival", 1.0)
add_rel("faction", F["United States"],   F["Great Britain"],     "faction", "ally",  1.0)
add_rel("faction", F["Great Britain"],   F["United States"],     "faction", "ally",  1.0)
add_rel("faction", F["Soviet Union"],    F["Great Britain"],     "faction", "ally",  0.75)
add_rel("faction", F["Great Britain"],   F["Soviet Union"],      "faction", "ally",  0.75)
add_rel("faction", F["Soviet Union"],    F["United States"],     "faction", "ally",  0.75)
add_rel("faction", F["United States"],   F["Soviet Union"],      "faction", "ally",  0.75)
add_rel("faction", F["Great Britain"],   F["Free France"],       "faction", "ally",  0.9)
add_rel("faction", F["Free France"],     F["Great Britain"],     "faction", "ally",  0.9)
add_rel("faction", F["United States"],   F["Free France"],       "faction", "ally",  0.8)
add_rel("faction", F["Great Britain"],   F["Poland"],            "faction", "ally",  0.9)

print("Relations set.")

# ── Conditions ─────────────────────────────────────────────────────────────────
db.add_condition(SLUG,
    "The Blitz",
    "Great Britain", "danger", "all",
    "-40%",
    description="The Luftwaffe begins systematic bombing of British cities on September 7, 1940. "
    "London burns for 57 consecutive nights. Over 43,000 civilians are killed. "
    "Churchill refuses to negotiate. The RAF holds. The invasion never comes — "
    "but the damage to civilian infrastructure and morale is staggering.",
    hidden=False)

db.add_condition(SLUG,
    "U-boat Blockade",
    "Atlantic Ocean", "supply", "all",
    "-35%",
    description="German submarines operate in 'wolf packs' across the Atlantic, "
    "sinking millions of tons of Allied shipping. Britain's food, fuel, and materiel "
    "depend on convoys. At the height of the Battle of the Atlantic in 1942-43, "
    "Allied losses threaten to strangle Britain before the US buildup can arrive.",
    hidden=False)

db.add_condition(SLUG,
    "Soviet Winter",
    "Eastern Front", "danger", "military",
    "catastrophic attrition",
    description="Operation Barbarossa freezes before Moscow in December 1941 as "
    "temperatures drop to -40°C. German troops have no winter equipment; "
    "oil freezes in engines; frostbite takes more men than bullets. "
    "The Wehrmacht that entered the Soviet Union in June will never be the same force again.",
    hidden=False)

db.add_condition(SLUG,
    "The Holocaust",
    "Occupied Europe", "danger", "all",
    "systematic extermination",
    description="The Wannsee Conference of January 1942 coordinates the 'Final Solution': "
    "the systematic murder of European Jews. Six million Jews are killed by war's end, "
    "along with Roma, disabled persons, political prisoners, and Soviet POWs. "
    "The full scale is not known to Allied commanders until the camps are liberated in 1944-45.",
    hidden=True)

print("Conditions seeded.")

# ── Historical Threads ─────────────────────────────────────────────────────────
db.add_quest(SLUG,
    "The Fall and Recovery of France",
    "France falls in six weeks in May-June 1940. De Gaulle escapes to London and declares "
    "Free France on the BBC. The collaborationist Vichy government controls the south. "
    "Three years later, French forces fight at Cassino, in North Africa, and land at Normandy. "
    "The question of what France was during the occupation will haunt it for generations.",
    hidden=False)

db.add_quest(SLUG,
    "The Eastern Front",
    "Operation Barbarossa is the largest military operation in history: three million German troops "
    "invade the Soviet Union on June 22, 1941, Hitler's most consequential decision. "
    "The Eastern Front kills twenty-seven million Soviet citizens. It is where the war is won — "
    "and at a cost that dwarfs everything else. Zhukov holds Moscow, Stalingrad, and finally Berlin.",
    hidden=False)

db.add_quest(SLUG,
    "The Pacific War",
    "Pearl Harbor on December 7, 1941 brings the United States into the war. "
    "Japan dominates the Pacific for six months. Midway in June 1942 destroys the IJN's "
    "carrier fleet and turns the tide. Island-hopping to Iwo Jima and Okinawa; "
    "then Hiroshima and Nagasaki. The Pacific war ends on the deck of the Missouri.",
    hidden=False)

db.add_quest(SLUG,
    "The Road to D-Day",
    "Churchill and Roosevelt debate a second front throughout 1942-43. "
    "North Africa first. Then Sicily and Italy — 'the soft underbelly of Europe.' "
    "On June 6, 1944, 156,000 Allied troops land on five beaches in Normandy. "
    "Eisenhower holds the coalition together; the Allies liberate Paris by August. "
    "Hitler's Europe is crumbling from all directions.",
    hidden=False)

print("Historical threads seeded.")

# ── Locations ──────────────────────────────────────────────────────────────────
db.add_location(SLUG, "Normandy — Omaha Beach",
    role="D-Day, June 6, 1944 — the Western Front opens",
    description="The five beaches of the Normandy coast where 156,000 Allied troops landed on June 6, 1944. Omaha Beach cost 2,000 American casualties in a single morning. By nightfall, the Allies had a foothold in France. [[Dwight D. Eisenhower|Eisenhower]] carried a message in his pocket for if the landings failed. He did not need to send it.",
    hidden=False,
    dm_notes="The night before D-Day, Eisenhower walked among his paratroopers and could not tell them the odds. The Omaha landing nearly fails — the demolition teams are killed before they can clear the obstacles; the bombers miss the beach by miles. The assault succeeds because the men simply keep moving forward into fire. The beach is secured at enormous cost.")

db.add_location(SLUG, "Stalingrad",
    role="The Eastern Front turning point — where Germany's advance died",
    description="A Soviet city on the Volga that [[Adolf Hitler|Hitler]] attached his name to and refused to surrender. The Battle of Stalingrad lasted from August 1942 to February 1943. Three hundred thousand German troops were encircled by [[Georgy Zhukov|Zhukov's]] Operation Uranus. Field Marshal Paulus surrendered with 91,000 survivors. The Wehrmacht never recovered.",
    hidden=False,
    dm_notes="Hitler's refusal to allow retreat at Stalingrad is his most consequential military error. The city becomes a trap: every soldier sent into it is consumed. Zhukov's encirclement is prepared for months while the city fighting draws German attention. The surrender is the first time the German public is told that something has gone seriously wrong.")

db.add_location(SLUG, "Pearl Harbor",
    role="December 7, 1941 — the attack that brought America into the war",
    description="The US naval base at Pearl Harbor, Hawaii, attacked by the Japanese carrier fleet at dawn on December 7, 1941. Eighteen US warships were sunk or damaged. 2,403 Americans were killed. Four battleships went to the bottom. The three US aircraft carriers were not in port — they were at sea — and survived. [[Isoroku Yamamoto|Yamamoto]] knew this.",
    hidden=False,
    dm_notes="The carriers' absence from Pearl Harbor is the decisive fact of the Pacific war. Yamamoto designed the attack to destroy American offensive capability; without the carriers, it is only a tactical success. He reportedly says: 'I fear we have awakened a sleeping giant.' The quote may be apocryphal. The sentiment is not.")

db.add_location(SLUG, "London and Whitehall",
    role="Britain's wartime capital — where Churchill governed",
    description="London endured 57 consecutive nights of Luftwaffe bombing beginning September 7, 1940. Over 43,000 civilians were killed. [[Winston Churchill|Churchill]] refused to leave the city or consider armistice. He walked through the rubble in his hat and his cigar and the people cheered. The Cabinet War Rooms beneath Whitehall were where the war was actually run.",
    hidden=False,
    dm_notes="Churchill's decision to remain in London and be seen among the bombed streets is a calculated act of political psychology. His broadcast speeches are the instrument by which he convinces Britain and the watching world that this is survivable. The Battle of Britain is won partly in the air and partly in these broadcasts.")

db.add_location(SLUG, "The Berlin Bunker",
    role="Hitler's final refuge — where the Reich ended",
    description="The Führerbunker beneath the Reich Chancellery garden in Berlin, where [[Adolf Hitler|Hitler]] spent his final weeks as [[Soviet Union|Soviet]] forces fought street by street above him. He died here on April 30, 1945 — a gunshot wound and cyanide, with Eva Braun, in the underground conference room. Their bodies were carried upstairs and burned in the garden. [[Nazi Germany|Germany]] surrendered eight days later.",
    hidden=False,
    dm_notes="Hitler's last weeks in the bunker are marked by increasingly disconnected military conferences in which he moves nonexistent divisions. He is told Berlin is lost and continues to give orders. On April 28 he learns Himmler has tried to negotiate a separate peace. On April 29 he marries Eva Braun and dictates his final testament. On April 30 he dies. Germany holds on for eight more days.")

db.add_location(SLUG, "Auschwitz",
    role="The Holocaust's largest killing center — six million murdered",
    description="The Auschwitz-Birkenau complex in [[Occupied Europe|occupied Poland]] was the largest of the [[Nazi Germany|Nazi]] extermination camps. Between 1942 and 1944 it was the primary site of the industrial murder of European Jews. The camp was liberated by [[Soviet Union|Soviet]] forces on January 27, 1945. [[Dwight D. Eisenhower|Eisenhower]] ordered every available soldier and nearby German civilian to tour the liberated camps as witnesses.",
    hidden=True,
    dm_notes="The Holocaust is not a sidebar to the war — it is the war's central crime. The Wannsee Conference of January 1942 coordinates the 'Final Solution.' Himmler's SS continues deportations to the gas chambers until the camps are physically liberated. Eisenhower's insistence on witness is the right instinct: 'I want to be in a position to give firsthand evidence of these things if ever in the future there develops a tendency to charge these allegations merely to propaganda.'")

db.add_location(SLUG, "Hiroshima",
    role="August 6, 1945 — the atomic bomb",
    description="A Japanese city of 350,000 people. On August 6, 1945, a single B-29 dropped a uranium bomb that killed 80,000 people immediately. Total deaths reached 135,000. Three days later, Nagasaki. On August 15, [[Emperor Hirohito]] broadcast to his people in a voice they had never heard before. He did not say 'surrender.' He did not need to.",
    hidden=False,
    dm_notes="Truman's decision is argued about for the rest of the century. His calculation: an invasion of the Japanese home islands projects 250,000 to one million Allied casualties, and comparable Japanese losses. The bombs kill fewer people than an invasion would. Whether this arithmetic justifies the atomic destruction of two cities is a question the engine cannot answer and neither can we.")

locations_data = db._load(SLUG, "world/locations.json")
L = {loc["name"]: loc["id"] for loc in locations_data["locations"]}
print(f"  Locations: {list(L.keys())}")

# ── Helpers ───────────────────────────────────────────────────────────────────
def log_n(npc_id, session, note, polarity=None, intensity=1,
          event_type=None, visibility="public", ripple=False, actor_id=None, actor_type=None, location_id=None):
    evt = db.log_npc(SLUG, npc_id, session, note, polarity=polarity,
                     intensity=intensity, event_type=event_type, visibility=visibility,
                     actor_id=actor_id, actor_type=actor_type, location_id=location_id)
    if ripple and polarity:
        db.apply_ripple(SLUG, npc_id, "npc", session, note, polarity, intensity,
                        event_type, visibility=visibility, source_event_id=evt)
    return evt

def log_f(fid, session, note, polarity=None, intensity=1,
          event_type=None, visibility="public", ripple=False, actor_id=None, actor_type=None, location_id=None):
    evt = db.log_faction(SLUG, fid, session, note, polarity=polarity,
                         intensity=intensity, event_type=event_type, visibility=visibility,
                         actor_id=actor_id, actor_type=actor_type, location_id=location_id)
    if ripple and polarity:
        db.apply_ripple(SLUG, fid, "faction", session, note, polarity, intensity,
                        event_type, visibility=visibility, source_event_id=evt)
    return evt

def log_l(loc_id, session, note, polarity=None, intensity=1,
          event_type=None, visibility="public", actor_id=None, actor_type=None):
    db.log_location(SLUG, loc_id, session, note, visibility=visibility,
                    polarity=polarity, intensity=intensity, event_type=event_type,
                    actor_id=actor_id, actor_type=actor_type)

# ── Session 1: The Axis Rises (1933–1938) ─────────────────────────────────────
log_n(N["Adolf Hitler"], 1,
    "Hitler is appointed Chancellor of Germany on January 30, 1933. "
    "Within eighteen months he is Führer, having abolished the presidency, "
    "merged it with the chancellorship, and purged his own party's rivals "
    "in the Night of the Long Knives. The democratic Weimar Republic is dead.",
    polarity="negative", intensity=3, event_type="politics", ripple=True)

log_n(N["Benito Mussolini"], 1,
    "Mussolini invades Ethiopia in 1935 with chemical weapons and overwhelming force, "
    "in defiance of the League of Nations. The League's impotent response — "
    "toothless sanctions — signals to Hitler that the international order "
    "will not resist force with force. The Rome-Berlin Axis is formalized in 1936.",
    polarity="negative", intensity=2, event_type="combat", ripple=True)

log_f(F["Nazi Germany"], 1,
    "Germany remilitarizes the Rhineland in 1936, violating the Treaty of Versailles. "
    "France and Britain protest and do nothing. Germany annexes Austria in the "
    "Anschluss of March 1938. The Munich Agreement of September 1938 gives Hitler "
    "the Sudetenland in exchange for his promise that he has no further territorial "
    "ambitions. 'Peace for our time,' Chamberlain announces. "
    "Hitler has contempt for men who can be bought with appeasement.",
    polarity="negative", intensity=3, event_type="politics", ripple=True)

log_n(N["Winston Churchill"], 1,
    "Churchill is in his 'wilderness years' — out of government, warning from "
    "the backbenches about German rearmament that no one wants to hear. "
    "He is right about everything and politically irrelevant. "
    "He uses the time to write history and paint watercolors. "
    "His moment is coming.",
    polarity="negative", intensity=1, event_type="politics")

log_f(F["Occupied Europe"], 1,
    "The Nuremberg Laws of 1935 strip German Jews of citizenship and forbid "
    "marriage between Jews and Germans. Kristallnacht (November 9, 1938) — "
    "the Night of Broken Glass — sees Jewish synagogues, businesses, and homes "
    "destroyed across Germany and Austria. Ninety-one Jews are killed; "
    "thirty thousand are arrested and sent to concentration camps. "
    "This is the visible surface of what is being built beneath.",
    polarity="negative", intensity=3, event_type="other", visibility="dm_only",
    ripple=True)

db.post_journal(SLUG, 1, "2024-01-01",
    "**Session 1 — The Axis Rises (1933–1938)**\n\n"
    "The precondition for everything. Hitler's rise is not inevitable: "
    "it requires the specific failure of Weimar's democracy, the specific "
    "humiliation of Versailles, and the specific cowardice of appeasement. "
    "Each of these is a choice made by real people.\n\n"
    "**Causal chain:** The League of Nations fails over Ethiopia — "
    "this tells Hitler the international order is decorative. "
    "Munich tells him it will pay ransom. Kristallnacht tells the world "
    "what is being built. The world mostly looks away. "
    "Churchill alone says clearly what this is. No one listens yet."
)

# ── Session 2: The World Goes to War (1939) ───────────────────────────────────
log_n(N["Adolf Hitler"], 2,
    "The Molotov-Ribbentrop Pact (August 23, 1939) — a non-aggression agreement "
    "with the Soviet Union that also secretly divides Eastern Europe between them. "
    "It frees Hitler to move west without a two-front war. "
    "Stalin believes he has bought time. Hitler believes he has solved his "
    "strategic problem. Both are partially right.",
    polarity="negative", intensity=3, event_type="politics", ripple=True)

log_f(F["Poland"], 2,
    "Germany invades Poland from the west on September 1, 1939. "
    "The Soviet Union invades from the east on September 17. "
    "Britain and France declare war on Germany on September 3 — "
    "and then do almost nothing. Poland falls in five weeks. "
    "The Polish government escapes to London. "
    "A hundred thousand Polish soldiers eventually fight in British uniform.",
    polarity="negative", intensity=3, event_type="combat", ripple=True)

log_n(N["Franklin D. Roosevelt"], 2,
    "Roosevelt watches Europe go to war and begins positioning the United States "
    "to support Britain without entering the conflict — a delicate domestic "
    "political balance. He wins a third term in 1940 partly by promising "
    "not to send American boys into foreign wars. He does not believe this promise "
    "is one he will be able to keep.",
    polarity="negative", intensity=2, event_type="politics")

db.post_journal(SLUG, 2, "2024-01-01",
    "**Session 2 — The World Goes to War (1939)**\n\n"
    "The Molotov-Ribbentrop Pact is the most consequential diplomatic event "
    "of the war's opening. It enables the Polish invasion, enables Dunkirk, "
    "enables the Fall of France. Stalin believes he has bought time. "
    "He has bought less than two years.\n\n"
    "**Causal chain:** Poland's destruction is swift and total. "
    "The Allied declaration of war produces no military action — "
    "the 'Phoney War' is eight months of waiting while Germany consolidates. "
    "The engine scores Poland hostile immediately. The rival edges "
    "between Germany and its neighbors are now active."
)

# ── Session 3: The Fall of France (May–June 1940) ────────────────────────────
log_f(F["Nazi Germany"], 3,
    "Germany invades France through the Ardennes on May 10, 1940 — "
    "the one direction the French do not expect. The Allied line breaks. "
    "Three hundred and thirty thousand British and French troops are "
    "evacuated from Dunkirk's beaches by an armada of warships and "
    "civilian boats in nine days. France signs an armistice on June 22. "
    "The Wehrmacht has conquered Western Europe in six weeks.",
    polarity="negative", intensity=3, event_type="combat", ripple=True)

log_n(N["Winston Churchill"], 3,
    "[[Winston Churchill]] becomes Prime Minister on May 10, 1940 — the day [[Nazi Germany|Germany]] attacks. "
    "He tells the House of Commons he has nothing to offer but blood, toil, "
    "tears, and sweat. He refuses to consider any armistice or negotiated peace. "
    "When the War Cabinet debates terms, he ends it: 'If this long island story "
    "of ours is to end at last, let it end only when each one of us lies "
    "choking in his own blood upon the ground.' The cabinet stands and cheers.",
    polarity="positive", intensity=3, event_type="dialogue", ripple=True,
    location_id=L["London and Whitehall"])

log_n(N["Charles de Gaulle"], 3,
    "De Gaulle is a junior general when France falls. He flies to London "
    "and broadcasts on the BBC on June 18, 1940: 'Whatever happens, the flame "
    "of French resistance must not and shall not die.' "
    "The French government in Vichy considers him a traitor and sentences him "
    "to death in absentia. He has no army, no recognition, and no territory. "
    "He has the microphone and the argument.",
    polarity="positive", intensity=2, event_type="dialogue", ripple=True)

log_f(F["Great Britain"], 3,
    "The Battle of Britain (July–September 1940): the Luftwaffe attempts to "
    "destroy the RAF and establish air superiority for invasion. "
    "The RAF holds — by a narrow margin, exhausting its pilots, "
    "but holding. [[Adolf Hitler]] postpones Operation Sea Lion indefinitely. "
    "[[Great Britain]] will not be invaded. [[Winston Churchill]]: 'Never in the field of human "
    "conflict was so much owed by so many to so few.'",
    polarity="positive", intensity=3, event_type="combat", ripple=True,
    location_id=L["London and Whitehall"])

db.post_journal(SLUG, 3, "2024-01-01",
    "**Session 3 — The Fall of France (1940)**\n\n"
    "The engine's most complex session: simultaneous catastrophe and resistance. "
    "France falls (massive negative for the Allied cause) while Churchill "
    "and de Gaulle perform acts of pure will that keep the resistance alive.\n\n"
    "**Causal chain:** Dunkirk saves the army but not the territory. "
    "Churchill's refusal to negotiate is the decision that makes Allied victory "
    "possible — without it, Britain makes a deal and the US never enters. "
    "The Battle of Britain is the RAF's finest hour and the Luftwaffe's "
    "first defeat. The rival edge between Germany and Britain is now the "
    "defining relationship of the European war."
)

# ── Session 4: Operation Barbarossa (June–December 1941) ─────────────────────
log_n(N["Adolf Hitler"], 4,
    "Hitler launches Operation Barbarossa on June 22, 1941 — "
    "3 million German troops invade the Soviet Union on a front "
    "1,800 miles wide. It is the largest military operation in history. "
    "Stalin is warned by multiple intelligence sources. He ignores them all. "
    "The initial German advance is catastrophic for the Soviets: "
    "the Red Army loses 800,000 men in the first two months.",
    polarity="negative", intensity=3, event_type="combat", ripple=True)

log_n(N["Joseph Stalin"], 4,
    "Stalin collapses psychologically for approximately ten days after Barbarossa begins — "
    "retreating to his dacha, unreachable. The Politburo comes to him. "
    "He recovers. He broadcasts to the Soviet people, calling them 'brothers and sisters' "
    "for the first time. He does not leave Moscow when the Germans reach its suburbs. "
    "The decision to stay — visible, symbolic, immovable — is one of the most "
    "consequential of the war.",
    polarity="negative", intensity=3, event_type="dialogue", ripple=True)

log_n(N["Georgy Zhukov"], 4,
    "Zhukov is appointed to defend Moscow in October 1941 when German forces "
    "are close enough to see the Kremlin's golden domes through field glasses. "
    "He holds. On December 5, 1941, he launches a counteroffensive with "
    "fresh Siberian divisions — troops acclimatized to cold that the Germans, "
    "who were never issued winter equipment, are not. "
    "The Wehrmacht is stopped forty miles from Moscow.",
    polarity="positive", intensity=3, event_type="combat", ripple=True)

db.post_journal(SLUG, 4, "2024-01-01",
    "**Session 4 — Operation Barbarossa (1941)**\n\n"
    "The war's largest single event. Barbarossa breaks the Nazi-Soviet Pact "
    "and transforms the war's geometry: the Soviet Union is now fighting "
    "for survival, and survival requires the destruction of the Wehrmacht.\n\n"
    "**Causal chain:** The rival edge between Hitler and Stalin activates fully. "
    "Soviet losses in the opening months are almost incomprehensible — "
    "but the Soviets have manpower depth Germany does not. "
    "Zhukov's Moscow defense is the first crack in German invincibility. "
    "The engine scores Germany's relationship with the Soviets as war "
    "from this point forward. It will never recover."
)

# ── Session 5: Pearl Harbor — America Enters (December 1941) ─────────────────
log_n(N["Isoroku Yamamoto"], 5,
    "[[Isoroku Yamamoto]]'s strike force attacks [[Pearl Harbor]] at dawn on December 7, 1941. "
    "Eighteen US warships are sunk or damaged; 2,403 Americans are killed. "
    "Four battleships go to the bottom. Crucially, three US aircraft carriers "
    "are not in port — they are at sea — and survive. "
    "Yamamoto knows this. He knows the carriers are what matter.",
    polarity="negative", intensity=3, event_type="combat", ripple=True,
    location_id=L["Pearl Harbor"])

log_n(N["Franklin D. Roosevelt"], 5,
    "[[Franklin D. Roosevelt]] addresses Congress on December 8, 1941: "
    "'Yesterday, December 7, 1941 — a date which will live in infamy.' "
    "Congress declares war on Japan in thirty-three minutes. "
    "[[Adolf Hitler]], in the single most consequential blunder of the war, "
    "declares war on the [[United States]] four days later. "
    "He was not required to do this by the Axis pact. He does it anyway.",
    polarity="positive", intensity=3, event_type="dialogue", ripple=True,
    location_id=L["Pearl Harbor"])

log_n(N["Winston Churchill"], 5,
    "[[Winston Churchill]] hears about [[Pearl Harbor]] on a radio and goes to bed and slept "
    "the sleep of the saved and thankful. He knows that with [[United States|America]] in the war, "
    "victory is now certain — it is only a question of time and suffering. "
    "He sails immediately to Washington to meet [[Franklin D. Roosevelt]] and begin building "
    "the Grand Alliance.",
    polarity="positive", intensity=3, event_type="dialogue", ripple=True,
    location_id=L["London and Whitehall"])

log_f(F["United States"], 5,
    "America's industrial conversion is immediate and total. "
    "Car factories become tank factories. Shipyards work around the clock. "
    "The US produces more weapons in 1942 than Germany, Japan, and Italy combined. "
    "Lend-Lease ships supplies to Britain and the Soviet Union on a scale "
    "that neither could sustain their war effort without.",
    polarity="positive", intensity=3, event_type="other", ripple=True)

db.post_journal(SLUG, 5, "2024-01-01",
    "**Session 5 — Pearl Harbor: America Enters (December 1941)**\n\n"
    "The war's pivot. Pearl Harbor is a tactical success and a strategic "
    "catastrophe for Japan: it brings the one nation whose industrial capacity "
    "can simply outbuild the Axis into the war at full commitment.\n\n"
    "**Causal chain:** Hitler's declaration of war on the US is the most "
    "unforced error of the war — he was not required to do it. "
    "It completes the Grand Alliance. Churchill goes to bed satisfied. "
    "The rival edge between Yamamoto and Roosevelt is now at its sharpest. "
    "The engine reflects American entry as a strong positive ripple "
    "through every Allied entity in the graph."
)

# ── Session 6: Midway — The Pacific Turns (June 1942) ────────────────────────
log_n(N["Isoroku Yamamoto"], 6,
    "Yamamoto plans the Midway operation: lure the US carriers into a trap "
    "at Midway Atoll and destroy them. US code-breakers read the Japanese "
    "naval codes and know the plan. Admiral Nimitz sets his own trap. "
    "June 4–7, 1942: in five minutes of divebombing, the US sinks four "
    "Japanese fleet carriers — the same carriers that attacked Pearl Harbor. "
    "Japan loses its offensive capability in the Pacific. The war's direction changes.",
    polarity="negative", intensity=3, event_type="combat", ripple=True)

log_f(F["Imperial Japan"], 6,
    "Japan's early 1942 conquests stretch from Burma to Guadalcanal, "
    "from Manchuria to the Dutch East Indies. The 'Greater East Asia Co-Prosperity Sphere' "
    "is a colonial empire built in six months. After Midway, the defensive perimeter "
    "begins to contract. The US island-hopping campaign — taking key islands, "
    "bypassing others to 'wither on the vine' — begins to compress Japan's "
    "supply lines and air cover.",
    polarity="negative", intensity=3, event_type="other", ripple=True)

log_n(N["Douglas MacArthur"], 6,
    "MacArthur, forced to abandon the Philippines ('I shall return'), "
    "commands the Southwest Pacific theater from Australia. "
    "The Guadalcanal campaign (August 1942 – February 1943) is the first "
    "major Allied land offensive of the Pacific war — six months of jungle "
    "fighting, naval battles, and attrition that Japan cannot sustain.",
    polarity="positive", intensity=2, event_type="combat", ripple=True)

db.post_journal(SLUG, 6, "2024-01-01",
    "**Session 6 — Midway: The Pacific Turns (1942)**\n\n"
    "Midway is decided in five minutes but prepared over months. "
    "The decisive factor is not bravery or numbers but intelligence: "
    "US code-breakers know the Japanese plan. Yamamoto's fatal flaw "
    "is that he does not know they know.\n\n"
    "**Causal chain:** Four Japanese carriers gone means no offensive air cover "
    "for future operations. The rival edge between Yamamoto and Roosevelt "
    "inverts after Midway — Japan goes defensive. "
    "MacArthur and Nimitz begin competing for resources and credit, "
    "a rivalry the engine captures in their inter-commander scores."
)

# ── Session 7: El Alamein and Stalingrad (1942–1943) ─────────────────────────
log_n(N["Bernard Montgomery"], 7,
    "The Second Battle of El Alamein (October–November 1942): "
    "Montgomery's 8th Army defeats Rommel's Afrika Korps in twelve days "
    "of fighting in the Egyptian desert. It is the first major British "
    "land victory of the war. Churchill orders church bells rung across Britain "
    "for the first time since the invasion threat of 1940. "
    "'Before Alamein we never had a victory. After Alamein we never had a defeat.'",
    polarity="positive", intensity=3, event_type="combat", ripple=True)

log_n(N["Erwin Rommel"], 7,
    "Rommel is beaten at El Alamein — outmanned, outgunned, and outmaneuvered. "
    "The Afrika Korps retreats across North Africa. Operation Torch "
    "(US landings in Morocco and Algeria) cuts off retreat. "
    "The last Axis forces in North Africa surrender in May 1943. "
    "Rommel has already been recalled to Germany on sick leave — "
    "Hitler does not want to be present for the defeat.",
    polarity="negative", intensity=3, event_type="combat", ripple=True)

log_n(N["Georgy Zhukov"], 7,
    "Operation Uranus (November 1942): [[Georgy Zhukov]]'s encirclement of the German "
    "6th Army at [[Stalingrad]]. Three hundred thousand German troops are surrounded. "
    "[[Adolf Hitler]] forbids retreat. Operation Winter Storm — the relief attempt — fails. "
    "Field Marshal Paulus surrenders with 91,000 survivors on January 31, 1943. "
    "The Wehrmacht has never suffered a defeat of this magnitude. "
    "The war on the Eastern Front has turned.",
    polarity="positive", intensity=3, event_type="combat", ripple=True,
    location_id=L["Stalingrad"])

log_f(F["Nazi Germany"], 7,
    "[[Stalingrad]] kills the myth of [[Nazi Germany|German]] invincibility. "
    "The German public is told for the first time that something has gone wrong. "
    "Goebbels declares 'total war' in February 1943. "
    "Germany's manpower and material reserves, already strained, "
    "begin an irreversible decline. The Kursk offensive in July 1943 — "
    "the last major German offensive on the Eastern Front — fails. "
    "After Kursk, Germany never attacks in the East again.",
    polarity="negative", intensity=3, event_type="other", ripple=True,
    location_id=L["Stalingrad"])

db.post_journal(SLUG, 7, "2024-01-01",
    "**Session 7 — El Alamein and Stalingrad (1942–1943)**\n\n"
    "The twin turning points. El Alamein ends the North African threat "
    "to the Suez Canal; Stalingrad ends the German offensive capacity in the East. "
    "Both happen within three months of each other.\n\n"
    "**Causal chain:** Montgomery's score peaks; Rommel's collapses. "
    "The rival edge between them delivers the cleanest payoff in the war's "
    "first half. Zhukov's Stalingrad encirclement is the Eastern Front's "
    "decisive moment — 300,000 Germans surrounded is a wound Germany cannot heal. "
    "The engine correctly scores both as the war's major inflection point."
)

# ── Session 8: Sicily, Italy, Mussolini Falls (1943) ─────────────────────────
log_f(F["Fascist Italy"], 8,
    "Operation Husky (July 1943): Allied forces invade Sicily. "
    "On July 25, Mussolini is voted out by his own Grand Council, "
    "arrested by King Victor Emmanuel III, and imprisoned. "
    "Italy's new government opens secret armistice negotiations. "
    "Italy surrenders on September 8, 1943. Germany occupies northern Italy "
    "and installs Mussolini as puppet ruler of the Italian Social Republic "
    "after a German commando raid rescues him from mountain imprisonment.",
    polarity="positive", intensity=3, event_type="combat", ripple=True)

log_n(N["Benito Mussolini"], 8,
    "Mussolini's fall is sudden and ignominious: voted out by his own council, "
    "arrested by the king he served for twenty years. The German rescue gives him "
    "a final act as puppet, but real power is gone. "
    "He is captured by Italian partisans on April 27, 1945, "
    "attempting to escape to Switzerland. He and his mistress are shot "
    "the following day. Their bodies are hung upside down in Milan.",
    polarity="positive", intensity=3, event_type="politics", ripple=True)

log_n(N["Dwight D. Eisenhower"], 8,
    "Eisenhower commands the Sicily invasion and the subsequent Italian campaign. "
    "The Italian front bogs down against the German Gustav Line — "
    "Monte Cassino is besieged for five months. The Italian campaign "
    "ties down German divisions but at enormous Allied cost. "
    "It is strategically important and operationally agonizing.",
    polarity="positive", intensity=2, event_type="combat", ripple=True)

db.post_journal(SLUG, 8, "2024-01-01",
    "**Session 8 — Sicily, Italy, Mussolini Falls (1943)**\n\n"
    "The first Axis partner collapses. Italy's defection is strategically "
    "significant (it opens the Mediterranean and forces German redeployment) "
    "but tactically costly — fighting up the Italian boot is some of the "
    "most grueling combat of the war.\n\n"
    "**Causal chain:** Mussolini's fall ripples through the Axis alliance. "
    "The ally edge between Hitler and Mussolini, already strained by "
    "Italy's military failures, reaches its lowest point. "
    "The engine records this correctly: Mussolini's scores collapse "
    "as Allied scores in the Mediterranean improve."
)

# ── Session 9: D-Day and Liberation (June–December 1944) ─────────────────────
log_n(N["Dwight D. Eisenhower"], 9,
    "Operation Overlord, June 6, 1944: the largest amphibious assault in history. "
    "156,000 Allied troops land on five Normandy beaches. "
    "[[Normandy — Omaha Beach|Omaha Beach]] costs 2,000 American casualties in a single morning. "
    "By nightfall, the Allies have a foothold in France. "
    "The night before, [[Dwight D. Eisenhower]] prepares a message for if the operation fails: "
    "'Our landings have failed... If any blame or fault attaches to the attempt, "
    "it is mine alone.' He writes it. He does not need to send it.",
    polarity="positive", intensity=3, event_type="combat", ripple=True,
    location_id=L["Normandy — Omaha Beach"])

log_n(N["George S. Patton"], 9,
    "Operation Cobra (July 1944): [[George S. Patton]]'s Third Army breaks out of Normandy "
    "and races across France — 600 miles in two weeks, the fastest advance "
    "in the history of armored warfare. Patton outstrips his supply lines "
    "and is eventually halted by fuel shortages. He argues — correctly — "
    "that if given the fuel he could end the war by Christmas. "
    "He is not given the fuel. The war does not end by Christmas.",
    polarity="positive", intensity=3, event_type="combat", ripple=True,
    location_id=L["Normandy — Omaha Beach"])

log_n(N["Charles de Gaulle"], 9,
    "Paris is liberated on August 25, 1944. De Gaulle insists that French "
    "forces enter the city first. He then walks down the Champs-Élysées "
    "on foot, in full uniform, under sniper fire from Vichy holdouts, "
    "in front of two million people. The scene is deliberate theater: "
    "it establishes that France liberated itself, not that it was liberated. "
    "The distinction matters enormously to de Gaulle.",
    polarity="positive", intensity=3, event_type="other", ripple=True)

log_f(F["Nazi Germany"], 9,
    "July 20, 1944: German officers plant a bomb in Hitler's conference room. "
    "It explodes. Hitler survives — the briefcase was moved, deflecting the blast "
    "behind a table leg. The conspirators are arrested, tortured, and executed. "
    "Rommel, implicated, is given the choice of a people's court or private suicide. "
    "He takes the poison on October 14. Germany buries him with full military honors.",
    polarity="negative", intensity=3, event_type="betrayal", ripple=True)

db.post_journal(SLUG, 9, "2024-01-01",
    "**Session 9 — D-Day and Liberation (1944)**\n\n"
    "The war's climactic Allied operation. D-Day is the result of two years "
    "of argument — Churchill wanted to fight in the Mediterranean; "
    "the Americans wanted to cross the Channel. The Americans were right.\n\n"
    "**Causal chain:** Patton's breakout delivers what Eisenhower's coalition "
    "building makes possible. De Gaulle's Paris entry is the political payoff. "
    "The July 20 plot reveals the Wehrmacht's own crisis of faith — "
    "senior officers try to kill their Führer. Rommel's death is the "
    "engine's most complex inter-NPC event: the ally edge between Rommel "
    "and Hitler terminates with the poison capsule."
)

# ── Session 10: The Eastern Colossus and V-E Day (1944–1945) ─────────────────
log_n(N["Georgy Zhukov"], 10,
    "Operation Bagration (June 1944): the Soviet summer offensive destroys "
    "Army Group Centre — 17 German divisions annihilated, 350,000 casualties. "
    "It is the largest defeat in German military history, larger than Stalingrad, "
    "happening at the same time as D-Day. "
    "The Red Army advances 400 miles in two months. "
    "By early 1945, Zhukov is 40 miles from Berlin.",
    polarity="positive", intensity=3, event_type="combat", ripple=True)

log_n(N["Adolf Hitler"], 10,
    "The Battle of the Bulge (December 1944): Germany's last western offensive. "
    "30 German divisions strike through the Ardennes in the American sector. "
    "The Americans are surprised, bent, and do not break. "
    "Bastogne holds. Patton turns his entire army ninety degrees in winter "
    "and relieves it in seventy-two hours. "
    "The Bulge costs Germany its last operational reserves. "
    "Hitler retreats to his Berlin bunker and does not emerge again.",
    polarity="negative", intensity=3, event_type="combat", ripple=True)

log_n(N["Georgy Zhukov"], 10,
    "Berlin falls to the Red Army on May 2, 1945. "
    "[[Adolf Hitler]] dies by suicide on April 30 — a gunshot wound and cyanide, "
    "with Eva Braun, in the Führerbunker. "
    "Their bodies are burned in the garden above. "
    "Germany signs unconditional surrender on May 8, 1945. "
    "V-E Day. The war in Europe is over.",
    polarity="positive", intensity=3, event_type="combat", ripple=True,
    location_id=L["The Berlin Bunker"])

log_n(N["Adolf Hitler"], 10,
    "[[Adolf Hitler]] kills himself in the Führerbunker on April 30, 1945, "
    "as [[Soviet Union|Soviet]] forces fight street by street through Berlin. "
    "He has governed [[Nazi Germany|Germany]] for twelve years, started a war that kills "
    "seventy to eighty-five million people, and presided over the "
    "deliberate murder of six million Jews. "
    "He dies blaming everyone else.",
    polarity="positive", intensity=3, event_type="other", ripple=True,
    location_id=L["The Berlin Bunker"])

db.post_journal(SLUG, 10, "2024-01-01",
    "**Session 10 — The Eastern Colossus and V-E Day (1945)**\n\n"
    "The war in Europe ends where it was decided — on the Eastern Front. "
    "Operation Bagration is larger than D-Day, less photographed, and "
    "more decisive. The Soviet contribution to defeating Germany is "
    "proportionally the largest of any Allied nation.\n\n"
    "**Causal chain:** Hitler's score reaches its floor. "
    "The rival edge between Zhukov and Hitler terminates in the ruins of Berlin. "
    "Germany's surrender on May 8 closes all open rivalries in the European theater. "
    "The engine's European map reaches its final state: "
    "every Axis entity at war or hostile; every Allied entity improved."
)

# ── Session 11: Himmler, the Holocaust, and the Liberation of the Camps ───────
log_n(N["Heinrich Himmler"], 11,
    "The Holocaust reaches its industrial peak in 1942–1944 at [[Auschwitz|Auschwitz-Birkenau]], "
    "Treblinka, Sobibor, Belzec, Chelmno, and Majdanek. "
    "Six million Jews are murdered — two-thirds of [[Occupied Europe|European Jewry]]. "
    "The killing does not stop when Germany begins losing the war; "
    "it accelerates. [[Heinrich Himmler]]'s SS continues deportations to the gas chambers "
    "until the camps are liberated by Allied forces in 1945.",
    polarity="negative", intensity=3, event_type="other",
    visibility="dm_only", ripple=True,
    location_id=L["Auschwitz"])

log_f(F["Occupied Europe"], 11,
    "Allied forces liberate the concentration camps in spring 1945: "
    "Buchenwald (April 11), Bergen-Belsen (April 15), Dachau (April 29). "
    "[[Dwight D. Eisenhower]] orders every available soldier and nearby German civilian "
    "to tour the camps. He cables Washington: the evidence is 'beyond the "
    "American mind to comprehend.' He wants witnesses. He is afraid "
    "that someday someone will say this did not happen.",
    polarity="positive", intensity=3, event_type="discovery", ripple=True,
    location_id=L["Auschwitz"])

log_n(N["Heinrich Himmler"], 11,
    "In the war's final weeks, Himmler secretly contacts the World Jewish Congress "
    "and Allied representatives through a Swedish intermediary — "
    "offering to exchange Jews for trucks, then offering to surrender "
    "Germany's forces in the west to the Americans. "
    "He believes, even now, that the Western Allies will accept a "
    "separate peace against the Soviet Union. "
    "Hitler strips him of all offices when he learns of this. "
    "Himmler is captured by British forces in disguise and bites down "
    "on a cyanide capsule on May 23, 1945.",
    polarity="positive", intensity=2, event_type="politics", ripple=True)

db.post_journal(SLUG, 11, "2024-01-01",
    "**Session 11 — The Holocaust and Liberation of the Camps**\n\n"
    "The Holocaust is not a sidebar. It is the war's central crime and its "
    "most important fact. Six million Jews murdered, alongside Roma, "
    "disabled people, political prisoners, Soviet POWs, and others. "
    "The machinery of killing runs until the camps are physically liberated.\n\n"
    "**Causal chain:** Himmler's score reaches its absolute floor. "
    "The ripple from the camp liberations reaches every Allied entity — "
    "Eisenhower's insistence on witness is the right instinct. "
    "Himmler's attempted escape and surrender offers are the final record "
    "of a man who built an extermination apparatus and then tried to "
    "trade it for his life. The engine records it as it was: cowardice after atrocity."
)

# ── Session 12: Pacific Endgame — VJ Day (1945) ───────────────────────────────
log_n(N["Douglas MacArthur"], 12,
    "Iwo Jima (February–March 1945): 26,000 American casualties to take "
    "an eight-square-mile island. Okinawa (April–June 1945): 50,000 American "
    "casualties, 110,000 Japanese killed, 100,000 Okinawan civilians dead. "
    "The math of invading the Japanese home islands — Operation Downfall — "
    "projects 250,000 to one million Allied casualties. "
    "MacArthur is assigned to command it.",
    polarity="negative", intensity=3, event_type="combat", ripple=True)

log_n(N["Harry S. Truman"], 12,
    "[[Harry S. Truman]] authorizes the use of atomic bombs on [[Imperial Japan|Japan]]. "
    "[[Hiroshima]]: August 6, 1945. One bomb kills 80,000 people immediately; "
    "total deaths reach 135,000. Nagasaki: August 9. "
    "On August 8, the [[Soviet Union]] declares war on Japan and invades Manchuria. "
    "Japan faces atomic annihilation and Soviet invasion simultaneously. "
    "Truman's calculation — that the bombs save more lives than an invasion — "
    "is argued about for the rest of the century.",
    polarity="positive", intensity=3, event_type="other", ripple=True,
    location_id=L["Hiroshima"])

log_n(N["Emperor Hirohito"], 12,
    "[[Emperor Hirohito]] records a message on August 14, 1945 — the first time "
    "a Japanese emperor has spoken directly to the people. "
    "The army briefly attempts to seize the recording and prevent surrender. "
    "They fail. The broadcast goes out August 15: [[Imperial Japan|Japan]] has decided to "
    "'endure the unendurable and suffer the insufferable.' "
    "He does not say 'surrender.' He does not need to.",
    polarity="positive", intensity=3, event_type="dialogue", ripple=True,
    location_id=L["Hiroshima"])

log_n(N["Douglas MacArthur"], 12,
    "Japan formally surrenders on the deck of the USS Missouri in Tokyo Bay "
    "on September 2, 1945. MacArthur accepts the surrender and signs for the "
    "Allied Powers. He speaks: 'It is my earnest hope — indeed the hope of "
    "all mankind — that from this solemn occasion a better world shall emerge.' "
    "The war is over. Total dead: seventy to eighty-five million people.",
    polarity="positive", intensity=3, event_type="other", ripple=True)

log_f(F["Imperial Japan"], 12,
    "Japan surrenders unconditionally. The Empire of Japan is dissolved. "
    "MacArthur oversees the occupation and reconstruction of Japan with "
    "pragmatic brilliance: Hirohito is retained as symbolic figurehead, "
    "the military is abolished, a democratic constitution is written. "
    "Japan becomes a US ally within a decade.",
    polarity="positive", intensity=3, event_type="politics", ripple=True)

db.post_journal(SLUG, 12, "2024-01-01",
    "**Session 12 — Pacific Endgame: VJ Day (September 2, 1945)**\n\n"
    "The war ends where it began in the Pacific — with a decision made "
    "by one man and delivered from the air. Whether the atomic bombs were "
    "necessary is the most argued question of the twentieth century. "
    "What is not argued: they ended the war.\n\n"
    "**Causal chain:** Truman inherits a war he did not start and makes "
    "a decision no one else would have to make. Hirohito's radio address "
    "is the moment the engine has been building toward: the hostile faction "
    "surrenders. The rival edges between Imperial Japan and every Allied "
    "entity go quiet. MacArthur on the deck of the Missouri is the final "
    "positive ripple in the Pacific map.\n\n"
    "Total dead: seventy to eighty-five million people. "
    "The engine cannot hold that number. Neither can we."
)

# ── Location log entries ───────────────────────────────────────────────────────

log_l(L["London and Whitehall"], 3,
      "[[Winston Churchill]] refuses armistice. He tells the War Cabinet: 'If this long island story of ours is to end at last, let it end only when each one of us lies choking in his own blood upon the ground.' The cabinet stands and cheers. [[Great Britain]] will not negotiate.",
      polarity="positive", intensity=3, event_type="dialogue",
      actor_id=N["Winston Churchill"], actor_type="npc")

log_l(L["Pearl Harbor"], 5,
      "[[Isoroku Yamamoto]]'s carrier fleet attacks at dawn. 18 warships sunk or damaged. 2,403 Americans killed. The three US aircraft carriers are not in port — they are at sea. [[Isoroku Yamamoto|Yamamoto]] knows this. [[Adolf Hitler]] declares war on the [[United States]] four days later. He was not required to.",
      polarity="negative", intensity=3, event_type="combat")

log_l(L["Stalingrad"], 7,
      "[[Georgy Zhukov]]'s Operation Uranus encircles 300,000 German troops. [[Adolf Hitler]] forbids retreat. The relief attempt fails. Field Marshal Paulus surrenders on January 31, 1943 with 91,000 survivors. The myth of German invincibility is over.",
      polarity="positive", intensity=3, event_type="combat",
      actor_id=N["Georgy Zhukov"], actor_type="npc")

log_l(L["Normandy — Omaha Beach"], 9,
      "156,000 Allied troops land on five beaches. Omaha costs 2,000 American casualties in a morning. [[Dwight D. Eisenhower]] carries a message in his pocket for if the operation fails. By nightfall, the Allies are ashore. He does not need to send it.",
      polarity="positive", intensity=3, event_type="combat",
      actor_id=N["Dwight D. Eisenhower"], actor_type="npc")

log_l(L["Auschwitz"], 11,
      "[[Heinrich Himmler]]'s SS operates the killing machinery at peak capacity through 1942-44. The camp is liberated by Soviet forces on January 27, 1945. [[Dwight D. Eisenhower]] orders every available soldier to tour the camps. He wants witnesses. He is afraid that someday someone will say this did not happen.",
      polarity="negative", intensity=3, event_type="discovery",
      visibility="dm_only")

log_l(L["The Berlin Bunker"], 10,
      "[[Adolf Hitler]] dies here on April 30, 1945, as Soviet forces fight street by street above him. Cyanide and a gunshot, with Eva Braun. Their bodies are burned in the garden. Germany holds on for eight more days.",
      polarity="positive", intensity=3, event_type="other",
      actor_id=N["Georgy Zhukov"], actor_type="npc")

log_l(L["Hiroshima"], 12,
      "[[Harry S. Truman]] orders the bomb. August 6, 1945. 80,000 dead immediately. Nagasaki on August 9. On August 15, [[Emperor Hirohito]] speaks to his people in a voice they have never heard. He does not say 'surrender.' Japan surrenders.",
      polarity="positive", intensity=3, event_type="other",
      actor_id=N["Harry S. Truman"], actor_type="npc")

print("  Location logs complete")

print("\nWorld War II campaign seeded successfully.")
print("To deploy to Pi:  rsync -av campaigns/ww2/ simonhans@raspberrypi:/mnt/serverdrive/coding/rippleforge/campaigns/ww2/")
