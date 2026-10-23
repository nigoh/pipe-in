// 確認用ページ（成果物のタブ）の見本の文章（純粋。文字を組み立てるだけで、ファイルには触れない）。
// 置くのは previewPages.ts で、一時フォルダの中だけ。tests/fixtures/ の見本の記録は変えない。
// 見本で確かめるもの：
//   - 長い Markdown（入れ子の箇条書き・番号つきの途中のコードブロック・表・引用）
//   - 先頭 256 KiB を超える日本語（切れた案内）
//   - 外から来た文字（HTML・リンク・画像が、文字のまま出る）
//   - 名前や段の表示名が極端なパイプ（特別な文字・.txt・広い表・空白の無い長い名前）
// 手元の情報（ユーザー名の入ったパス・メールアドレス）は書かない。
import { ARTIFACT_MAX_BYTES } from '../src/domain/artifacts.ts';

/** 行を改行でつなぎ、最後に改行を 1 つ付ける。 */
const lines = (...rows: string[]): string => `${rows.join('\n')}\n`;

// ---- (a) 動いている開発フロー ----------------------------------------------------------------

/**
 * 04_implementation.md：長い Markdown。入れ子の箇条書き（3 段）・番号つきの途中のコードブロック（番号が 3 から続く）・表・コード・引用が入る。
 * updated が true のとき（更新後の見本）は、末尾に 1 段落だけ足す。
 */
export function implementationSample(updated: boolean): string {
  const base = lines(
    '# 実装の記録',
    '',
    'ユーザー一覧に CSV 出力ボタンを足した作業の記録です（確認用の見本）。',
    '',
    '## 方針',
    '',
    '- 出力の関数は `src/users/export.py` に置く。',
    '  - 列の順は一覧と同じにする。',
    '    - 先頭から ID・名前・登録日の順に並べる。',
    '    - 並べ替えの指定があれば、それに従う。',
    '  - 文字コードは UTF-8（BOM つき）にする。',
    '- ボタンと API は同じ関数を呼ぶ（入口を 1 つにする）。',
    '- 絞り込みは **一覧と同じ条件** を使い、*見えている行だけ* を出力する。',
    '',
    '## 手順',
    '',
    '1. 出力の関数 `export_users_csv` を足す。',
    '2. 一覧の絞り込みを関数に渡す。次のコマンドでテストを流す。',
    '',
    '```bash',
    'pytest -q tests/test_users_export.py',
    'pytest -q',
    '```',
    '',
    '3. 画面に「CSV 出力」ボタンを足す。',
    '4. 画面で押して、ダウンロードされたファイルを開いて確かめる。',
    '',
    '## 変えたファイル',
    '',
    '| ファイル | 変えたこと | 行数 |',
    '| --- | --- | ---: |',
    '| `src/users/export.py` | `export_users_csv` を足した | 48 |',
    '| `src/users/views.py` | ボタンの入口を足した | 21 |',
    '| `templates/users/list.html` | 「CSV 出力」ボタンを足した | 6 |',
    '| `tests/test_users_export.py` | AC-01〜AC-03 のテスト | 72 |',
    '',
    '## 出力の関数',
    '',
    '```python',
    'def export_users_csv(users, columns=COLUMNS):',
    '    """絞り込み済みの users を、BOM つきの UTF-8 の CSV にする。"""',
    '    buffer = io.StringIO()',
    '    writer = csv.writer(buffer)',
    '    writer.writerow([c.label for c in columns])',
    '    for user in users:',
    '        writer.writerow([c.value(user) for c in columns])',
    '    return "\\ufeff" + buffer.getvalue()',
    '```',
    '',
    '## 注意',
    '',
    '> BOM が無いと、Excel で開いたときに文字化けする。',
    '>',
    '> 列の順を変えるときは、一覧の列の順と一緒に直す。',
    '',
    '---',
    '',
    '行の中の書き方は `インラインのコード` と **太字** と *斜体* が使えます。',
  );
  if (!updated) return base;
  return `${base}\n${lines(
    '## 2 回目',
    '',
    '検証の指摘（AC-02）を受けて、出力の先頭に BOM を付けた。',
  )}`;
}

/** 02_design.md の 1 節（番号 n で少しずつ変わる日本語）。 */
function designSection(n: number): string {
  const topics = ['記録の読み方', '画面の組み立て', '更新の反映', '外から来た文字の扱い', '選びとスクロール'];
  const topic = topics[n % topics.length];
  return lines(
    `## 第 ${n} 節 ${topic}`,
    '',
    `この節（${n} 番目）は、${topic}について決めたことを書く。拡張は記録の置き場所を読むだけで、書き込みはしない。`,
    '外から来た文字は、画面に出すところで必ず escapeHtml を通し、外部から何も読み込まない。',
    `描き直しがあっても、選んだものと、スクロールの位置と、焦点は残す。${n} 回目の描き直しでも同じ。`,
    '',
    `- ${topic}は、基盤・アプリケーション・画面の順に向きをそろえる。`,
    '- 同じ入力からは同じ出力になるようにして、時計や乱数に頼らない。',
    '',
  );
}

/**
 * 02_design.md：上限（ARTIFACT_MAX_BYTES）を超える日本語の Markdown。先頭 256 KiB までが出て、切れた案内が付く。
 * 最後の節は上限の外に置く（これが画面に出ていたら、切っていない）。
 */
export function longDesignSample(): string {
  const head = lines(
    '# 設計書（長い見本）',
    '',
    '先頭 256 KiB を超える長さの日本語の文章です。プレビューは先頭の 256 KiB までを表示し、続きはエディタで開いて読みます。',
    '',
  );
  const parts = [head];
  let bytes = Buffer.byteLength(head, 'utf8');
  for (let n = 1; bytes < ARTIFACT_MAX_BYTES + 32 * 1024; n += 1) {
    const section = designSection(n);
    parts.push(section);
    bytes += Buffer.byteLength(section, 'utf8');
  }
  parts.push(lines('## 最後の節（上限の外）', '', 'この節が画面に出ていれば、先頭の 256 KiB で切れていません。'));
  return parts.join('');
}

/**
 * 03_red_tests.md：外から来た文字の見本。HTML の要素・属性・リンク・画像は、要素にならず文字のまま出る。
 * メールアドレスの形（@ のある書き方）は、手元の情報の検査に当たるので書かない。
 */
export function hostileSample(): string {
  return lines(
    '# テスト先行の記録（外から来た文字の見本）',
    '',
    'この文書の HTML・リンク・画像は、要素にならず、文字のまま見えるのが正しい動きです。',
    '',
    '## HTML',
    '',
    '<script>alert(1)</script>',
    '',
    '<img src=x onerror=alert(1)>',
    '',
    '<iframe src="https://example.com/"></iframe>',
    '',
    '<style>body { display: none }</style>',
    '',
    '<a href="javascript:alert(1)" onclick="alert(2)">HTML のリンク</a>',
    '',
    '## リンクと画像',
    '',
    '[リンクの見本](https://example.com/page)',
    '',
    '[危ないリンク](javascript:alert(1))',
    '',
    '![画像の見本](https://example.com/image.png)',
    '',
    '![](data:image/png;base64,AAAA)',
    '',
    '## 表とコード',
    '',
    '| 書き方 | 出方 |',
    '| --- | --- |',
    '| `<b>` | <b>太字にはならない</b> |',
    '| 属性 | " onmouseover="alert(1) |',
    '',
    '```html',
    '<script>document.body.innerHTML = "";</script>',
    '```',
    '',
    '> <img src=y onerror=alert(3)> は引用の中でも文字のまま。',
    '',
    '- 箇条書きの中の <b>タグ</b> と &amp; と &lt;script&gt; も文字のまま。',
  );
}

// ---- (b) 12 個の成果物を持つパイプ（終わった記録） ------------------------------------------------

/** パイプの段 1 つ：段の名前・表示名・成果物のファイル名・成果物の文章。 */
export interface PipeStageSample {
  name: string;
  label: string;
  output: string;
  text: string;
}

/** 空白の無い 100 文字を超える成果物の名前（ASCII のみ。Windows でも作れる文字だけ）。 */
export const LONG_OUTPUT_NAME = `06_${'very_long_output_name_'.repeat(6)}end.md`;
/** 名前に ' ] & 空白を含む成果物の名前（Windows でも作れる文字だけ）。 */
export const SPECIAL_OUTPUT_NAME = "03_it's [draft] & notes.md";
/** 空白の無い長い段の表示名。 */
export const LONG_STAGE_LABEL = 'ExtremelyLongStageLabelWithoutAnySpaceToCheckTheWrapping';

/** 見出しと段落だけの短い成果物。 */
function plainDoc(title: string, body: readonly string[]): string {
  return lines(`# ${title}`, '', ...body.flatMap((p) => [p, '']));
}

/** 広い表（10 列）：横にはみ出したときの、表の中だけのスクロールを見る。 */
function wideTableDoc(): string {
  const head = ['番号', '段', '状態', '開始', '終了', '所要（秒）', '費用（USD）', '入力', '出力', '備考'];
  const rows: string[] = [];
  for (let i = 1; i <= 12; i += 1) {
    rows.push(
      `| ${i} | stage-${i} | ${i % 4 === 0 ? '差し戻し' : '合格'} | 07:${String(i * 2).padStart(2, '0')}:00 | 07:${String(i * 2 + 1).padStart(2, '0')}:30 | ${60 + i * 7} | ${(0.1 * i).toFixed(2)} | ${1000 * i} | ${300 * i} | ${i % 4 === 0 ? '確認の指摘を反映して、もう一度流した' : ''} |`,
    );
  }
  return lines('# 広い表', '', `| ${head.join(' | ')} |`, `| ${head.map((_, k) => (k >= 5 && k <= 8 ? '---:' : '---')).join(' | ')} |`, ...rows);
}

/** 生の記録（.txt）：Markdown に直さず、そのままの文字で出る。長い行は横にスクロールする。 */
function rawLogText(): string {
  const rows: string[] = [];
  for (let i = 1; i <= 24; i += 1) rows.push(`2026-10-17 07:${String(i).padStart(2, '0')}:00 INFO  step ${i} done (items=${i * 3}, skipped=${i % 5})`);
  rows.push('2026-10-17 07:25:00 WARN  <b>この行の < と > と & は、文字のまま出る</b> "quoted" \'single\'');
  rows.push(`2026-10-17 07:26:00 INFO  ${'とても長い行（折り返さずに横へスクロールする）'.repeat(8)}`);
  rows.push('2026-10-17 07:27:00 INFO  finished');
  return lines(...rows);
}

/** 少し長い成果物（縦にスクロールする）。 */
function surveyDoc(): string {
  const parts: string[] = ['# ソースの調査', '', '調べた結果の一覧です（確認用の見本）。', ''];
  for (let i = 1; i <= 14; i += 1) {
    parts.push(`## 調べた所 ${i}`, '', `- 場所：\`src/module_${i}/main.py\``, `- 見つけたこと：入口の関数が ${i} 個あり、どれも同じ検査を通る。`, '- 気づいたこと：名前の付け方がそろっていない。', '');
  }
  return lines(...parts);
}

/** パイプの段 10 個（成果物の名前が極端なものを含む）。 */
export const PIPE_STAGES: readonly PipeStageSample[] = [
  {
    name: 'triage',
    label: '依頼の仕分け',
    output: '01_triage.md',
    text: plainDoc('依頼の仕分け', ['依頼を読んで、調べる範囲を決めた。', '対象は一覧の画面と、出力の関数の 2 つ。']),
  },
  { name: 'survey', label: 'ソースの調査', output: '02_survey.md', text: surveyDoc() },
  {
    name: 'drafts',
    label: '下書きと控え',
    output: SPECIAL_OUTPUT_NAME,
    text: plainDoc("下書き & 控え（名前に ' ] & 空白がある成果物）", ['名前の特別な文字は、画面の一覧・押したときの選び・「エディタで開く」でも、そのままの文字として扱われる。']),
  },
  { name: 'rawlog', label: '生の記録', output: '04_raw_log.txt', text: rawLogText() },
  { name: 'matrix', label: '広い表', output: '05_wide_table.md', text: wideTableDoc() },
  {
    name: 'longname',
    label: '長い名前',
    output: LONG_OUTPUT_NAME,
    text: plainDoc('名前が長い成果物', ['ファイル名に空白が無く、100 文字を超える。一覧の欄からはみ出さずに、折り返すか省かれて見える。']),
  },
  {
    name: 'longlabel',
    label: LONG_STAGE_LABEL,
    output: '07_long_label.md',
    text: plainDoc('段の表示名が長い成果物', ['段の表示名に空白が無く、長い。一覧の「作った段」の欄からはみ出さない。']),
  },
  {
    name: 'verify',
    label: '突き合わせ',
    output: '08_verify.md',
    text: lines('# 突き合わせ', '', '| 項目 | 結果 |', '| --- | --- |', '| 入口 | 合格 |', '| 列の順 | 合格 |', '| 文字コード | 差し戻し |', '', '> 文字コードは BOM を付けて直す。'),
  },
  {
    name: 'fix',
    label: '直し',
    output: '09_fix.md',
    text: lines('# 直し', '', '1. 出力の先頭に BOM を付ける。', '2. テストを流し直す。', '   - 3 件とも通ることを確かめる。'),
  },
  {
    name: 'report',
    label: '報告',
    output: '10_report.md',
    text: plainDoc('報告', ['指摘を直して、3 件とも合格した。', '残りの課題は無い。']),
  },
];

/** 00_input.md（依頼メモ）。 */
export function pipeMemoSample(): string {
  return plainDoc('依頼メモ', ['ユーザー一覧の出力まわりを調べて、直す所をまとめてください。', '成果物は 10 個の段に分けて作ります（確認用の見本）。']);
}

/** 99_summary.md（まとめ）：12 個の成果物の最後の行。既定の選びはこの行。 */
export function pipeSummarySample(): string {
  return lines(
    '# まとめ',
    '',
    '## 結果',
    '',
    '- 10 個の段がすべて終わった。',
    '- 直す所は 1 つ（文字コード）で、直して合格した。',
    '',
    '## 成果物',
    '',
    '| 番号 | 成果物 | 内容 |',
    '| ---: | --- | --- |',
    '| 1 | `01_triage.md` | 依頼の仕分け |',
    '| 2 | `02_survey.md` | ソースの調査 |',
    '| 5 | `05_wide_table.md` | 10 列の広い表 |',
    '',
    '> 一覧の最後の行がこのまとめです。開いたときに、選んだ行が見える所まで一覧が動きます。',
  );
}
