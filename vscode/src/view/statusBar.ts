// 図の状態 → ステータスバーのボタンの文字と説明（純粋）。文字の $(…) は VSCode の組み込みアイコン。
// 選んでいる実行のほかに数える行（確認待ち・動いている・待ち）があるときは、件数の形（動き N・確認待ち M）で出す。無いときは選んでいる実行の段と状態。
import { NO_RECORDS_MESSAGE, WAITING_MESSAGE } from '../domain/pipelineView.ts';
import type { PipelineView } from '../domain/pipelineView.ts';
import { countedRows, finalWord, frontWaitingKey, hasOtherCounted, statusCounts, stateWord } from '../domain/runList.ts';
import type { RunListView, StatusCounts } from '../domain/runList.ts';
import { normalizeName } from '../domain/sessionName.ts';
import { formatPercent } from './usageHtml.ts';

export interface StatusBarLabel {
  text: string;
  tooltip: string;
}

/** 件数の形に要る一覧の部分。extension.ts は render() が作る一覧をそのまま渡す。 */
export type StatusList = Pick<RunListView, 'rows' | 'selected' | 'omittedWorktrees'>;

/** ボタンに出す名前 */
const NAME = 'pipe-in';

/** 説明に並べる数えた実行の上限 */
export const STATUS_LINES_LIMIT = 10;

/** 状態 → アイコン（今の出し方と件数の形が同じ綴りを読む） */
const ICONS: Readonly<Record<NonNullable<StatusCounts['top']>, string>> = {
  waiting: 'comment-discussion',
  running: 'sync~spin',
  idle: 'clock',
};

/** 本体の終了の名前（state.json の final）→ アイコン。言葉は一覧の行と同じ表（domain/runList.ts の finalWord）から読む。 */
const FINAL_ICONS: Readonly<Record<string, string>> = {
  PASSED: 'pass',
  TEST_FAILED: 'error',
  STOPPED_BY_HUMAN: 'debug-stop',
  STAGE_ERROR: 'error',
  BLOCKED: 'warning',
};

const CLICK = 'クリックでパネルを開く';
const CLICK_WAITING_FIRST = '（確認待ちの実行を先に出す）';
const DASH = '—';

/**
 * 説明の中で空白に替える文字の範囲（コードポイントの始まりと終わり）：
 * 改行を含む制御文字（U+0000〜U+001F・U+007F〜U+009F）、行区切り・段落区切り（U+2028・U+2029）、向きを変える制御文字（U+200E・U+200F・U+202A〜U+202E・U+2066〜U+2069）。
 * 範囲のすぐ外の文字（U+00A0・U+200D など）は替えない。
 */
const REPLACED_RANGES: readonly (readonly [number, number])[] = [
  [0x0000, 0x001f],
  [0x007f, 0x009f],
  [0x2028, 0x2029],
  [0x200e, 0x200f],
  [0x202a, 0x202e],
  [0x2066, 0x2069],
];

function isReplaced(ch: string): boolean {
  const code = ch.codePointAt(0) ?? 0;
  return REPLACED_RANGES.some(([from, to]) => code >= from && code <= to);
}

/** 外から来た文字を、説明に入れる 1 行のプレーンな文字にする。制御文字などを空白に替え、前後と連続する空白を整え、長ければ省く。空なら「—」。 */
export function plainLine(text: string): string {
  return normalizeName(Array.from(text, (ch) => (isReplaced(ch) ? ' ' : ch)).join('')) ?? DASH;
}

/** 利用枠の今の使用率（「5時間枠 2%」）の配列。枠の名前は渡した関数で整える。使用量のない記録では空。 */
function rateWindows(view: PipelineView, tidy: (label: string) => string): string[] {
  return (view.usage?.summary.rateLimits ?? []).map((w) => `${tidy(w.label)} ${formatPercent(w.last)}`);
}

/** 利用枠の今の使用率（「・5時間枠 2%・7日枠 15%」）。使用量のない記録では空。 */
function rateNow(view: PipelineView): string {
  return rateWindows(view, (label) => label)
    .map((w) => `・${w}`)
    .join('');
}

/** 選んでいる実行の段と状態（今の出し方）。 */
function viewLabel(view: PipelineView): StatusBarLabel {
  const cost = `合計 $${view.totalCostUsd.toFixed(3)}${rateNow(view)}`;
  if (view.noRecords) {
    return { text: `$(circuit-board) ${NAME}`, tooltip: `${NAME}：${NO_RECORDS_MESSAGE}（${view.noRecords.workDir}）\n${CLICK}` };
  }
  if (view.final !== null) {
    const icon = Object.hasOwn(FINAL_ICONS, view.final) ? FINAL_ICONS[view.final] : 'info';
    const word = finalWord(view.final);
    return { text: `$(${icon}) ${NAME}: ${word}`, tooltip: `${NAME}：${word}・${cost}\n${CLICK}` };
  }
  if (view.runningStage !== null && view.terminal.source !== null) {
    const src = view.terminal.source;
    const now = `${view.stageLabels[src.stage] ?? src.stage}${src.attempt === null ? '' : `（${src.attempt} 回目）`}`;
    return { text: `$(${ICONS.running}) ${NAME}: ${now}`, tooltip: `${NAME}：${now}が動いている・${cost}\n${CLICK}` };
  }
  if (view.pendingReview !== null) {
    const { label, doc } = view.pendingReview;
    return {
      text: `$(${ICONS.waiting}) ${NAME}: ${label}の確認待ち`,
      tooltip: `${NAME}：${label}の確認を待っている（${doc}）・${cost}\n${CLICK}`,
    };
  }
  if (view.waiting) {
    return { text: `$(${ICONS.idle}) ${NAME}: 待ち`, tooltip: `${NAME}：${WAITING_MESSAGE}・${cost}\n${CLICK}` };
  }
  return { text: `$(circuit-board) ${NAME}`, tooltip: `${NAME}・${cost}\n${CLICK}` };
}

/** 件数の形：「動き N・確認待ち M」（0 の項目は省く）。説明は実行ごとの名前と状態・選んでいる実行・利用枠・ボタンの案内。 */
function countsLabel(view: PipelineView, list: StatusList): StatusBarLabel {
  const counts = statusCounts(list.rows);
  // 数える行が無い一覧は件数の形にしない。statusBarLabel が hasOtherCounted で先に外すので、ここへは来ない
  // （型を絞るための確かめ。もし来ても、今までの出し方に戻す安全側）
  if (counts.top === null) return viewLabel(view);
  const summary = [counts.active > 0 ? `動き ${counts.active}` : null, counts.waiting > 0 ? `確認待ち ${counts.waiting}` : null]
    .filter((part) => part !== null)
    .join('・');

  const counted = countedRows(list.rows);
  const lines = [`${NAME}：${summary}`];
  for (const row of counted.slice(0, STATUS_LINES_LIMIT)) {
    const branch = row.branch === null ? '' : `・${plainLine(row.branch)}`;
    lines.push(`${stateWord(row)}：${plainLine(row.session)}（${plainLine(row.stage)}${branch}）`);
  }
  if (counted.length > STATUS_LINES_LIMIT) lines.push(`ほか ${counted.length - STATUS_LINES_LIMIT} 件（パネルの一覧で見られます）`);
  if (list.omittedWorktrees > 0) lines.push(`別の worktree を ${list.omittedWorktrees} 個、省いています（件数に入っていません）`);

  const self = list.rows.find((r) => r.key === list.selected);
  lines.push(self === undefined ? '選んでいる実行：記録なし' : `選んでいる実行：${plainLine(self.session)}（${plainLine(stateWord(self))}）`);

  const windows = rateWindows(view, plainLine);
  if (windows.length > 0) lines.push(`利用枠：${windows.join('・')}`);
  lines.push(frontWaitingKey(list.rows, list.selected) === null ? CLICK : `${CLICK}${CLICK_WAITING_FIRST}`);

  return { text: `$(${ICONS[counts.top]}) ${NAME}: ${summary}`, tooltip: lines.join('\n') };
}

/**
 * ボタンの文字と説明。list を渡し、選んでいる実行のほかに数える行があるときは件数の形にする。
 * list を省いたとき・ほかに数える行が無いときは、選んでいる実行の段と状態（今までの出し方）。
 */
export function statusBarLabel(view: PipelineView, list?: StatusList): StatusBarLabel {
  if (list !== undefined && hasOtherCounted(list.rows, list.selected)) return countsLabel(view, list);
  return viewLabel(view);
}
