// パイプ作図台のパネルの外側の HTML。中の操作は webview/pipeEditor.ts（out/pipeEditor.js）が行う。
// 色はすべて VSCode のテーマ（var(--vscode-*)）から。外から何も読み込まない（CSP は nonce と webview の出どころだけ）。
import { escapeHtml } from './escape.ts';

export interface PipeEditorHtmlOptions {
  nonce: string;
  /** webview.asWebviewUri で作った out/pipeEditor.js の URI */
  scriptUri: string;
  /** webview.cspSource */
  cspSource: string;
}

const STYLE = `
:root {
  --paper: var(--vscode-editor-background);
  --ink: var(--vscode-foreground);
  --muted: var(--vscode-descriptionForeground);
  --panel: var(--vscode-editorWidget-background);
  --rule: var(--vscode-panel-border);
  --grid: var(--vscode-editorIndentGuide-background);
  --next: var(--vscode-charts-blue);
  --route: var(--vscode-charts-orange);
  --return: var(--vscode-charts-red);
  --par: var(--vscode-charts-green);
  --sel: var(--vscode-editor-selectionBackground);
  --todo: var(--vscode-charts-yellow);
  --on-accent: var(--vscode-button-foreground);
  --k-research: var(--vscode-charts-blue);
  --k-agent: var(--vscode-charts-purple);
  --k-docs: var(--vscode-charts-blue);
  --k-tests: var(--vscode-charts-purple);
  --k-code: var(--vscode-foreground);
  --k-verify: var(--vscode-charts-green);
  --k-branch: var(--vscode-charts-orange);
  --k-outside: var(--vscode-charts-red);
  --sans: var(--vscode-font-family);
  --mono: var(--vscode-editor-font-family);
}
* { box-sizing: border-box; }
html, body { height: 100%; }
body { margin: 0; background: var(--paper); color: var(--ink); font-family: var(--sans); font-size: 13px; line-height: 1.5;
  padding: 8px 10px; display: grid; grid-template-rows: auto minmax(0, 1fr); gap: 8px; }
button, input, select, textarea { font: inherit; color: inherit; }
:focus-visible { outline: 2px solid var(--vscode-focusBorder); outline-offset: 2px; }
.top { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; }
.top h1 { margin: 0; font-size: 15px; font-weight: 700; display: flex; align-items: center; gap: 8px; }
.top h1 .mark { width: 18px; height: 18px; border-radius: 50%; border: 4px solid var(--next); }
.top .path { font-family: var(--mono); font-size: 12px; color: var(--muted); }
.spacer { flex: 1; }
.btn { border: 1px solid var(--vscode-button-border, var(--rule)); background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground);
  border-radius: 2px; padding: 3px 10px; cursor: pointer; white-space: nowrap; }
.btn:hover { background: var(--vscode-button-secondaryHoverBackground); }
.btn.primary { background: var(--vscode-button-background); color: var(--vscode-button-foreground); }
.btn.primary:hover { background: var(--vscode-button-hoverBackground); }
.btn.small { padding: 1px 8px; font-size: 12px; }
.zoom { font-family: var(--mono); font-size: 12px; min-width: 44px; text-align: center; }
.work { display: grid; grid-template-columns: 92px minmax(0, 1fr) 420px; gap: 8px; min-height: 0; }
.shelf { display: flex; flex-direction: column; gap: 4px; border: 1px solid var(--rule); border-radius: 3px; padding: 6px 4px; overflow-y: auto; background: var(--panel); }
.shelf h2 { margin: 0 0 2px; font-size: 11px; color: var(--muted); text-align: center; }
.tile { display: grid; justify-items: center; gap: 2px; padding: 5px 2px 4px; border: 1px solid transparent; border-radius: 3px; cursor: grab; font-size: 11px; text-align: center; touch-action: none; user-select: none; }
.tile:hover { border-color: var(--rule); background: var(--vscode-list-hoverBackground); }
.tile svg { width: 62px; height: 36px; overflow: visible; }
.tile svg .sh { fill: var(--paper); stroke: var(--ink); stroke-width: 1.6; }
.tile svg .sh.thick { stroke-width: 5; }
.tile svg .sh.hollow { fill: none; stroke-width: 4; }
.tile svg .par { fill: none; stroke: var(--par); }
.ghost { position: fixed; pointer-events: none; z-index: 50; opacity: .85; background: var(--panel); border: 1px solid var(--ink); }
.stage-area { position: relative; overflow: hidden; border: 1px solid var(--rule); border-radius: 3px; touch-action: none; user-select: none; min-height: 380px;
  background-color: var(--paper); background-image: radial-gradient(var(--grid) 1.2px, transparent 1.3px); background-size: 20px 20px; }
.world { position: absolute; left: 0; top: 0; transform-origin: 0 0; }
.wires { position: absolute; left: 0; top: 0; overflow: visible; }
.wire { fill: none; stroke-width: 5; stroke-linejoin: round; stroke-linecap: round; }
.wire.next { stroke: var(--next); } .wire.route { stroke: var(--route); } .wire.return { stroke: var(--return); stroke-dasharray: 8 6; stroke-width: 3; }
.wire.start, .wire.temp { stroke: var(--muted); }
.wire.sel { stroke-width: 8; }
.cable-out { fill: none; stroke: var(--ink); stroke-width: 8; stroke-linejoin: round; stroke-linecap: round; opacity: .55; }
.wire-hit { fill: none; stroke: transparent; stroke-width: 14; cursor: pointer; pointer-events: stroke; }
.socket { fill: var(--panel); stroke: var(--ink); stroke-width: 1.6; }
.socket.empty { stroke-dasharray: 3 2; }
.slot { fill: var(--ink); }
.plug-body { stroke: var(--ink); stroke-width: 1.4; }
.plug-body.next { fill: var(--next); } .plug-body.route { fill: var(--route); } .plug-body.return { fill: var(--return); } .plug-body.start, .plug-body.temp { fill: var(--muted); }
.prong { fill: var(--muted); stroke: var(--ink); stroke-width: .8; }
.seat { fill: var(--ink); }
.plug.grab { cursor: grab; }
.plug-hit { fill: transparent; }
.plug.grab:hover .plug-body { stroke-width: 2.4; }
.in-hand { pointer-events: none; }
/* 差した瞬間に、プラグをコンセントへ押し込む */
.plug-in.snap { animation: plug-snap .22s ease-out; }
@keyframes plug-snap { from { transform: translateX(-9px); } to { transform: translateX(0); } }
@media (prefers-reduced-motion: reduce) { .plug-in.snap { animation: none; } }
.bush { fill: var(--ink); }
.tag rect { fill: var(--route); } .tag text { fill: var(--on-accent); font-family: var(--mono); font-size: 10.5px; }
.node { position: absolute; cursor: move; user-select: none; touch-action: none; }
.node > svg.shape { position: absolute; inset: 0; overflow: visible; z-index: 1; }
.node > svg.shape .sh { fill: var(--panel); stroke: var(--ink); stroke-width: 1.6; }
.node > svg.shape .sh2 { fill: none; stroke: var(--ink); stroke-width: 1.2; }
.node.sel > svg.shape .sh { fill: var(--sel); stroke-width: 2.6; }
.node.drop > svg.shape .sh { stroke: var(--route); stroke-width: 3; }
.frame.drop { border-color: var(--route); }
.node .body { position: absolute; z-index: 2; display: grid; grid-template-columns: 26px minmax(0, 1fr); grid-template-rows: auto auto 1fr; column-gap: 7px; overflow: hidden; }
.node .ico { grid-row: 1 / 3; width: 26px; height: 26px; border-radius: 3px; display: grid; place-items: center; color: var(--paper); }
.ico.k-research { background: var(--k-research); } .ico.k-agent { background: var(--k-agent); } .ico.k-docs { background: var(--k-docs); } .ico.k-tests { background: var(--k-tests); }
.ico.k-code { background: var(--k-code); } .ico.k-verify { background: var(--k-verify); } .ico.k-branch { background: var(--k-branch); } .ico.k-outside { background: var(--k-outside); }
.node .ico svg { width: 17px; height: 17px; }
.node .head { display: flex; gap: 6px; align-items: baseline; min-width: 0; }
.node .no { font-family: var(--mono); font-size: 10px; font-weight: 600; background: var(--ink); color: var(--paper); padding: 0 4px; border-radius: 2px; }
.node .nm { font-family: var(--mono); font-size: 10px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.node .lb { font-weight: 700; font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; }
.node .chips { grid-column: 1 / -1; display: flex; gap: 3px; overflow: hidden; align-self: end; }
.node.diamond .body { grid-template-columns: 1fr; text-align: center; justify-items: center; }
.node.diamond .ico { grid-row: auto; margin: 0 auto 2px; width: 22px; height: 22px; }
.node.diamond .head, .node.diamond .chips { justify-content: center; }
.node.term .body { inset: 6px 14px; grid-template-columns: 1fr; text-align: center; place-content: center; }
.node.term > svg.shape .sh { fill: var(--ink); }
.node.term .lb { color: var(--paper); } .node.term .nm { color: var(--paper); opacity: .7; }
.chip { font-family: var(--mono); font-size: 9.5px; padding: 0 5px; border: 1px solid var(--rule); border-radius: 99px; color: var(--muted); line-height: 15px; white-space: nowrap; }
.chip.ok { border-color: var(--par); color: var(--par); } .chip.warn { border-color: var(--return); color: var(--return); } .chip.rt { border-color: var(--route); color: var(--route); }
.chip.sdk { border-color: var(--ink); background: var(--ink); color: var(--paper); }
.port { position: absolute; width: 30px; height: 22px; cursor: grab; z-index: 4; touch-action: none; opacity: 0; }
.node .port { right: -32px; top: calc(50% - 11px); }
.port svg { width: 30px; height: 22px; display: block; }
.port .pb { fill: var(--ink); } .port .pp { fill: var(--muted); stroke: var(--ink); stroke-width: .8; }
.port:hover .pb { fill: var(--route); }
.node:hover .port, .node.sel .port, .node.free .port, .frame:hover .port, .frame.free .port, .frame.sel .port { opacity: 1; }
.frame { position: absolute; border: 2px solid var(--par); border-radius: 24px; background: color-mix(in srgb, var(--par) 7%, transparent); }
.frame.sel { box-shadow: 0 0 0 3px var(--sel); }
.frame .ftab { position: absolute; top: -12px; left: 18px; background: var(--par); color: var(--on-accent); font-family: var(--mono); font-size: 11px; padding: 1px 10px; border-radius: 99px; cursor: move; touch-action: none; user-select: none; white-space: nowrap; }
.frame .resize { position: absolute; right: 4px; bottom: 4px; width: 14px; height: 14px; border-right: 3px solid var(--par); border-bottom: 3px solid var(--par); cursor: nwse-resize; touch-action: none; }
.frame .port { right: -32px; top: calc(50% - 11px); }
.frame .port .pb { fill: var(--par); }
.toast { position: absolute; left: 10px; bottom: 10px; background: var(--vscode-notifications-background); color: var(--vscode-notifications-foreground); border: 1px solid var(--rule); font-size: 12px; padding: 5px 9px; border-radius: 3px; max-width: calc(100% - 20px); }
.legend { position: absolute; right: 10px; bottom: 10px; display: grid; gap: 2px; background: var(--panel); border: 1px solid var(--rule); border-radius: 3px; padding: 5px 8px; font-size: 11px; color: var(--muted); }
.legend i { display: inline-block; width: 20px; border-top: 5px solid; vertical-align: middle; margin-right: 5px; border-radius: 3px; }
.legend .ln { border-color: var(--next); } .legend .lr { border-color: var(--route); } .legend .lx { border-color: var(--return); border-top-style: dashed; border-top-width: 3px; } .legend .lp { border-color: var(--par); }
.side { display: grid; grid-template-rows: auto minmax(0, 1fr); border: 1px solid var(--rule); border-radius: 3px; min-height: 0; min-width: 0; background: var(--panel); }
.tabs { display: flex; border-bottom: 1px solid var(--rule); }
.tabs button { flex: 1; border: 0; background: transparent; padding: 7px 6px; cursor: pointer; font-weight: 700; color: var(--muted); border-bottom: 2px solid transparent; }
.tabs button[aria-selected="true"] { color: var(--ink); border-bottom-color: var(--vscode-focusBorder); }
.badge { font-family: var(--mono); font-size: 10px; background: var(--return); color: var(--on-accent); border-radius: 99px; padding: 0 5px; margin-left: 4px; }
.badge.ok { background: var(--par); }
.pane { overflow: auto; padding: 10px; display: flex; flex-direction: column; gap: 10px; }
.pane > * { flex: none; }
.bhead { display: flex; gap: 10px; align-items: center; }
.bhead svg.mini { width: 54px; height: 34px; flex: none; overflow: visible; }
.bhead svg.mini .sh { fill: var(--paper); stroke: var(--ink); stroke-width: 1.6; }
.bhead svg.mini .sh.hollow { fill: none; } .bhead svg.mini .sh.ink { fill: var(--ink); }
.bhead .t { display: grid; gap: 2px; flex: 1; min-width: 0; }
.bhead input { border: 0; border-bottom: 1px solid var(--rule); background: transparent; padding: 2px 0; width: 100%; }
.bhead .t input:first-child { font-size: 16px; font-weight: 700; }
.bhead select { border: 1px solid var(--vscode-dropdown-border, var(--rule)); border-radius: 2px; background: var(--vscode-dropdown-background); color: var(--vscode-dropdown-foreground); padding: 2px 4px; }
.mono { font-family: var(--mono); }
.composer { border: 1px solid var(--vscode-input-border, var(--rule)); border-radius: 8px; background: var(--vscode-input-background); overflow: hidden; }
.composer:focus-within { border-color: var(--vscode-focusBorder); }
.composer .lane { padding: 6px 9px; border-bottom: 1px solid var(--rule); display: flex; flex-wrap: wrap; gap: 5px; align-items: center; }
.composer .lane .k { font-size: 11px; color: var(--muted); }
.ref { font-family: var(--mono); font-size: 11px; border: 1px solid var(--rule); border-radius: 3px; padding: 0 6px; display: inline-flex; gap: 4px; align-items: center; }
.ref.auto { border-style: dashed; color: var(--muted); }
.ref button { border: 0; background: none; padding: 0; cursor: pointer; color: var(--muted); }
.ref-add { font-family: var(--mono); font-size: 11px; border: 0; background: transparent; min-width: 140px; flex: 1; padding: 2px; }
.composer textarea { display: block; width: 100%; border: 0; resize: vertical; min-height: 130px; padding: 9px 11px; line-height: 1.6; background: transparent; color: var(--vscode-input-foreground); }
.composer textarea:focus { outline: none; }
.composer .bar { display: flex; flex-wrap: wrap; gap: 6px; padding: 6px 9px; border-top: 1px solid var(--rule); align-items: center; }
.pill { display: inline-flex; align-items: center; gap: 4px; border: 1px solid var(--rule); border-radius: 99px; padding: 0 4px 0 9px; font-size: 12px; }
.pill select, .pill input { border: 0; background: transparent; font-size: 12px; padding: 2px; }
.pill select option { background: var(--vscode-dropdown-background); color: var(--vscode-dropdown-foreground); }
.pill input[type="number"] { width: 46px; font-family: var(--mono); }
.pill.toggle { padding: 1px 10px; cursor: pointer; }
.pill.on { border-color: var(--vscode-focusBorder); background: var(--sel); }
.box { border: 1px solid var(--rule); border-radius: 8px; padding: 8px 10px; display: grid; gap: 8px; }
.box h3 { margin: 0; font-size: 12px; color: var(--muted); font-weight: 700; }
details.box > summary { cursor: pointer; font-size: 12px; color: var(--muted); font-weight: 700; }
.rgrid { display: flex; flex-wrap: wrap; gap: 6px 10px; align-items: center; }
.field { display: grid; gap: 3px; font-size: 11px; color: var(--muted); }
.field input, .field select, .field textarea { border: 1px solid var(--vscode-input-border, var(--rule)); border-radius: 2px; background: var(--vscode-input-background); color: var(--vscode-input-foreground); padding: 3px 6px; font-size: 12.5px; width: 100%; }
.field textarea { font-family: var(--mono); font-size: 11.5px; }
.choices { display: flex; flex-wrap: wrap; gap: 5px; }
.choice { display: inline-flex; align-items: center; gap: 4px; border: 1px solid var(--route); border-radius: 3px; padding: 0 2px 0 6px; font-family: var(--mono); font-size: 11px; }
.choice input { border: 0; width: 80px; font-family: var(--mono); font-size: 11px; background: transparent; }
.choice span { color: var(--muted); }
.choice button, .card button.x { border: 0; background: none; cursor: pointer; color: var(--muted); }
.card { border: 1px solid var(--rule); border-radius: 5px; padding: 6px 8px; display: grid; gap: 6px; }
.card .row { display: grid; grid-template-columns: 1fr 1fr auto; gap: 6px; align-items: end; }
.row2 { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.note { margin: 0; font-size: 12px; color: var(--muted); }
details.preview { border: 1px dashed var(--rule); border-radius: 8px; }
details.preview summary { cursor: pointer; padding: 7px 10px; font-weight: 700; }
details.preview pre { margin: 0; padding: 0 10px 10px; white-space: pre-wrap; font-family: var(--mono); font-size: 11px; }
.result { list-style: none; margin: 0; padding: 0; display: grid; gap: 5px; }
.result li { padding: 5px 8px; border-left: 3px solid var(--return); background: var(--vscode-inputValidation-errorBackground); }
.result li.ok { border-left-color: var(--par); background: transparent; font-weight: 700; }
.file h3 { margin: 0 0 4px; font-family: var(--mono); font-size: 11.5px; display: flex; justify-content: space-between; gap: 8px; }
.file pre { margin: 0; padding: 7px 9px; background: var(--vscode-textCodeBlock-background); border-radius: 3px; font-family: var(--mono); font-size: 11px; overflow: auto; max-height: 340px; white-space: pre; }
/* 狭い幅：右の欄を面の下に回し、高さを面と半分ずつに分ける（どちらも中でスクロールする）。凡例は図に重なるので隠す */
@media (max-width: 1000px) {
  .work { grid-template-columns: 92px minmax(0, 1fr); grid-template-rows: minmax(0, 1fr) minmax(0, 1fr); }
  .shelf { grid-row: 1; } .stage-area { grid-row: 1; min-height: 0; }
  .side { grid-column: 1 / -1; grid-row: 2; }
  .legend { display: none; }
}
`;

export function renderPipeEditorHtml(o: PipeEditorHtmlOptions): string {
  const n = escapeHtml(o.nonce);
  const src = escapeHtml(o.cspSource);
  return `<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'nonce-${n}'; script-src 'nonce-${n}' ${src};">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>パイプ作図台</title>
<style nonce="${n}">${STYLE}</style>
</head>
<body>
<header class="top">
  <h1><span class="mark" aria-hidden="true"></span>パイプ作図台</h1>
  <span class="path" id="pipe-path"></span>
  <span class="spacer"></span>
  <button type="button" class="btn" id="zoom-out" aria-label="縮小">−</button>
  <span class="zoom" id="zoom">100%</span>
  <button type="button" class="btn" id="zoom-in" aria-label="拡大">＋</button>
  <button type="button" class="btn" id="fit">全体を見る</button>
  <button type="button" class="btn" id="arrange">自動で並べる</button>
  <button type="button" class="btn primary" id="save">保存</button>
</header>
<main class="work">
  <nav class="shelf" id="shelf" aria-label="ブロックの棚"><h2>ブロック</h2></nav>
  <section class="stage-area" id="area" aria-label="路線図">
    <div class="world" id="world"></div>
    <div class="legend" aria-hidden="true"><span><b>ケーブルの色</b></span><span><i class="ln"></i>次の段</span><span><i class="lr"></i>分岐</span><span><i class="lx"></i>差し戻し</span><span><i class="lp"></i>並列の枠</span></div>
    <div class="toast" id="toast">読み込んでいます…</div>
  </section>
  <aside class="side">
    <div class="tabs" role="tablist">
      <button type="button" role="tab" data-tab="block" aria-selected="true">ブロック</button>
      <button type="button" role="tab" data-tab="check" aria-selected="false">検査<span class="badge" id="badge">0</span></button>
      <button type="button" role="tab" data-tab="files" aria-selected="false">書き出し</button>
    </div>
    <div class="pane" id="pane"></div>
  </aside>
</main>
<script nonce="${n}" src="${escapeHtml(o.scriptUri)}"></script>
</body>
</html>`;
}
