// 外で書き換わったときの帯の HTML（D0065、純粋）。外から来た文字（差分の target・text、reason）は escapeHtml を通す。
import { DIFF_KIND_LABEL } from '../domain/pipeDiff.ts';
import type { DiffItem } from '../domain/pipeDiff.ts';
import { escapeHtml as esc } from './escape.ts';

export type BannerState = { type: 'externalConflict'; diff: DiffItem[] } | { type: 'externalUnreadable'; reason: string };

const diffRow = (d: DiffItem): string =>
  `<li><span class="ext-kind">${esc(DIFF_KIND_LABEL[d.kind] ?? d.kind)}</span> <b>${esc(d.target)}</b> ${esc(d.text)}</li>`;

/** 帯の中身。conflict は 2 つのボタン（data-ext="load" / "keep"）、unreadable は理由だけでボタンなし */
export function renderExternalBanner(s: BannerState): string {
  if (s.type === 'externalUnreadable') {
    return `<div class="ext-title">外で書き換わっていますが、読めませんでした</div><div class="ext-reason">${esc(s.reason)}</div>`;
  }
  return [
    '<div class="ext-title">外で書き換わっています</div>',
    '<div class="ext-note">保存していない変更があるので、作業台はそのままにしています。どちらを残すか選んでください。</div>',
    `<ul class="ext-diff">${s.diff.map(diffRow).join('')}</ul>`,
    '<div class="ext-actions"><button type="button" data-ext="load">外の変更を読み込む</button><button type="button" data-ext="keep">自分の変更を残す</button></div>',
  ].join('');
}
