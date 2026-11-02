# D0061 作業台の検査と pipe-in-gen check の結果がずれないように、同じ見本を両方に掛けて確かめる

## 目的

Claude Code と作業台が同じパイプを触るので、片方で通って片方で落ちるずれを無くす。作業台の検査（`vscode/src/domain/pipeModel.ts` の `validatePipe`）は `pipe-in-gen check`（`pipe_in/pipe/definition.py` の `check_pipe`）と同じ決まりを拡張の中で作り直したもの。同じ見本のパイプを両方に掛けて結果が合うことをテストで確かめ、見つかったずれを直し、決まりを足すときは両方を直すことを文書に書く（GitHub の issue #18）。issue が挙げる `pipeCheck.ts` は段の判定スイッチで、突き合わせる相手は `validatePipe` だった。

## 機能要件と受け入れ基準

### 機能要件

- FR-01：見本を `tests/fixtures/check_parity/<ケース>/`（`expected.json` と `pipe-in-<名前>/`）に置き、Python と拡張が同じ見本を同じ `expected.json` に照らす。
- FR-02：突き合わせの規則は、誤りの件数が等しい・各キーワードがどれかの誤りに含まれる・どの誤りもどれかのキーワードを含む、の3つ（文の言いまわしは比べない）。規則は `_matcher.json` で両側が同じ実装を保つ。
- FR-03：片側だけの差は `only`（`python` か `extension`）と理由を `expected.json` に書く。
- FR-04：拡張の `validatePipe` に、Python と同じ決まりを足す。
- FR-05：画面から作れない組み合わせを持たないよう、`pipeEdit.ts` に `setAccess` を足す。
- FR-06：`docs/development/` に、決まりを足すときは両方を直すことを書く。

### 受け入れ基準

- D0061-AC-01：各ケースに `pipe.toml` と `expected.json` があり、形が合う。
- D0061-AC-02：通るケースは、Python でも拡張でも誤りが0件。
- D0061-AC-03：`only` の無い誤りのケースが、Python で `expected.json` の件数とキーワードに合う。
- D0061-AC-04：同じケースが、拡張でも同じ `expected.json` に合う。
- D0061-AC-05：read の段に writes を書くと、両側で誤りになる。
- D0061-AC-06：`check.command` の危険な語（`DANGEROUS_BASH`）が、両側で誤りになる。
- D0061-AC-07：writes・docs_dir・add_dirs の絶対パス・`C:` 形・`\` 始まりなどが、両側で誤りになる。
- D0061-AC-08：`output` の予約名が、両側で誤りになる。
- D0061-AC-09：MCP サーバー名が使えない形だと、両側で誤りになる。
- D0061-AC-10：`check.judge`・`max_budget_usd` は両側で誤りになる。`timeout_sec`・`max_agent_calls` は作業台が読まないので `only: python`。
- D0061-AC-11：group（並列の枠）の決まりが、両側で同じ件数の誤りになる。
- D0061-AC-12：`only` を持つケースには理由がある。
- D0061-AC-13：`only: python` のケースは、Python で `expected.json` に合う（見本が古くならない）。
- D0061-AC-14：前の名前の頭のフォルダ・`kind` 無しの前の形のパイプを、両側が同じに通す。
- D0061-AC-15：`docs/development/` に、両方を直すことを書いた節・行がある。
- D0061-AC-16：既存の `pytest -q` と、拡張の `npm test`・`npm run typecheck`・`npm run build` が通る。
- D0061-AC-17（画面）（手で）：作業台で read の段に writes を書いたパイプを開いて保存すると、保存は済み、「確認」の一覧に同じ理由の誤りが出る。
- D0061-AC-18：`only: extension` のケースが、拡張で `expected.json` に合う。
- D0061-AC-19：突き合わせの規則の実装が、両側で `_matcher.json` の全件と合う。
- D0061-AC-20：`setAccess` が、read で writes を、docs 以外で docsDir を空にする。

## 決めたことと理由

人が居ない夜の実行だったため、決めきれない点は推しの案で進めた（人の確認は朝）。

- **突き合わせる相手は `validatePipe`**。`pipeCheck.ts`（段の判定スイッチ）ではない。
- **見本は `tests/fixtures/check_parity/` の1か所**。拡張のテストが `vscode/` の外を読む。依存の向き・層の検査には触れない。
- **文の一致ではなく、件数とキーワードで比べる**。言いまわしは両側で違ってよい（拡張に足した決まりの文は Python と同じにした）。
- **拡張が読む項目だけ検査し、読まない項目は意図した差（`only: python`）**。読み込みで黙って直る項目（access・MCP の type・next と routes の併用など）も同じ。保存すると直った形で書かれる。
- **拡張が厳しい側の差（前の段へのつなぎ・空の指示ファイル）は Python に足さず `only: extension`**。
- **意図した差の一覧は `docs/development/design.md` の節「検査の二重化（Python と拡張）」に置く**。
- **`max_budget_usd = 0` は拡張でも誤りにする**。D0051 の「`validatePipe` には足さない」「0 を保存できる」は当時の事実で、この記録で置き換えた。入力欄の `min="0"` は変えていない（下の残った課題）。
- 保護の仕組み（`guard.py`・`guard_hook.py`・`pipe_in_guard.py`）には触らず、依存も足さない。記録・設定・パイプの形は変わらない。
- 古い名前の検査（`tests/test_rename.py`）の許す一覧に、前の名前を含む新しい3ファイルを理由つきで足した。

### 監査・助言

- 監査の5件（A-01〜A-05）は、指示どおり直していない。内容は PR の本文の「朝に見ること」に全文を残した。A-01（この記録が無かった）はこの記録を書いて済んだ。
- 助言と審査は流していない（変えたファイルに `.claude/`・`plugin/`・`runner.py`・`guard.py`・`guard_hook.py` が無いため）。

## 対象外・残った課題

- 言いまわしの一致、`lint` の警告、guard 類の変更、検査の一本化。
- 作業台が読めない項目を保存で消す件（別 issue）。
- 入力欄の `min="0"` と検査の食い違い（0 を打てて、検査で誤りになる）。
- 監査 A-02〜A-05（テストの書き方の整理、vscode/README.md の言い方、接頭辞の説明）。
- CLAUDE.md への1行の案（PR の本文）。

## 確かめたこと

- `python -m pytest -q`：記録を書く前は、この記録が無い1件を除いて通過（12241 件）。
- `npm --prefix vscode test`：5264 件通過。`npm run typecheck`・`npm run build`：通過。
- 画面の確認（AC-17）：まだ。
