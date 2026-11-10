// 確認待ちの帯（黄の知らせ）の、返事の部分（D0079）。純粋（ファイル・時計・vscode に触れない）。
// 端末の pipe-in が確認の段で待っているとき（図の状態に reply があるとき）、帯に「承認」「修正を依頼」「中止」のボタンを出す。
// 帯の中は 4 つの枠（choose・revise・confirm・sent）。どれを見せるかはパネルのスクリプトが持つ状態で決め、HTML は最初の状態（送ったあとなら sent）を書く。
// 外から来た文字（段の表示名・文書名・識別子）は escapeHtml を通す。style 属性・インラインの動作・外部の読み込みは書かない。確認はダイアログでなく、帯の中の確かめの枠で取る。
import type { PipelineView } from '../domain/pipelineView.ts';
import { escapeHtml } from './escape.ts';

/** 確認待ちの帯の、確かめる文書を開くボタンの文字（D0064）。押すと既存の openArtifact になる */
export const OPEN_DOC_LABEL = '確かめる文書を開く';

/** 返事の部分の CSS（SHELL_STYLE が取り込む）。色は var(--vscode-*)。幅の @media は足さず、折り返しで 800px の幅でも重ならない。 */
export const REPLY_STYLE = `
.notice[data-reply-id] { gap: 8px; }
.reply { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; min-width: 0; }
.reply-input { display: block; flex: 1 1 100%; width: 100%; min-width: 0; box-sizing: border-box; resize: vertical; padding: 6px 8px; border: 1px solid var(--vscode-input-border, var(--vscode-panel-border)); border-radius: 4px; background: var(--vscode-input-background); color: var(--vscode-input-foreground); font: inherit; }
.reply-input:focus-visible { outline: 2px solid var(--vscode-focusBorder); outline-offset: -1px; }
.reply-primary { min-height: 28px; padding: 4px 14px; border: 1px solid var(--vscode-button-background); border-radius: 6px; background: var(--vscode-button-background); color: var(--vscode-button-foreground); font: inherit; font-size: 12px; font-weight: 600; cursor: pointer; }
.reply-primary:hover:not(:disabled) { background: var(--vscode-button-hoverBackground); }
.reply-primary:disabled { opacity: 0.5; cursor: default; }
.reply-primary:focus-visible { outline: 2px solid var(--vscode-focusBorder); outline-offset: 1px; }
.reply-sent { font-weight: 600; }
`;

/** 確かめる文書は、成果物の一覧にあって読めるものだけ開く（openArtifact は一覧にある名前しか通さない） */
export function renderOpenDocButton(view: PipelineView, file: string): string {
  return view.artifacts.some((a) => a.name === file && a.ready)
    ? `<button type="button" class="secondary" data-artifact="${escapeHtml(file)}">${OPEN_DOC_LABEL}</button>`
    : '';
}

const SENT_TEXT = '送りました（pipe-in が読むのを待っています）';
const STALLED_TEXT = '端末の pipe-in が止まっていないか確かめてください';

/** 帯の枠 1 つ。hidden は最初に隠す枠 */
function pane(name: string, hidden: boolean, body: string): string {
  return `<div class="reply" data-reply-pane="${name}"${hidden ? ' hidden' : ''}>${body}</div>`;
}

/**
 * 返事を受け付けている確認待ちの帯。view.reply が無いときは空の文字。
 * 帯は識別子・送ったか・30 秒たったかを属性に持つ（パネルのスクリプトが描き直しをまたいで読む）。
 */
export function renderReplyNotice(view: PipelineView): string {
  const reply = view.reply ?? null;
  if (reply === null) return '';
  const title = reply.doc === '' ? `${reply.label}の確認を待っている` : `${reply.label}の確認を待っている：${reply.doc}`;
  const sent = reply.sent;
  const stalled = sent && reply.stalled;
  return (
    `<div class="notice" role="status" data-reply-id="${escapeHtml(reply.id)}" data-reply-sent="${sent ? 1 : 0}" data-reply-stalled="${stalled ? 1 : 0}">` +
    `<strong>${escapeHtml(title)}</strong>` +
    '<span class="notice-sub">読んで、承認・修正の依頼・中止のどれかを返してください（返事は端末の pipe-in が読みます）</span>' +
    renderOpenDocButton(view, reply.doc) +
    pane(
      'choose',
      sent,
      '<button type="button" class="reply-primary" data-reply="approve">承認</button>' +
        '<button type="button" class="secondary" data-reply="revise-open">修正を依頼</button>' +
        '<button type="button" class="secondary" data-reply="quit-open">中止</button>',
    ) +
    pane(
      'revise',
      true,
      '<textarea class="reply-input" data-keep="reply-feedback" rows="3" aria-label="直してほしい点"></textarea>' +
        '<span class="notice-sub">1,000 文字まで</span>' +
        '<button type="button" class="reply-primary" data-reply="revise-send" disabled>送る</button>' +
        '<button type="button" class="secondary" data-reply="back">戻る</button>',
    ) +
    pane(
      'confirm',
      true,
      '<span>本当に中止しますか</span>' +
        '<button type="button" class="secondary" data-reply="quit-send">中止する</button>' +
        '<button type="button" class="secondary" data-reply="back">戻る</button>',
    ) +
    pane('sent', !sent, `<span class="reply-sent">${SENT_TEXT}</span>${stalled ? `<span class="notice-sub">${STALLED_TEXT}</span>` : ''}`) +
    '</div>'
  );
}

/** 返事を書けなかった理由の文（拡張が警告に出す）。理由は決まった語だけで、入力の文字は入れない。 */
export function replyRefusalText(reason: string): string {
  switch (reason) {
    case 'no_offer':
      return 'いまは返事を受け付けていません';
    case 'changed':
      return '確認が進んだか別の確認になったので、送りませんでした';
    case 'exists':
      return 'すでに返事を送っています';
    case 'bad_input':
      return '送れませんでした（動作か直してほしい点の形が合いません）';
    case 'bad_run':
    case 'outside':
      return '送れませんでした（返事を置く場所を確かめられませんでした）';
    case 'bad_text':
      return '送れませんでした（返事が大きすぎます）';
    case 'failed':
      return '送れませんでした（返事のファイルを書けませんでした）';
    default:
      return '送れませんでした';
  }
}
