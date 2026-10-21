// パネルの中で動く小さなスクリプト（文字列）。panelHtml.ts が <script nonce> に入れる。外部の読み込みはしない。
// render を受けたら本体を差し替え、ボタンで openArtifact・selectRun、読み込み後に ready を送る。拡張へ送るメッセージはこの 3 種類だけ。
// 理由を持つ節（data-reasons）を押す・Enter・Space で、その節の理由の欄を開け閉めする。選びはこの中だけで持ち、拡張へは送らない。
// 時間の数え上げ（D0017）：[data-elapsed] は「基準の秒」。基準を受けた時刻（このパネルの時計）からの差だけを足し、記録の時刻は読まない。
// タイマーは1つだけ。見えていない間と、数える要素が無いときは回さない。
// 止まっているかも（D0021）：[data-quiet] は「最後の更新からの秒（基準）」、data-stale-after は「目安の秒」。同じ数え上げの中で、
// 基準＋差 が目安に届いた要素に is-stale を付ける。付けるだけで、外すのは描き直し（DOM ごとの入れ替え）だけ。数字だけの整数の文字でない値は読み取らない。
// 数える要素は [data-elapsed] と [data-quiet] の両方（どちらか 1 つでもあればタイマーを回す）。
// 戻る矢印の光り：data-count が前の描き直しより増えたときだけ is-new を付け（動きを減らす設定では付けない）、
// 光り始めから FLASH_MS のあいだは描き直しをまたいで付け直す。
// D0019 で足したもの（どれもパネルの中だけで決め、拡張へ送らず、保存もしない）：
// - 絞り込みの入力（data-keep="filter"）・状態のタブ（data-list-tab）・詳細のタブ（data-detail-tab）・「成果物を開く」（data-open-artifacts）。
// - 描き直しをまたぐ保持：入力の文字・タブの選び・各枠（data-scroll）のスクロール位置・焦点（data-keep・data-run・data-reasons を持つ要素）と入力の選択範囲。
//   選んだ run が変わったときは、図の枠・出力・時系列・ページの位置を先頭に戻す（一覧の位置・絞り込み・タブの選びは残す）。
// - 図の拡大縮小（AC-79）：Ctrl（⌘）＋ホイールと図の枠のボタンで 50%〜200%（10% 刻み）。倍率は svg の width 属性で効かせ、描き直しのあとも付け直す。
// - 日本語入力の変換中（compositionstart から compositionend まで）に来た描き直しは取っておき、終わったあとに最後の 1 回だけ適用する。
export const PANEL_SCRIPT = `
(function () {
  const vscode = acquireVsCodeApi();
  const root = document.querySelector('.root');
  const FLASH_MS = 1400;
  let picked = null;
  let baseMs = Date.now();
  let timerId = null;
  let loopMemo = null;
  let flashMemo = {};
  let filterText = '';
  let listTab = 'all';
  let detailTab = 'diagram';
  let scrollMemo = {};
  let composing = false;
  let pendingHtml = null;
  let shownRun = null;
  const ZOOM_MIN = 50;
  const ZOOM_MAX = 200;
  const ZOOM_STEP = 10;
  let zoom = 100;
  function fmt(sec) {
    const t = isFinite(sec) && sec > 0 ? Math.floor(sec) : 0;
    const h = Math.floor(t / 3600);
    const m = Math.floor((t % 3600) / 60);
    const s = String(t % 60).padStart(2, '0');
    return h > 0 ? h + ':' + String(m).padStart(2, '0') + ':' + s : m + ':' + s;
  }
  const COUNTING = '[data-elapsed],[data-quiet]';
  function wholeNumber(raw, min) {
    if (raw === null || !/^\\d+$/.test(raw)) return null;
    const n = Number(raw);
    return Number.isSafeInteger(n) && n >= min ? n : null;
  }
  function paint() {
    const dt = Math.max(0, Math.floor((Date.now() - baseMs) / 1000));
    root.querySelectorAll('[data-elapsed]').forEach(function (el) {
      const raw = el.getAttribute('data-elapsed');
      if (raw === null || !/^-?\\d+(\\.\\d+)?$/.test(raw)) return;
      el.textContent = fmt(Number(raw) + dt);
    });
    root.querySelectorAll('[data-quiet]').forEach(function (el) {
      const quiet = wholeNumber(el.getAttribute('data-quiet'), 0);
      const after = wholeNumber(el.getAttribute('data-stale-after'), 1);
      if (quiet === null || after === null) return;
      if (quiet + dt >= after) el.classList.add('is-stale');
    });
  }
  function stopTimer() {
    if (timerId !== null) { clearInterval(timerId); timerId = null; }
  }
  function startTimer() {
    stopTimer();
    if (document.visibilityState === 'hidden') return;
    if (root.querySelectorAll(COUNTING).length === 0) return;
    paint();
    timerId = setInterval(paint, 1000);
  }
  function reducedMotion() {
    return typeof window.matchMedia !== 'function' || window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }
  function flashOn(l, elapsed) {
    l.classList.add('is-new');
    if (typeof l.getAnimations !== 'function') return;
    l.getAnimations({ subtree: true }).forEach(function (a) { a.currentTime = elapsed; });
  }
  function pressedRun() {
    const pressed = root.querySelector('button[data-run][aria-pressed="true"]');
    return pressed ? pressed.getAttribute('data-run') : null;
  }
  function markNewLoops() {
    const counts = {};
    root.querySelectorAll('[data-loop]').forEach(function (l) {
      counts[l.getAttribute('data-loop')] = Number(l.getAttribute('data-count')) || 0;
    });
    const pressed = pressedRun();
    const run = pressed === null ? '' : pressed;
    const sameRun = loopMemo !== null && loopMemo.run === run;
    if (!sameRun) flashMemo = {};
    const now = Date.now();
    if (!reducedMotion()) {
      root.querySelectorAll('[data-loop]').forEach(function (l) {
        const id = l.getAttribute('data-loop');
        if (sameRun && id in loopMemo.counts && counts[id] > loopMemo.counts[id]) {
          flashMemo[id] = now;
          flashOn(l, 0);
        } else if (id in flashMemo) {
          const age = now - flashMemo[id];
          if (age < FLASH_MS) flashOn(l, age);
          else delete flashMemo[id];
        }
      });
    }
    loopMemo = { run: run, counts: counts };
  }
  function nearBottom(el) { return !el || el.scrollHeight - el.scrollTop - el.clientHeight < 40; }
  function follow(wasNear) { const t = root.querySelector('.terminal'); if (t && wasNear) t.scrollTop = t.scrollHeight; }
  function applyPick() {
    const nodes = Array.from(root.querySelectorAll('[data-reasons]'));
    if (picked !== null && !nodes.some(function (g) { return g.getAttribute('data-reasons') === picked; })) picked = null;
    const pickedNode = nodes.find(function (g) { return g.getAttribute('data-reasons') === picked; });
    const loopId = pickedNode ? pickedNode.getAttribute('data-reasons-loop') : null;
    nodes.forEach(function (g) {
      const on = g === pickedNode;
      g.setAttribute('aria-pressed', on ? 'true' : 'false');
      g.classList.toggle('is-picked', on);
    });
    root.querySelectorAll('[data-loop]').forEach(function (l) {
      l.classList.toggle('is-picked', loopId !== null && l.getAttribute('data-loop') === loopId);
    });
    root.querySelectorAll('[data-reasons-for]').forEach(function (s) {
      s.hidden = s.getAttribute('data-reasons-for') !== picked;
    });
  }
  function togglePick(g) {
    const id = g.getAttribute('data-reasons');
    picked = picked === id ? null : id;
    applyPick();
  }

  // ---- 絞り込み・タブ（パネルの中だけ） ----
  function applyUi() {
    const input = root.querySelector('input[data-keep="filter"]');
    if (input && input.value !== filterText) input.value = filterText;
    root.querySelectorAll('button[data-list-tab]').forEach(function (b) {
      b.setAttribute('aria-selected', b.getAttribute('data-list-tab') === listTab ? 'true' : 'false');
    });
    const needle = filterText.trim().toLowerCase();
    let shown = 0;
    root.querySelectorAll('li[data-group]').forEach(function (li) {
      const tabOk = listTab === 'all' || li.getAttribute('data-group') === listTab;
      const textOk = needle === '' || ['data-name', 'data-sid', 'data-branch'].some(function (a) {
        return (li.getAttribute(a) || '').toLowerCase().indexOf(needle) !== -1;
      });
      const on = tabOk && textOk;
      li.hidden = !on;
      if (on) shown += 1;
    });
    root.querySelectorAll('section[data-group]').forEach(function (s) {
      s.hidden = !Array.from(s.querySelectorAll('li[data-group]')).some(function (li) { return !li.hidden; });
    });
    const empty = root.querySelector('.run-empty');
    if (empty) empty.hidden = shown > 0;
    root.querySelectorAll('button[data-detail-tab]').forEach(function (b) {
      b.setAttribute('aria-selected', b.getAttribute('data-detail-tab') === detailTab ? 'true' : 'false');
    });
    root.querySelectorAll('[data-detail-panel]').forEach(function (p) {
      p.hidden = p.getAttribute('data-detail-panel') !== detailTab;
    });
    applyPick();
  }

  // ---- スクロール位置・焦点の保持 ----
  function visibleScrollers() {
    return Array.from(root.querySelectorAll('[data-scroll]')).filter(function (el) { return el.closest('[hidden]') === null; });
  }
  function captureScroll() {
    visibleScrollers().forEach(function (el) {
      scrollMemo[el.getAttribute('data-scroll')] = { top: el.scrollTop, left: el.scrollLeft };
    });
    if (typeof window.scrollY === 'number') scrollMemo.page = { top: window.scrollY, left: window.scrollX || 0 };
  }
  function restoreScroll() {
    visibleScrollers().forEach(function (el) {
      const m = scrollMemo[el.getAttribute('data-scroll')];
      if (m) { el.scrollTop = m.top; el.scrollLeft = m.left; }
    });
    if (scrollMemo.page && typeof window.scrollTo === 'function') window.scrollTo(scrollMemo.page.left, scrollMemo.page.top);
  }
  function focusKey() {
    const active = document.activeElement;
    if (!active || typeof active.closest !== 'function') return null;
    const el = active.closest('[data-keep],[data-run],[data-reasons]');
    if (!el) return null;
    const attr = el.hasAttribute('data-keep') ? 'data-keep' : el.hasAttribute('data-run') ? 'data-run' : 'data-reasons';
    const key = { attr: attr, value: el.getAttribute(attr), start: null, end: null };
    if (typeof el.selectionStart === 'number') { key.start = el.selectionStart; key.end = el.selectionEnd; }
    return key;
  }
  function restoreFocus(key) {
    if (key === null) return;
    const again = Array.from(root.querySelectorAll('[' + key.attr + ']')).find(function (n) { return n.getAttribute(key.attr) === key.value; });
    if (!again) return;
    again.focus();
    if (key.start !== null && typeof again.setSelectionRange === 'function') again.setSelectionRange(key.start, key.end);
  }

  // ---- 図の拡大縮小（倍率はここだけで持つ。拡張へは送らず、保存もしない） ----
  function applyZoom() {
    const svg = root.querySelector('svg.flow');
    if (svg) {
      const vb = (svg.getAttribute('viewBox') || '').split(/\\s+/);
      const base = Number(vb[2]);
      if (base > 0) svg.setAttribute('width', String(Math.round(base * zoom) / 100));
    }
    const reset = root.querySelector('button[data-zoom="reset"]');
    if (reset) {
      reset.textContent = zoom + '%';
      reset.setAttribute('aria-label', '図の大きさを 100% に戻す（今 ' + zoom + '%）');
    }
  }
  function setZoom(next) {
    zoom = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, next));
    applyZoom();
  }

  // ---- 描き直し ----
  function applyRender(html) {
    let wasNear = nearBottom(root.querySelector('.terminal'));
    captureScroll();
    const before = shownRun;
    const key = focusKey();
    root.innerHTML = html;
    baseMs = Date.now();
    shownRun = pressedRun();
    if (before !== shownRun) {
      delete scrollMemo.diagram;
      delete scrollMemo.output;
      delete scrollMemo.gantt;
      delete scrollMemo.page;
      wasNear = true;
    }
    applyUi();
    applyZoom();
    restoreScroll();
    markNewLoops();
    startTimer();
    restoreFocus(key);
    follow(wasNear);
  }
  function endComposition(event) {
    composing = false;
    const t = event && event.target;
    if (t && typeof t.matches === 'function' && t.matches('input[data-keep="filter"]')) filterText = t.value;
    if (pendingHtml !== null) {
      const html = pendingHtml;
      pendingHtml = null;
      applyRender(html);
    } else {
      applyUi();
    }
  }
  window.addEventListener('message', function (event) {
    const msg = event.data;
    if (!msg || msg.type !== 'render' || typeof msg.html !== 'string') return;
    if (composing) { pendingHtml = msg.html; return; }
    applyRender(msg.html);
  });
  function switchTab(change) {
    captureScroll();
    change();
    applyUi();
    restoreScroll();
  }
  root.addEventListener('click', function (event) {
    const target = event.target;
    const button = target.closest('button[data-artifact]');
    if (button && !button.disabled) vscode.postMessage({ type: 'openArtifact', name: button.getAttribute('data-artifact') });
    const run = target.closest('button[data-run]');
    if (run) vscode.postMessage({ type: 'selectRun', id: run.getAttribute('data-run') });
    const listBtn = target.closest('button[data-list-tab]');
    if (listBtn) switchTab(function () { listTab = listBtn.getAttribute('data-list-tab'); });
    const detailBtn = target.closest('button[data-detail-tab]');
    if (detailBtn) switchTab(function () { detailTab = detailBtn.getAttribute('data-detail-tab'); });
    const open = target.closest('button[data-open-artifacts]');
    if (open) switchTab(function () { detailTab = 'artifacts'; });
    const zoomBtn = target.closest('button[data-zoom]');
    if (zoomBtn) {
      const kind = zoomBtn.getAttribute('data-zoom');
      setZoom(kind === 'in' ? zoom + ZOOM_STEP : kind === 'out' ? zoom - ZOOM_STEP : 100);
    }
    const node = target.closest('[data-reasons]');
    if (node) togglePick(node);
  });
  root.addEventListener('wheel', function (event) {
    if (!event.ctrlKey && !event.metaKey) return;
    const t = event.target;
    if (!t || typeof t.closest !== 'function' || !t.closest('.pane-diagram')) return;
    event.preventDefault();
    if (event.deltaY < 0) setZoom(zoom + ZOOM_STEP);
    else if (event.deltaY > 0) setZoom(zoom - ZOOM_STEP);
  }, { passive: false });
  root.addEventListener('keydown', function (event) {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const node = event.target.closest('[data-reasons]');
    if (!node) return;
    event.preventDefault();
    togglePick(node);
  });
  root.addEventListener('input', function (event) {
    const t = event.target;
    if (!t || typeof t.matches !== 'function' || !t.matches('input[data-keep="filter"]')) return;
    if (composing || event.isComposing) return;
    filterText = t.value;
    applyUi();
  });
  root.addEventListener('compositionstart', function () { composing = true; });
  root.addEventListener('compositionend', endComposition);
  root.addEventListener('focusout', function (event) {
    if (composing && event.target && typeof event.target.matches === 'function' && event.target.matches('input[data-keep="filter"]')) endComposition(event);
  });
  root.addEventListener('animationend', function (event) {
    const flashing = event.target && event.target.closest ? event.target.closest('.is-new') : null;
    if (!flashing) return;
    flashing.classList.remove('is-new');
    delete flashMemo[flashing.getAttribute('data-loop')];
  });
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') stopTimer();
    else startTimer();
  });
  shownRun = pressedRun();
  applyUi();
  applyZoom();
  markNewLoops();
  startTimer();
  follow(true);
  vscode.postMessage({ type: 'ready' });
})();
`;
