# 段の決め方と、検査と審査の組み方

`/pipe-in:pipe-build` が段の表を作るときと、pipe-builder が `pipe.toml` を書くときに読む文書です。人が読む説明は公開リポジトリの `docs/guide/pipes.md`（https://github.com/nigoh/pipe-in/blob/main/docs/guide/pipes.md）にあります（プラグインには入っていないので、要点はここに書いてあります）。

## 段の決め方

- `access` は、目的を満たす中でいちばん狭い型にする（文書を作るだけなら `read`、別のフォルダに文書や図を置くなら `docs`）。書き込む場所が決まっているなら `writes` で絞る。
- `bash = true` は、テストの実行など本当に必要な段だけ。
- 人が中身を確かめるべき段（方針が決まる段・最終の成果物）には `review = true`。
- 図は Mermaid で書かせる。
- 作った物を確かめる段には `[stages.check]`（`verdict = true` で判定させ、`on_fail` で直す段へ戻す。テストで確かめられるなら `command`）。検査と審査の組み方は下の節。
- 目的で道が分かれるなら `[stages.routes]`、分岐先の最後には `next`。互いに独立した段は `group` で同時に流す。
- 段の中で手分けしたいときは `[stages.agents.<名前>]`。方針だけを立てさせたい段は `permission_mode = "plan"`。
- サブエージェントは待つ形（`run_in_background: false` を付ける。付けないと裏で動くので止まる）でしか呼べず、`isolation` も付けられない。1回の実行で呼べるのは `max_agent_calls` 回まで（既定 20。`agents` のある段だけに書ける）。手分けの数が多い段だけ、要る数を `max_agent_calls` に書く。サブエージェントの中からさらにサブエージェントを呼ぶと止まる（Claude Code では既定で呼べるが、pipe-in のガードが止める）。段の指示文にもこの呼び方を書いておくと、止められて呼び直す手間が減る。
- Bash を裏で動かす呼び方（`run_in_background: true`）は、どの段でも止まる。
- 試作・図・下書きなど、成果物のほかに置く場所が要る段は `access = "docs"` と `docs_dir`（要るなら `writes` で絞る）にする。`access = "read"` の段は、Bash でも自分の成果物のほかは書けない。
- `agents` のある段の指示文には、サブエージェントを `run_in_background: false` で呼び、全部返るまで成果物を書かないことを書く（返る前に成果物を書いて終えると、批評や採点が抜ける）。
- テストを書く段（`access = "tests"`）は、あとの段に `check.command` があるなら `bash = true` にして、あとの段の `check.command` と同じ検査（lint・型検査・文書の機械検査など）を自分でも流させる。書いたテストがその検査で落ちると、実装の段が直せずに差し戻しが回る。
- 実装の段（`access = "code"`）の指示文には、テストを Bash でも書き換えないこと（直したいテストは理由を成果物に書く）を書く。決まった形の書き込みはガードが止めるが、スクリプトを流すなどのすり抜けの道は残る。
- 検査（`[stages.check]`）の `on_fail` は、指摘を直せる段（`code`・`tests`・`docs`）に戻す。読むだけの段に戻しても直せない。
- 新しい項目や部品を足す段の指示文には、既定のままなら前と同じ結果になること（新しいキーを false にしたら前とバイト同一など）を確かめさせる。前の結果が変わると、どこで悪くなったかを比べられない。
- Web や MCP は、要る段だけに `web`・`mcp` を書く。`web` はできればドメインの一覧で絞り、MCP は読むだけの道具を選ぶ。MCP を使うなら、対象の `pipeline.toml` の `setting_sources` に設定の出どころが要ることを伝える。
- 会話を挟まずに Claude に段を組ませる `pipe-in-gen design` もあるが、利用料がかかるので、人に言われたときだけ使う（pipe-builder には使わせない）。

## 検査と審査の組み方

`[stages.check]` には、機械で確かめる `command` と、審査役が中身を見る `judge` を書けます。

### 使い分け

| 組み方 | 向くもの |
| --- | --- |
| `command` だけ | 機械で確かめられること（テスト・形の検査） |
| `judge` だけ | 中身の良し悪しの指摘。差し戻さず、指摘だけにする |
| 両方 | 検査で決まりの崩れを拾い、審査で中身を指摘する |

### 決まり

- **合否は検査で決め**、審査は中身の指摘に使う。審査の指摘による書き直しは決まりを崩すことがあり、それを拾えるのは検査（機械のコマンド）だけだから。
- 審査で差し戻す（`on_fail` を書く）ときは、必ず command と組む。組めないなら、`on_fail` を書かず指摘だけにする。`on_fail` を省くと自分の段に戻る点に注意する。`max_retries` は 1〜3 がおすすめ（検査は 0 以上を通す）。
- 審査で合否を出すなら、平均ではなく `must`（違反は即不合格）を使う。1つの `must` に1つの決まりを書く。`description` は審査役が yes / no で答えられる文にする（向きを間違えないよう「（ある＝違反）」のように添える）。
- `criteria` は点数をつける項目。`pipe-in-gen check` が求めるのは1つ以上で、2つ以上が目安。`must` だけでは検査を通らないので、`criteria` を最低1つ書く。平均が `threshold`（0〜1、既定 0.7）に届かなければ不合格。
- `on_fail` は不合格のときに戻す段の名前、`max_retries` は戻す回数の上限（1〜3 がおすすめ。検査は 0 以上を通す）。
- 古い版の pipe-in では `judge` が黙って無視される。`judge` だけだと検証が無いのと同じになる。`verdict`・`command` を併記していれば、審査なしで動く。

### command の書き方

- シェルを通して、対象プロジェクトのフォルダで、`timeout_sec`（既定 600 秒）まで流れる。終了コード 0 で合格。
- `git push`・`curl`・`rm -r`・`sudo` など危ない語は、検査が止める。
- OS をまたいで引用符が壊れないように、外側は**ダブルクォート**、中の文字列は**シングルクォート**にする。バッククォート・`$`・`%`・`!`・`\` を中に書かない（sh ではバッククォートが実行され、cmd.exe では `%` が展開される）。`pipe.toml` には TOML の基本文字列として `\"` で書く。バッククォートが要るときは `chr(96)` で作る。
- `python` が無い・`python3` しか無い環境では動かない。そのときは別のコマンドに書き換える。

### 例

作る段と、`verdict`・`command`・`judge` で確かめる段の組です。

```toml
[pipe]
kind = "linear"
label = "文書を作って確かめる"
description = "文書を書き、テストと審査で確かめる"
input = "optional"

[[stages]]
name = "write"
label = "文書を書く"
output = "01_write.md"
access = "docs"
docs_dir = "docs"
review = true
prompt_file = "prompts/01_write.md"

[[stages]]
name = "verify"
label = "確かめる"
output = "02_verify.md"
access = "read"
bash = true
prompt_file = "prompts/02_verify.md"

[stages.check]
verdict = true
command = "python -m pytest -q"
on_fail = "write"
max_retries = 2

[stages.check.judge]
threshold = 0.7

[[stages.check.judge.criteria]]
name = "網羅"
description = "公開されているものが過不足なく載っている"

[[stages.check.judge.criteria]]
name = "使い方"
description = "使い方の例が、ソースの動きと合っている"

[[stages.check.judge.must]]
name = "根拠のない記述がない"
description = "ソースに根拠のない記述がありますか（ある＝違反）"
```

## 比較実験から分かった組み方の目安

段の組み方を比べた実験（pipe-in の外で行った）から分かったことです。Claude Haiku だけで、生成器で作った課題（方式ごとに 20〜30）で比べた結果で、ほかのモデルや実際のプロジェクトでは確かめていません。上の「段の決め方」の決まりとは分け、目安として使います。くわしい数字は公開リポジトリの https://github.com/nigoh/pipe-in/blob/main/docs/research/harness-compare/README.md にあります（プラグインのフォルダの外なので、入れたプラグインからは読めません。人が見る参考です）。

- **土台は、作る段1つと外の検査。** テストなど外から測れる終わりの条件があれば、作る段に `check.command` を付けて自分へ戻すだけで満点に届く課題が多かった（不具合の修正・素直な仕様の実装では、段を足しても差が出なかった）。段を足すのは、それで足りないと分かってから。
- **指摘を出す段には、指摘ごとに原文の行を逐語で引用させ、機械で照合する。** 原文に無い引用を含む指摘を落とすと、文書レビューで F1 が 0.86 → 0.94 に上がった（費用はほぼ同じ）。設計レビューでは、引用の照合だけでは上がらなかった。照合には `pipe-in-gen findings-check`（指摘の形 v1）を `check.command` に組む（ひな形 `spec-review` の `verify` 段の形）。指摘を出す段に引用の指示も `findings-check` も無いと、`pipe-in-gen check` が警告を出す。
- **指摘の精度を上げる確かめは1つだけにする。** 同じ課題を何回か解かせて多く出た指摘を残す方式に、道具での確かめなどを重ねると、重ねないときより下がった（文書レビュー 30 課題で F1 −0.024）。段の合否を決める `command` と `judge` の組み方（上の節）の話ではない。
- **指摘を探すレビューで、下見（偵察）の点数で調べる範囲を絞らない。** 文書レビューでは効いたが、設計レビューでは悪化した（20 課題で F1 −0.071、2勝15敗）。分野で確かめるまで使わない。
- **テストを書く段と実装の段を分ける。** 同じ段に、実装の前に自分でテストを書かせても効かなかった（自分の読み違いをテストに写すため）。pipe-in の開発フローの「テスト先行」は、別の担当が書き、人が確かめる形なので、これとは条件が違う。

## 流すとき

- 長い段（実装・批評など）は `max_turns` を足りるだけにする（目安 80〜150。実際に流した経験の値）。足りないと、pipe-in はその段を失敗として止める（成果物を書く前に止まることがある）。
- 対象の `pipeline.toml` の `setting_sources` は、段に読ませる設定の範囲を要るものだけに絞る（例：`["project"]`。手元の user の設定に左右されない）。`["project"]` は `.claude/settings.local.json`（local）も読まないので、要るなら `["project", "local"]` にする。
- 段の始めに SDK が応答を待ちきれずに止まる環境では、流すときに環境変数 `CLAUDE_CODE_STREAM_CLOSE_TIMEOUT`（ミリ秒）を長めにする（例：`300000`）。これは Python 版の SDK のコードが読む変数で、公式の文書には載っていない。
- 1回目は `--pause` で流し、段ごとの成果物と止められた操作（`99_summary.md`）を見てから、指示文を直す。止められた操作が多い段は、`access`・`writes`・`bash` か指示文が合っていない。
