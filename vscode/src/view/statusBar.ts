// 図の状態 → ステータスバーのボタンの文字と説明（純粋）。文字の $(…) は VSCode の組み込みアイコン。
import { NO_RECORDS_MESSAGE, WAITING_MESSAGE } from '../domain/pipelineView.ts';
import type { PipelineView } from '../domain/pipelineView.ts';
import { formatPercent } from './usageHtml.ts';

export interface StatusBarLabel {
  text: string;
  tooltip: string;
}

/** devpipe の終了の名前（state.json の final）→ アイコンと短い言葉。 */
const FINALS: Readonly<Record<string, [string, string]>> = {
  PASSED: ['pass', '合格'],
  TEST_FAILED: ['error', '不合格'],
  STOPPED_BY_HUMAN: ['debug-stop', '中止'],
  STAGE_ERROR: ['error', '段が失敗'],
  BLOCKED: ['warning', '実行できず'],
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
    return { text: '$(circuit-board) devpipe', tooltip: `devpipe：${NO_RECORDS_MESSAGE}（${view.noRecords.workDir}）\n${CLICK}` };
  }
  if (view.final !== null) {
    const [icon, word] = FINALS[view.final] ?? ['info', view.final];
    return { text: `$(${icon}) devpipe: ${word}`, tooltip: `devpipe：${word}・${cost}\n${CLICK}` };
  }
  if (view.runningStage !== null && view.terminal.source !== null) {
    const src = view.terminal.source;
    const now = `${view.stageLabels[src.stage] ?? src.stage}${src.attempt === null ? '' : `（${src.attempt} 回目）`}`;
    return { text: `$(sync~spin) devpipe: ${now}`, tooltip: `devpipe：${now}が動いている・${cost}\n${CLICK}` };
  }
  if (view.pendingReview !== null) {
    const { label, doc } = view.pendingReview;
    return {
      text: `$(comment-discussion) devpipe: ${label}の確認待ち`,
      tooltip: `devpipe：${label}の確認を待っている（${doc}）・${cost}\n${CLICK}`,
    };
  }
  if (view.waiting) {
    return { text: '$(clock) devpipe: 待ち', tooltip: `devpipe：${WAITING_MESSAGE}・${cost}\n${CLICK}` };
  }
  return { text: '$(circuit-board) devpipe', tooltip: `devpipe・${cost}\n${CLICK}` };
}
