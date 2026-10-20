// テストの補助：実行の一覧（D0019）の行と一覧の入れ物を作る。型だけを読み込む（まだ無いモジュールは import しない）。
// 2版目で、行の項目が増えた：session（セッション名）・pipe（パイプ名）・branch・other（別の worktree）・sessionId・updatedDate・elapsed。
import type { RunListView, RunRow } from '../domain/runList.ts';

/** 行1つ。既定は「動いている開発フロー」（ブランチ・ID・経過は無し）。 */
export function row(p: Partial<RunRow> = {}): RunRow {
  return {
    key: 'here|',
    session: '開発フロー',
    pipe: '開発フロー',
    branch: null,
    other: false,
    previous: false,
    state: 'running',
    result: null,
    stage: '設計',
    sessionId: null,
    costText: '$0.123',
    updatedText: '10/17 10:05',
    updatedDate: '10/17',
    updatedMs: Date.UTC(2026, 9, 17, 10, 5, 0),
    elapsed: null,
    waitingSec: null,
    ...p,
  };
}

/** 一覧 1 つ。既定の作業フォルダの表示は docs/pipeline（設定の相対パスのまま）。 */
export function listView(rows: RunRow[], p: Partial<RunListView> = {}): RunListView {
  return { rows, selected: rows[0]?.key ?? 'here|', omitted: [], omittedWorktrees: 0, workDir: 'docs/pipeline', ...p };
}

/** セッション ID の見本（全部）。先頭 8 文字は行に出る。 */
export const SID = {
  here: 'aaaa1111-0000-4000-8000-0123456789a1',
  feat: 'bbbb2222-0000-4000-8000-0123456789b2',
  diagrams: 'cccc3333-0000-4000-8000-0123456789c3',
  fix: 'dddd4444-0000-4000-8000-0123456789d4',
} as const;

/**
 * 確認待ち 2・動いている 2・待ち 1・終わった 3（合格・不合格・前の実行）が並ぶ見本の一覧（8 行）。別の worktree の行が 2 つ。
 * 状態のタブの件数は すべて 8・確認待ち 2・動いている 3（待ちを含む）・終わった 3。
 */
export function sampleRows(): RunRow[] {
  return [
    row({
      key: 'here|',
      session: '仕様の QA を回す',
      pipe: '開発フロー',
      branch: 'main',
      state: 'waiting',
      stage: '要件定義',
      waitingSec: 42,
      sessionId: SID.here,
      costText: '$1.250',
      updatedDate: '10/17',
    }),
    row({
      key: 'wt.feat-x|',
      session: 'CSV 出力を足す',
      pipe: 'spec-qa',
      branch: 'feat/export-csv',
      other: true,
      state: 'waiting',
      stage: '図を描く',
      waitingSec: 7,
      sessionId: SID.feat,
    }),
    row({
      key: 'here|diagrams',
      session: 'diagrams を直す',
      pipe: 'diagrams',
      branch: 'main',
      state: 'running',
      stage: '図を描く（2 回目）',
      elapsed: { seconds: 125, live: true },
      sessionId: SID.diagrams,
    }),
    row({
      key: 'wt.fix-login|',
      session: 'ログインの不具合',
      pipe: '開発フロー',
      branch: 'fix/login',
      other: true,
      state: 'running',
      stage: '実装',
      elapsed: { seconds: 61, live: true },
      sessionId: SID.fix,
    }),
    row({ key: 'here|idle', session: '合間の実行', pipe: 'idle-pipe', branch: 'main', state: 'idle', stage: '設計' }),
    row({
      key: 'here|survey',
      session: '調査',
      pipe: 'survey',
      branch: 'main',
      state: 'done',
      result: '合格',
      stage: '検証',
      elapsed: { seconds: 420, live: false },
    }),
    row({
      key: 'here|review',
      session: 'レビュー',
      pipe: 'review',
      branch: 'main',
      state: 'done',
      result: '不合格',
      stage: '検証',
      elapsed: { seconds: 300, live: false },
    }),
    row({
      key: 'here|archive/20261016-090000',
      session: '前の仕様',
      pipe: '開発フロー',
      branch: 'main',
      previous: true,
      state: 'done',
      result: '合格',
      stage: '検証',
      elapsed: { seconds: 900, live: false },
      updatedDate: '10/16',
    }),
  ];
}
