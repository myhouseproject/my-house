(function (root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (root) {
    root.AIInteriorDesigner = api;
    if (root.document) {
      const start = () => api.mount(root);
      if (root.document.readyState === 'loading') root.document.addEventListener('DOMContentLoaded', start, {once:true});
      else setTimeout(start, 0);
    }
  }
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  const unique = values => [...new Set(values)];
  const byKey = config => new Map((config?.variants || []).map(v => [String(v.key), v]));

  function normalizePair(config, keys) {
    const variants = byKey(config);
    const clean = unique((keys || []).map(String)).filter(k => variants.has(k));
    if (clean.length < 2) return null;
    return clean.slice(0, 2).map(k => variants.get(k));
  }

  function differingAxes(a, b, axes) {
    return (axes || []).filter(axis => String(a?.axes?.[axis] ?? '') !== String(b?.axes?.[axis] ?? ''));
  }

  function localPair(config, history = []) {
    const variants = config?.variants || [];
    if (variants.length < 2) throw new Error('Designer potrzebuje co najmniej dwóch wariantów.');
    if (!history.length) {
      const opening = normalizePair(config, config.opening_pair);
      if (opening) return {candidates: opening, comparison_axis: differingAxes(opening[0], opening[1], config.axis_order)[0] || 'kierunek'};
      return {candidates: variants.slice(0, 2), comparison_axis: 'kierunek'};
    }

    const map = byKey(config);
    const lastWinnerKey = String(history.at(-1)?.winner_key || variants[0].key);
    const winner = map.get(lastWinnerKey) || variants[0];
    const compared = new Set();
    for (const round of history) {
      const a = String(round?.winner_key || ''), b = String(round?.loser_key || '');
      if (a && b) compared.add([a, b].sort().join('|'));
    }
    const axes = config.axis_order?.length ? config.axis_order : unique(variants.flatMap(v => Object.keys(v.axes || {})));
    const targetAxis = axes[history.length % Math.max(axes.length, 1)] || 'kierunek';

    const candidates = variants.filter(v => String(v.key) !== String(winner.key));
    candidates.sort((a, b) => {
      const score = challenger => {
        const diffs = differingAxes(winner, challenger, axes);
        const pairId = [String(winner.key), String(challenger.key)].sort().join('|');
        let s = compared.has(pairId) ? -100 : 100;
        if (diffs.length === 1) s += 35;
        if (diffs.includes(targetAxis)) s += 25;
        s -= Math.max(0, diffs.length - 1) * 8;
        return s;
      };
      return score(b) - score(a) || String(a.key).localeCompare(String(b.key));
    });
    const challenger = candidates[0] || variants.find(v => String(v.key) !== String(winner.key));
    return {candidates: [winner, challenger], comparison_axis: differingAxes(winner, challenger, axes)[0] || targetAxis};
  }

  function validateRemotePair(config, payload) {
    const pair = normalizePair(config, [payload?.candidate_a, payload?.candidate_b]);
    if (!pair) return null;
    return {candidates: pair, comparison_axis: String(payload?.comparison_axis || 'kierunek')};
  }

  async function remotePair(config, history, fetchImpl = globalThis.fetch) {
    const endpoint = String(config?.backend_endpoint || '').trim();
    if (!endpoint || !fetchImpl) return localPair(config, history);
    const request = {
      schema_version: 1,
      room: config.room || {},
      axis_order: config.axis_order || [],
      variants: (config.variants || []).map(v => ({key:v.key, label:v.label, axes:v.axes || {}, description:v.description || ''})),
      history: history.map(h => ({winner_key:h.winner_key, loser_key:h.loser_key, comparison_axis:h.comparison_axis || ''}))
    };
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    const timeout = setTimeout(() => controller?.abort(), Number(config.request_timeout_ms) || 10000);
    try {
      const response = await fetchImpl(endpoint, {
        method: 'POST',
        headers: {'content-type':'application/json'},
        body: JSON.stringify(request),
        signal: controller?.signal
      });
      if (!response.ok) throw new Error('HTTP ' + response.status);
      const parsed = await response.json();
      return validateRemotePair(config, parsed) || localPair(config, history);
    } finally {
      clearTimeout(timeout);
    }
  }

  function mount(win) {
    const document = win.document;
    if (!document || document.getElementById('aiDesignerLauncher')) return;
    const config = win.__AI_DESIGNER_CONFIG__ || win.VIEWER_CONFIG?.ai_designer || win.VIEWER_CONFIG?.aiDesigner;
    if (!config?.enabled || Number(config?.room?.number || config?.room_number || 0) !== 15 || !(config.variants || []).length) return;

    const roomNumber = Number(config.room?.number || config.room_number || 15);
    const state = win.__aiDesignerState = win.__aiDesignerState || {
      active: false,
      activeVariant: null,
      roomNumber,
      history: [],
      pair: null,
      loading: false
    };
    const storageKey = 'dom_ai_designer_r15_v1';
    try {
      const saved = JSON.parse(win.sessionStorage?.getItem(storageKey) || 'null');
      if (saved?.history && Array.isArray(saved.history)) state.history = saved.history.slice(0, Number(config.max_rounds) || 20);
    } catch (_) {}

    const style = document.createElement('style');
    style.textContent = \`
#aiDesignerLauncher{position:absolute;left:16px;bottom:84px;z-index:72;border:0;background:#173f47;color:#fff;border-radius:999px;padding:11px 16px;font-weight:750;box-shadow:0 8px 28px rgba(0,0,0,.22);display:none}
#aiDesignerPanel{position:absolute;left:10px;right:10px;bottom:76px;z-index:74;background:rgba(255,255,255,.97);backdrop-filter:blur(12px);border:1px solid #d7e0e2;border-radius:18px;padding:12px;box-shadow:0 16px 42px rgba(14,30,36,.28);display:none;max-width:760px;margin:auto}
#aiDesignerPanel.open{display:block}
#aiDesignerHead{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:9px}
#aiDesignerTitle{font-weight:800;font-size:14px;color:#17353d}
#aiDesignerStatus{font-size:10px;color:#61727a;margin-top:2px}
#aiDesignerClose{width:34px;height:34px;border-radius:50%;padding:0;font-size:18px}
#aiDesignerOptions{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.aiDesignCard{padding:0;overflow:hidden;border-radius:13px;background:#f5f7f7;border:2px solid transparent;text-align:left;min-width:0}
.aiDesignCard:hover,.aiDesignCard:active{border-color:#1e5b64}
.aiDesignCard img{display:block;width:100%;aspect-ratio:4/3;object-fit:cover;background:#e8edee}
.aiDesignCard .aiMeta{padding:8px}
.aiDesignCard strong{display:block;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.aiDesignCard span{display:block;font-size:10px;color:#687981;margin-top:2px}
#aiDesignerFooter{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-top:9px;font-size:10px;color:#63747c}
#aiDesignerReset{padding:6px 9px;font-size:10px}
#aiDesignerBusy{position:absolute;inset:48px 12px 42px;display:none;place-items:center;background:rgba(255,255,255,.78);border-radius:12px;font-weight:750;color:#244b53}
#aiDesignerBusy.show{display:grid}
@media (max-width:600px){#aiDesignerPanel{bottom:92px}.aiDesignCard strong{font-size:11px}#aiDesignerLauncher{bottom:94px}}
\`;
    document.head.appendChild(style);

    const launcher = document.createElement('button');
    launcher.id = 'aiDesignerLauncher';
    launcher.type = 'button';
    launcher.textContent = '✨ Porównaj A/B';
    const panel = document.createElement('section');
    panel.id = 'aiDesignerPanel';
    panel.setAttribute('aria-label', 'Projektant AI gabinetu');
    panel.innerHTML = \`
      <div id="aiDesignerHead"><div><div id="aiDesignerTitle">Gabinet · wybierz lepszą wersję</div><div id="aiDesignerStatus"></div></div><button id="aiDesignerClose" type="button" aria-label="Zamknij">×</button></div>
      <div id="aiDesignerOptions">
        <button class="aiDesignCard" id="aiOptionA" type="button"><img alt="Wariant A"><div class="aiMeta"><strong>Wariant A</strong><span></span></div></button>
        <button class="aiDesignCard" id="aiOptionB" type="button"><img alt="Wariant B"><div class="aiMeta"><strong>Wariant B</strong><span></span></div></button>
      </div>
      <div id="aiDesignerFooter"><span id="aiDesignerRound"></span><button id="aiDesignerReset" type="button">Zacznij od nowa</button></div>
      <div id="aiDesignerBusy">Przygotowuję dwa widoki…</div>\`;
    const wrap = document.querySelector('#canvas-wrap') || document.body;
    wrap.append(launcher, panel);

    const status = panel.querySelector('#aiDesignerStatus');
    const busy = panel.querySelector('#aiDesignerBusy');
    const round = panel.querySelector('#aiDesignerRound');
    const cards = [panel.querySelector('#aiOptionA'), panel.querySelector('#aiOptionB')];

    const currentMode = () => {
      try { return String(win.__modelMode?.() || win.viewerMode || ''); } catch (_) { return ''; }
    };
    const isOfficeMode = mode => /^office(?:_top)?$/.test(String(mode).replaceAll('-', '_'));
    const save = () => {
      try { win.sessionStorage?.setItem(storageKey, JSON.stringify({history:state.history})); } catch (_) {}
    };
    const renderNow = () => { try { win.__renderTest?.(); } catch (_) {} };
    const setActiveVariant = key => {
      state.activeVariant = key || null;
      renderNow();
    };
    const stop = () => {
      state.active = false;
      state.activeVariant = null;
      panel.classList.remove('open');
      renderNow();
    };
    const syncMode = mode => {
      const visible = isOfficeMode(mode);
      launcher.style.display = visible && !panel.classList.contains('open') ? 'block' : 'none';
      if (!visible && state.active) stop();
    };
    win.__aiDesignerModeChanged = syncMode;

    async function capture(key) {
      setActiveVariant(key);
      await new Promise(resolve => win.requestAnimationFrame ? win.requestAnimationFrame(() => resolve()) : setTimeout(resolve, 0));
      renderNow();
      const canvas = document.querySelector('#view');
      try { return canvas?.toDataURL('image/jpeg', .82) || ''; } catch (_) { return ''; }
    }

    async function nextRound() {
      if (state.loading) return;
      state.loading = true;
      busy.classList.add('show');
      status.textContent = config.backend_endpoint ? 'AI dobiera następne porównanie' : 'Tryb szybki · warianty modelu 3D';
      try {
        let result;
        try { result = await remotePair(config, state.history, win.fetch?.bind(win)); }
        catch (_) {
          result = localPair(config, state.history);
          status.textContent = 'Tryb szybki · backend AI niedostępny';
        }
        state.pair = result;
        const [a, b] = result.candidates;
        const previews = [await capture(a.key), await capture(b.key)];
        [a, b].forEach((candidate, index) => {
          const card = cards[index];
          card.dataset.key = candidate.key;
          const image = card.querySelector('img');
          if (previews[index]) { image.src = previews[index]; image.hidden = false; } else image.hidden = true;
          card.querySelector('strong').textContent = (index ? 'B · ' : 'A · ') + candidate.label;
          card.querySelector('span').textContent = candidate.description || ('Sprawdzamy: ' + result.comparison_axis);
        });
        setActiveVariant(a.key);
        round.textContent = 'Runda ' + (state.history.length + 1) + ' · ' + (result.comparison_axis || 'porównanie');
      } finally {
        state.loading = false;
        busy.classList.remove('show');
      }
    }

    async function choose(index) {
      if (state.loading || !state.pair) return;
      const winner = state.pair.candidates[index], loser = state.pair.candidates[index ? 0 : 1];
      state.history.push({
        winner_key: winner.key,
        loser_key: loser.key,
        comparison_axis: state.pair.comparison_axis || '',
        at: new Date().toISOString()
      });
      const maxRounds = Number(config.max_rounds) || 12;
      if (state.history.length > maxRounds) state.history = state.history.slice(-maxRounds);
      save();
      setActiveVariant(winner.key);
      await nextRound();
    }

    launcher.onclick = async () => {
      state.active = true;
      panel.classList.add('open');
      launcher.style.display = 'none';
      await nextRound();
    };
    panel.querySelector('#aiDesignerClose').onclick = () => {
      stop();
      syncMode(currentMode());
    };
    panel.querySelector('#aiDesignerReset').onclick = async () => {
      state.history = [];
      save();
      await nextRound();
    };
    cards[0].onclick = () => choose(0);
    cards[1].onclick = () => choose(1);
    syncMode(currentMode());
  }

  return {normalizePair, differingAxes, localPair, validateRemotePair, remotePair, mount};
});
