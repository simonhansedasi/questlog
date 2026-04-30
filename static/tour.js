(function() {
  var STEPS = [
    {
      path: /^\/demo\/?$/,
      title: "Welcome to RippleForge",
      body: "This demo runs a full World War II campaign \u2014 twelve chapters, eight nations, fully interactive. We\u2019ll show you three things: ripple chains, the AI layer, and timeline forking.",
      cta: "See a ripple happen \u2192",
      next: "/demo/world/ripples"
    },
    {
      path: /^\/demo\/world\/ripples/,
      title: "One event. Four consequences.",
      body: "When Paulus surrendered at Stalingrad, RippleForge automatically updated four entities \u2014 each with a different consequence based on their relationship to him. You didn\u2019t write any of this.",
      cta: "See the AI layer \u2192",
      next: "/demo/ai"
    },
    {
      path: /^\/demo\/ai/,
      title: "The AI layer",
      body: "Two features that save hours. Paste messy session notes and get structured world events \u2014 or ask what probably happens next based on every active tension in your world.\n\nTry both buttons, then keep going.",
      cta: "Try timeline forking \u2192",
      next: "/demo/world"
    },
    {
      path: /^\/demo\/world/,
      title: "Timeline forking",
      body: "Scroll down to \u201cNew alternate timeline.\u201d Pick any chapter as your fork point, give it a name, and branch. Events you log go into the branch only \u2014 the original history stays intact.\n\nThe relationship graph updates to show the divergence.",
      cta: "Got it",
      next: null
    }
  ];

  function idx() { return parseInt(sessionStorage.getItem('rf_tour') || '0'); }

  document.addEventListener('DOMContentLoaded', function() {
    var i = idx();
    if (i >= STEPS.length) return;
    var step = STEPS[i];
    if (!step.path.test(window.location.pathname)) return;

    var dots = STEPS.map(function(_, j) {
      return '<span style="width:7px;height:7px;border-radius:50%;display:inline-block;background:' +
        (j === i ? 'var(--purple)' : 'var(--border)') + ';transition:background 0.2s;"></span>';
    }).join('');

    var actionBtn = step.next
      ? '<a href="' + step.next + '" onclick="sessionStorage.setItem(\'rf_tour\',\'' + (i + 1) + '\');" ' +
        'style="background:var(--purple);color:#fff;border-radius:4px;padding:7px 16px;font-size:0.82rem;font-weight:700;text-decoration:none;white-space:nowrap;">' +
        step.cta + '</a>'
      : '<button onclick="sessionStorage.setItem(\'rf_tour\',\'99\');document.getElementById(\'rf-tour\').remove();" ' +
        'style="background:var(--purple);color:#fff;border:none;border-radius:4px;padding:7px 16px;font-size:0.82rem;font-weight:700;cursor:pointer;">' +
        step.cta + '</button>';

    var bodyHtml = step.body.replace(/\n\n/g, '</p><p style="color:var(--muted);font-size:0.82rem;line-height:1.55;margin:8px 0 0 0;">');

    var div = document.createElement('div');
    div.id = 'rf-tour';
    div.style.cssText = [
      'position:fixed',
      'bottom:24px',
      'right:24px',
      'z-index:10000',
      'background:var(--surface)',
      'border:1px solid var(--purple)',
      'border-radius:10px',
      'padding:18px 20px',
      'max-width:300px',
      'width:calc(100vw - 48px)',
      'box-shadow:0 8px 32px rgba(0,0,0,0.5)'
    ].join(';');

    div.innerHTML =
      '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">' +
        '<span style="color:var(--purple);font-size:0.65rem;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;">RippleForge Tour</span>' +
        '<button onclick="sessionStorage.setItem(\'rf_tour\',\'99\');document.getElementById(\'rf-tour\').remove();" ' +
          'style="background:none;border:none;color:var(--muted);cursor:pointer;font-size:0.78rem;padding:0;line-height:1;">skip</button>' +
      '</div>' +
      '<h3 style="margin:0 0 8px 0;font-size:0.95rem;color:var(--text);">' + step.title + '</h3>' +
      '<p style="color:var(--muted);font-size:0.82rem;line-height:1.55;margin:0 0 16px 0;">' + bodyHtml + '</p>' +
      '<div style="display:flex;justify-content:space-between;align-items:center;gap:12px;">' +
        '<div style="display:flex;gap:5px;align-items:center;">' + dots + '</div>' +
        actionBtn +
      '</div>';

    document.body.appendChild(div);
  });
})();
