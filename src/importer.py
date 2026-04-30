import io
import re
import zipfile

FRONTMATTER_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n?', re.DOTALL)

_NPC = {
    'npc', 'npcs', 'character', 'characters', 'person', 'people',
    'cast', 'notable', 'notables', 'personage', 'individuals', 'persons',
}
_FACTION = {
    'faction', 'factions', 'organization', 'organizations', 'org', 'orgs',
    'group', 'groups', 'guild', 'guilds', 'order', 'orders',
    'house', 'houses', 'clan', 'clans', 'nation', 'nations',
    'party', 'parties', 'power', 'powers', 'allegiance', 'allegiances',
}
_QUEST = {
    'quest', 'quests', 'mission', 'missions', 'hook', 'hooks',
    'plot', 'plots', 'adventure', 'adventures', 'arc', 'arcs',
    'thread', 'threads', 'objective', 'objectives',
}
_SKIP = {
    'location', 'locations', 'place', 'places', 'region', 'regions',
    'map', 'maps', 'item', 'items', 'spell', 'spells', 'monster', 'monsters',
    'statblock', 'statblocks', 'template', 'templates', '_templates',
    'attachment', 'attachments', 'asset', 'assets', 'rule', 'rules',
    'calendar', 'session', 'sessions', 'journal', 'journals',
    'note', 'notes', 'daily', 'index', 'readme',
}


def _parse_frontmatter(text):
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm = {}
    for line in m.group(1).splitlines():
        if ':' not in line:
            continue
        key, _, val = line.partition(':')
        key = key.strip().lower()
        val = val.strip().strip('"\'')
        if not key or not val:
            continue
        if val.startswith('[') and val.endswith(']'):
            fm[key] = [v.strip().strip('"\'') for v in val[1:-1].split(',') if v.strip()]
        else:
            fm[key] = val
    return fm, text[m.end():]


def _classify(folder_parts, fm, body):
    # Returns 'npc'|'faction'|'quest'|'skip'|None
    # 'skip' = intentionally ignored type; None = no signal found

    # 1. frontmatter type:
    t = fm.get('type', '').lower()
    for token in re.split(r'[\s_\-]+', t):
        if token in _NPC: return 'npc'
        if token in _FACTION: return 'faction'
        if token in _QUEST: return 'quest'
        if token in _SKIP: return 'skip'

    # 2. folder hierarchy (deepest folder first)
    for part in reversed(folder_parts):
        p = part.lower()
        if p in _NPC: return 'npc'
        if p in _FACTION: return 'faction'
        if p in _QUEST: return 'quest'
        if p in _SKIP: return 'skip'

    # 3. tags (frontmatter + inline)
    tags_fm = fm.get('tags', [])
    if isinstance(tags_fm, str):
        tags_fm = [tags_fm]
    inline_tags = re.findall(r'(?:^|\s)#(\w+)', body, re.MULTILINE)
    all_tags = {t.lower() for t in tags_fm + inline_tags}
    if all_tags & _NPC: return 'npc'
    if all_tags & _FACTION: return 'faction'
    if all_tags & _QUEST: return 'quest'

    return None


def _extract_description(body):
    lines = []
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or line == '---':
            continue
        line = re.sub(r'\[\[(?:[^\]|]+\|)?([^\]]+)\]\]', r'\1', line)
        line = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', line)
        line = re.sub(r'(?:^|\s)#\w+', '', line).strip()
        if line:
            lines.append(line)
    text = ' '.join(lines)
    return (text[:497] + '…') if len(text) > 500 else text


def parse_vault_zip(zip_bytes, max_files=600):
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        raise ValueError("Not a valid zip file.")

    md_files = [
        n for n in zf.namelist()
        if n.endswith('.md')
        and '/__MACOSX/' not in n
        and '/.' not in n
        and not n.startswith('.')
    ]
    if not md_files:
        raise ValueError("No markdown files found in zip.")

    # Strip common single root-folder prefix (e.g. "MyVault/...")
    top_dirs = {n.split('/')[0] for n in md_files if '/' in n}
    root = (top_dirs.pop() + '/') if len(top_dirs) == 1 else ''

    npcs, factions, quests, skipped = [], [], [], []
    seen = set()

    for filepath in md_files[:max_files]:
        rel = filepath[len(root):] if filepath.startswith(root) else filepath
        parts = rel.split('/')
        filename = parts[-1]
        folder_parts = parts[:-1]

        if filename.startswith(('_', '.')):
            continue

        name = filename[:-3].strip()
        if not name:
            continue

        try:
            info = zf.getinfo(filepath)
            if info.file_size > 500_000:  # skip files > 500 KB uncompressed
                continue
            content = zf.read(filepath).decode('utf-8', errors='replace')
        except Exception:
            continue

        fm, body = _parse_frontmatter(content)
        display_name = (fm.get('name') or name).strip()
        entity_type = _classify(folder_parts, fm, body)

        if entity_type == 'skip':
            skipped.append({'name': display_name, 'source': rel,
                            'reason': 'Location, item, session, or template — intentionally skipped'})
            continue
        if entity_type is None:
            skipped.append({'name': display_name, 'source': rel,
                            'reason': 'No signal — add frontmatter `type: npc` or tag `#npc` to include'})
            continue

        key = (entity_type, display_name.lower())
        if key in seen:
            skipped.append({'name': display_name, 'source': rel, 'reason': 'Duplicate name'})
            continue
        seen.add(key)

        desc = _extract_description(body)

        if entity_type == 'npc':
            role = (fm.get('role') or fm.get('occupation') or fm.get('class')
                    or fm.get('title') or '').strip()
            faction_name = (fm.get('faction') or fm.get('organization')
                            or fm.get('group') or '').strip()
            npcs.append({'name': display_name, 'role': role,
                         'faction_name': faction_name, 'description': desc, 'source': rel})
        elif entity_type == 'faction':
            factions.append({'name': display_name, 'description': desc, 'source': rel})
        elif entity_type == 'quest':
            status = fm.get('status', 'active').lower()
            if status not in ('active', 'complete', 'failed'):
                status = 'active'
            quests.append({'name': display_name, 'status': status,
                           'description': desc, 'source': rel})

    return {'npcs': npcs, 'factions': factions, 'quests': quests, 'skipped': skipped}
