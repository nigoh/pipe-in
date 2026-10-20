// 図の状態 → ステータスバーのボタンの文字と説明（純粋）。文字の $(…) は VSCode の組み込みアイコン。
import { NO_RECORDS_MESSAGE, WAITING_MESSAGE } from '../domain/pipelineView.ts';
import type { PipelineView } from '../domain/pipelineView.ts';
import { finalWord } from '../domain/runList.ts';
import { formatPercent } from './usageHtml.ts';

export interface StatusBarLabel {
  text: string;
  tooltip: string;
}

/** ボタンに出す名前 */
const NAME = 'pipe-in';

/** 本体の終了の名前（state.json の final）→ アイコン。言葉は一覧の行と同じ表（domain/runList.ts の finalWord）から読む。 */
const FINAL_ICONS: Readonly<Record<string, string>> = {
  PASSED: 'pass',
  TEST_FAILED: 'error',
  STOPPED_BY_HUMAN: 'debug-stop',
  STAGE_ERROR: 'error',
  BLOCKED: 'warning',
};

const CLICK = 'クリックでパネルを開く';

/** 利用枠の今の使用率（「・5時間枠 2%・7日枠 15%」）。使用量のない記録では空。 */
function rateNow(view: PipelineView): string {
  const windows = view.usage?.summary.rateLimits ?? [];
  return windows.map((w) => `・${w.label} ${formatPercent(w.last)}`).join('');
}

export function statusBarLabel(view: PipelineView): StatusBarLabel {
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
    return { text: `$(sync~spin) ${NAME}: ${now}`, tooltip: `${NAME}：${now}が動いている・${cost}\n${CLICK}` };
  }
  if (view.pendingReview !== null) {
    const { label, doc } = view.pendingReview;
    return {
      text: `$(comment-discussion) ${NAME}: ${label}の確認待ち`,
      tooltip: `${NAME}：${label}の確認を待っている（${doc}）・${cost}\n${CLICK}`,
    };
  }
  if (view.waiting) {
    return { text: `$(clock) ${NAME}: 待ち`, tooltip: `${NAME}：${WAITING_MESSAGE}・${cost}\n${CLICK}` };
  }
  return { text: `$(circuit-board) ${NAME}`, tooltip: `${NAME}・${cost}\n${CLICK}` };
}
