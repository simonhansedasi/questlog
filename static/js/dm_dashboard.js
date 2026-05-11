// DM Dashboard — all interactive logic for dm/index.html
// Data is injected by the template into window.RF before this file loads.

var RF = window.RF || {};
var _allEntities     = RF.allEntities     || [];
var _proposalData    = RF.proposals       || [];
var _partyChars      = RF.partyChars      || [];
var _partyName       = RF.partyName       || '';
var _locationOptions = RF.locationOptions || [];
var _pcFlags         = [];
var _discreteFlags   = [];
var _panelCache      = {};
window._futureDmState = (RF.futureDmState || []).map(function(f) {
  return { note: f.hypothesis, confidence: f.confidence };
});

// ── Getting Started ──────────────────────────────────────────────────────────
function rfDismissGs() {
  localStorage.setItem('rf_gs_' + RF.slug, '1');
  var el = document.getElementById('rf-gs');
  if (el) el.style.display = 'none';
}

// ── Ripple reveal / dismiss ──────────────────────────────────────────────────
var _rippleWitnesses = {};

function onDepthChange(rid, val) {
  var picker = document.getElementById('witness-picker-' + rid);
  picker.style.display = (val === '-1') ? 'flex' : 'none';
  if (val === '-1' && !_rippleWitnesses[rid]) {
    _rippleWitnesses[rid] = [];
    filterEntities(rid, '');
  }
}

function filterEntities(rid, query) {
  var q = query.trim().toLowerCase();
  var results = document.getElementById('entity-results-' + rid);
  var selected = (_rippleWitnesses[rid] || []).map(function(w) { return w.id; });
  var matches = _allEntities
    .filter(function(e) { return !selected.includes(e.id) && (!q || e.name.toLowerCase().includes(q)); })
    .slice(0, 20);
  results.innerHTML = matches.map(function(e) {
    return '<button onclick="addWitness(\'' + rid + '\',\'' + e.id + '\',\'' + e.type + '\',' + JSON.stringify(e.name) + ')"' +
           ' style="background:var(--surface); border:1px solid var(--border); color:var(--text);' +
           ' border-radius:3px; padding:2px 8px; font-size:0.75rem; cursor:pointer;">' +
           e.name + ' <span style="color:var(--muted); font-size:0.68rem;">' + e.type + '</span></button>';
  }).join('');
}

function addWitness(rid, eid, etype, ename) {
  if (!_rippleWitnesses[rid]) _rippleWitnesses[rid] = [];
  if (_rippleWitnesses[rid].find(function(w) { return w.id === eid; })) return;
  _rippleWitnesses[rid].push({ id: eid, type: etype, name: ename });
  renderWitnesses(rid);
  var inp = document.querySelector('#witness-picker-' + rid + ' input');
  filterEntities(rid, inp ? inp.value : '');
}

function removeWitness(rid, eid) {
  _rippleWitnesses[rid] = (_rippleWitnesses[rid] || []).filter(function(w) { return w.id !== eid; });
  renderWitnesses(rid);
  var inp = document.querySelector('#witness-picker-' + rid + ' input');
  filterEntities(rid, inp ? inp.value : '');
}

function renderWitnesses(rid) {
  var el = document.getElementById('selected-witnesses-' + rid);
  el.innerHTML = (_rippleWitnesses[rid] || []).map(function(w) {
    return '<span style="background:#d9770622; border:1px solid #d97706; border-radius:3px;' +
           ' padding:2px 8px; font-size:0.75rem; color:#d97706; display:flex; align-items:center; gap:4px;">' +
           w.name +
           '<button onclick="removeWitness(\'' + rid + '\',\'' + w.id + '\')"' +
           ' style="background:none; border:none; color:#d97706; cursor:pointer; font-size:0.8rem; padding:0; line-height:1;">×</button>' +
           '</span>';
  }).join('');
}

function revealRipple(rid) {
  var radios = document.querySelectorAll('input[name="depth-' + rid + '"]');
  var val = Array.from(radios).find(function(r) { return r.checked; });
  val = val ? val.value : null;
  if (val === 'dismiss') { dismissRipple(rid); return; }
  var depth;
  if (val === '-1') depth = -1;
  else if (val === '0') depth = null;
  else depth = parseInt(val);
  var extra = (val === '-1') ? (_rippleWitnesses[rid] || []).map(function(w) { return { id: w.id, type: w.type }; }) : [];
  var body = { depth: depth, extra_entities: extra };
  var statusEl = document.getElementById('pr-status-' + rid);
  statusEl.textContent = 'Firing…';
  fetch('/' + RF.slug + '/dm/ripple/' + rid + '/reveal', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
  }).then(function(r) { return r.json(); }).then(function(d) {
    if (d.error) { statusEl.textContent = d.error; return; }
    document.getElementById('pr-' + rid).remove();
    var list = document.getElementById('pending-ripples-list');
    if (!list || !list.children.length) {
      var ci = document.getElementById('contained-incidents');
      if (ci) ci.remove();
    }
  }).catch(function() { statusEl.textContent = 'Something went wrong.'; });
}

function dismissRipple(rid) {
  fetch('/' + RF.slug + '/dm/ripple/' + rid + '/dismiss', { method: 'POST' })
    .then(function() {
      document.getElementById('pr-' + rid).remove();
      var list = document.getElementById('pending-ripples-list');
      if (!list || !list.children.length) {
        var ci = document.getElementById('contained-incidents');
        if (ci) ci.remove();
      }
    });
}

// ── Session Recap ────────────────────────────────────────────────────────────
function generateRecap(slug) {
  var btn = document.getElementById('recap-btn');
  btn.textContent = 'Generating…';
  btn.disabled = true;
  fetch('/' + slug + '/dm/session/recap', { method: 'POST' })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      btn.textContent = '✦ ' + RF.terms.recapCta;
      btn.disabled = false;
      if (data.error === 'ai_locked') { if (confirm('AI features require Pro. Try Pro free for 14 days?')) { window.location.href = '/billing'; } return; }
      if (data.error) { alert(data.error); return; }
      document.getElementById('recap-raw').value = data.recap;
      document.getElementById('recap-output').innerHTML = data.recap_html || data.recap.replace(/\n/g, '<br>');
      document.getElementById('journal-recap').value = data.recap;
      document.getElementById('journal-date').value = new Date().toISOString().split('T')[0];
      document.getElementById('recap-section').style.display = 'block';
      document.getElementById('recap-section').scrollIntoView({ behavior: 'smooth' });
    })
    .catch(function() { btn.textContent = '✦ ' + RF.terms.recapCta; btn.disabled = false; alert('Something went wrong.'); });
}

function proposeEntries(slug) {
  var btn = document.getElementById('propose-btn');
  btn.textContent = 'Parsing…';
  btn.disabled = true;
  var sessionInput = document.getElementById('parse-session');
  var fd = new FormData();
  if (sessionInput && sessionInput.value) fd.append('session_override', sessionInput.value);
  fetch('/' + slug + '/dm/session/propose', { method: 'POST', body: fd })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      btn.textContent = '✦ ' + RF.terms.parseCta;
      btn.disabled = false;
      if (data.error === 'ai_locked') { if (confirm('AI features require Pro. Try Pro free for 14 days?')) { window.location.href = '/billing'; } return; }
      if (data.error) { alert(data.error); return; }
      _proposalData = data.proposals;
      renderProposals(data.proposals, data.session);
      document.getElementById('proposals-section').style.display = 'block';
      document.getElementById('proposals-section').scrollIntoView({ behavior: 'smooth' });
      if (data.relation_suggestions && data.relation_suggestions.length) {
        renderRelSuggestions(data.relation_suggestions);
        document.getElementById('rel-suggestions-section').style.display = 'block';
      }
    })
    .catch(function(err) { btn.textContent = '✦ ' + RF.terms.parseCta; btn.disabled = false; alert('Something went wrong: ' + err); console.error(err); });
}

// ── Proposal rendering ───────────────────────────────────────────────────────
function _setPropPol(i, val) {
  _proposalData[i].polarity = val || null;
  var polColors = { positive: '#7ec87e', negative: '#e05c5c', neutral: 'var(--muted)' };
  var col = polColors[val] || 'var(--border)';
  var card = document.getElementById('prop-card-' + i);
  if (card) {
    if (!_proposalData[i].conflict) card.style.borderLeftColor = _discreteFlags[i] ? '#d97706' : col;
    var sel = card.querySelector('.prop-pol-sel');
    if (sel) sel.style.color = col;
  }
}

function _setCondMeta(i, field, val) {
  if (!_proposalData[i].condition_meta) {
    _proposalData[i].condition_meta = { region: '', effect_type: 'custom', effect_scope: '', magnitude: { type: 'custom', label: '' } };
  }
  _proposalData[i].condition_meta[field] = val;
}

function _setProposalEntityType(i, type) {
  _proposalData[i].entity_type = type;
  var condFields = document.getElementById('prop-cond-' + i);
  var hiddenField = document.getElementById('prop-hidden-' + i);
  if (condFields) condFields.style.display = type === 'condition' ? 'flex' : 'none';
  if (hiddenField) hiddenField.style.display = type === 'condition' ? 'none' : 'flex';
  if (type === 'condition' && !_proposalData[i].condition_meta) {
    _proposalData[i].condition_meta = { region: '', effect_type: 'custom', effect_scope: '', magnitude: { type: 'custom', label: '' } };
  } else if (type !== 'condition') {
    _proposalData[i].condition_meta = null;
  }
}

function _buildProposalCard(p, i, polarityColor, _entitySelectOptions, _actorOptions) {
  var isShip = p.entity_type === 'ship';
  var isPartyGroup = p.entity_type === 'party_group' || p.entity_type === 'party';
  var col = isShip ? '#5ba4cf' : (polarityColor[p.polarity] || 'var(--border)');
  var shipBadge = isShip ? '<span style="color:#5ba4cf; font-size:0.68rem; font-weight:700; margin-left:4px;">ship log</span>' : '';
  var conflictBadge = p.conflict ? '<span style="color:#e05c5c; font-size:0.68rem; font-weight:700; margin-left:4px;" title="This may contradict the entity\'s known state — review before committing">⚠ conflict</span>' : '';
  var borderCol = p.conflict ? '#e05c5c' : col;
  var locHtml = _locationOptions.length ? '<div style="display:flex; align-items:center; gap:8px;"><span style="color:var(--muted); font-size:0.68rem; white-space:nowrap;">At</span><select onchange="_proposalData[' + i + '].location_id=this.value||null" style="background:var(--surface); border:1px solid var(--border); color:var(--text); border-radius:3px; padding:1px 5px; font-size:0.72rem; cursor:pointer; flex:1; min-width:120px;"><option value="">— no location —</option>' + _locationOptions.map(function(l) { return '<option value="' + l.id + '"' + ((p.location_id || '') === l.id ? ' selected' : '') + '>' + l.name + '</option>'; }).join('') + '</select></div>' : '';
  return `<div id="prop-card-${i}" style="display:flex; gap:10px; align-items:flex-start; background:var(--surface2);
                     border:1px solid var(--border); border-left:3px solid ${borderCol}; border-radius:5px; padding:10px 12px;">
    <input type="checkbox" id="prop-${i}" checked style="margin-top:3px; accent-color:var(--gold); flex-shrink:0;">
    <div style="flex:1; min-width:0; display:flex; flex-direction:column; gap:6px;">
      <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
        <select onchange="(function(s){const opt=s.options[s.selectedIndex]; _proposalData[${i}].entity_id=opt.dataset.id||null; _proposalData[${i}].entity_name=opt.dataset.name||s.value; _proposalData[${i}].entity_type=opt.dataset.type||'npc';})(this)"
                style="background:var(--surface); border:1px solid var(--border); color:var(--text); font-weight:700; border-radius:3px; padding:2px 6px; font-size:0.83rem; cursor:pointer; max-width:200px;">
          <option value="_party" data-id="_party" data-name="${_partyName}" data-type="party_group"${isPartyGroup ? ' selected' : ''}>${_partyName} (party)</option>
          ${(!isPartyGroup && !p.entity_id) ? `<option value="" data-id="" data-name="${p.entity_name || ''}" data-type="${p.entity_type || 'npc'}" selected>${p.entity_name || '?'} ⚠ new</option>` : ''}
          ${_entitySelectOptions.map(function(e) { var sel = !isPartyGroup && !!p.entity_id && e.id === p.entity_id; return '<option value="' + e.id + '" data-id="' + e.id + '" data-name="' + e.name + '" data-type="' + e.type + '"' + (sel ? ' selected' : '') + '>' + e.name + ' (' + e.type + ')</option>'; }).join('')}
        </select>
        ${shipBadge}${conflictBadge}
        <select class="prop-pol-sel" onchange="_setPropPol(${i}, this.value)"
                style="background:var(--surface); border:1px solid var(--border); color:${col}; border-radius:3px; padding:1px 5px; font-size:0.72rem; cursor:pointer;">
          <option value="">— tone —</option>
          <option value="positive"${p.polarity === 'positive' ? ' selected' : ''}>positive</option>
          <option value="neutral"${p.polarity === 'neutral' ? ' selected' : ''}>neutral</option>
          <option value="negative"${p.polarity === 'negative' ? ' selected' : ''}>negative</option>
        </select>
        <select onchange="_proposalData[${i}].intensity=+this.value"
                style="background:var(--surface); border:1px solid var(--border); color:var(--muted); border-radius:3px; padding:1px 5px; font-size:0.72rem; cursor:pointer;">
          <option value="1"${(p.intensity || 1) === 1 ? ' selected' : ''}>x1</option>
          <option value="2"${(p.intensity || 1) === 2 ? ' selected' : ''}>x2</option>
          <option value="3"${(p.intensity || 1) === 3 ? ' selected' : ''}>x3</option>
        </select>
        <input type="text" value="${p.event_type || ''}" placeholder="type…"
               onchange="_proposalData[${i}].event_type = this.value"
               style="background:var(--surface); border:1px solid var(--border); color:var(--purple); border-radius:3px; padding:1px 5px; font-size:0.72rem; width:90px;">
        <span style="color:var(--muted); font-size:0.7rem;">${p.visibility === 'dm_only' ? RF.terms.dm + ' only' : 'public'}</span>
        <button id="pc-btn-${i}" onclick="togglePC(${i})"
                style="margin-left:auto; background:none; border:1px solid var(--border); color:var(--muted);
                       border-radius:3px; padding:1px 7px; font-size:0.68rem; font-weight:700;
                       text-transform:uppercase; cursor:pointer; letter-spacing:0.04em;"
                title="Mark as player character — exclude from commit">PC</button>
        <button id="disc-btn-${i}" onclick="toggleDiscrete(${i})"
                style="background:none; border:1px solid var(--border); color:var(--muted);
                       border-radius:3px; padding:1px 7px; font-size:0.68rem; font-weight:700;
                       text-transform:uppercase; cursor:pointer; letter-spacing:0.04em;"
                title="Keep discrete — event logged DM-only, ripple queued for manual reveal">Discrete</button>
      </div>
      <input type="text" value="${p.note.replace(/"/g, '&quot;')}"
             onchange="_proposalData[${i}].note = this.value"
             style="background:var(--surface); border:1px solid var(--border); color:var(--text);
                    border-radius:4px; padding:4px 8px; font-size:0.82rem; width:100%; box-sizing:border-box;">
      <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
        <span style="color:var(--muted); font-size:0.68rem; white-space:nowrap;">Caused by</span>
        <select onchange="(function(s){_proposalData[${i}].actor_id=s.value||null;_proposalData[${i}].actor_type=s.options[s.selectedIndex].dataset.type||null;})(this)"
                style="background:var(--surface); border:1px solid var(--border); color:var(--text); border-radius:3px; padding:1px 5px; font-size:0.72rem; cursor:pointer; flex:1; min-width:120px;">
          <option value="" data-type="">— nobody specific —</option>
          ${_actorOptions.map(function(e) { var sel = e.id === p.actor_id || (e.id.startsWith('__proposed__:') && e.id.slice(13).toLowerCase() === (p.actor_name || '').toLowerCase()); return '<option value="' + e.id + '" data-type="' + e.type + '"' + (sel ? ' selected' : '') + '>' + e.name + ' (' + e.type + ')</option>'; }).join('')}
        </select>
        <label style="display:flex; align-items:center; gap:4px; font-size:0.68rem; color:var(--muted); cursor:pointer; white-space:nowrap;">
          <input type="checkbox" ${p.actor_dm_only ? 'checked' : ''} onchange="_proposalData[${i}].actor_dm_only=this.checked"
                 style="accent-color:var(--purple);"> Secret actor
        </label>
      </div>
      ${locHtml}
      ${(!p.entity_id && !isShip && !isPartyGroup) ? `<div style="display:flex; flex-direction:column; gap:5px;">
        <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
          <span style="color:#7ec87e; font-size:0.7rem; flex-shrink:0;">New</span>
          <select onchange="_setProposalEntityType(${i}, this.value)"
                  style="background:var(--surface); border:1px solid var(--border); color:var(--text); border-radius:3px; padding:1px 5px; font-size:0.72rem; cursor:pointer;">
            <option value="npc"${(p.entity_type || 'npc') === 'npc' ? ' selected' : ''}>NPC</option>
            <option value="faction"${p.entity_type === 'faction' ? ' selected' : ''}>Faction</option>
            <option value="condition"${p.entity_type === 'condition' ? ' selected' : ''}>Condition</option>
            <option value="location"${p.entity_type === 'location' ? ' selected' : ''}>Location</option>
          </select>
          <div id="prop-hidden-${i}" style="display:${p.entity_type === 'condition' ? 'none' : 'flex'}; align-items:center;">
            <label style="display:flex; align-items:center; gap:4px; font-size:0.68rem; color:var(--muted); cursor:pointer; white-space:nowrap;">
              <input type="checkbox" ${p.entity_hidden ? 'checked' : ''} onchange="_proposalData[${i}].entity_hidden=this.checked" style="accent-color:var(--gold);"> Hidden
            </label>
          </div>
        </div>
        <div id="prop-cond-${i}" style="display:${p.entity_type === 'condition' ? 'flex' : 'none'}; flex-wrap:wrap; gap:6px; align-items:center;">
          <input type="text" placeholder="Region (where?)" value="${(p.condition_meta || {}).region || ''}"
                 onchange="_setCondMeta(${i},'region',this.value)"
                 style="background:var(--surface); border:1px solid var(--border); color:var(--text); border-radius:3px; padding:2px 6px; font-size:0.72rem; width:110px; box-sizing:border-box;">
          <select onchange="_setCondMeta(${i},'effect_type',this.value)"
                  style="background:var(--surface); border:1px solid var(--border); color:var(--text); border-radius:3px; padding:2px 5px; font-size:0.72rem; cursor:pointer;">
            ${['price', 'access', 'danger', 'supply', 'draft', 'custom'].map(function(t) { return '<option value="' + t + '"' + (((p.condition_meta || {}).effect_type || 'custom') === t ? ' selected' : '') + '>' + t + '</option>'; }).join('')}
          </select>
          <input type="text" placeholder="Affects (what?)" value="${(p.condition_meta || {}).effect_scope || ''}"
                 onchange="_setCondMeta(${i},'effect_scope',this.value)"
                 style="background:var(--surface); border:1px solid var(--border); color:var(--text); border-radius:3px; padding:2px 6px; font-size:0.72rem; width:130px; box-sizing:border-box;">
        </div>
      </div>` : ''}
      ${_partyChars.length ? `<div style="display:flex; gap:3px; flex-wrap:wrap; align-items:center;">
        <span style="color:var(--muted); font-size:0.68rem; flex-shrink:0;">Seen by:</span>
        ${_partyChars.map(function(name) {
          var isW = (p.witnesses || []).includes(name);
          return '<button type="button" onclick="toggleProposalWitness(' + i + ', \'' + name.replace(/'/g, "\\'") + '\')"' +
            ' id="pw-' + i + '-' + name.replace(/[^a-z0-9]/gi, '_') + '"' +
            ' style="background:' + (isW ? 'var(--gold)' : 'none') + '; color:' + (isW ? '#080a18' : 'var(--muted)') + ';' +
            ' border:1px solid ' + (isW ? 'var(--gold)' : 'var(--border)') + ';' +
            ' border-radius:3px; padding:1px 6px; font-size:0.65rem; cursor:pointer; font-family:inherit;">' + name + '</button>';
        }).join('')}
      </div>` : ''}
    </div>
  </div>`;
}

function renderProposals(proposals, sessionN) {
  var list = document.getElementById('proposals-list');
  if (!proposals.length) {
    list.innerHTML = '<p style="color:var(--muted); font-size:0.85rem;">No events detected in the notes.</p>';
    return;
  }
  var polarityColor = { positive: '#7ec87e', negative: '#e05c5c', neutral: 'var(--muted)' };
  _pcFlags = proposals.map(function() { return false; });
  _discreteFlags = proposals.map(function() { return false; });

  var _existingEntities = _allEntities;
  var _entitySelectOptions = _existingEntities.filter(function(e) { return !e.actor_only && e.type !== 'char'; });
  var _seenNames = new Set(_existingEntities.map(function(e) { return e.name.toLowerCase(); }));
  var _proposedActors = [];
  proposals.forEach(function(p) {
    var _isPG = p.entity_type === 'party_group' || p.entity_type === 'party';
    if (!p.entity_id && p.entity_name && !_seenNames.has(p.entity_name.toLowerCase()) && !_isPG) {
      _seenNames.add(p.entity_name.toLowerCase());
      _proposedActors.push({ id: '__proposed__:' + p.entity_name, name: p.entity_name + ' (new)', type: p.entity_type || 'npc' });
    }
  });
  var _actorOptions = [..._existingEntities, ..._proposedActors];

  var groups = [];
  var groupIndex = {};
  proposals.forEach(function(p, i) {
    var key = p.entity_name || '(unknown)';
    if (!(key in groupIndex)) { groupIndex[key] = groups.length; groups.push({ name: key, entries: [] }); }
    groups[groupIndex[key]].entries.push({ p: p, i: i });
  });

  list.innerHTML = groups.map(function(group) {
    var hasConflict = group.entries.some(function(x) { return x.p.conflict; });
    var hasUnknown = group.entries.some(function(x) { return !x.p.entity_id && x.p.entity_type !== 'ship' && x.p.entity_type !== 'party_group' && x.p.entity_type !== 'party'; });
    var n = group.entries.length;
    var countLabel = '<span style="color:var(--muted); font-size:0.72rem; margin-left:8px;">' + n + ' event' + (n !== 1 ? 's' : '') + '</span>';
    var conflictFlag = hasConflict ? '<span style="color:#e05c5c; font-size:0.7rem; font-weight:700; margin-left:8px;">⚠ conflict</span>' : '';
    var unknownFlag = hasUnknown ? '<span style="color:#d97706; font-size:0.7rem; font-weight:700; margin-left:8px;">new entity</span>' : '';
    var cards = group.entries.map(function(x) { return _buildProposalCard(x.p, x.i, polarityColor, _entitySelectOptions, _actorOptions); }).join('');
    return '<details open style="margin-bottom:8px;">' +
      '<summary style="list-style:none; cursor:pointer; display:flex; align-items:center; padding:8px 10px;' +
      ' background:var(--surface2); border:1px solid var(--border); border-radius:5px; user-select:none;">' +
      '<span style="font-size:0.7rem; color:var(--muted); margin-right:6px; flex-shrink:0;">▾</span>' +
      '<span style="font-weight:700; font-size:0.88rem; color:var(--text);">' + group.name + '</span>' +
      countLabel + conflictFlag + unknownFlag +
      '</summary>' +
      '<div style="display:flex; flex-direction:column; gap:8px; margin-top:6px; padding-left:14px; border-left:2px solid var(--border);">' +
      cards + '</div></details>';
  }).join('');
}

function toggleProposalWitness(i, name) {
  var p = _proposalData[i];
  if (!p.witnesses) p.witnesses = [];
  var idx = p.witnesses.indexOf(name);
  var btnId = 'pw-' + i + '-' + name.replace(/[^a-z0-9]/gi, '_');
  var btn = document.getElementById(btnId);
  if (idx >= 0) {
    p.witnesses.splice(idx, 1);
    if (btn) { btn.style.background = 'none'; btn.style.color = 'var(--muted)'; btn.style.borderColor = 'var(--border)'; }
  } else {
    p.witnesses.push(name);
    if (btn) { btn.style.background = 'var(--gold)'; btn.style.color = '#080a18'; btn.style.borderColor = 'var(--gold)'; }
  }
}

function togglePC(i) {
  _pcFlags[i] = !_pcFlags[i];
  var card = document.getElementById('prop-card-' + i);
  var btn = document.getElementById('pc-btn-' + i);
  var cb = document.getElementById('prop-' + i);
  if (_pcFlags[i]) {
    card.style.opacity = '0.45'; btn.style.background = 'var(--purple)'; btn.style.borderColor = 'var(--purple)'; btn.style.color = '#fff'; cb.checked = false; cb.disabled = true;
  } else {
    card.style.opacity = '1'; btn.style.background = 'none'; btn.style.borderColor = 'var(--border)'; btn.style.color = 'var(--muted)'; cb.checked = true; cb.disabled = false;
  }
}

function toggleDiscrete(i) {
  _discreteFlags[i] = !_discreteFlags[i];
  var btn = document.getElementById('disc-btn-' + i);
  var card = document.getElementById('prop-card-' + i);
  if (_discreteFlags[i]) {
    btn.style.background = '#d97706'; btn.style.borderColor = '#d97706'; btn.style.color = '#fff'; card.style.borderLeftColor = '#d97706';
  } else {
    btn.style.background = 'none'; btn.style.borderColor = 'var(--border)'; btn.style.color = 'var(--muted)';
    var p = _proposalData[i];
    var col = { positive: '#7ec87e', negative: '#e05c5c', neutral: 'var(--border)' }[p.polarity] || 'var(--border)';
    card.style.borderLeftColor = p.conflict ? '#e05c5c' : col;
  }
}

function commitProposals(slug) {
  var entries = _proposalData
    .filter(function(p, i) { return !_pcFlags[i] && document.getElementById('prop-' + i) && document.getElementById('prop-' + i).checked; })
    .map(function(p, i) {
      return { entity_id: p.entity_id || '', entity_name: p.entity_name || '', entity_type: p.entity_type, note: p.note, polarity: p.polarity, intensity: p.intensity, event_type: p.event_type, visibility: p.visibility, discrete: !!_discreteFlags[i], witnesses: p.witnesses || [], actor_id: p.actor_id || null, actor_type: p.actor_type || null, actor_dm_only: !!p.actor_dm_only, entity_hidden: !!p.entity_hidden, location_id: p.location_id || null };
    });
  if (!entries.length) { document.getElementById('commit-status').textContent = 'Nothing to commit.'; return; }
  document.getElementById('commit-status').textContent = 'Committing…';
  fetch('/' + slug + '/dm/session/commit_proposals', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ entries: entries })
  }).then(function(r) { return r.json(); }).then(function(data) {
    if (data.error) { document.getElementById('commit-status').textContent = data.error; return; }
    var msg = data.committed + ' event' + (data.committed !== 1 ? 's' : '') + ' logged.';
    if (data.created && data.created.length) msg += ' Created: ' + data.created.map(function(e) { return e.name + ' (' + e.type + ')'; }).join(', ') + ' — hidden, edit in World.';
    var statusEl = document.getElementById('commit-status');
    statusEl.textContent = msg;
    if (data.condition_alerts && data.condition_alerts.length) {
      var alertHtml = data.condition_alerts.map(function(a) { return '<span style="display:inline-block; margin-top:4px; background:var(--surface2); border:1px solid var(--gold); border-radius:4px; padding:2px 8px; font-size:0.75rem; color:var(--gold);">⚔ ' + a.char_name + ' — ' + a.condition_name + ' (' + a.entity_name + ')</span>'; }).join(' ');
      statusEl.innerHTML = msg + '<br>' + alertHtml;
    }
    setTimeout(function() { document.getElementById('proposals-section').style.display = 'none'; location.reload(); }, 2400);
  }).catch(function() { document.getElementById('commit-status').textContent = 'Something went wrong.'; });
}

function discardProposals(slug) {
  fetch('/' + slug + '/dm/session/discard_proposals', { method: 'POST' })
    .then(function() { document.getElementById('proposals-section').style.display = 'none'; _proposalData = []; });
}

// ── Futures ──────────────────────────────────────────────────────────────────
function loadFutures() {
  var btn = document.getElementById('futures-btn');
  var section = document.getElementById('futures-section');
  var loading = document.getElementById('futures-loading');
  var cards = document.getElementById('futures-cards');
  btn.disabled = true; btn.textContent = 'Thinking…';
  section.style.display = 'block'; loading.style.display = 'block'; cards.innerHTML = '';
  fetch('/' + RF.slug + '/dm/world/futures', { method: 'POST' })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      loading.style.display = 'none'; btn.textContent = 'Refresh ✦'; btn.disabled = false;
      if (data.error === 'ai_locked') { if (confirm('AI features require Pro. Try Pro free for 14 days?')) { window.location.href = '/billing'; } return; }
      if (data.error) { cards.innerHTML = '<p style="color:#e05c5c; font-size:0.8rem;">' + data.error + '</p>'; return; }
      var confColor = { high: '#e05c5c', medium: '#d97706', low: 'var(--muted)' };
      window._futureDmState = data.futures.map(function(f) { return { note: f.hypothesis, confidence: f.confidence }; });
      var btnS = function(i, c) {
        var active = c === data.futures[i].confidence;
        return 'background:' + (active ? (confColor[c] || 'var(--purple)') : 'none') + '; color:' + (active ? '#fff' : 'var(--muted)') + '; border:1px solid var(--border); border-radius:3px; padding:2px 7px; font-size:0.65rem; cursor:pointer; font-weight:700; text-transform:uppercase;';
      };
      cards.innerHTML = data.futures.map(function(f, i) {
        return '<div id="dmfcard-' + i + '" style="background:var(--surface2); border:1px solid var(--border); border-left:3px solid ' + (confColor[f.confidence] || 'var(--purple)') + '; border-radius:5px; padding:10px 14px; display:flex; gap:10px; align-items:flex-start;">' +
          '<input type="checkbox" class="future-cb" checked data-idx="' + i + '" data-entity-id="' + (f.entity_id || '') + '" data-entity-type="' + (f.entity_kind || 'npc') + '" data-entity-name="' + (f.entity_name || '') + '" style="margin-top:4px; accent-color:var(--purple); flex-shrink:0;" onchange="updateFuturesCommitBtn()">' +
          '<div style="flex:1;"><div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; flex-wrap:wrap; gap:6px;"><span style="font-weight:700; font-size:0.83rem; color:var(--text);">' + f.entity_name + '</span>' +
          '<div style="display:flex; gap:3px;"><button onclick="setDmFutureConf(' + i + ',\'high\')" id="dmfc-' + i + '-high" style="' + btnS(i, 'high') + '">high</button><button onclick="setDmFutureConf(' + i + ',\'medium\')" id="dmfc-' + i + '-medium" style="' + btnS(i, 'medium') + '">med</button><button onclick="setDmFutureConf(' + i + ',\'low\')" id="dmfc-' + i + '-low" style="' + btnS(i, 'low') + '">low</button></div></div>' +
          '<textarea id="dmft-' + i + '" oninput="_futureDmState[' + i + '].note = this.value" style="width:100%; box-sizing:border-box; background:var(--surface); border:1px solid var(--border); color:var(--text); border-radius:4px; padding:6px 8px; font-size:0.82rem; font-family:inherit; line-height:1.45; resize:vertical; margin-bottom:4px;" rows="3">' + f.hypothesis.replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</textarea>' +
          '<p style="margin:0; font-size:0.72rem; color:var(--muted); font-style:italic;">' + f.reasoning + '</p></div></div>';
      }).join('') +
      '<div style="display:flex; align-items:center; gap:12px; padding-top:4px;"><button id="futures-commit-btn" onclick="commitFutures()" style="background:var(--purple);color:#fff;border:none;border-radius:4px;padding:5px 14px;font-size:0.78rem;font-weight:700;cursor:pointer;">Commit selected</button></div>' +
      '<div id="futures-commit-msg" style="display:none;"></div>';
    })
    .catch(function() {
      loading.style.display = 'none'; btn.textContent = 'What happens next? ✦'; btn.disabled = false;
      cards.innerHTML = '<p style="color:#e05c5c; font-size:0.8rem;">Request failed.</p>';
    });
}

function updateFuturesCommitBtn() {
  var btn = document.getElementById('futures-commit-btn');
  if (!btn) return;
  var any = Array.from(document.querySelectorAll('.future-cb')).some(function(cb) { return cb.checked; });
  btn.disabled = !any; btn.style.opacity = any ? '1' : '0.4';
}

function setDmFutureConf(i, conf) {
  if (!window._futureDmState) return;
  _futureDmState[i].confidence = conf;
  var confColor = { high: '#e05c5c', medium: '#d97706', low: 'var(--muted)' };
  ['high', 'medium', 'low'].forEach(function(c) {
    var btn = document.getElementById('dmfc-' + i + '-' + c);
    if (!btn) return;
    btn.style.background = c === conf ? (confColor[c] || 'var(--purple)') : 'none';
    btn.style.color = c === conf ? '#fff' : 'var(--muted)';
  });
  var card = document.getElementById('dmfcard-' + i);
  if (card) card.style.borderLeftColor = confColor[conf] || 'var(--purple)';
}

function renderWorldDiff(diffs) {
  if (!diffs || !diffs.length) return '';
  var relColor = { allied: '#7ec87e', friendly: '#7ec87e', neutral: 'var(--muted)', hostile: '#e05c5c' };
  var rows = diffs.map(function(d) {
    var parts = [];
    if (d.log_added) parts.push('+' + d.log_added + ' entr' + (d.log_added === 1 ? 'y' : 'ies'));
    if (d.score_before !== undefined && d.score_after !== undefined && d.score_before !== d.score_after) parts.push('score ' + d.score_before + ' → ' + d.score_after);
    var relPart = '';
    if (d.relationship_before && d.relationship_after && d.relationship_before !== d.relationship_after) {
      relPart = ' <span style="color:' + (relColor[d.relationship_before] || 'var(--muted)') + ';">' + d.relationship_before + '</span>' +
                ' → <span style="color:' + (relColor[d.relationship_after] || 'var(--muted)') + '; font-weight:700;">' + d.relationship_after + '</span>';
    }
    return '<div style="display:flex; justify-content:space-between; align-items:baseline; padding:3px 0; border-bottom:1px solid var(--border); font-size:0.72rem;"><span style="color:var(--text); font-weight:700;">' + d.entity_name + relPart + '</span><span style="color:var(--muted);">' + parts.join(' · ') + '</span></div>';
  }).join('');
  return '<div style="margin-top:8px;"><p style="color:var(--muted); font-size:0.68rem; text-transform:uppercase; letter-spacing:0.08em; margin:0 0 4px 0;">World changed</p>' + rows + '</div>';
}

function commitFutures() {
  var btn = document.getElementById('futures-commit-btn');
  btn.disabled = true; btn.textContent = 'Committing…';
  var entries = Array.from(document.querySelectorAll('.future-cb')).filter(function(cb) { return cb.checked; }).map(function(cb) {
    var i = parseInt(cb.dataset.idx);
    var st = window._futureDmState && _futureDmState[i];
    return { entity_id: cb.dataset.entityId, entity_type: cb.dataset.entityType, entity_name: cb.dataset.entityName || '', note: st ? st.note : (cb.dataset.note || ''), confidence: st ? st.confidence : (cb.dataset.confidence || 'medium') };
  });
  fetch('/' + RF.slug + '/dm/world/commit_futures', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ entries: entries })
  }).then(function(r) { return r.json(); }).then(function(data) {
    btn.style.display = 'none';
    var msg = document.getElementById('futures-commit-msg');
    msg.style.display = 'block';
    msg.innerHTML = '<p style="color:#7ec87e; font-size:0.75rem; margin:4px 0 0 0;">✓ ' + data.committed + ' consequence' + (data.committed !== 1 ? 's' : '') + ' committed as PROJECTED events.</p>' + renderWorldDiff(data.diffs);
  }).catch(function() { btn.disabled = false; btn.textContent = 'Commit selected'; });
}

// ── Relation Suggestions ─────────────────────────────────────────────────────
function renderRelSuggestions(suggestions) {
  var list = document.getElementById('rel-suggestions-list');
  if (!list) return;
  var relColor = { ally: '#7ec87e', rival: '#e05c5c' };
  list.innerHTML = suggestions.map(function(s) {
    var key = s.source_id + '-' + s.target_id;
    var sJson = JSON.stringify(s).replace(/'/g, '&#39;');
    return '<div id="relsug-' + key + '" style="background:var(--surface2); border:1px solid var(--border); border-left:3px solid var(--purple); border-radius:5px; padding:10px 14px; display:flex; justify-content:space-between; align-items:flex-start; gap:12px;">' +
      '<div style="flex:1; min-width:0;"><div style="display:flex; align-items:center; gap:8px; margin-bottom:4px; flex-wrap:wrap;">' +
      '<span style="font-weight:700; font-size:0.85rem; color:var(--text);">' + s.source_id + '</span>' +
      '<span style="color:' + (relColor[s.relation] || 'var(--muted)') + '; font-size:0.72rem; font-weight:700; text-transform:uppercase;">' + s.relation + '</span>' +
      '<span style="font-weight:700; font-size:0.85rem; color:var(--text);">' + s.target_id + '</span>' +
      '<span style="color:var(--muted); font-size:0.7rem;">' + s.weight + '×</span></div>' +
      '<p style="color:var(--muted); font-size:0.78rem; margin:0; font-style:italic;">' + s.reason + '</p></div>' +
      '<div style="display:flex; gap:6px; flex-shrink:0; align-items:center;">' +
      '<button onclick=\'acceptRelSuggestion(' + sJson + ', this)\' style="background:var(--purple); color:#fff; border:none; border-radius:4px; padding:3px 12px; font-size:0.75rem; font-weight:700; cursor:pointer;">Accept</button>' +
      '<button onclick="dismissRelSuggestion(\'' + s.source_id + '\',\'' + s.target_id + '\', this)" style="background:none; border:1px solid var(--border); color:var(--muted); border-radius:4px; padding:3px 8px; font-size:0.75rem; cursor:pointer;">Dismiss</button>' +
      '</div></div>';
  }).join('');
}

function acceptRelSuggestion(s, btn) {
  btn.disabled = true; btn.textContent = 'Adding…';
  fetch('/' + RF.slug + '/dm/relation_suggestion/accept', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(s)
  }).then(function(r) { return r.json(); }).then(function(d) {
    if (d.ok) {
      var card = document.getElementById('relsug-' + s.source_id + '-' + s.target_id);
      if (card) {
        card.style.opacity = '0.5'; card.style.pointerEvents = 'none';
        var label = d.backfilled > 0 ? 'Added ✓ — ' + d.backfilled + ' historical ripple' + (d.backfilled !== 1 ? 's' : '') + ' backfilled' : 'Added ✓';
        card.querySelector('p').textContent = label; card.style.borderLeftColor = '#7ec87e';
      }
    } else { btn.disabled = false; btn.textContent = 'Accept'; }
  });
}

function dismissRelSuggestion(sourceId, targetId, btn) {
  btn.disabled = true;
  fetch('/' + RF.slug + '/dm/relation_suggestion/dismiss', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ source_id: sourceId, target_id: targetId })
  }).then(function(r) { return r.json(); }).then(function(d) {
    if (d.ok) {
      var card = document.getElementById('relsug-' + sourceId + '-' + targetId);
      if (card) card.remove();
      var list = document.getElementById('rel-suggestions-list');
      if (list && !list.children.length) document.getElementById('rel-suggestions-section').style.display = 'none';
    } else { btn.disabled = false; }
  });
}

// ── World panel relations ─────────────────────────────────────────────────────
function _renderCharRelations(panelId, charRelations, npcId) {
  var container = document.getElementById(panelId + '-charrels');
  if (!container) return;
  var deleteRoute = '/' + RF.slug + '/dm/npc/' + npcId + '/char_relation/delete';
  if (!charRelations.length) { container.innerHTML = '<p style="color:var(--muted); font-size:0.75rem; margin:0 0 8px 0;">No personal relations yet.</p>'; return; }
  var rows = charRelations.map(function(cr) {
    var col = cr.relation === 'rival' ? '#e05c5c' : '#7ec87e';
    return '<div style="display:flex; align-items:center; gap:8px; font-size:0.8rem;">' +
      '<span style="color:var(--gold); font-weight:700; font-size:0.78rem;">' + cr.char_name + '</span>' +
      '<span style="color:' + col + '; font-weight:700; font-size:0.68rem; text-transform:uppercase; min-width:34px;">' + cr.relation + '</span>' +
      '<span style="color:var(--muted); font-size:0.7rem;">' + cr.weight + '×</span>' +
      '<form method="POST" action="' + deleteRoute + '" data-ajax data-rel-panel="' + panelId + '" data-entity-type="npc" data-entity-id="' + npcId + '" style="margin-left:auto;">' +
      '<input type="hidden" name="ajax" value="1"><input type="hidden" name="char_name" value="' + cr.char_name + '">' +
      '<button type="submit" style="background:none; border:none; color:var(--muted); font-size:0.8rem; cursor:pointer; padding:0 2px;">×</button>' +
      '</form></div>';
  });
  container.innerHTML = '<div style="display:flex; flex-direction:column; gap:4px; margin-bottom:8px;">' + rows.join('') + '</div>';
}

function _renderRelations(panelId, relations, entityType, entityId) {
  var container = document.getElementById(panelId + '-rels');
  if (!container) return;
  var routeBase = '/' + RF.slug + '/dm/' + entityType + '/' + encodeURIComponent(entityId) + '/relation';
  if (!relations.length) { container.innerHTML = '<p style="color:var(--muted); font-size:0.75rem; margin:0 0 8px 0;">No relations yet.</p>'; return; }
  var rows = relations.map(function(r) {
    var color = r.relation === 'rival' ? '#e05c5c' : '#7ec87e';
    return '<div style="display:flex; align-items:center; gap:8px; font-size:0.8rem;">' +
      '<span style="color:' + color + '; font-weight:700; font-size:0.68rem; text-transform:uppercase; min-width:34px;">' + r.relation + '</span>' +
      '<span style="flex:1;">' + r.target_name + '</span>' +
      '<span style="color:var(--muted); font-size:0.7rem;">' + r.weight + '×</span>' +
      '<form method="POST" action="' + routeBase + '/' + r.idx + '/delete" data-ajax data-rel-panel="' + panelId + '" data-entity-type="' + entityType + '" data-entity-id="' + entityId + '">' +
      '<input type="hidden" name="ajax" value="1">' +
      '<button type="submit" style="background:none; border:none; color:var(--muted); font-size:0.8rem; cursor:pointer; padding:0 2px;">×</button>' +
      '</form></div>';
  });
  container.innerHTML = '<div style="display:flex; flex-direction:column; gap:4px; margin-bottom:8px;">' + rows.join('') + '</div>';
}

function toggleWorldPanel(id) {
  var panel = document.getElementById(id);
  var chevron = document.getElementById(id + '-chevron');
  if (!panel) return;
  var open = panel.style.display !== 'none';
  panel.style.display = open ? 'none' : 'block';
  if (chevron) chevron.style.transform = open ? '' : 'rotate(90deg)';
}

function toggleWorldSection() {
  var body = document.getElementById('world-section-body');
  var btn = document.getElementById('world-toggle-btn');
  var isHidden = body.style.display === 'none';
  body.style.display = isHidden ? '' : 'none';
  btn.textContent = isHidden ? 'Collapse ▴' : 'Expand ▾';
  sessionStorage.setItem('rf_world_open', isHidden ? '1' : '0');
}

// ── Intel panel ──────────────────────────────────────────────────────────────
function toggleIntelPanel(panelId, entityType, entityId) {
  var panel = document.getElementById(panelId);
  var chevron = document.getElementById(panelId + '-chevron');
  if (!panel) return;
  var open = panel.style.display !== 'none';
  panel.style.display = open ? 'none' : 'block';
  chevron.style.transform = open ? '' : 'rotate(90deg)';
  if (!open && !_panelCache[panelId]) loadIntelPanel(panelId, entityType, entityId);
}

function loadIntelPanel(panelId, entityType, entityId) {
  fetch('/' + RF.slug + '/dm/entity/' + entityType + '/' + entityId + '/panel')
    .then(function(r) { return r.json(); })
    .then(function(d) {
      _panelCache[panelId] = true;
      var polColors = { positive: '#7ec87e', negative: '#e05c5c', neutral: 'var(--muted)' };
      var polSymbols = { positive: '+', negative: '−', neutral: '·' };
      var html = '';
      if (d.entries && d.entries.length) {
        html += '<div style="display:flex; flex-direction:column; gap:5px; margin-bottom:10px; max-height:200px; overflow-y:auto;">';
        d.entries.forEach(function(e) {
          var pol = e.polarity ? '<span style="color:' + (polColors[e.polarity] || 'var(--muted)') + '; font-size:0.7rem; font-weight:700; margin-right:3px;">' + (polSymbols[e.polarity] || '') + (e.intensity || '') + '</span>' : '';
          var vis = e.visibility === 'dm_only' ? '<span style="color:var(--muted); font-size:0.65rem; font-style:italic; margin-left:4px;">dm only</span>' : '';
          html += '<div style="font-size:0.78rem; color:var(--text); padding:4px 0; border-bottom:1px solid var(--border);">' + pol + e.note + vis + '<span style="color:var(--muted); font-size:0.68rem; margin-left:6px;">S' + e.session + '</span></div>';
        });
        html += '</div>';
      } else {
        html += '<p style="color:var(--muted); font-size:0.75rem; margin:0 0 8px 0;">No log entries yet.</p>';
      }
      html += '<div style="display:flex; flex-direction:column; gap:6px;">' +
        '<textarea id="' + panelId + '-note" rows="2" placeholder="Log a new event…" style="width:100%; box-sizing:border-box; background:var(--surface); border:1px solid var(--border); color:var(--text); border-radius:4px; padding:6px 8px; font-size:0.78rem; resize:none;"></textarea>' +
        '<div style="display:flex; gap:6px; align-items:center; flex-wrap:wrap;"><div style="display:flex; gap:3px;">' +
        ['positive', 'neutral', 'negative'].map(function(p) {
          var c = polColors[p]; var sym = polSymbols[p];
          return '<button onclick="setPanelPol(\'' + panelId + '\',\'' + p + '\',this)" data-pol="' + p + '" style="background:none; border:1px solid ' + c + '; color:' + c + '; border-radius:3px; padding:2px 7px; font-size:0.72rem; cursor:pointer;">' + sym + '</button>';
        }).join('') + '</div>' +
        '<select id="' + panelId + '-etype" style="background:var(--surface); border:1px solid var(--border); color:var(--muted); border-radius:4px; padding:2px 6px; font-size:0.72rem;"><option value="">type…</option>' +
        ['dialogue', 'combat', 'politics', 'discovery', 'betrayal', 'movement', 'other'].map(function(t) { return '<option value="' + t + '">' + t + '</option>'; }).join('') + '</select>' +
        '<select id="' + panelId + '-vis" style="background:var(--surface); border:1px solid var(--border); color:var(--muted); border-radius:4px; padding:2px 6px; font-size:0.72rem;"><option value="public">public</option><option value="dm_only">dm only</option></select>' +
        '<button onclick="submitPanelLog(\'' + panelId + '\',\'' + entityType + '\',\'' + entityId + '\',' + d.session + ')" style="background:var(--gold); color:#080a18; border:none; border-radius:4px; padding:3px 12px; font-size:0.72rem; font-weight:700; cursor:pointer; margin-left:auto;">Log</button>' +
        '</div></div>';
      document.getElementById(panelId + '-content').innerHTML = html;
    });
}

function setPanelPol(panelId, pol, btn) {
  var parent = btn.parentElement;
  parent.querySelectorAll('button').forEach(function(b) { b.style.fontWeight = ''; b.style.opacity = '0.5'; });
  btn.style.fontWeight = '700'; btn.style.opacity = '1'; btn.dataset.selected = 'true'; parent.dataset.selected = pol;
}

function submitPanelLog(panelId, entityType, entityId, session) {
  var note = document.getElementById(panelId + '-note').value.trim();
  if (!note) return;
  var polContainer = document.querySelector('#' + panelId + '-content [data-selected]');
  var pol = polContainer ? polContainer.dataset.selected : '';
  var etype = document.getElementById(panelId + '-etype').value;
  var vis = document.getElementById(panelId + '-vis').value;
  var form = new FormData();
  form.append('entity', entityType + ':' + entityId);
  form.append('note', note); form.append('session', session);
  if (pol) form.append('polarity', pol);
  form.append('intensity', '1');
  if (etype) form.append('event_type', etype);
  form.append('visibility', vis);
  fetch('/' + RF.slug + '/dm/log/quick', { method: 'POST', body: form })
    .then(function() {
      _panelCache[panelId] = false;
      loadIntelPanel(panelId, entityType, entityId);
      document.getElementById(panelId + '-note').value = '';
    });
}

// ── Projections ──────────────────────────────────────────────────────────────
function confirmProjection(eventId, entityId, entityType) {
  var btn = event.target;
  var newType = document.getElementById('etype-' + eventId).value;
  btn.disabled = true; btn.textContent = '...';
  fetch('/' + RF.slug + '/dm/world/confirm_projection', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ event_id: eventId, entity_id: entityId, entity_type: entityType, event_type: newType })
  }).then(function(r) { return r.json(); }).then(function(data) {
    if (data.ok) {
      var card = document.getElementById('proj-' + eventId);
      if (card) { card.style.opacity = '0.4'; card.style.pointerEvents = 'none'; card.querySelector('p').textContent += '  ✓ confirmed — ripples fired'; card.style.borderLeftColor = '#7ec87e'; }
    } else { btn.disabled = false; btn.textContent = 'Confirm'; }
  });
}

function dismissProjection(eventId, entityId, entityType) {
  var btn = event.target;
  btn.disabled = true;
  fetch('/' + RF.slug + '/dm/world/dismiss_projection', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ event_id: eventId, entity_id: entityId, entity_type: entityType })
  }).then(function(r) { return r.json(); }).then(function(data) {
    if (data.ok) { var card = document.getElementById('proj-' + eventId); if (card) card.remove(); }
    else { btn.disabled = false; }
  });
}

function generateBrief() {
  var btn = document.getElementById('brief-btn');
  btn.disabled = true; btn.textContent = 'Building...';
  fetch('/' + RF.slug + '/dm/session/brief', { method: 'POST' })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.brief) {
        var ta = document.getElementById('plan-textarea');
        ta.value = data.brief;
        var editPane = document.getElementById('plan-edit');
        editPane.style.display = 'block';
        var empty = document.getElementById('plan-empty');
        if (empty) empty.style.display = 'none';
        ta.focus();
      }
      btn.disabled = false; btn.textContent = RF.terms.briefCta + ' ✦';
    })
    .catch(function() { btn.disabled = false; btn.textContent = RF.terms.briefCta + ' ✦'; });
}

// ── Event log edit / delete ───────────────────────────────────────────────────
function rfEvtEdit(btn) {
  var id = btn.dataset.eid;
  var ed = document.getElementById('evtedit-' + id);
  if (!ed) return;
  ed.style.display = 'flex';
  var ta = document.getElementById('evtinput-' + id);
  if (ta) ta.value = btn.dataset.note || '';
  var ps = document.getElementById('evtpol-' + id);
  if (ps) ps.value = btn.dataset.polarity || '';
  var is = document.getElementById('evtint-' + id);
  if (is) is.value = btn.dataset.intensity || 1;
  document.querySelectorAll('[id^="evtwit-' + id + '-"]').forEach(function(cb) { cb.dataset.initial = cb.checked ? 'true' : 'false'; });
}

function rfEvtCancelEdit(id) {
  var ed = document.getElementById('evtedit-' + id);
  if (ed) ed.style.display = 'none';
}

function rfEvtSave(id, entityId, entityType) {
  var note = (document.getElementById('evtinput-' + id) || {}).value || '';
  var polarity = (document.getElementById('evtpol-' + id) || {}).value || '';
  var intensity = +((document.getElementById('evtint-' + id) || {}).value || 1);
  var visibility = (document.getElementById('evtvis-' + id) || {}).value || 'public';
  var actorSel = document.getElementById('evtactor-' + id);
  var actor_id = null, actor_type = null, clear_actor = false;
  if (actorSel) {
    if (actorSel.value) { actor_id = actorSel.value; var actorOpt = actorSel.options[actorSel.selectedIndex]; actor_type = actorOpt ? (actorOpt.dataset.type || null) : null; }
    else { clear_actor = true; }
  }
  var locSel = document.getElementById('evtloc-' + id);
  var location_id = locSel && locSel.value ? locSel.value : null;
  var clear_location = locSel ? !locSel.value : false;
  var witnesses_add = [], witnesses_remove = [];
  document.querySelectorAll('[id^="evtwit-' + id + '-"]').forEach(function(cb) {
    var was = cb.dataset.initial === 'true';
    if (cb.checked && !was) witnesses_add.push(cb.value);
    if (!cb.checked && was) witnesses_remove.push(cb.value);
  });
  fetch('/' + RF.slug + '/dm/log/event/edit', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ event_id: id, entity_id: entityId, entity_type: entityType, note: note, polarity: polarity, intensity: intensity, visibility: visibility, actor_id: actor_id, actor_type: actor_type, clear_actor: clear_actor, location_id: location_id, clear_location: clear_location, witnesses_add: witnesses_add, witnesses_remove: witnesses_remove })
  }).then(function(r) { return r.json(); }).then(function(d) {
    if (d.ok) {
      var noteEl = document.getElementById('evtnote-' + id);
      if (noteEl) noteEl.textContent = note;
      document.querySelectorAll('[id^="evtwit-' + id + '-"]').forEach(function(cb) { cb.dataset.initial = cb.checked ? 'true' : 'false'; });
      rfEvtCancelEdit(id);
    }
  });
}

function rfEvtDelete(btn) {
  var id = btn.dataset.eid;
  fetch('/' + RF.slug + '/dm/log/event/delete', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ event_id: id, entity_id: btn.dataset.entityId, entity_type: btn.dataset.etype })
  }).then(function(r) { return r.json(); }).then(function(d) {
    if (d.ok) { var card = document.getElementById('evtcard-' + id); if (card) card.remove(); }
  });
}

// ── Initialization (DOM ready) ────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function() {
  // Scroll restore
  var y = sessionStorage.getItem('rf_scroll');
  if (y !== null) { sessionStorage.removeItem('rf_scroll'); window.scrollTo(0, parseInt(y, 10)); }

  // Render proposals if saved
  if (_proposalData.length) renderProposals(_proposalData, RF.proposalSession);

  // Getting started banner
  var rfgs = document.getElementById('rf-gs');
  if (rfgs && !localStorage.getItem('rf_gs_' + RF.slug)) rfgs.style.display = 'block';

  // World section collapse restore
  var stored = sessionStorage.getItem('rf_world_open');
  if (stored === '1') {
    var wbody = document.getElementById('world-section-body');
    var wbtn = document.getElementById('world-toggle-btn');
    if (wbody) wbody.style.display = '';
    if (wbtn) wbtn.textContent = 'Collapse ▴';
  }

  // Quick log faction checkboxes
  var factionNames = {};
  (RF.factions || []).forEach(function(f) { factionNames[f.id] = f.name; });
  var sel = document.getElementById('quick-entity-select');
  var container = document.getElementById('also-faction-checkboxes');
  if (sel && container) {
    function updateFactionCheckboxes() {
      var opt = sel.options[sel.selectedIndex];
      var fids = opt ? (opt.getAttribute('data-factions') || '').split(',').filter(Boolean) : [];
      var hfids = opt ? (opt.getAttribute('data-hidden-factions') || '').split(',').filter(Boolean) : [];
      container.innerHTML = '';
      fids.concat(hfids).forEach(function(fid, i) {
        if (!factionNames[fid]) return;
        var isDm = i >= fids.length;
        var lbl = document.createElement('label');
        lbl.style.cssText = 'display:flex;align-items:center;gap:6px;cursor:pointer;font-size:0.78rem;color:var(--muted);' + (isDm ? 'opacity:0.7;' : '');
        var cb = document.createElement('input');
        cb.type = 'checkbox'; cb.name = 'also_faction_ids'; cb.value = fid;
        cb.setAttribute('form', 'quick-log-form');
        cb.checked = false; cb.style.accentColor = 'var(--gold)';
        lbl.appendChild(cb);
        lbl.appendChild(document.createTextNode('Also affect ' + factionNames[fid] + (isDm ? ' (DM)' : '')));
        container.appendChild(lbl);
      });
    }
    sel.addEventListener('change', updateFactionCheckboxes);
    updateFactionCheckboxes();
  }

  // Quick log form AJAX
  var qlForm = document.getElementById('quick-log-form');
  if (qlForm) {
    qlForm.addEventListener('submit', function(e) {
      e.preventDefault();
      var submitBtn = qlForm.querySelector('[type=submit]');
      if (submitBtn) submitBtn.disabled = true;
      var fd = new FormData(qlForm);
      fd.set('ajax', '1');
      sessionStorage.setItem('rf_scroll', window.scrollY);
      fetch(qlForm.action, { method: 'POST', body: fd })
        .then(function(r) { return r.json(); })
        .then(function(data) {
          if (!data.ok) { sessionStorage.removeItem('rf_scroll'); if (submitBtn) submitBtn.disabled = false; return; }
          if (submitBtn) { submitBtn.textContent = 'Logged ✓'; submitBtn.style.background = '#7ec87e'; }
          setTimeout(function() { location.reload(); }, 1200);
        })
        .catch(function() { sessionStorage.removeItem('rf_scroll'); if (submitBtn) submitBtn.disabled = false; });
    });
  }

  // AJAX relation / edit forms
  document.addEventListener('submit', function(e) {
    var form = e.target;
    if (!('ajax' in form.dataset)) return;
    e.preventDefault();
    var fd = new FormData(form);
    var submitBtn = form.querySelector('[type=submit]');
    if (submitBtn) submitBtn.disabled = true;
    fetch(form.action, { method: 'POST', body: fd })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (!data.ok) { if (submitBtn) submitBtn.disabled = false; return; }
        var panelId = form.dataset.relPanel;
        var etype = form.dataset.entityType;
        var eid = form.dataset.entityId;
        var saveBtnId = form.dataset.saveBtn;
        if (panelId && etype && eid) {
          fetch('/' + RF.slug + '/dm/entity/' + etype + '/' + encodeURIComponent(eid) + '/panel')
            .then(function(r) { return r.json(); })
            .then(function(d) {
              _renderRelations(panelId, d.relations || [], etype, eid);
              if (d.char_relations) _renderCharRelations(panelId, d.char_relations, eid);
              form.reset();
              if (submitBtn) submitBtn.disabled = false;
            });
        } else if (saveBtnId) {
          var btn = document.getElementById(saveBtnId);
          if (btn) { var orig = btn.textContent; btn.textContent = 'Saved ✓'; btn.style.background = '#7ec87e'; setTimeout(function() { btn.textContent = orig; btn.style.background = ''; btn.disabled = false; }, 1500); }
        } else if (form.dataset.addForm) {
          if (submitBtn) { submitBtn.textContent = 'Added ✓'; submitBtn.style.background = '#7ec87e'; }
          setTimeout(function() { location.reload(); }, 600);
        }
      })
      .catch(function() { if (submitBtn) submitBtn.disabled = false; });
  });

  // Convert mode hint
  var convertSel = document.getElementById('convert-mode-select');
  var hint = document.getElementById('convert-hint');
  if (convertSel && hint) {
    var currentMode = RF.currentMode || 'ttrpg';
    var hints = {
      ttrpg: "You'll choose which characters become party members.",
      fiction: currentMode === 'ttrpg' ? "Party members will become Characters." : "Only terminology changes — no data affected.",
      historical: currentMode === 'ttrpg' ? "Party members will become Figures." : "Only terminology changes — no data affected."
    };
    function updateConvertHint() { hint.textContent = hints[convertSel.value] || ''; }
    convertSel.addEventListener('change', updateConvertHint);
    updateConvertHint();
  }
});
