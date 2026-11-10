// 作業台の「流す」の節の中身（D0078。起こすコマンドの形・理由・文字数）。外から来た文字（引数・理由）は escapeHtml を通す。style 属性は書かない。
import { escapeHtml } from './escape.ts';

export interface RunView {
  /** 起こすコマンドの形。決まらないときは null */
  command: { command: string; args: string[]; placeholder: boolean } | null;
  /** command が null のときに、同じ箱に出す文（実行ファイルが見つからない理由、または「保存すると…」） */
  commandNote: string | null;
  /** 流せない理由。null なら <p> ごと出さない。commandNote と同じ文を両方に渡さない（呼ぶ側の決まり） */
  reason: string | null;
  /** 依頼メモの文字数と上限。none のときは null */
  count: { length: number; limit: number } | null;
}

function commandHtml(v: RunView): string {
  if (v.command !== null) {
    const args = v.command.args.map((a) => `<li><code>${escapeHtml(a)}</code></li>`).join('');
    return `<div class="run-cmd"><div class="run-exe"><code>${escapeHtml(v.command.command)}</code></div><ul class="run-args">${args}</ul></div>`;
  }
  if (v.commandNote !== null) return `<div class="run-cmd"><p class="run-note">${escapeHtml(v.commandNote)}</p></div>`;
  return '';
}

function countHtml(count: RunView['count']): string {
  if (count === null) return '';
  const over = count.length > count.limit;
  const text = `${count.length} / ${count.limit}${over ? '（超えています）' : ''}`;
  return `<p class="${over ? 'run-count over' : 'run-count'}">${text}</p>`;
}

/** 「流す」の節の #run-info に入れる HTML */
export function runInfoHtml(v: RunView): string {
  const reason = v.reason === null ? '' : `<p class="run-reason" role="status">${escapeHtml(v.reason)}</p>`;
  return commandHtml(v) + countHtml(v.count) + reason;
}
