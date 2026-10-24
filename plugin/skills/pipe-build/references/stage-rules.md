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
- サブエージェントは待つ形（`run_in_background: false` を付ける。付けないと裏で動くので止まる）でしか呼べず、`isolation` も付けられない。1回の実行で呼べるのは `max_agent_calls` 回まで（既定 20。`agents` のある段だけに書ける）。手分けの数が多い段だけ、要る数を `max_agent_calls` に書く。サブエージェントの中からさらにサブエージェントは呼べない。段の指示文にもこの呼び方を書いておくと、止められて呼び直す手間が減る。
- Bash を裏で動かす呼び方（`run_in_background: true`）は、どの段でも止まる。
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
