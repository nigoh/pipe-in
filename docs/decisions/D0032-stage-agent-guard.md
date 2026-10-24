# D0032 段の中のサブエージェントの呼び方を守る（裏で動かす形・入れ子を止め、1回の実行で呼べる数に上限 `max_agent_calls`、既定 20）

## 目的

パイプの段がサブエージェントを「裏で動かす」形で呼んで、結果を待てずに段が失敗することを、パイプの指示文に頼らずガードで防ぐ。
あわせて、1つの段の中でサブエージェントを呼ぶ回数に上限を設け、サブエージェントの呼び出しが回り続けないこと（無限ループにならないこと）を仕組みで約束する。

## 機能要件と受け入れ基準

- FR-01 段の中で `Agent` か `Task` を、`run_in_background` を付けて（値が `false` 以外で）呼ぶと、ガードが止める。理由の文に「`run_in_background: false` で呼び直してください」を入れる。
  - D0032-AC-01 `Agent` に `run_in_background: True` を渡すと理由を返し、その文に `run_in_background: false` が入る。SDK に渡すサブエージェントは `background` を持たない（`tests/test_agent_guard.py::test_d0032_ac01_*`・`test_d0032_sdk_options*`）。
  - D0032-AC-02 `Task` に `run_in_background: True` を渡すと理由を返す（`test_d0032_ac02_*`）。
  - D0032-AC-03 `run_in_background` が `"true"`・`"false"`・`1`・`0`・`None`・`[]`・`{}` のときも止まる。`tool_input` が表でないときも止まる（`test_d0032_ac03_*`・`test_d0032_tool_inputが表でない*`）。
- FR-02 `Bash` も `run_in_background` を付けて呼ぶと止める。理由の文に「`run_in_background` を付けずに呼び直してください」を入れる。
  - D0032-AC-04 `Bash` の `ls` に `True`・`"true"`・`None`・`1` を付けると止まり、理由に「run_in_background を付けずに」が入る（`test_d0032_ac04_*`）。
- FR-03 `Agent`・`Task` は `run_in_background: false`（真偽値）の呼び出しだけを通す。`Bash` は書かない呼び出しと `false` を、今までどおり通す。（監査と助言のあとに直した。はじめは `Agent`・`Task` も「書かない」を通していた。）
  - D0032-AC-10 `Agent`・`Task` は、`False` で上限まで通る（`test_d0032_ac10_*`）。
  - D0032-AC-11 `Bash` は、キーなし・`False` で今までどおり危ないコマンドの判定だけが掛かる（`test_d0032_ac11_*`）。
  - D0032-AC-12 `agents` の無い段では、待つ形・裏の形のどちらも「この段では Agent を使えません」（`Task` も同じ）で、数えるより前に止まる（`test_d0032_ac12_*`）。
- FR-04・FR-05 段の1回の実行の中で、ガードを通った `Agent`・`Task` を合わせて数え、上限（既定 20。`pipe.toml` の `[[stages]]` の `max_agent_calls`）に達したあとは止める。理由の文に上限の数と「これまでに返った結果で成果物を書いてください」を入れる。
  - D0032-AC-05 上限 3 で 4 回目が deny になり、理由に 3 が入る。`Agent` と `Task` を混ぜても合わせて数える。1つの応答で 25 個を並べて渡しても、上限 20 なら通るのはちょうど 20（`test_d0032_ac05_*`・`test_d0032_並べて呼んでも*`）。
  - D0032-AC-06 上限を超えたあとは何度呼んでも deny のまま。上限が 1 未満・真偽値・`None`・文字のガードは作れない（`ValueError`）（`test_d0032_ac06_*`・`test_d0032_make_guard_hookは*`）。
  - D0032-AC-15 `max_agent_calls` を書かない段の上限は 20（`test_d0032_ac15_*`）。
  - D0032-AC-16 `max_agent_calls = 5` の段は上限 5 で、その段のガードは 6 回目を止める。ガイドの書き方の例に `max_agent_calls` の行がある（`test_d0032_ac16_*`・`tests/test_guide.py::test_D0032_AC_16_*`）。
- FR-06 数えるのは段の1回の実行ごと。止めた呼び出しは数えない。
  - D0032-AC-07 裏で動かす形・入れ子で止めた呼び出しは数に入らない（`test_d0032_ac07_*`）。
  - D0032-AC-13 別々に作った2つのガードは数を分け合わない。本物の経路（`run_stage_sdk`）も `stage_guard` で段の実行ごとにガードを作る（`test_d0032_ac13_*`・`test_d0032_run_stage_sdkは*`）。
  - D0032-AC-14 差し戻しでやり直した段のガードは 0 から数え、差し戻しが続いても段を流す回数は `check.max_retries` で止まる（`tests/test_pipe_flow.py::test_d0032_ac14_*`）。
- FR-07 上限で止めたことは、ほかの止めた操作と同じく `StageRun.denials` に残る。段は失敗にしない。
  - D0032-AC-09 上限で止めると `on_deny` が呼ばれ、`"Agent: <理由>"` の形で残り、上限の数が入る（`test_d0032_ac09_*`）。
- FR-08 サブエージェントの中からの `Agent`・`Task`（入れ子）は止める。見分けがつかない呼び出しは段の呼び出しとして数える。
  - D0032-AC-08 フックの入力に `agent_id` があれば（値は問わない）、上限に余りがあっても止まる。`agent_type` だけの呼び出しは入れ子とみなさず数える。サブエージェントの中の `Read` は通る。安全の文書に、裏で動かす形・上限・入れ子を止めることが書いてある（`test_d0032_ac08_*`・`tests/test_guide.py::test_D0032_AC_01_05_08_*`）。
- FR-09 定義の検査（`check_pipe`）は、`max_agent_calls` が 1 以上の整数でないとき、または `agents` の無い段に書いたときに誤りにする。
  - D0032-AC-17 `0`・`-1`・`"5"`・`true`・`1.5` のとき「max_agent_calls は 1 以上の整数で書いてください」（`test_d0032_ac17_*`）。
  - D0032-AC-18 `agents` の無い段の `max_agent_calls` は誤り（`test_d0032_ac18_*`）。
- FR-10 `agents` のある段の system prompt に、`Agent`・`Task` は `run_in_background: false` を付けて呼ぶことと上限の数を入れる（`Bash` の行は「`run_in_background` を付けずに」）。
  - D0032-AC-19 `agents` のある段の `system_append` に `run_in_background` と「<上限> 回まで」が入る。`agents` の無い段には入らない（`test_d0032_ac19_*`）。
- FR-11 `Agent`・`Task` を `run_in_background` を書かずに呼ぶと止める。メインから呼ぶと、書かないときは裏で動くため（公式の文書 https://code.claude.com/docs/en/agent-sdk/python の Agent の入力「Default when omitted: your main agent's call runs the new agent in the background」）。
  - D0032-AC-22 書かない `Agent`・`Task` は「run_in_background: false を付けて呼び直してください」で止まり、数に入らない。`Bash` は書かなくても通る（`test_d0032_ac22_*`）。
  - D0032-AC-23 `agents` のある段の system prompt は `run_in_background: false` を付けて呼ぶように書く（`test_d0032_ac23_*`）。
- FR-12 `tool_input` が表でないとき（`[]`・`""`・`None`・`"x"`・`["x"]`）は、`Agent`・`Task`・`Bash` とも、本物のガードの経路で止め、数に入れない。`tool_input` のキーが無いときは `Agent`・`Task` を止め、ほかは今のまま。
  - D0032-AC-24 表でない値のとき止まり、数に入らない（`test_d0032_ac24_*`）。
  - D0032-AC-25 キーが無いとき `Agent`・`Task` は止まり、`Read`・`Bash` は今までどおり（`test_d0032_ac25_*`）。
- FR-13 段の SDK の options の `env` に `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` と `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1` を必ず入れる。手元の環境変数に別の値があっても上書きされない。
  - D0032-AC-26 `sdk_options` と `ClaudeAgentOptions` の `env` に2つが "1" で入る（`test_d0032_ac26_*`）。
- FR-14 段の `agents` から作るサブエージェントには `disallowedTools = ["Agent", "Task"]` を渡す。
  - D0032-AC-27 サブエージェントの dict と `AgentDefinition` に `disallowedTools` が入る（`test_d0032_ac27_*`・`tests/test_pipe_sdk.py::test_sdk_options_from_spec`）。
- FR-15 `Agent`・`Task` の `isolation` は書かないときだけ通す。値があれば（`None` も）止める。
  - D0032-AC-28 `worktree`・`remote`・`None` などで止まり、理由に `isolation` が入る（`test_d0032_ac28_*`）。
- 古い形
  - D0032-AC-20 `max_agent_calls` の無い前からの `pipe.toml`（`pipe-in-` の頭も前の版の頭も）は、検査を今までどおり通り、上限は 20。記録の形は変わらない（`test_d0032_ac20_*` と、通ったままの `tests/test_showcase.py`・`tests/test_pipeline.py`）。
  - D0032-AC-21 開発フローの段は `Agent`・`Task` を今までどおり止める（`test_d0032_ac21_*`）。

## 決めたことと理由

### 聞かずに決め、推しで確定したこと

- `run_in_background` が `None`（JSON の null）でも止める。許すのは「書かない」と `false`（真偽値）の2つだけ（許すものの一覧の決まり）。選ばなかった形：`None` を書かないのと同じに通す。
- 上限を変える場所は `pipe.toml` の `[[stages]]` の `max_agent_calls` だけ。何体のサブエージェントを呼ぶかはパイプの作りで決まるので、パイプに書く。選ばなかった形：`pipeline.toml` の `[stages.<段>]` でも上書きする（置き場所が2つになる）。
- 既定の上限は 20。審査役を何体か呼び、呼び直しを入れても足り、`max_turns`（既定 100）より十分小さい。選ばなかった形：10。
- 上限を超えたら、止めて理由を返すだけ。段は失敗にしない。手元の結果で成果物を書けるので、途中まで書けたものを捨てない。止めたあとも呼び続けると、すべて止まり、最後は `max_turns` で段の実行が終わる。選ばなかった形：段を失敗にする。
- `Bash` の `run_in_background` も止める。段の応答が終わると結果を待てない点は同じで、裏で動いたコマンドが段のあとに残るのも防げる。止める範囲を広げるので安全側。
- 入れ子は、PreToolUse のフックの入力の `agent_id` で見分ける。入っている SDK（`claude-agent-sdk` 0.2.165）の `PreToolUseHookInput` の型の説明に、「`agent_id` は Task で作ったサブエージェントの中からフックが動いたときだけ入る」とある。`agent_type` は `--agent` で始めたセッションのメインのスレッドにも入るので、印にしない。
- `AgentDefinition` に `disallowedTools = ["Agent", "Task"]` を渡す（監査と助言のあとに直した。この項目は SDK 0.1.51 からあり、依存の下限 0.2.159 にもある）。ガードの `agent_id` と数の上限に重ねて、SDK の側でも入れ子を切る。`background`（いつも裏で動かす）は渡さない（テストで押さえる）。
- 段の SDK に `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` と `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1` を渡す。`Bash` は時間切れのコマンドを裏に回すことがあり、これはフックでは止められないため。最低の版の SDK・CLI でこの2つが効くかは、まだ確かめていない（効かなくてもガードと上限は残る）。
- `agent_id` は、同じプロセスで動くチームの仲間の呼び出しにも入る。段はチームを使わないので、それも止めてよい。
- VSCode の作業台は触らない。作業台は段の知らない項目を持たないので、開いて保存すると `max_agent_calls` が消え、上限は既定の 20 に戻る。上限が無くなるわけではないので安全側は保たれる。ガイドに書いた。

### 作り

- `pipe_in/engine/guard.py`：`check_tool` に、裏で動かす形を止める判定（`_foreground`。許すものの一覧の形）を足した。`allowed_tools` の検査のあとに置くので、`agents` の無い段は今までどおり「この段では Agent を使えません」で止まる。表でない `tool_input` は読めない入力として止め、落ちないようにした。`check_agent_call` が入れ子と上限を見る。
- `make_guard_hook` に `max_agent_calls`（既定 20）を足した。1 以上の整数でないと `ValueError` にし、上限の無いガードを作れないようにした。数はガードを作るたびに作る閉じた変数に持ち（ガードを作る単位 ＝ 数える単位）、外から触れない。確かめてから数えるまでのあいだに `await` を置かないので、1つの応答で並べて呼ばれても上限を超えない。
- `pipe_in/engine/runner.py`：段のガードを作る所を `stage_guard(spec, cfg, on_deny)` に分け、`run_stage_sdk` はそれを使う。偽の runner も同じガードを作れる。
- `pipe_in/engine/spec.py`：`StageSpec.max_agent_calls`（既定 20）。
- `pipe_in/pipe/definition.py`：`max_agent_calls` の読み込みと検査。`pipe_in/pipe/specs.py`：上限を段の設定に渡し、`agents` のある段の system prompt に「サブエージェントの呼び方」を足す（`bash = true` の段には Bash の行も）。

### 呼び出しの総数が有限になること

N は段の `max_agent_calls`（1 以上。既定 20）。

| 道 | 上を押さえるもの | 1回の実行で通るサブエージェントの数 |
| --- | --- | --- |
| 段が待つ形で呼ぶ | ガードの数（通すたびに +1、`used >= N` で止める） | N まで |
| 上限を超えたあとも呼び続ける | 止めた呼び出しはサブエージェントを作らない。数は減らず、数え直す道も無い。最後は `max_turns` で段の実行が終わる | 0（増えない） |
| 裏で動かす形で呼ぶ | `check_tool` が止める | 0 |
| サブエージェントの中から呼ぶ（印あり） | `agent_id` で止める | 0 |
| サブエージェントの中から呼ぶ（印なし） | 段の呼び出しとして同じ数に入る | 段の分と合わせて N まで |
| 1つの応答で並べて呼ぶ | 確かめてから数えるまでに `await` が無い | N まで |
| `background = true` のサブエージェント | `AgentDefinition` に `background` を渡さない | — |

パイプ全体では、段の実行の回数は `[pipe]` の `max_steps`（既定 50）・`check.max_retries`・人の指摘の回数で押さえられるので、1回の `pipe-in` の実行で通るサブエージェントは多くても N ×（それらの合計）で、有限。サブエージェントの中からさらにサブエージェントは増えないので、枝分かれして増え続けることも無い。

### 互換

- `pipe.toml` の `[[stages]]` に省ける項目 `max_agent_calls` を足しただけ。無ければ 20 として読む（`docs/development/design.md` の「形を変えるとき（互換）」）。
- `state.json`・`99_summary.md`・`logs/*.jsonl`・終了コード・`pipeline.toml`・置き場所は変えない。上限で止めたものは、今の「止めた操作」に入るだけ。
- 古い版の pipe-in は `max_agent_calls` を知らないキーとして黙って無視する（古い版には上限が無い。今と同じ）。
- 止める範囲を広げるだけで、許していたもので止めなくなるものは無い。依存は足さない。

### 受け入れたリスク

- `agent_id` が来ない SDK・CLI の組み合わせでは、入れ子を見分けられない。その呼び出しは段の呼び出しとして数えるので、上限は破れない。
- 作業台で保存すると `max_agent_calls` が消える。既定の 20 で止まるので、無限ループにはならない。

## 対象外・残った課題

- `.claude/hooks/pipe_in_guard.py` と `generator/guard_hook.py` は変えない。
- VSCode の拡張（作業台で `max_agent_calls` を読み書きすること）。後の作業にする。
- `pipeline.toml` から `max_agent_calls` を上書きすること、パイプ全体での上限、サブエージェント1体のターン数・費用の上限、`max_turns` の既定の見直し。

## 番号

D0022 が予約した D0023〜D0025 とは重ならない（D0031 は main の live-watch が使ったので、D0032 にした）。

## 確かめたこと

- `tests/test_agent_guard.py`・`tests/test_pipe_flow.py`・`tests/test_guide.py` の D0032 のテストと、全体のテストが通った（SDK は呼ばない）。
- 実機の SDK で、裏で動かす形の呼び出しと入れ子の呼び出しが止まるかは、まだ確かめていない。
- 公式の文書（https://code.claude.com/docs/en/agent-sdk/hooks・https://code.claude.com/docs/en/agent-sdk/python）と照らした。`run_in_background` を書かないときにメインからは裏で動くこと、`agent_id` がサブエージェントとチームの仲間の中で入ることは、文書のとおり。

## 監査と助言

検証で合格したあと、矛盾監査（A-01〜A-05）と公式の文書と照らした助言（V-01〜V-08）を流した。助言の報告の審査は総合 0.85 で合格。人が「全部直す」を選んだ。
- コードで直した：V-01（書かない `Agent`・`Task` を止める）、A-01・A-02（表でない `tool_input` を本物の経路で止める）、V-02・V-05（環境変数）、V-04（`disallowedTools`）、V-07（`isolation`）。テストは D0032-AC-22〜28。
- 文書で直した：A-03（`Bash` の裏で動かす形はどの段でも止める）、A-04（呼び直しの書き方をそろえた。プラグインの pipe-build も）、A-05（安全の文書に `Agent`・`Task`）、V-03（時間切れの `Bash` は環境変数で切る）、V-06（チームの仲間にも `agent_id`）、V-08（出典の URL）。
