# QuestLog

A campaign-agnostic CRM (Campaign Relationship Manager) for tabletop RPGs. Track your party, assets, world relationships, and story across any system.

## Live

`https://questlog.duckdns.org`

Also accessible at `https://game-ranking.duckdns.org/questbook/` (legacy path).

## Concept

QuestLog is not a character sheet replacement. It does not track spell slots, inventory weight, ability scores, or combat mechanics — those live in your VTT or character sheet.

What it tracks:

- **Party** — who is in the party, their status, and brief notes
- **Assets** — shared resources: currency, items, ships (weapon loadouts + HP tracking), stronghold, property
- **World** — NPCs and factions, each with a relationship status and running interaction log
- **Story** — quest log with objectives, status tracking, and session history
- **References** — rulebook tables and notes, editable per campaign

The interaction log is the core feature: every meaningful encounter with an NPC or faction gets a one-line entry tied to a session number, building a full relationship history over time.

---

## User Accounts

QuestLog uses username/password login. Users only see campaigns they own.

Accounts are stored in `users.json` at the repo root with werkzeug pbkdf2-hashed passwords.

To add a user, generate a hash and edit `users.json`:

```bash
python3 -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('yourpassword'))"
```

```json
{
  "users": {
    "username": {
      "password_hash": "<hash>",
      "display_name": "Display Name"
    }
  }
}
```

---

## Campaigns

### Ownership

Each `campaign.json` has an `"owner"` field (username). Non-demo campaigns are only accessible to their owner. Demo campaigns (marked `"demo": true`) are accessible to all users as templates.

### Starting a Campaign

From the index page:
- **Start from Scratch** — clone the Blank Campaign template
- **Starter Campaigns** — clone a pre-populated system-specific demo (D&D 5e, PF2e, Blades in the Dark)

Cloning copies the full campaign folder, assigns ownership to the current user, and generates a unique slug (`pabtso-a3f2b1`). The DM is auto-logged-in and redirected to the DM dashboard.

### Player Share Link

From the DM dashboard → **Player Share Link**: generate a token URL (`/share/<token>`). Players visit the link, get a read-only session, and can browse the campaign without creating an account. Regenerating the link invalidates the old one.

---

## DM Mode

Each campaign has a DM PIN set in `campaign.json`. Log in via the **DM** link in the nav.

When authenticated as DM:

- **Reveal/hide** entities from players (NPCs, factions, quests, party members)
- **Add/edit/delete** NPCs, factions, quests, party members, assets, ships, weapons
- **Edit objectives** — toggle done, edit text, delete individual objectives
- **Edit quest description** inline from the story page
- **Edit ship details** — name, type, HP, notes, crew, cargo (add/remove)
- **Edit stronghold** — name, type, location, condition, notes, features, upgrades; delete stronghold
- **Delete ship** — remove a ship entirely from DM Controls
- **Session Plan** — write in markdown, rendered on the DM dashboard
- **Session Notes** — freeform textarea; use Export .md to save as next session plan
- **✦ Generate Recap** — AI-generated player-facing session recap from notes (Claude Haiku)
- **Campaign Settings** — rename campaign, update system and description
- **Delete Campaign** — permanent, requires typing campaign name to confirm (owner only)

To exit DM mode: **Exit DM** in the nav or the logout button on the dashboard.

---

## Hidden Entities

All entities support `"hidden": true`. Hidden entities are visible only to the DM — players see nothing until revealed.

Demo campaign entities all start hidden. The DM reveals them as the story unfolds using the **Reveal to Players** button on each entity's detail page (NPCs, factions) or in the quest's DM Controls (story page). Hidden entities appear dimmed on the World page with a "Hidden" badge.

---

## Assets

### Ships

Ships track name, type, HP, crew, cargo, notes, and weapons. Weapon HP is trackable by players without DM login.

DM controls on the Assets page allow editing all ship fields, adding/removing crew and cargo members, and adding weapons after creation.

### Stronghold

A single stronghold per campaign. Fields: name, type, location, condition, notes, features (list), upgrades (list). DM can add/remove individual features and upgrades.

---

## URL Structure

```
/login                       Login page
/                            My Campaigns + Start a Campaign (login required)
/share/<token>               Player read-only access via share link
/demo/<slug>/clone           Clone a demo campaign (POST)

/<slug>/                     Campaign home
/<slug>/party                Full party roster
/<slug>/assets               Currency, items, ships, stronghold
/<slug>/world                NPC and faction overview
/<slug>/world/npc/<id>       NPC detail + interaction log
/<slug>/world/faction/<id>   Faction detail + interaction log
/<slug>/story                Quest log grouped by status
/<slug>/references           Rulebook reference tables

/<slug>/dm                   DM dashboard (PIN required)
/<slug>/dm/log               Post-session logging tool
/<slug>/dm/login             DM PIN entry
/<slug>/dm/logout            Exit DM mode
```

---

## Data Model

Each campaign is a folder under `campaigns/<slug>/`:

```
campaigns/
  my-campaign/
    campaign.json        name, system, slug, description, owner, dm_pin, share_token
    party.json           characters array
    assets.json          currency, items, ships, stronghold, property
    world/
      npcs.json          npcs array
      factions.json      factions array
    story/
      quests.json        quests array
    references.json      optional lookup tables
    dm/
      session.json       session plan (markdown) + notes
```

### campaign.json

```json
{
  "name": "My Campaign",
  "system": "D&D 5e",
  "slug": "my-campaign",
  "description": "Optional one-liner.",
  "created": "2026-04-19",
  "owner": "username",
  "dm_pin": "1234",
  "share_token": "abc123..."
}
```

Add `"demo": true` instead of `"owner"` for template campaigns.

### assets.json

```json
{
  "currency": { "gold": 0 },
  "items": [{ "name": "Rope (50 ft)", "notes": "" }],
  "ships": [
    {
      "name": "The Osprey",
      "type": "Sloop",
      "hp": "80/80",
      "crew": ["Captain Vex"],
      "weapons": [{ "name": "Ballista #1", "hp": 50, "max_hp": 50 }],
      "cargo": ["50 barrels of ale"],
      "notes": ""
    }
  ],
  "stronghold": {
    "name": "The Old Keep",
    "type": "Fortress",
    "location": "Phandalin",
    "condition": "Ruined",
    "notes": "",
    "features": ["Great hall", "Dungeon"],
    "upgrades": ["Reinforced gate"]
  },
  "property": []
}
```

### story/quests.json

```json
{
  "quests": [
    {
      "id": "missing_merchant",
      "title": "The Missing Merchant",
      "status": "active",
      "description": "Torvald vanished on the road to Millhaven.",
      "hidden": false,
      "objectives": [
        { "text": "Find out what happened", "done": false }
      ],
      "log": [
        { "session": 1, "note": "Quest picked up from Mara." }
      ]
    }
  ]
}
```

Status options: `active`, `complete`, `failed`

### dm/session.json

```json
{
  "plan": "# Session Plan\n\n## Beat 1...",
  "notes": ""
}
```

Notes export as `.md` for direct use as next session's plan.

---

## AI Session Recap

The DM dashboard includes a **✦ Generate Recap** button. After writing session notes, click it to generate a player-facing chronicle-style recap using Claude Haiku (Anthropic API).

Requires `ANTHROPIC_API_KEY` in a `.env` file at the repo root:

```
ANTHROPIC_API_KEY=sk-ant-...
```

The `.env` is gitignored. If the key is missing the button will return a 500 error.

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

## Deploying to Raspberry Pi

Deploy individual changed files:

```bash
rsync -av /path/to/file simonhans@raspberrypi:/home/simonhans/coding/questbook/path/to/file
ssh simonhans@raspberrypi "sudo systemctl restart questbook"
```

Or sync everything:

```bash
rsync -av --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' \
  ~/coding/questbook/ simonhans@raspberrypi:~/coding/questbook/
ssh simonhans@raspberrypi "sudo systemctl restart questbook"
```

### Systemd service

`/etc/systemd/system/questbook.service`:

```ini
[Service]
User=simonhans
WorkingDirectory=/home/simonhans/coding/questbook
ExecStart=/home/simonhans/coding/questbook/venv/bin/python app.py
Environment=FLASK_ENV=production
Environment=QUESTBOOK_PREFIX=
Environment=QUESTBOOK_SECRET=<hex secret>
```

Generate a secret: `python3 -c "import secrets; print(secrets.token_hex(32))"`

### nginx

Configured in `/etc/nginx/sites-enabled/default` (certbot-managed). Routes `questlog.duckdns.org` → `127.0.0.1:5052`. Do not expose port 5052 directly.
