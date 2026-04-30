# RippleForge

A causality engine for narrative. Characters, factions, and events form a relationship graph — log one event, and every connected entity feels it automatically. Cause propagates. Consequence compounds. The world keeps moving.

Use it for tabletop campaigns, novels, historical timelines, alternate histories, or any story where what happens to one character ripples through everyone else.

## Live

`https://rippleforge.gg`

Try it: `https://rippleforge.gg/demo/`

---

## What it does

RippleForge is not a note-taking tool or character sheet replacement. It models **cause and effect** across a narrative world.

- **Ripple system** — log one event against any entity, and every connected character and faction updates automatically based on their relationship (allies share the impact, rivals feel the opposite)
- **AI event parsing** — paste raw session notes, chapter summaries, or historical records; get structured log entries matched to known entities with polarity and intensity assigned
- **Projected consequences** — AI reads every active tension in the world and forecasts what happens next; Narrator reviews, selects, commits
- **World diff** — every commit shows a before/after snapshot: score changes, relationship label shifts, entries added
- **Intelligence layer** — algorithmic ranked lists of active pressure, consequence risk, stale threads, and narrative gaps; no manual curation
- **Per-player fog of war** — each character knows only what they've witnessed; author can preview the world through any character's eyes
- **Ripple chain view** — visual cause→effect chains showing every downstream consequence of any source event
- **Dual-axis relationships** — entities (NPCs, factions, party members) can have a formal relationship that differs from a personal one; both are rendered as separate arcs in the graph so you can see the tension at a glance
- **Branching timelines** — fork from any point and write alternate histories inside the same world; switch between timelines to compare how the graph diverges

RippleForge does not invent narrative. AI proposes; Narrator approves; the world updates.

---

## Concept: AI as referee

The AI role is constraint enforcement, not storytelling:

- **Summarization** — compresses session notes into a chronicle
- **Event parsing** — extracts discrete world events from freeform notes or text
- **Consequence projection** — given current world state, predicts what logically follows
- **Narrator always approves** — nothing is written without explicit commit

---

## Starter Worlds

Three cloneable demo campaigns show the system across domains:

| World | Domain | Sessions |
|-------|--------|---------|
| The Iliad | Epic fiction | 8 books |
| The Book of Genesis | Biblical fiction | 15 |
| World War II | Historical (1933-1945) | 12 |
| The Ashcroft Vein | Original TTRPG fiction | 5 |
| Paladin's Grace | Original TTRPG fiction | 4 |

The Ashcroft Vein doubles as the demo source (`DEMO_SOURCE=ashford`).

**Note on share links:** Each starter world has a read-only `/share/<token>` URL. The token is stored in `campaign.json` and regenerates every time the seed script runs. After any re-seed, retrieve the new token from `campaigns/<slug>/campaign.json` on the Pi and update any hardcoded links in `templates/landing.html`.

---

## User Accounts

Username/password login for existing alpha testers. Google OAuth planned for public launch (replaces invite-gated signup).

Accounts stored in `users.json` at repo root with werkzeug pbkdf2-hashed passwords.

```bash
python3 -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('yourpassword'))"
```

```json
{
  "users": {
    "username": { "password_hash": "<hash>", "display_name": "Display Name", "ai_enabled": true }
  }
}
```

**AI gate:** AI features (`/dm/session/recap`, `/dm/session/propose`, `/dm/world/futures`) require `ai_enabled: true` on the user account. New signups default to `false`. Kickstarter backers redeem a code at `/redeem` to unlock. Admin generates codes by tier at `/admin/ks-codes`.

---

## Worlds (Campaigns)

Each world is a folder under `campaigns/<slug>/`. Three access modes:

| Mode | Flag in campaign.json | Who can write |
|------|----------------------|---------------|
| Normal | `"owner": "username"` | Owner + Narrator PIN |
| Public (read-only) | `"public": true` | Nobody (Narrator login still works) |
| Demo | `"demo_mode": true` | Everyone |

### Starting a World

From the index page: clone a Blank World or a starter template. Cloning copies the full folder, assigns ownership, and generates a unique slug.

### Player/Reader Share Link

Narrator dashboard → **Share Link**: generates a token URL. Readers browse read-only without an account.

---

## Demo

`/demo/` is a live writable copy of The Ashcroft Vein (original fiction, no third-party IP). Resets every 30 minutes.

The demo includes a 4-step guided tour (world → ripples → AI tools → timeline forking) and an AI tools page at `/demo/ai`.

**Parse limit:** Visitors get 3 free live parses. Tracked via `demo_id` cookie (30-day) + `campaigns/demo_parse_counts.json`. Survives resets and new tabs.

---

## Narrator Mode

Log in via the **Narrator** link in the nav. Each world has a Narrator PIN in `campaign.json`.

Narrator dashboard (top to bottom):

1. **World State** — intelligence grid: Active Pressure / Consequence Risk / Stale Threads / Narrative Gaps
2. **What happens next? ✦** — AI projects 2–3 consequences from current world tensions; checkboxes + Commit writes them as `PROJECTED` log entries and shows a world diff
3. **Session Tools** — plan (markdown) + notes; notes card has ✦ Generate Recap and ✦ Parse into Events
4. **Proposed Events** — AI parse output; Narrator reviews/edits/rejects, Commit logs with full ripple propagation
5. **Player Recap** — AI-generated chronicle recap; post to journal
6. **Session Delta** — all events from session N grouped by entity
7. **Quick Log** — inline logging with tone, weight, visibility, ripple checkbox
8. **World / Ships / Add New / Share / Settings / Danger Zone**

Danger Zone contains **Delete World** (not "Delete Campaign") — requires typing the world name to confirm.

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

All AI routes require Narrator auth **and** `ai_enabled: true` on the user account (or `admin: true`).

### Event parsing — entity types

| entity_type | Commit behavior | Notes |
|-------------|----------------|-------|
| `npc` | `log_npc()` + ripple | Auto-creates hidden entity if unknown |
| `faction` | `log_faction()` + ripple | Auto-creates hidden faction if unknown |
| `ship` | `log_ship()` (matched by name) | No ripple; no auto-create |

---

## URL Structure

```
/                            Login page / My worlds (authenticated)
/demo/                       Live writable demo
/demo/ai                     AI tools demo page
/demo/reset                  Force reset demo (POST)
/share/<token>               Read-only via share link

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

/<slug>/dm                   Narrator dashboard
/<slug>/dm/log               Post-session logging tool
/<slug>/dm/login             Narrator PIN entry
/<slug>/branch/create        Create alternate timeline branch (POST)
/<slug>/branch/switch        Switch active branch (POST)
/<slug>/branch/delete        Delete branch + purge entries (POST)
```

---

## Data Model

```
campaigns/<slug>/
  campaign.json        name, system, slug, owner, dm_pin, share_token, demo, branches[]
  party.json           characters: [{name, assigned_user, known_events, ...}]
  assets.json          currency, items, ships[{name, type, log[]}], stronghold
  world/
    npcs.json          npcs: [{id, name, role, relationship, log, hidden, factions, relations}]
    factions.json      factions: [{id, name, relationship, log, hidden, relations}]
  story/
    quests.json
  dm/
    session.json       plan (markdown), notes
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
  "branch": "br_ef30f2"
}
```

`event_type` is freeform. Reserved: `projected` (AI-committed consequence projection).
`branch` is only present on entries belonging to an alternate timeline branch.

### Relationship computation

`compute_npc_relationship(npc)` — decay-weighted score from polarity events. Score thresholds: `allied` (≥6), `friendly` (≥3), `neutral` (≥−3), `hostile` (<−3). Decay: `0.85^age_in_sessions`.

### Branch filtering

When viewing branch X forked at session N:
- Include main timeline entries where `session <= N` and no `branch` field
- Include entries where `branch == X` (any session)
- Exclude main timeline entries after session N

---

## Setup

```bash
cd questbook
python3 -m venv venv
venv/bin/pip install flask markdown werkzeug anthropic python-dotenv flask-limiter
venv/bin/python app.py
```

Runs at `http://localhost:5052`.

---

## Deploy (Raspberry Pi)

```bash
cd questbook && ./deploy.sh
```

`deploy.sh` rsyncs all non-data files (excludes `venv/`, `campaigns/`, `.env`) and restarts the service. For single-file deploys:

```bash
rsync -av --checksum <file> simonhans@raspberrypi:/mnt/serverdrive/coding/questbook/<relative-path>
ssh simonhans@raspberrypi "sudo systemctl restart questbook"
```

Always use the explicit `/mnt/serverdrive/` path, never `~/coding` (symlink).

Systemd service: `/etc/systemd/system/questbook.service`. nginx routes `rippleforge.gg` → `127.0.0.1:5052`.
