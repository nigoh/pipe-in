// 時系列（ガントチャート）のモデル：段の実行ごとの行・エージェントの帯・人の確認を待った帯・横軸を組み立てる。
// 純粋な関数：記録の写しと「今」（引数）だけから決まる。ファイル・時計・vscode に触れない。
import type { RunRecord, StageRun } from './runRecord.ts';
import type { Stage } from './stage.ts';
import { MAX_SPAN_SEC, parseInstant } from './timestamp.ts';

/** 実行の始まりからの秒。0 以上 totalSec 以下。 */
export interface GanttBar {
  startSec: number;
  endSec: number;
}

export interface GanttRow {
  seq: number;
  /** 「段の表示名」＋「 N 回目」（回が無ければ省く） */
  label: string;
  /** 受け持ち。記録に無ければ null */
  agent: string | null;
  /** エージェントが動いた帯。null ＝ 時刻の記録なし。quietSec は動いている帯だけ（段のログが最後に更新されてからの秒。印の対象のときだけ） */
  run: (GanttBar & { failed: boolean; live: boolean; quietSec?: number }) | null;
  /** 人の確認を待った帯 */
  wait: (GanttBar & { live: boolean }) | null;
}

export interface GanttModel {
  rows: GanttRow[];
  /** 行が多いとき、省いた古い方の数 */
  omittedRows: number;
  totalSec: number;
  /** 横軸の目盛り（秒）。0 を含む */
  ticks: number[];
  /** 動いている段か、いま確認待ちがある（帯が「今」まで伸びる） */
  live: boolean;
  /** 読める時刻が 1 つでもあるか */
  hasTimes: boolean;
}

/** 段のログから取った、時系列に要る項目。 */
export interface GanttLog {
  seq: number;
  stage: Stage;
  attempt: number | null;
  /** 最後の Prompt 行の at の文字 */
  startedAt: string | null;
  agent: string | null;
}

export interface GanttClock {
  nowMs: number;
  localOffsetMin: number;
}

export interface GanttInput {
  record: RunRecord;
  logs: GanttLog[];
  /** 動いている段のログ（まだ runs[] に無い）。無ければ null */
  running: GanttLog | null;
  labels: Readonly<Record<string, string>>;
  clock: GanttClock | undefined;
  /** 動いている段の、段のログが最後に更新されてからの秒（PipelineView.quietSec と同じ値）。無い・null なら帯に付けない */
  quietSec?: number | null;
}

export const MAX_ROWS = 200;
/** 今より先の時刻は、この秒数までは時計のずれとして許す。超えると読めない値にする */
const FUTURE_SLACK_MS = 60_000;
/** 目盛りの間隔の候補（秒）。これを超えるときは倍にしていく */
const TICK_STEPS: readonly number[] = [5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600];
/** 0 を除く目盛りの本数の上限（0 と合わせて 6 本以下） */
const MAX_POSITIVE_TICKS = 5;

interface Draft {
  seq: number;
  stage: Stage;
  attempt: number | null;
  agent: string | null;
  /** 始まりの時刻（UTC ミリ秒）。読めない値は null */
  startMs: number | null;
  durationSec: number;
  isError: boolean;
  live: boolean;
  run: StageRun | null;
}

function labelOf(stage: Stage, attempt: number | null, labels: Readonly<Record<string, string>>): string {
  const name = labels[stage] ?? stage;
  return attempt !== null && attempt > 0 ? `${name} ${attempt} 回目` : name;
}

function clampDuration(sec: number): number {
  return Number.isFinite(sec) ? Math.min(Math.max(sec, 0), MAX_SPAN_SEC) : 0;
}

/** その回の判定が不合格か実行できずか。 */
function verdictFailed(record: RunRecord, run: StageRun): boolean {
  if (run.stage !== 'test' || run.attempt === null) return false;
  const verdict = record.verdicts.findLast((v) => v.attempt === run.attempt);
  return verdict !== undefined && verdict.status !== 'pass';
}

/** 目盛り（秒）。間隔は候補の中から、0 を除く本数が上限以下になる最小のもの。 */
export function buildTicks(totalSec: number): number[] {
  if (!Number.isFinite(totalSec) || totalSec <= 0) return [0];
  const candidates = [...TICK_STEPS];
  while (Math.floor(totalSec / candidates[candidates.length - 1]!) > MAX_POSITIVE_TICKS) {
    candidates.push(candidates[candidates.length - 1]! * 2);
  }
  const step = candidates.find((s) => Math.floor(totalSec / s) <= MAX_POSITIVE_TICKS) ?? TICK_STEPS[0]!;
  const ticks = [0];
  for (let t = step; t <= totalSec && ticks.length <= MAX_POSITIVE_TICKS; t += step) ticks.push(t);
  return ticks;
}

export function buildGantt(input: GanttInput): GanttModel {
  const { record, logs, running, labels, clock, quietSec } = input;
  const offset = clock?.localOffsetMin ?? 0;
  const instant = (text: string | null): number | null => (text === null ? null : parseInstant(text, offset));
  const logOf = new Map<number, GanttLog>();
  for (const log of logs) if (!logOf.has(log.seq)) logOf.set(log.seq, log);

  // 実行ごとの下書き（通し番号の順）
  const drafts: Draft[] = [...record.stageRuns]
    .sort((a, b) => a.seq - b.seq)
    .map((run) => ({
      seq: run.seq,
      stage: run.stage,
      attempt: run.attempt,
      agent: run.agent ?? logOf.get(run.seq)?.agent ?? null,
      startMs: instant(logOf.get(run.seq)?.startedAt ?? null),
      durationSec: clampDuration(run.durationSec),
      isError: run.isError,
      live: false,
      run,
    }));
  if (running !== null) {
    drafts.push({
      seq: running.seq,
      stage: running.stage,
      attempt: running.attempt,
      agent: running.agent,
      startMs: instant(running.startedAt),
      durationSec: 0,
      isError: false,
      live: true,
      run: null,
    });
  }

  // 「今」。時計が無いときは、記録から読めた一番新しい時刻
  const known = [
    ...drafts.map((d) => (d.startMs === null ? null : d.startMs + d.durationSec * 1000)),
    instant(record.updatedAt),
  ].filter((v): v is number => v !== null);
  // 時計の値が壊れていても（NaN・無限大）、時計が無いときと同じに扱う
  const nowMs = clock !== undefined && Number.isFinite(clock.nowMs) ? clock.nowMs : known.length > 0 ? Math.max(...known) : 0;

  // 先の時刻（今より 60 秒を超えて先）は読めない値にする
  for (const d of drafts) {
    if (d.startMs !== null && d.startMs > nowMs + FUTURE_SLACK_MS) d.startMs = null;
  }

  // 横軸の 0：started_at、無ければ読めた最初の始まり
  const starts = drafts.map((d) => d.startMs).filter((v): v is number => v !== null);
  const originMs = instant(record.startedAt) ?? (starts.length > 0 ? Math.min(...starts) : null);
  if (originMs === null || starts.length === 0) {
    const rows = drafts.map((d) => emptyRow(d, labels));
    return finish(rows, { live: running !== null, hasTimes: false, totalSec: 0 });
  }
  const sec = (ms: number): number => Math.max((ms - originMs) / 1000, 0);

  const pending = record.pendingReview;
  const waitingNow = pending !== null && record.final === null && running === null;
  const last = drafts.length - 1;

  const rows: GanttRow[] = drafts.map((d, i) => {
    const row = emptyRow(d, labels);
    if (d.startMs === null) return row;
    const startSec = sec(d.startMs);
    const endSec = d.live ? Math.max(sec(nowMs), startSec) : startSec + d.durationSec;
    const failed = d.isError || (d.run !== null && verdictFailed(record, d.run));
    // 更新なしの秒は、動いている帯にだけ付ける（持たない帯の形は今までと同じ）
    row.run = { startSec, endSec, failed, live: d.live, ...(d.live && quietSec != null ? { quietSec } : {}) };

    if (waitingNow && i === last && !d.live) {
      // いま確認待ち：待ち始め（since。読めなければ実行の終わり）から「今」まで
      const since = instant(pending.since);
      const from = since === null ? endSec : Math.max(sec(since), endSec);
      row.wait = { startSec: from, endSec: Math.max(sec(nowMs), from), live: true };
      return row;
    }
    if (d.run?.review != null) {
      // 過ぎた確認：実行の終わりから、次の実行の始まり（最後なら updated_at）まで。承認・修正の依頼・中止のどれでも
      const next = drafts.slice(i + 1).find((x) => x.startMs !== null);
      const endMs = next?.startMs ?? instant(record.updatedAt);
      const to = endMs === null ? null : sec(endMs);
      if (to !== null && to > endSec) row.wait = { startSec: endSec, endSec: to, live: false };
    }
    return row;
  });

  // 横軸の終わり：動いている・確認待ちなら「今」まで、終わった run は最後の帯の終わりまで
  const live = running !== null || rows.some((r) => r.wait?.live === true);
  let totalSec = 0;
  for (const r of rows) totalSec = Math.max(totalSec, r.run?.endSec ?? 0, r.wait?.endSec ?? 0);
  if (live) totalSec = Math.max(totalSec, sec(nowMs));
  return finish(rows, { live, hasTimes: true, totalSec });
}

function emptyRow(d: Draft, labels: Readonly<Record<string, string>>): GanttRow {
  return { seq: d.seq, label: labelOf(d.stage, d.attempt, labels), agent: d.agent, run: null, wait: null };
}

/** 行の上限（新しい方の MAX_ROWS 行を残す）をかけ、帯を [0, totalSec] に収めて、モデルにする。 */
function finish(allRows: GanttRow[], meta: { live: boolean; hasTimes: boolean; totalSec: number }): GanttModel {
  const omittedRows = Math.max(allRows.length - MAX_ROWS, 0);
  const rows = omittedRows > 0 ? allRows.slice(omittedRows) : allRows;
  let totalSec = 0;
  if (meta.hasTimes) {
    totalSec = meta.totalSec;
    // 古い行を省いたぶん、全体の長さは残した行の帯の終わりまで（動いているときは「今」まで）
    if (omittedRows > 0 && !meta.live) {
      totalSec = rows.reduce((m, r) => Math.max(m, r.run?.endSec ?? 0, r.wait?.endSec ?? 0), 0);
    }
  }
  const fit = (n: number): number => Math.min(Math.max(n, 0), totalSec);
  for (const r of rows) {
    if (r.run) r.run = { ...r.run, startSec: fit(r.run.startSec), endSec: fit(r.run.endSec) };
    if (r.wait) r.wait = { ...r.wait, startSec: fit(r.wait.startSec), endSec: fit(r.wait.endSec) };
  }
  return {
    rows,
    omittedRows,
    totalSec,
    ticks: meta.hasTimes ? buildTicks(totalSec) : [],
    live: meta.live,
    hasTimes: meta.hasTimes,
  };
}
