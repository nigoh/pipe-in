# D0038 監査・助言・審査のサブエージェントに回数の上限を付け、会話を開かない呼び方で MCP の道具も断る

イシュー #35（`maxTurns`）・#34（`--disallowedTools "mcp__*"`）。D0012 の呼び方の2行を置き換える。

## 目的

監査・助言・審査のサブエージェントが長く回り続けて利用料が増えるのを、定義の前置きの `maxTurns` で仕組みとして止める。あわせて、会話を開かずに流す監査・助言の呼び方で MCP の道具もモデルに見せないようにして、読むだけの絞りを `--tools` では消えない道具にまで広げる。D0012・D0015 の残った課題（#34・#35・審査役の `maxTurns`）を、この記録で解く。D0012・D0015 の記録は書き換えない。

## 機能要件と受け入れ基準

定義と記録のテストは `tests/test_agent_limits.py`、呼び方と説明のテストは `tests/test_headless_audit.py`（下では `::` からの名前だけを書く）。

- FR-01 `pipe-in-auditor` の定義の前置きに `maxTurns: 100` を足す
- FR-02 `pipe-in-advisor` の定義の前置きに `maxTurns: 80` を足す
- FR-03 `pipe-in-judge` の定義の前置きに `maxTurns: 50` を足す。本文の「多くても 15 件まで」は残す
- FR-04 文書係と段の4つには `maxTurns` を付けない
- FR-05 会話を開かずに流す監査・助言の呼び方の2行に、`--tools "…"` のすぐ後ろ・`--allowedTools` の前に `--disallowedTools "mcp__*"` を足す。2か所（`/pipe-help`・`docs/guide/develop.md`）の行は空白をそろえて同じにする
- FR-06 2か所の説明の、MCP の道具の言い方を「`--tools` では消えないので `--disallowedTools "mcp__*"` で断る」に直す
- FR-07 2か所の説明に、サブエージェントの `maxTurns`（`--max-turns` とは別）と、上限で止まったら範囲を狭めて流し直すことを書く
- FR-08 `--strict-mcp-config` は呼び方に足さない
- FR-09 フック（`.claude/hooks/pipe_in_guard.py`）・`pipe_in/engine/guard.py`・`generator/guard_hook.py` は変えない
- FR-10 この決定の記録を書き、索引に行を足す
  - D0038-AC-01 監査の前置きに `maxTurns: 100` がちょうど1つある（`tests/test_agent_limits.py::test_D0038_AC_01_03_読むだけの3つの前置きにmaxTurnsが1つだけあり値が決めたとおり`）
  - D0038-AC-02 助言の前置きに `maxTurns: 80` がちょうど1つある（同じテスト）
  - D0038-AC-03 審査役の前置きに `maxTurns: 50` がちょうど1つある（同じテスト）
  - D0038-AC-04 正の整数でない値（0・-1・abc・空・1.5）と前置きの外の `maxTurns` を、検査が見分ける（`::test_D0038_AC_04_検査は正の整数でないmaxTurnsと前置きの外のmaxTurnsを見分ける`・`::test_D0038_AC_04_検査は正しいmaxTurnsを通す`）
  - D0038-AC-05 `maxTurns` があるのは8つの定義のうち監査・助言・審査の3つだけ（`::test_D0038_AC_05_maxTurnsが付いているのは監査_助言_審査の3つだけ`）
  - D0038-AC-06 前置きの今の検査（`tools:` の中身・本文の語）がそのまま通り、審査役の `effort: high` が残る（`tests/test_pipe_in_guard.py` の D0008 の定義の検査、`tests/test_pipe_judge.py::test_d0015_ac01_judge_definition_tools`、`::test_D0038_AC_06_審査役の前置きにeffort_highが残る`）
  - D0038-AC-07 前の版の定義（`maxTurns` の無い前置き）は、例外でなく「maxTurns が無い」で落ちる（`::test_D0038_AC_07_前の版の定義はmaxTurnsが無いと分かり例外で落ちない`）
  - D0038-AC-08 審査役の本文に「多くても 15 件まで」が残る（`::test_D0038_AC_08_審査役の本文に多くても15件までが残る`）
  - D0038-AC-09（実機）`maxTurns` を付けた定義で会話を開かずに監査を流すと、報告を返して止まり、`git status` に差が出ない
  - D0038-AC-10（実機）小さい `maxTurns` で監査を流し、サブエージェントが途中で止まることと、メインに何が返るかを確かめる
  - D0038-AC-11 2か所の呼び方の行が承認された2行と同じ（`tests/test_headless_audit.py::test_呼び方の行は承認された2行と同じ`・`::test_D0014_AC_30_ガイドとpipe_helpの呼び方が空白をそろえて同じ`、`tests/test_guide.py::test_D0014_AC_12_前のコードブロックの行がREADMEかガイドのコードブロックに残る`）
  - D0038-AC-12 呼び方の行すべての `--disallowedTools` の値がちょうど `mcp__*`。抜け・狭い値・空の値を検査が見つける（`::test_D0038_AC_12_呼び方の行のdisallowedToolsはちょうどmcpの全部`・`::test_D0038_AC_12_検査はdisallowedToolsの抜けと狭い値と空の値を見つける`）
  - D0038-AC-13 `--disallowedTools` を足しても `--allowedTools` の語が変わらず、D0012 の検査がそのまま通る（`::test_D0038_AC_13_disallowedToolsを足してもallowedToolsの語が変わらない`）
  - D0038-AC-14 `--allowedTools` に `mcp__` で始まる語が無い。混ざった偽の行を検査が見つける（`::test_D0038_AC_14_allowedToolsにmcpで始まる語が無い`・`::test_D0038_AC_14_検査はallowedToolsに混ざったmcpの語を見つける`）
  - D0038-AC-15 前の版の呼び方の行（D0012 の2行）は新しい検査で落ちる（`::test_D0038_AC_15_前の版の呼び方の行は新しい検査で落ちる`）
  - D0038-AC-16 2つの節に MCP を断る説明があり、前の言い方が残っていない（`::test_D0038_AC_16_節にMCPを断る説明がある`・`::test_D0038_AC_16_節に前の言い方が残っていない`）
  - D0038-AC-17 2つの節に `maxTurns`・`--max-turns`・狭めて流し直す説明がある（`::test_D0038_AC_17_節にmaxTurnsと狭めて流し直す説明がある`）
  - D0038-AC-18 呼び方の行は2か所だけで、この記録にも無い（`::test_D0014_AC_30_呼び方の行はpipe_helpと開発の文書の2か所だけ`・`::test_D0038_AC_18_D0038の記録に呼び方の行を書かない`）
  - D0038-AC-19（実機）新しい監査の行で、`system/init` の `tools` に `mcp__` の道具が無く、`slash_commands` に `pipe-audit` があり、報告で止まる
  - D0038-AC-20（実機）助言の行でも同じ（WebFetch は公式の文書の場所だけ）
  - D0038-AC-21（実機）`--disallowedTools "mcp__*"` を外した監査の行では、同じ環境で `mcp__` の道具が出る
  - D0038-AC-22（実機）`--strict-mcp-config` を付けずに AC-19 が満たせたかと、要るかの判断を書く
  - D0038-AC-23 フックと guard の3つに差が無く、今のフックのテストがそのまま通る（`tests/test_pipe_in_guard.py`・`tests/test_guard_hook.py` の全部。差が無いことは `git diff --name-only main...HEAD` で手で確かめる）
  - D0038-AC-24 この記録と索引の行があり、置き換えと解く課題が書いてある（`tests/test_agent_limits.py::test_D0038_AC_24_決定の記録に置き換えと解く課題が書いてある`・`::test_D0038_AC_24_索引にD0038の行がある`）
  - D0038-AC-25 D0012・D0015 の記録に D0038 が出てこない（`::test_D0038_AC_25_D0012とD0015の記録にD0038が出てこない`）
  - D0038-AC-26 「決めたことと理由」に3つの値と根拠と付けない理由がある（`::test_D0038_AC_26_決めたことと理由に3つの値と根拠と付けない理由がある`）

## 決めたことと理由

- **値は監査 100・助言 80・審査 50。** 上限は「道具の呼び出しの数がそのままターンになっても足りる」ところに置いた（1回の返事で道具を並べて呼べるので、ターンの数は呼び出しの数以下になる見込み）。
  - 監査 100：D0008 の記録にある監査（D0008-AC-22 で流したもの）では、道具の呼び出しが Read・Grep・Glob を合わせて 73 回だった。およそ3割の余裕を見た。
  - 助言 80：WebFetch・WebSearch で利用料が増えやすいので、監査より低くした。これまででいちばん多いのは D0008 の記録の WebFetch 12 回（D0012 では 9 回）で、読む道具を合わせても足りる見込み。
  - 審査 50：WebFetch は定義の文で 15 件まで。取り直しと報告の「ファイル:行」の確かめを合わせても足りる見込み。本文の「多くても 15 件まで」は残した（上限はターンの数で、WebFetch の件数ではないため）。
  - 選ばなかった案：3つとも 100 にそろえる（Web を使う助言の利用料を抑える力が弱い）。低めの 60・40・30（範囲なしの監査が D0008 の 73 回を下回り、途中で止まるおそれがある）。
- **付けるのは読むだけの3つだけ。** 文書係 `pipe-in-documenter` と段の4つ（`pipe-in-analyst`・`pipe-in-tester`・`pipe-in-coder`・`pipe-in-verifier`）は書き込む役で、途中で止まると直しかけのファイルが残る。Web も使わず、段の4つは `/pipe-in` の段の区切りで人が止められる。読むだけの3つは、途中で止まっても何も壊れない。
- **`--disallowedTools "mcp__*"` は `--tools "…"` のすぐ後ろ、`--allowedTools` の前に置く。** 公式の文書（https://code.claude.com/docs/en/cli-reference ）の例は、どちらのフラグも後ろに値を空白で区切って並べる形なので、別の値の並びの途中に挟まない（並べる順の決まりは文書に無く、これはこのリポジトリの安全側の判断）。D0012 の検査（`--allowedTools` の語の読み方）も変えずに済む。
- **`--strict-mcp-config` は足さない。** `--disallowedTools "mcp__*"` でモデルに見える道具から MCP が消えれば、読むだけの絞りの目的は果たせる。行は短いほうが打ち間違いが少ない。このリポジトリには `.mcp.json` が無い。ただし、消えるのは道具だけで、MCP のサーバーそのものはつながる（公式の文書 https://code.claude.com/docs/en/permissions に、`claude -p` では `.mcp.json` のサーバーが確認なしでつながるとある）。`.mcp.json` が入ったときに `--strict-mcp-config`（`--mcp-config` 無しで付けたときの動き）で起動まで止めるかは、AC-22 の実機のあとで決め直す。
- **D0012 の呼び方の2行を置き換える。** 2行に `--disallowedTools "mcp__*"` を足した。D0012 の記録は書き換えず、この記録で置き換える。
- **テストの期待の値を変えた。** 呼び方の行が変わる（仕様の変更）ので、次を新しい2行に合わせた。前の版の2行は、`tests/test_headless_audit.py` に AC-15 の偽の文として残した。
  - D0012 の `EXPECTED_AUDIT`・`EXPECTED_ADVISE`（`tests/test_headless_audit.py`）。
  - D0014-AC-12 の `OLD_CODE_LINES` の2行（`tests/test_guide.py`。ガイドのコードブロックに残っているべき行の一覧なので、行が変わる今回は新しい行にした）。
- **検査は新しいファイル `tests/test_agent_limits.py` にまとめた。** D0038 の AC がまとまって読める。前置きは先頭の `---` から次の `---` までだけを読み、本文の `---` と取り違えない。
- **上限で止まったときの扱いは、`/pipe-help` と `docs/guide/develop.md` に1行ずつ書いた。** 公式の文書（https://code.claude.com/docs/en/sub-agents ）では、上限に当たったサブエージェントの報告は途中までの印（partial）を付けて返り（Claude Code v2.1.246 以降）、メインは `SendMessage` で続きを頼める。会話を開かない呼び方では `--tools` に `SendMessage` が無いので続けられない（推し量り。AC-10 で確かめる）ため、範囲（テーマ）を狭めて流し直す。
- **番号は D0038。** はじめは D0035 で書いたが、載せ直したときに main にはもう D0034〜D0036 の記録が入っていて、D0037 は先に載せ直した別のブランチ（Windows の `live watch`）が使った。D0033 はテストが main で使っている（記録はまだ無い）ので飛ばした。

## 対象外・残った課題

- 実機の AC（AC-09・10・19〜22）は、まだ確かめていない（下の「確かめたこと」）。
- プラグインのエージェント（`plugin/agents/` の2つ）の `maxTurns`。利用者のプロジェクトで動くので、別に検討する。
- 本体の `pipeline.toml`・パイプの `pipe.toml` の `max_turns`（SDK の段の上限で、すでにある）。
- `--max-turns` を呼び方の行に入れること（任意のまま）。
- `/pipe-judge`・`/pipe-docs` など、ほかのスキルの会話を開かない呼び方。
- サブエージェントの定義の前置きに `disallowedTools` を足すこと（`tools:` は許すものの一覧で、MCP は入っていない。フックも止めている）。
- 上限で止まったときに、メインが自動で範囲を分けて流し直す仕組み。
- `/pipe-audit`・`/pipe-advise`・`/pipe-judge` の SKILL.md と、会話の中で監査・助言・審査を流す手順（`/pipe-in` の SKILL.md の「監査と助言」・`docs/development/workflow.md` の同じ節）に、止まったときの扱い（partial の報告に続きを頼むか、狭めて流し直すか）を書くこと（AC-10 で何が返るかが分かってから決める）。
- メインの `--disallowedTools "mcp__*"` がサブエージェントにも及ぶか（公式の文書からは及ぶと読めるが、はっきりした1文は無い。定義の `tools:` は許すものの一覧なので、実害は小さい）。

## 確かめたこと

- `tests/test_agent_limits.py`・`tests/test_headless_audit.py`・`tests/test_guide.py`・`tests/test_rules.py` の D0038 のテストが通る（実装の段）。
- `.claude/` の4ファイル（定義3つと `/pipe-help`）は、テスト先行・実装の段のサブエージェントが書けないので（フックが止める）、設計の文をメインが入れた。
- 実機の AC-09・AC-10・AC-19・AC-20・AC-21・AC-22：まだ（人が確かめる）。AC-10 では、報告に partial の印が付くかも見る。
- 検証のあとの監査で5件、助言で4件が挙がり、人が9件とも承認して直した（上限の根拠の数・残った課題の範囲・テストのコメント・番号の決まりの文、partial で返ること、サーバーは起動すること、`--disallowedTools` を前に置く理由、信頼していない作業フォルダの例）。助言の報告の審査は overall 0.88・pass（道具の効率は回数を渡さなかったので採点なし）。
