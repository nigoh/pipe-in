# D0037 パイプを流して分かったことを、pipe-build のスキルと pipe-in-gen check の警告に入れる

## 目的

実際のパイプ（isography の街並みの醸成）を流して分かった「段の作り方の落とし穴」を、パイプを作る人（`/pipe-in:pipe-build` と `pipe-builder`）が、作る前にスキルで読め、作ったあとに `pipe-in-gen check` の警告で気づけるようにする。誤りにはしない（check は通す）。

### 分かったことと、入れ先

| # | 分かったこと | 入れ先 |
| --- | --- | --- |
| 1 | 試作・図・下書きを置く段は `access = "docs"` と `docs_dir`。`access = "read"` で `bash = true` の段は、Bash でも成果物以外を書けない（D0036） | スキル＋警告 |
| 2 | `agents` のある段は、サブエージェントを `run_in_background: false` で呼び、全部返るまで成果物を書かない（D0035 がガードと system prompt で押さえた） | スキルだけ（警告は要らない：もう仕組みで止まる） |
| 3 | テストを書く段（`access = "tests"`）は、あとの段の `check.command` と同じ検査を自分でも流す | スキル＋警告 |
| 4 | 実装の段（`access = "code"`）の指示文に、テストを Bash でも書き換えないと書く（D0036 で止まるが、すり抜けの道がある） | スキルだけ |
| 5 | 検査（`[stages.check]`。判定の段も、コマンドの段も）の `on_fail` の先は、指摘を直せる段にする（`access = "read"` の段に戻しても直せない） | スキル＋警告 |
| 6 | 長い段は `max_turns` を足りるだけ、SDK の起動は時間がかかる（`setting_sources` を絞る）など | スキルの末尾「流すとき」 |

## 機能要件と受け入れ基準

### 機能要件

- FR-01 定義の注意（警告）を出す部品を、`pipe_in.pipe` に足す。入力はパイプの定義と読み込んだ指示文、出力は日本語の文の一覧（空なら注意なし）。誤り（`check_pipe`）とは別で、`check_pipe` の返り値は変えない。
- FR-02 警告 W1：`access = "read"` かつ `bash = true` の段で、指示文（`prompt_file` か `prompt` の中身）に書き込みを思わせる言葉があるとき、「Bash でも成果物以外は書けない。置き場所が要るなら `access = "docs"` と `docs_dir` にする」と、段の名前つきで知らせる。
- FR-03 警告 W3：`access = "tests"` の段が `bash = true` でなく、あとの段に `check.command` があるとき、「この段は検査を流せない。`bash = true` にして、あとの段と同じ検査を流させる」と知らせる。
- FR-04 警告 W5：`check` の `on_fail` が自分以外の段を指し、その段が `access = "read"` のとき、「その段は成果物以外を書けず、指摘を直せない」と知らせる。
- FR-05 `pipe-in-gen check` と `pipe-in-gen new` の結果に、警告を出す。誤りが無ければ終了コード 0 のまま。誤りがあれば今までどおり 1。
- FR-06 `plugin/skills/pipe-build/SKILL.md` の「段の決め方」に分かったことの 1〜5 を、末尾の新しい節「流すとき」に 6 を書く。
- FR-07 `plugin/agents/pipe-builder.md` の check の扱いを、警告も読み、直すか、直さない理由を返す形に直す。
- FR-08 `docs/guide/pipes.md` に、警告の一覧と出し方を書く。

### 受け入れ基準

- D0037-AC-01 W1：`access = "read"`・`bash = true` の段で、指示文に書き込みを思わせる言葉（「書き出」「保存」「取り出」「置き場所」「下書き」「試作」「出力先」「描」「mkdir」など。一覧は設計に書く）があると、警告が1件出て、段の名前と `access = "docs"` の案内を含む。
- D0037-AC-02 W1 を出さない：同じ形でも指示文に上の言葉が無いとき。`bash = true` でない `read` の段。`access = "docs"`・`"tests"`・`"code"` で `bash = true` の段。
- D0037-AC-03 W3：`access = "tests"`・`bash` なしの段のあとに `check.command` を持つ段があると、警告が1件出る。
- D0037-AC-04 W3 を出さない：`tests` の段が `bash = true` のとき。あとの段に `check.command` が無いとき。`check.command` が前の段にあるとき。
- D0037-AC-05 W5：`on_fail` が別の段を指し、その段が `access = "read"` なら、警告が1件出る。出さない：先が `docs`・`tests`・`code` の段、`on_fail` を省いたとき、自分を指すとき、`check` が無いとき。
- D0037-AC-06 `pipe-in-gen check` は、警告だけのとき終了コード 0 で、「⚠」つきで警告を1行ずつ出す。誤りと警告の両方があるとき、終了コードは 1 で、誤りも警告も出す。
- D0037-AC-07 警告が無いとき、出力は今までどおり「問題ありません」の1行（`tests/test_generator.py` の既存のテストが変更なしで通る）。
- D0037-AC-08 `pipe-in-gen new` でも、警告があれば同じ形で出し、終了コードは 0。
- D0037-AC-09 ひな形 `dev`・`diagrams`・`spec-qa` は警告 0 件。`examples/video` の見本も 0 件（`verify` 段は D0036 の PR で `access = "docs"` に直した）。直す前の形（`access = "read"` で Bash でこまを書く）は、手作りの定義で W1 が1件出る。
- D0037-AC-10 `check_pipe` の返り値は変わらない。ひな形・見本・既存のパイプの定義は、誤りの有無が今までと同じ。`pipe-in`（本体の流し）は警告を出さず、止めない。
- D0037-AC-11 （古い形）前の版の名前のフォルダ・置き場所（[前の名前から移る](../guide/migrate.md)）のパイプも、同じ警告の検査を受ける。`pipe.toml`・`pipeline.toml`・記録（`state.json`・`99_summary.md`）・終了コード・置き場所の形は変えない。
- D0037-AC-12 新しい部品は、`pipe_in.pipe` の中にあり、`pipe_in_generator` を読まない（`tests/test_architecture.py`）。ガード（`guard.py`・`guard_hook.py`・`pipe_in_guard.py`）は変えない。
- D0037-AC-13 スキル `pipe-build` の「段の決め方」と「流すとき」に、分かったこと 1〜6 の要点が入っている（言葉の目印で検査する：`tests/test_plugin.py`）。
- D0037-AC-14 `docs/guide/pipes.md` に警告の3つが書かれている（`tests/test_guide.py` の言葉の目印）。

## 決めたことと理由

### 聞かずに決め、推しで確定したこと

- 警告は誤りにしない。`check_pipe` は変えず、新しい `pipe_in/pipe/lint.py` の `lint_pipe` が警告だけを返す。警告だけなら終了コード 0、警告が無ければ出力は今までと同じ1行。
- W1（`access = "read"` で `bash = true`）は、形だけでなく、指示文に書き込みを思わせる言葉があるときだけ出す。形だけだと、テストの結果を読むだけの検証の段にも出てしまうため。
- 分かったことの 2（`agents` の段は全部返るまで待つ）と 4（実装の段の指示文にテストを Bash でも書き換えないと書く）は、スキルに書くだけにした。2 は D0035 がガードと system prompt で押さえ、4 は指示文の中身で、形からは決められないため。
- 本体の `pipe-in --pipe`・`pipe-in-gen design`・拡張の検査には警告を出さない（流すのを止めないため）。
- `examples/video` の確かめる段は、警告の最初の実例だった（`access = "read"` のまま Bash でこまを書く。D0036 のもとでは動かない）。直しは D0036 の PR に入れた（このコミットには入れない）。

## 実物のパイプでの出方

指示文の言葉の条件を W1 に重ねる案（推し）と、形だけの案の両方で数えた。

| パイプ | 段 | W1（言葉つき） | W1（形だけ） | W3 | W5 |
| --- | --- | --- | --- | --- | --- |
| ひな形 `dev` | なし（`kind = "dev"`） | 0 | 0 | 0 | 0 |
| ひな形 `diagrams` | survey（read）・draw（docs）・verify（read・verdict、`on_fail = draw`＝docs） | 0 | 0 | 0 | 0 |
| ひな形 `spec-qa` | trace・gaps・qa（すべて read、bash なし） | 0 | 0 | 0 | 0 |
| `examples/video` | ask（read）・script（docs）・mock（docs・bash）・render（docs・bash）・verify（read・bash・`on_fail = render`＝docs） | 直す前は 1（verify：「取り出し」「置き場所」）、直したあとは 0 | 直す前は 1 | 0 | 0 |
| `pipes/`・`.pipe-in/`（このリポジトリ） | パイプの実物なし（`pipes/` は README だけ） | — | — | — | — |

- 合計：実物 4 つ・段 13（`dev` は段なし）で、直す前の見本に W1 が 1 件だけ（今は 0 件）。誤検知は 0 件（`verify` は本当に「こまを `video/verify/frames/` に Bash で作る」と指示しているので、D0036 のもとで動かない。W1 は正しく当たっている）。
- 実物では「言葉つき」と「形だけ」の差は出ない。差は、テストの実行結果を読むだけの検証の段（`read`＋`bash`、指示文に書き込みの話が無い）に出る想定の誤検知で、推しは言葉つき。外れても警告なので、言葉の一覧を足し引きすれば直せる。
- W3・W5 は実物で 0 件。ひな形・見本では当たらず、テストの手作りの定義で確かめる。

## 対象外・残った課題

- 警告 W2（`agents` の段の呼び方）：もうガードと system prompt で止まるので、警告は足さない。
- `access = "code"` の段の指示文の検査（分かったこと 4）：指示文の言葉は見ない。スキルに書くだけ。
- 本体の流し（`pipe-in --pipe`）での警告、拡張の「検査」（`pipeCheck.ts`、`pipe-in-gen check` と同じ決まりとあるが、今回は足さない）、`pipe-in-gen design` の設計の直しの往復への警告の組み込み。
- 警告を誤りに格上げすること。警告を消す設定（`pipe.toml` の項目）。

## 番号

D0032〜D0036 は使われていたので、D0037 にした。D0036（段の Bash の書き込みの範囲）の上に積んでいる。

## 確かめたこと

- `tests/test_pipe_lint.py`（新）と `tests/test_generator.py`・`tests/test_architecture.py`・`tests/test_plugin.py`・`tests/test_guide.py` の D0037 のテスト、全体のテストが通った（main 由来で前から落ちている sdk-buffer の 4 件を除く）。

## 監査と助言

検証で合格したあと、矛盾監査（A-01〜A-06）と公式の文書と照らした助言（V-01〜V-09）を流した。助言の報告の審査は総合 0.81 で合格。人が「全部直す」を選び、すべて文書で直した（コードは変えていない）。
- 監査：A-01（pipe-builder の終わりの条件を「誤りが無くなるまで」に）、A-02（スキルの「結果を伝える」に、警告を見せて直すなら確認を取り直すこと）、A-03（ガイドの W1 の言葉の例を実装の一覧に合わせた）、A-04（W5 の条件は `check` の `on_fail`。判定の段に限らない）、A-05（スキルの W3 の行に「あとの段に `check.command` があるとき」）。A-06 は要約の行なので直していない。
- 助言：V-01（`CLAUDE_CODE_STREAM_CLOSE_TIMEOUT` は公式の文書に無く、Python 版の SDK のコードが読む変数だと断った）、V-02・V-03（`setting_sources` は読む範囲の話として書き、local も読まなくなることを足した。https://code.claude.com/docs/en/agent-sdk/python）、V-05（入れ子は Claude Code では既定で呼べるが、pipe-in のガードが止めると書き分けた。https://code.claude.com/docs/en/sub-agents）、V-09（`max_turns` の目安は経験の値で、足りないと止めるのは pipe-in の動きと書いた）。V-04 は、審査役が `run_in_background` を SDK の文書の Agent の入力で確かめ、今の書き方で正しいと分かったので直していない。V-06〜V-08 は今のままでよいことの確認。

