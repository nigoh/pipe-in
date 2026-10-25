// 拡張の名前の表（設定の節・コマンド ID・パネルの型）と、前の版の名前の読み替え。
// vscode を import しない（判断は純粋な関数に置き、extension.ts はこれを使うだけ）。

/** 設定の節（pipe-in.workDir など） */
export const SECTION = 'pipe-in';
/** 前の版の設定の節（devpipe.workDir など）。新しい設定が書かれていないときだけ読む。0.4 で消す */
export const LEGACY_SECTION = 'devpipe';

export const COMMANDS = { showRun: 'pipe-in.showRun', editPipe: 'pipe-in.editPipe' } as const;

/** 前の版のコマンド ID → 新しい ID。パレットには出さず、キー割り当てが効くように登録だけする */
export const LEGACY_COMMANDS: Readonly<Record<string, string>> = {
  [`${LEGACY_SECTION}.showRun`]: COMMANDS.showRun,
  [`${LEGACY_SECTION}.editPipe`]: COMMANDS.editPipe,
};

/** 別の worktree の実行も一覧に出すかの設定の名前（pipe-in.showOtherWorktrees）。この設定には前の版（devpipe）の名前が無い */
export const SETTING_SHOW_OTHER = 'showOtherWorktrees';

/** 「止まっているかも」の印を出す目安（分）の設定の名前（pipe-in.staleAfterMinutes）。この設定にも前の版（devpipe）の名前が無い */
export const SETTING_STALE_AFTER = 'staleAfterMinutes';

/** 新しく確認待ちになったときに知らせるかの設定の名前（pipe-in.notifyWhenWaiting）。この設定にも前の版（devpipe）の名前が無い（書いてあれば読む） */
export const SETTING_NOTIFY = 'notifyWhenWaiting';

export const VIEW_IDS = { status: 'pipe-in.status', run: 'pipe-in.run', pipeEditor: 'pipe-in.pipeEditor' } as const;

/** 設定の各側の値（VSCode の inspect の結果のうち、使う所だけ） */
export interface SettingValues<T> { globalValue?: T; workspaceValue?: T; workspaceFolderValue?: T }

/** 利用者が書いた値を、workspaceFolder → workspace → global の順に探す。どこにも無ければ undefined */
function written<T>(v: SettingValues<T> | undefined): T | undefined {
  if (!v) return undefined;
  if (v.workspaceFolderValue !== undefined) return v.workspaceFolderValue;
  if (v.workspaceValue !== undefined) return v.workspaceValue;
  return v.globalValue;
}

/**
 * 新しい設定を利用者が書いていれば（既定と同じ値でも）それ、
 * 無くて前の版の設定が書かれていればそれ、どちらも無ければ fallback。
 */
export function chooseSetting<T>(current: SettingValues<T> | undefined, legacy: SettingValues<T> | undefined, fallback: T): T {
  const now = written(current);
  if (now !== undefined) return now;
  const old = written(legacy);
  if (old !== undefined) return old;
  return fallback;
}

/** 設定が変わったかを確かめるキー（新しいもの・前の版のもの） */
export function settingKeys(key: 'workDir' | 'pipesDir'): [string, string] {
  return [`${SECTION}.${key}`, `${LEGACY_SECTION}.${key}`];
}
