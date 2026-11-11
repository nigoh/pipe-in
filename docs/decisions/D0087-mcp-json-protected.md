# D0087 既定で守る場所に .mcp.json を足す（#136）

## 目的

D0084 で、SDK の道も `.claude/`・`.git/`・`.pipe-in/`・`pipeline.toml` への書き込みを既定で止めるようにした。けれども、プロジェクトの直下の `.mcp.json` は、実装の段と `access = "code"` の段が書けた。

Claude の公式の文書では、`.mcp.json` は `setting_sources` に `project` があると読まれ、Claude Code 自身の守るファイルの一覧にも入っている。段が書き換えると、MCP サーバーの定義を足せる。これも既定で守る。

### 要求と前提

- UR-01 利用者として、パイプの段に、プロジェクトの直下の `.mcp.json`（MCP サーバーの設定）を書き換えられたくない。
- 前提：`setting_sources` に `project` があると、SDK は `.mcp.json` を読む。
- 状態を持ち、操作や出来事で移り変わるか
  - 答え：いいえ
  - 理由：守る場所の一覧に1つ足すだけで、状態を持たない。

## 機能要件と受け入れ基準

テストは、断りの無いかぎり `tests/test_mcp_json_protected.py`。

- FR-01（UR-01）`pipe_in/engine/spec.py` の `DEFAULT_PROTECTED_PATHS` に `.mcp.json` を足す（8つになる）。会話の道にも同じ定数が効く。
- FR-02（UR-01）場所の一覧を字で持つ文（`work_dir` の断りの文・`pipe-in-gen check` の警告 W7）にも `.mcp.json` を出す。
- FR-03（UR-01）守りの比較の表（`tests/guard_matrix.py`）に、`.mcp.json` の行を足す。
- FR-04（UR-01）`docs/guide/config.md` の `setting_sources` の説明に、`project` が `.mcp.json` も読むことを書く。
- FR-05（UR-01）`CLAUDE.md`・`CLAUDE.local.md` は、既定で守る場所に入れない。`protected_paths` に書けば守れることを、文書に書く。

止める側

- D0087-AC-01（FR-01）開発フローの全段とパイプの `access` のどの段でも、`.mcp.json` への Write・Edit・MultiEdit・NotebookEdit が止まる（`test_d0087_ac01_全段の種類で_mcp_json_への書き込み道具が止まる`）。
- D0087-AC-02（FR-01）Bash の書き込みが止まる。`..`・絶対パス・リンクを経た道・`cd` をまたぐ相対パスでも同じ（`test_d0087_ac02_*`）。
- D0087-AC-03（FR-01）会話の道でも止まる（`test_d0087_ac03_会話の道でも止まる`）。
- D0087-AC-04（FR-02）止めた理由の文と、段に渡す説明の文に `.mcp.json` が出る。利用者が `protected_paths` に書いても、出るのは1回（`test_d0087_ac04_*`）。
- D0087-AC-05（FR-02）`work_dir` が `.mcp.json` と重なる設定は、流す前に止まり、断りの文に出る。ふつうの `work_dir` は止まらない。断りの文と W7 の文は、定数の全部の型の語を持つ（`test_d0087_ac05_*`）。
- D0087-AC-06（FR-02）`docs_dir`・`writes` が `.mcp.json` と重なるパイプに、警告 W7 が出る。終了コードは変わらない（`test_d0087_ac06_*`）。

許す側

- D0087-AC-07（FR-01）型は直下の `.mcp.json` だけに当たる。`src/.mcp.json`・`mcp.json`・`.mcp.json.bak` は、今までどおり通る（`test_d0087_ac07_*`）。
- D0087-AC-08（FR-01）ひな形と見本のパイプに、`.mcp.json` を書く所が無く、定義を変えずに流せる（`test_d0087_ac08_*`）。
- D0087-AC-09（FR-03）比較の表に `.mcp.json` の行があり、SDK の道と会話の道は止める。ほかの行は変わらない（`test_d0087_ac09_比較の表に_mcp_json_の行があり_sdkと会話の道は止める`・`tests/test_guard_matrix.py`）。

古い形

- D0087-AC-10（FR-01）今までの `pipeline.toml`・前の版の置き場所のパイプは、そのまま読める。利用者が `protected_paths` に `.mcp.json` を書いていても読める（`test_d0087_ac10_*`）。
- D0087-AC-11（FR-04・FR-05）（文書）`docs/guide/config.md` の `setting_sources` の説明に `.mcp.json` も読むことが、`docs/guide/safety.md` に `CLAUDE.md`・`CLAUDE.local.md` は `protected_paths` に書けば守れることが、書いてある（人が読んで確かめる。この番号の付いたテストは無い。番号をずらしたときに足した）。

### 非機能要件

- 無し

## 決めたことと理由

- 守りの部品（`pipe_in/engine/guard.py`・`generator/guard_hook.py`・`.claude/hooks/pipe_in_guard.py`）は変えていない。定数に1つ足しただけで、止める範囲を狭める所は無い。
- 型は `.mcp.json` の1つだけ（プロジェクトの直下）。入れ子のフォルダの `.mcp.json` は足さない（公式の文書に、読まれるという記述が無い）。
- `CLAUDE.md`・`CLAUDE.local.md` は入れない。段への指示を変えうるが、設計の段などが正当に直す使い方とぶつかる。Claude Code 自身の守るファイルの一覧にも入っていない。守りたい対象では、`pipeline.toml` の `protected_paths` に書く（`docs/guide/config.md` に例を載せた：`CLAUDE.md`・`CLAUDE.local.md`・`.vscode/*`・`.husky/*`・`.envrc`・`.gitmodules`）。
- 一覧を字で持つ2つの文（`work_dir` の断りの文・W7 の文）は、手書きのまま語を足し、定数の全部の型の語が入っていることをテストで固定した。共通の文を1つ置く案は、2つの言い回しが違い、今の文が変わるので選ばなかった。
- 設計から足した直し（止める側）：`.mcp.json` は記号を含まない型なので、`work_dir` の重なりは「自分・上の階層のどれか・自分の下」で見る形に、`docs_dir` の重なりは、そのもの自身も見る形にした。前の見方（自分と、自分の下）では、`work_dir = ".mcp.json/x"` と `docs_dir = ".mcp.json"` が当たらなかった。
- パイプの定義の `mcp`・`mcp_servers`（段が使う MCP の道具とサーバー）と、プロジェクトの `.mcp.json` は別物。文書にそう書いた。
- 既存のテストの期待を直した：`tests/test_default_protected.py` の「決めた7つ」の中身を8つに（名前は、D0084 の記録が引いているので変えていない）。比較の表に行 `write-mcpjson` を足した。
- **動きが変わる場面**：SDK の道と会話の道で、プロジェクトの直下の `.mcp.json` を作る・直す段が止まる。`docs_dir`・`writes`・`work_dir` がそれと重なる設定は、警告が出る・流す前に止まる。
- 無人の実行で進めた。次の点は推しの案で決めた（人の確認は朝）：`CLAUDE.md` を入れない／型は直下の1つだけ／開発用とプラグインのフックには足さない／大文字小文字の違いは広げない／文の一覧は手書きのまま、テストで固定する。

## 対象外・残った課題

- 入れ子のフォルダの `.mcp.json`、`.vscode`・`.husky`・`.envrc` などを既定に入れること、`disallowed_tools` を使った二重の守りは、対象外。
- 開発用のフックの `pipe-in-coder` は、今も `.mcp.json` に書ける（比較の表の実測。自前の一覧に無い）。開発用のフックは、この件では変えていない。
- 大文字小文字の違う名前（`.MCP.JSON`）は、OS によって当たり方が変わる（ほかの守る場所と同じ）。
- 監査の報告（3件。直していない。人の確認は朝）：
  - A-01 比較の表の「守る場所を書いた SDK の道」の列は、`protected_paths` に `.mcp.json` を書いていない。`.mcp.json` の行で2つの列が同じなのは「既定で止まるから」で、書いた場合の確かめにはなっていない（書いた場合は `test_d0087_ac04_利用者が_protected_paths_に書いても1回だけ` が見ている）。`docs/guide/safety.md` の説明を書き分けるか、表の設定に足す。
  - A-02 `tests/guard_matrix.py` のコメントの「4か所」の見出しの下に、`.mcp.json` の行が入っている。
  - A-03 `pipe_in/pipe/chat_record.py` の `chat_specs` の説明の列挙が、守る場所の全部（`.mcp.json` と前の版の置き場所）を挙げていない（D0084 の監査 A-02 からの持ち越し）。
- 助言と審査は流さなかった（変えたのは `pipe_in/engine/spec.py` と `pipe_in/pipe/lint.py` で、助言を流す対象のファイルに当たらない。この件は、D0084 の助言 V-01 を受けた直し）。

## 確かめたこと

- 本体 `python -m pytest -q`：全部通った。拡張は触っていない。
- 赤の確かめ：足したテストは、実装の前に「`.mcp.json` に書ける」「説明の文と断りの文に出ない」「警告が出ない」「定数に無い」で落ちた。
- 比較の表：足したのは1行だけで、ほかの行・列は変わっていないことを差分で確かめた。足した行の、SDK の道と会話の道の列は、実装の前は「許す」だった。
- 画面の受け入れ基準は無い。本物の SDK を呼ぶ実行では、まだ確かめていない。
