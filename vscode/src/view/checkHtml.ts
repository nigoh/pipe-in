// 段の判定の札と、右のパネルの判定の箱（HTML の文字列、純粋）。外から来た文字は escapeHtml を通す。
// 自分をやり直す判定は図にケーブルを描かないので、札で行き先を示す（D0005）。
import { failKind, failTargets } from '../domain/pipeCheck.ts';
import type { PipeModel, StageModel } from '../domain/pipeModel.ts';
import { escapeHtml as esc } from './escape.ts';

const SELF = 'この段をやり直す';

/** カードの判定の札。判定がオフなら null */
export function checkChip(m: PipeModel, s: StageModel): { text: string; title: string } | null {
  if (!s.check.on) return null;
  const times = `（最大 ${s.check.maxRetries} 回）`;
  if (failKind(m, s) === 'self') return { text: '判定 ↻', title: `不合格なら、${SELF}${times}` };
  const to = m.stages.find((x) => x.id === s.onFail)!;
  return { text: '判定 ↩', title: `不合格なら「${to.label}」へ戻す${times}` };
}

export function checkChipHtml(m: PipeModel, s: StageModel): string {
  const c = checkChip(m, s);
  return c ? `<span class="chip ok" title="${esc(c.title)}">${esc(c.text)}</span>` : '';
}

/** 右のパネルの判定の箱。いちばん上にスイッチ。オンのときだけ、判定のしかた・不合格のとき・戻す上限を出す */
export function checkBoxHtml(m: PipeModel, s: StageModel): string {
  const on = s.check.on;
  const sw = `<label class="pill toggle${on ? ' on' : ''}"><input type="checkbox" id="b-check"${on ? ' checked' : ''}>判定する</label>`;
  if (!on) return `<div class="box check-box"><h3>判定</h3>${sw}<p class="note">オンにすると、段の結果を確かめ、通らなければやり直します。</p></div>`;
  const cur = failKind(m, s) === 'back' ? s.onFail! : '';
  const opts = [['', SELF], ...failTargets(m, s).map((x) => [x.id, x.label])]
    .map(([v, t]) => `<option value="${esc(v!)}"${v === cur ? ' selected' : ''}>${esc(t!)}</option>`).join('');
  return `<div class="box check-box"><h3>判定</h3>${sw}
      <div class="rgrid"><span class="note">判定のしかた</span>
        <label class="pill toggle${s.check.verdict ? ' on' : ''}"><input type="checkbox" id="b-verdict"${s.check.verdict ? ' checked' : ''}>Claude が判定する（verdict）</label>
      </div>
      <label class="field">確認用のコマンド（終了コード 0 で合格・任意）<input id="b-command" class="mono" value="${esc(s.check.command)}" placeholder="python -m pytest -q"></label>
      <div class="row2">
        <label class="field">不合格のとき<select id="b-onfail">${opts}</select></label>
        <label class="field">戻す上限<input type="number" id="b-retries" min="0" max="9" value="${s.check.maxRetries}"></label>
      </div></div>`;
}
