# RippleForge

A causality engine for narrative. Characters, factions, and events form a relationship graph — log one event, and every connected entity feels it automatically. Cause propagates. Consequence compounds. The world keeps moving.

Use it for tabletop campaigns, novels, historical timelines, alternate histories, or any story where what happens to one character ripples through everyone else.

## Live

`https://rippleforge.gg`

Try it: `https://rippleforge.gg/demo/`

---

## What it does

RippleForge is not a note-taking tool or character sheet replacement. It models **cause and effect** across a narrative world.

### As a worldbuilding tool

- **Ripple system** — log one event against any entity, and every connected character and faction updates automatically based on their relationship (allies share the impact, rivals feel the opposite)
- **AI event parsing** — paste raw session notes, chapter summaries, or historical records; get structured log entries matched to known entities with polarity and intensity assigned
- **Projected consequences** — AI reads every active tension in the world and forecasts what happens next; Narrator reviews, selects, commits
- **World diff** — every commit shows a before/after snapshot: score changes, relationship label shifts, entries added
- **Intelligence layer** — algorithmic ranked lists of active pressure, consequence risk, stale threads, and narrative gaps; no manual curation
- **Branching timelines** — fork from any point and write alternate histories inside the same world; switch between timelines to compare how the graph diverges

### As a writing assistant

- **Dual-axis relationships** — formal and personal relationship axes that can conflict; rendered as separate arcs in the world graph
- **Per-player fog of war** — each character knows only what they've witnessed; author can preview the world through any character's eyes
- **Ripple chain view** — visual cause→effect chains showing every downstream consequence of any source event
- **Session brief** — algorithmic pre-session intel: pending futures, active tensions, stale threads, narrative gaps

### As a party game

- **Pass-the-phone collaborative storytelling** — 30-minute session, 2–6 players, no prep
- **Secret objectives** — each player gets a private mission that may conflict with the group's arc; relationship biases (trusts/suspects) add tension
- **AI arc generation** — give the group a genre, place, and faction; the AI writes an arc with three open-ended leads (not linear steps)
- **AI epilogue** — at the end, reveals everyone's secret missions and generates a prose epilogue
- **World persists** — after the game, the campaign lives on as a full RippleForge world

RippleForge does not invent narrative. AI proposes; Narrator approves; the world updates.

---

## Concept: AI as referee

The AI role is constraint enforcement, not storytelling:

- **Summarization** — compresses session notes into a chronicle
- **Event parsing** — extracts discrete world events from freeform notes or text
- **Consequence projection** — given current world state, predicts what logically follows
- **Arc generation** — builds story arcs with open-ended leads for groups to pursue
- **Narrator always approves** — nothing is written without explicit commit

---

## Starter Worlds

Six cloneable demo campaigns show the system across domains:

| World | Domain | Sessions |
|-------|--------|---------|
| The Iliad | Epic fiction | 8 books |
| The Book of Genesis | Biblical fiction | 15 |
| World War II | Historical (1933–1945) | 12 |
| Wars of the Roses | Historical | 9 periods |
| The Ashcroft Vein | Original TTRPG fiction | 5 |
| Paladin's Grace | Original TTRPG fiction | 4 |

The Ashcroft Vein doubles as the demo source (`DEMO_SOURCE=ashford`).

**Note on share links:** Each starter world has a read-only `/share/<token>` URL. The token is stored in `campaign.json` and regenerates every time the seed script runs. After any re-seed, retrieve the new token from `campaigns/<slug>/campaign.json` on the Pi and update any hardcoded links in `templates/landing.html`.

---

## Pricing

| Tier | Price | Worlds |
|------|-------|--------|
| Free | — | 1 world |
| Pro Monthly | $8/mo | 5 worlds + AI features |
| Pro Annual | $76/yr (save $20) | 5 worlds + AI features |
| World add-on | $1 one-time | +1 world (stacks) |
| Party game | 1 free, then $2/game | Non-Pro users |

Players (read-only share link) are always free. Only Narrator accounts pay.

14-day free trial on Pro Monthly.

---

## User Accounts

Google OAuth at `/auth/google` — no password required. Username derived from email prefix on first sign-in.

Username/password login still works for legacy accounts (`users.json`, werkzeug pbkdf2).

```json
{
  "users": {
    "username": {
      "password_hash": "<hash>",
      "display_name": "Display Name",
      "ai_enabled": true,
      "world_limit": 5,
      "party_plays": 0
    }
  }
}
```

**AI gate:** AI features require `ai_enabled: true`. New signups default to `false`. Admin generates KS codes at `/admin/ks-codes`. Users redeem at `/redeem`.

---

## Worlds (Campaigns)

Each world is a folder under `campaigns/<slug>/`. Three access modes:

| Mode | Flag in campaign.json | Who can write |
|------|----------------------|---------------|
| Normal | `"owner": "username"` | Owner + Narrator PIN |
| Public (read-only) | `"public": true` | Nobody (Narrator login still works) |
| Demo | `"demo_mode": true` | Everyone |

Three world modes: `ttrpg` | `fiction` | `historical`. Mode drives all UI labels and nav structure. Party games use `fiction` mode.

---

## Demo

`/demo/` is a live writable copy of The Ashcroft Vein (original fiction, no third-party IP). Resets every 30 minutes.

The demo includes a 4-step guided tour and an AI tools page at `/demo/ai`.

**Parse limit:** Visitors get 3 free live parses. Tracked via `demo_id` cookie (30-day).

---

## Narrator Mode

Log in via the **Narrator** link in the nav. Each world has a Narrator PIN in `campaign.json`.

---

## AI Features

Requires `ANTHROPIC_API_KEY` in `.env` at repo root. Uses `claude-haiku-4-5-20251001`.

| Feature | Route | Description |
|---------|-------|-------------|
| Generate Recap | `POST /<slug>/dm/session/recap` | Chronicle from session notes |
| Parse into Events | `POST /<slug>/dm/session/propose` | Notes → structured log entries for review |
| Commit parsed | `POST /<slug>/dm/session/commit_proposals` | Write approved entries + trigger ripples |
| What happens next | `POST /<slug>/dm/world/futures` | Consequence projections from world state |
| Commit futures | `POST /<slug>/dm/world/commit_futures` | Write as PROJECTED entries, returns world diff |
| Party arc | `POST /<slug>/play/generate-arc` | Generate story arc + 3 open-ended leads |
| Party secrets | `POST /<slug>/play/generate-secrets` | Generate per-character secret objectives |
| Party summary | `POST /<slug>/play/generate-summary` | Generate prose epilogue for done screen |

All narrative AI routes require Narrator auth **and** `ai_enabled: true` (or `admin: true`). Party AI routes are unauthed (rate-limited).

---

## URL Structure

```
/                            Login page / My worlds (authenticated)
/demo/                       Live writable demo
/demo/ai                     AI tools demo page
/share/<token>               Read-only via share link
/welcome                     Party mode entry point (POST choice=party)
/billing                     Subscription management
/billing/checkout/pro        Stripe checkout — monthly Pro
/billing/checkout/pro-annual Stripe checkout — annual Pro
/billing/party/success       Post-payment redirect for $2 party game

/<slug>/                     World home
/<slug>/party                Cast roster
/<slug>/assets               Currency, items, ships, stronghold
/<slug>/world                Entity and faction overview
/<slug>/world/ripples        Ripple chain visualization
/<slug>/world/npc/<id>       Character detail + interaction log
/<slug>/world/faction/<id>   Faction detail
/<slug>/story                Quest / arc log
/<slug>/journal              Session journal
/<slug>/brief                Narrator briefing (full intelligence report)
/<slug>/play                 Party game screen (setup/arc/secrets/play/done)

/<slug>/dm                   Narrator dashboard
/<slug>/dm/login             Narrator PIN entry
/<slug>/branch/create        Create alternate timeline branch (POST)
/<slug>/branch/switch        Switch active branch (POST)
/<slug>/branch/delete        Delete branch + purge entries (POST)
```

---

## Data Model

```
campaigns/<slug>/
  campaign.json        name, system, slug, owner, dm_pin, share_token, mode, terminology, observer_name, branches[]
  party.json           characters: [{name, assigned_user, known_events, ...}]
  assets.json          currency, items, ships[{name, type, log[]}], stronghold
  world/
    npcs.json          npcs: [{id, name, role, relationship, log, hidden, factions, relations}]
    factions.json      factions: [{id, name, relationship, log, hidden, relations}]
    locations.json     locations: [{id, name, role, description, log, hidden, dm_notes}]
  story/
    quests.json
  dm/
    session.json       plan (markdown), notes
    party_game.json    phase, genre, characters, place, faction, arc, history, secret_objectives
  journal.json         {entries: [{session, date, recap}]}
  references.json
```

### Log entry schema

```json
{
  "id": "evt_abc123",
  "session": 4,
  "note": "Allied with the resistance against the occupation.",
  "visibility": "public",
  "polarity": "positive",
  "intensity": 2,
  "event_type": "politics",
  "axis": "formal",
  "actor_id": "iarno_albrek",
  "actor_type": "npc",
  "ripple_source": { "entity_id": "iarno_albrek", "entity_type": "npc", "event_id": "evt_111" },
  "branch": "br_ef30f2",
  "deleted": true
}
```

`event_type` is freeform. Reserved: `projected` (AI-committed consequence projection).
`axis` = `"formal"` | `"personal"` | absent. Only tagged entries feed the dual-axis conflict display.
`deleted: true` = soft-deleted. Never shown or counted in scores. Filter in every code path that reads logs.
`actor_id` / `actor_type` — display context for inter-entity events. Not a scoring exclusion.
`branch` is only present on entries belonging to an alternate timeline branch.

### Relationship computation

`compute_npc_relationship(npc)` — decay-weighted score from all polarity events (0.85^age per session). Score thresholds: `allied` (≥6), `friendly` (≥3), `neutral` (≥−3), `hostile` (<−3). Stored `relationship` field acts as score floor.

---

## Setup

```bash
cd rippleforge
python3 -m venv venv
venv/bin/pip install flask markdown werkzeug anthropic python-dotenv flask-limiter
venv/bin/python app.py
```

Runs at `http://localhost:5052`.

---

## Deploy

**Live site is on DigitalOcean (68.183.130.60). Edits happen on sbook. Two-step deploy:**

**Step 1 — push sbook → Pi:**
```bash
rsync -av --exclude='venv/' --exclude='campaigns/' --exclude='.env' \
  /home/simonhans/coding/rippleforge/ simonhans@raspberrypi:/mnt/serverdrive/coding/rippleforge/
```

**Step 2 — Pi → DO:**
```bash
ssh simonhans@raspberrypi "cd /mnt/serverdrive/coding/rippleforge && ./deploy_do.sh"
```

Skipping step 1 means `deploy_do.sh` pushes the Pi's stale copy — nothing new arrives on the live site.

Systemd service: `/etc/systemd/system/rippleforge.service`. nginx routes `rippleforge.gg` → `127.0.0.1:5052`.
