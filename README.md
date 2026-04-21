# RippleForge

A living world simulation engine for tabletop RPG campaigns. Player actions propagate automatically through every connected NPC and faction — the world remembers, and visibly changes.

## Live

`https://rippleforge.gg` — also `https://game-ranking.duckdns.org/questbook/` (legacy)

Try it: `https://rippleforge.gg/demo/`

---

## What it does

RippleForge is not a note-taking tool or character sheet replacement. It models **cause and effect** across your world state.

- **Ripple system** — log one event, and every related NPC and faction updates automatically based on their relationship (allies share the impact, rivals feel the opposite)
- **AI event parsing** — paste messy session notes, get structured log entries matched to known entities with polarity and intensity assigned
- **Projected consequences** — AI reads every active tension in the world and forecasts what happens if the party does nothing; DM reviews, selects, commits
- **World diff** — every commit shows a before/after snapshot: score changes, relationship label shifts, entries added
- **DM intelligence layer** — algorithmic ranked lists of active pressure, consequence risk, stale threads, and narrative gaps; no manual curation
- **Per-player fog of war** — each player sees only what their character knows; DM can preview the world through any character's eyes
- **Ripple chain view** — visual cause→effect chains showing every downstream consequence of any source event

RippleForge does not invent narrative. AI proposes; DM approves; the world updates.

---

## Concept: AI as referee

The AI role is constraint enforcement, not storytelling:

- **Summarization** — compresses session notes into a player-facing chronicle
- **Event parsing** — extracts discrete world events from freeform notes
- **Consequence projection** — given current world state, predicts what logically follows
- **DM always approves** — nothing is written without explicit commit

---

## User Accounts

Username/password login. Users only see campaigns they own.

Accounts stored in `users.json` at repo root with werkzeug pbkdf2-hashed passwords.

```bash
python3 -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('yourpassword'))"
```

```json
{
  "users": {
    "username": { "password_hash": "<hash>", "display_name": "Display Name" }
  }
}
```

---

## Campaigns

Each campaign is a folder under `campaigns/<slug>/`. Three modes:

| Mode | Flag in campaign.json | Who can write |
|------|----------------------|---------------|
| Normal | `"owner": "username"` | Owner + DM PIN |
| Public (read-only) | `"public": true` | Nobody (DM login still works) |
| Demo | `"demo_mode": true` | Everyone |

### Starting a Campaign

From the index page: clone a Blank Campaign or a starter template. Cloning copies the full folder, assigns ownership, and generates a unique slug (`pabtso-a3f2b1`).

### Player Share Link

DM dashboard → **Player Share Link**: generates a token URL. Players browse read-only without an account.

---

## Demo

`/demo/` is a live writable copy of the Lost Mine of Phandelver campaign. It resets from `campaigns/lmop/` every 30 minutes (or on force reset via the banner).

- `campaigns/lmop/` — frozen source, never written to
- `campaigns/demo/` — resettable copy, writable by anyone without login

The demo includes a 3-step guided tour and an AI tools page at `/demo/ai`.

**Parse limit:** Visitors get 3 free live parses with custom notes. Tracked server-side via a persistent `demo_id` cookie (30-day expiry) + `campaigns/demo_parse_counts.json`. Survives demo resets and new tabs — tied to the visitor, not the session.

If the user parses without changing the pre-filled notes, a pre-loaded result (`PARSE_DATA` in `demo_ai.html`) is served instantly — no API call, no counter decrement.

---

## DM Mode

Log in via the **DM** link in the nav. Each campaign has a DM PIN in `campaign.json`.

DM dashboard (top to bottom):

1. **World State** — DM intelligence grid: Active Pressure / Consequence Risk / Stale Threads / Narrative Gaps
2. **What happens next? ✦** — AI projects 2–3 consequences from current world tensions; checkboxes + Commit writes them as `PROJECTED` log entries and shows a world diff
3. **Session Tools** — plan (markdown) + notes; notes card has ✦ Generate Recap and ✦ Parse into Events
4. **Proposed Events** — AI parse output; DM reviews/edits/rejects, Commit logs with full ripple propagation
5. **Player Recap** — AI-generated chronicle recap; post to journal
6. **Session Delta** — all events from session N grouped by entity (← → navigation)
7. **Recent Activity** — entities touched in last 2 sessions
8. **Quick Log** — inline logging with tone, weight, visibility, ripple checkbox
9. **World / Ships / Add New / Share / Settings / Danger Zone**

---

## AI Features

Requires `ANTHROPIC_API_KEY` in `.env` at repo root. Uses `claude-haiku-4-5-20251001`.

| Feature | Route | Description |
|---------|-------|-------------|
| Generate Recap | `POST /<slug>/dm/session/recap` | Player-facing chronicle from session notes |
| Parse into Events | `POST /<slug>/dm/session/propose` | Notes → structured log entries for review |
| Commit parsed | `POST /<slug>/dm/session/commit_proposals` | Write approved entries + trigger ripples |
| What happens next | `POST /<slug>/dm/world/futures` | Consequence projections from world state |
| Commit futures | `POST /<slug>/dm/world/commit_futures` | Write as PROJECTED entries, returns world diff |

All AI routes are `@dm_required`.

### Event parsing — entity types

The parser extracts three entity types from session notes:

| entity_type | Commit behavior | Notes |
|-------------|----------------|-------|
| `npc` | `log_npc()` + ripple | Auto-creates hidden NPC if unknown |
| `faction` | `log_faction()` + ripple | Auto-creates hidden faction if unknown |
| `ship` | `log_ship()` (matched by name) | No ripple; no auto-create; blue badge in UI |

Ships are passed to the AI as known entities. Ship log entries are appended to `assets.json` under `ships[].log[]`. Party members are excluded as entity subjects but their interactions with ships/NPCs are still captured from the target entity's perspective.

---

## URL Structure

```
/                            Login page (unauthenticated) / My campaigns (authenticated)
/demo/                       Live writable demo (LMoP)
/demo/ai                     AI tools demo page
/demo/reset                  Force reset demo (POST)
/lmop/                       LMoP read-only public view
/share/<token>               Player read-only via share link

/<slug>/                     Campaign home
/<slug>/party                Full party roster
/<slug>/assets               Currency, items, ships, stronghold
/<slug>/world                NPC and faction overview
/<slug>/world/ripples        Ripple chain visualization
/<slug>/world/npc/<id>       NPC detail + interaction log
/<slug>/world/faction/<id>   Faction detail
/<slug>/story                Quest log
/<slug>/journal              Session journal
/<slug>/brief                DM briefing (full intelligence report)
/<slug>/references           Rulebook reference tables

/<slug>/dm                   DM dashboard
/<slug>/dm/log               Post-session logging tool
/<slug>/dm/login             DM PIN entry
```

---

## Data Model

```
campaigns/<slug>/
  campaign.json        name, system, slug, owner/demo_mode/public, dm_pin, share_token
  party.json           characters: [{name, assigned_user, known_events, ...}]
  assets.json          currency, items, ships[{name, type, hp, crew, cargo, notes, log[]}], stronghold
  world/
    npcs.json          npcs: [{id, name, role, relationship, log, hidden, faction, relations}]
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
  "note": "Captured by the party.",
  "visibility": "public",
  "polarity": "negative",
  "intensity": 3,
  "event_type": "combat",
  "ripple_source": { "entity_id": "iarno_albrek", "entity_type": "npc", "event_id": "evt_111ddd" }
}
```

`event_type` is freeform. Reserved values: `projected` (AI-committed consequence projection).

### Relationship computation

`compute_npc_relationship(npc)` — decay-weighted score from polarity events. Score thresholds: `allied` (≥4), `friendly` (≥1.5), `neutral` (≥−1.5), `hostile` (<−1.5). Decay: `0.85^age_in_sessions`.

---

## Setup

```bash
cd questbook
python3 -m venv venv
venv/bin/pip install flask markdown werkzeug anthropic python-dotenv
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
