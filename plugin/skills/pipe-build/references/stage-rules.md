# 段の決め方と、検査と審査の組み方

## 段の決め方

- `access` は目的を満たすいちばん狭い型（文書だけなら `read`）。書く場所が決まっていれば `writes` で絞る。
- `bash = true` はテストの実行など必要な段だけ。
- 方針が決まる段・最終の成果物など、人が確かめるべき段に `review = true`。
- 図は Mermaid で書かせる。
- 確かめる段に `[stages.check]`（`verdict = true` で判定、`on_fail` で直す段へ戻す。テストで確かめられるなら `command`）。
- 道が分かれるなら `[stages.routes]`、分岐先の最後に `next`。独立した段は `group` で同時に流す。
- 段の中の手分けは `[stages.agents.<名前>]`。方針だけを立てる段は `permission_mode = "plan"`。
- サブエージェントは待つ形（`run_in_background: false`）でしか呼べず、`isolation` も付けられない。呼べるのは `max_agent_calls` 回まで（既定 20。`agents` のある段だけ）で、多い段だけ要る数を書く。サブエージェントの中からさらにサブエージェントを呼ぶと止まる。`agents` のある段の指示文にも、この呼び方と、全部返るまで成果物を書かないことを書く。
- `run_in_background: true` の Bash は、どの段でも止まる。
- 成果物のほかに置き場所が要る段は `access = "docs"` と `docs_dir`。`access = "read"` の段は、Bash でも成果物のほかは書けない。
- テストを書く段（`access = "tests"`）は、あとに `check.command` があれば `bash = true` にして、同じ検査を流させる。
- 実装の段（`access = "code"`）の指示文に、テストを Bash でも書き換えない（直したいテストは理由を成果物に書く）と書く。
- `on_fail` は直せる段（`code`・`tests`・`docs`）に戻す。
- 新しい項目や部品を足す段には、既定のままなら前と同じ結果になることを確かめさせる。
- `web`・`mcp` は要る段だけ。`web` はできればドメインの一覧で絞り、MCP は読むだけの道具を選ぶ。MCP なら、対象の `pipeline.toml` の `setting_sources` に出どころが要ると伝える。
- `pipe-in-gen design` は人に言われたときだけ使う（利用料がかかる。pipe-builder には使わせない）。

## 名前の決まり

- 指示文（`prompts/`）と成果物（`output`）の名前の頭に、段の順の 2 桁の番号と `_` を付ける（例 `prompts/01_summary.md`・`01_summary.md`）。
- 段の `agents` に書かせるファイルと、`/pipe-in:pipe-run`（会話の中）で流すパイプで指示文が書かせるファイルも、`report`・`summary`・`findings`・`analysis` で始まる `.md` にしない（大文字と小文字は区別されない）。端末の `pipe-in` だけで流すパイプで、段が自分で書くファイルは当たらない。
- 理由：Claude Code は、サブエージェントからのその名前の書き込みを断る。pipe-builder 自身もサブエージェントなので、`prompts/summary.md` は書けない。
- 名前に段の名前まで入れなくてよい。

## 検査と審査の組み方

`[stages.check]` には、機械で確かめる `command` と、審査役が中身を見る `judge` を書ける。

- 合否は検査で決め、審査は中身の指摘に使う。審査の指摘による書き直しは決まりを崩すことがあり、拾えるのは検査だけだから。
- 審査で差し戻す（`on_fail` を書く）なら、必ず command と組む。組めないなら `on_fail` を書かず指摘だけにする（`on_fail` を省くと自分の段に戻る。審査に落ちると自分の段をやり直す）。
- 審査で合否を出すなら、平均でなく `must`（違反は即不合格）を使う。1つの `must` に1つの決まり。`description` は yes / no で答えられる文にし、「（ある＝違反）」のように向きを添える。
- `criteria` は点を付ける項目で、1つ以上要る（`must` だけでは `pipe-in-gen check` を通らない。2つ以上が目安）。平均が `threshold`（0〜1、既定 0.7）に届かなければ不合格。
- `on_fail` は戻す段の名前、`max_retries` は戻す回数の上限（1〜3 がおすすめ。検査は 0 以上を通す）。
- 古い版の pipe-in では `judge` が黙って無視される。`judge` だけだと検証が無いのと同じになる。`verdict`・`command` を併記していれば、審査なしで動く。

### command の書き方

- シェルを通して対象のフォルダで `timeout_sec`（既定 600 秒）まで流れ、終了コード 0 で合格。
- `git push`・`curl`・`rm -r`・`sudo` など危ない語は検査が止める。
- 外側はダブルクォート、中はシングルクォート。バッククォート・`$`・`%`・`!`・`\` を中に書かない。`pipe.toml` では `\"` で書き、バッククォートは `chr(96)` で作る。
- `python` が無い・`python3` しか無い環境では、別のコマンドに書き換える。

### 例（作る段と、`verdict`・`command`・`judge` で確かめる段）

```toml
[pipe]
kind = "linear"
label = "文書を作って確かめる"

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

Claude Haiku だけで比べた目安で、ほかのモデルや実際のプロジェクトでは確かめていない。上の決まりとは分けて使う。

- 土台は作る段1つと外の検査（作る段に `check.command` を付けて自分へ戻す）。段を足すのは、それで足りないと分かってから。
- 指摘を出す段には原文の行を逐語で引用させ、`pipe-in-gen findings-check` を `check.command` に組む（ひな形 `spec-review` の `verify` 段の形）。
- 指摘の精度を上げる確かめは1つだけ。段の合否を決める `command` と `judge` の組み方（上の節）の話ではない。
- Haiku で指摘を挙げるなら、2体の共通部分の方式がある。同じ指示の2体を同時に流し、両方が同じ節に挙げた指摘だけを残す（`pipe-in-gen quorum`、ひな形 `review-quorum`）。強いモデル・読み方を変えた2体・1体で解ける課題には使わない。割れた指摘の裁定は足していない。数字は事後の解析。
- 指摘を探すレビューで、下見の点数で調べる範囲を絞らない。
- テストを書く段と実装の段を分ける（pipe-in の開発フローのテスト先行は、別の担当が書いて人が確かめる形で、条件が違う）。

## 流すとき

- 長い段は `max_turns` を足りるだけ（目安 80〜150）。足りないと、pipe-in はその段を失敗で止める。
- 対象の `pipeline.toml` の `setting_sources` は要るものだけ（例 `["project"]`。local も要るなら `["project", "local"]`）。
- 段の始めに SDK が応答を待ちきれずに止まる環境では、環境変数 `CLAUDE_CODE_STREAM_CLOSE_TIMEOUT`（ミリ秒。例 `300000`）を長めにする。
- 1回目は `--pause` で流し、成果物と止められた操作（`99_summary.md`）を見てから、指示文を直す。止められた操作が多い段は、`access`・`writes`・`bash` か指示文が合っていない。
