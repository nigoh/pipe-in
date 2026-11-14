# pipe-in plugin

Build, run, check, and watch pipe-in pipelines from a Claude Code conversation. / pipe-in のパイプを、Claude Code の会話で作る・流す・検査する・見るためのプラグインです。

## English

pipe-in runs a development flow (requirements, design, tests, implementation, verification) and your own pipelines with the Claude Agent SDK. This plugin lets you build and fix those pipelines in a conversation, run them where the SDK cannot start, check and judge their output, and watch a terminal run in a Claude artifact. The plugin itself is only prompts and one hook definition; the real work is done by the `pipe-in-gen` command, which you install separately.

### Install

In a conversation (Claude Code v2.1.275 or later):

```
/plugin install pipe-in --marketplace nigoh/pipe-in
```

Claude Code asks you to confirm the new marketplace and to choose where to install it (the scope). In a shell (v2.1.292 or later): `claude plugin install pipe-in --marketplace nigoh/pipe-in`. On older versions, use two steps: `claude plugin marketplace add nigoh/pipe-in`, then `claude plugin install pipe-in@pipe-in` in a shell, or `/plugin marketplace add nigoh/pipe-in`, then `/plugin install pipe-in@pipe-in` in a conversation.

Then install `pipe-in-gen`. It is not bundled, because the guard hook and the commands run as ordinary Python programs on your machine. `pip install -e .` installs both commands, `pipe-in-gen` and `pipe-in`:

```
git clone https://github.com/nigoh/pipe-in.git
cd pipe-in
pip install -e .
pipe-in-gen --help
```

If `pipe-in-gen --help` prints the command list, you are ready. Without `pipe-in-gen` on your PATH the hook cannot start: the write limits described below do not apply, and Claude Code may show a hook error notice on every tool call. If you see that notice, check that `pipe-in-gen --help` works.

### What's included

| Skill | What it does |
| --- | --- |
| `/pipe-in:pipe-build` | Asks what you want, shows a table of stages for approval, then has the builder write the pipe and checks it. |
| `/pipe-in:pipe-eval` | Runs the check commands of a finished pipe and returns a pass or fail for each. |
| `/pipe-in:pipe-judge` | Scores an output against a rubric. The score math is done by a command. |
| `/pipe-in:pipe-live` | Shows the progress of a pipe-in run in a terminal as a Claude artifact. Watch only. |
| `/pipe-in:pipe-run` | Runs a pipe inside the conversation, for places where the SDK cannot start. |

| Agent | What it does |
| --- | --- |
| `pipe-builder` | Writes the pipe files. It may write only the fixed files of the pipe folder. |
| `pipe-judge` | Scores with read-only tools. |
| `pipe-stage` | Does one stage of a pipe for `pipe-run`. |
| `pipe-probe` | Tries one forbidden write before a run, to confirm the guard works. |

The plugin also ships one hook (a PreToolUse hook) that narrows what these agents may do.

### What it runs, sends, and fetches

What it runs. Before every tool call, the hook starts `pipe-in-gen guard-hook` (no shell is used). It allows or blocks the call and does nothing else. The skills and agents run these commands on your machine: `pipe-in-gen list`, `pipe-in-gen new`, `pipe-in-gen design`, `pipe-in-gen check`, `pipe-in-gen judge-score`, `pipe-in-gen chat`, and `pipe-in live page` and `pipe-in live watch`. The pipe guide also mentions `pipe-in-gen findings-check` and `pipe-in-gen quorum`. `/pipe-in:pipe-eval` runs the check commands written in the pipe or given by you, only after you answer yes.

What it sends. The plugin itself sends nothing to the author or to any third-party server. Records stay in your project. The check commands that `/pipe-in:pipe-eval` runs, and the shell commands of a stage, are whatever your pipe definition says; what they send depends on that definition. Only `/pipe-in:pipe-live`, and only when you call it, writes a copy of the run progress to the data store of a claude.ai artifact (`ArtifactData`), through the Artifact and Monitor tools of Claude Code. It uses no other service.

What it fetches. It does not use `WebFetch` or `WebSearch`. The only link in the skills (github.com/nigoh/pipe-in, in the install steps) is for people and is not opened by the plugin. Pipes you build may allow web access in a stage, but only if you ask for it.

Cost. Stages run by `pipe-run`, the builder, and the judge use your Claude usage. `pipe-eval`, `pipe-live`, and the hook do not start pipe-in stages.

### Where it works

Skills load in claude.ai chat, Cowork, and Claude Code. Agents and hooks are ignored in chat. `/pipe-in:pipe-build`, `/pipe-in:pipe-judge`, and `/pipe-in:pipe-run` need `pipe-in-gen`; `/pipe-in:pipe-live` needs `pipe-in`; `/pipe-in:pipe-eval` needs neither. The guard hook needs `pipe-in-gen` for every tool call. So the plugin works properly only in Claude Code with both commands installed. `/pipe-in:pipe-live` also needs a Claude Code signed in to claude.ai, with the Artifact, `ArtifactData`, and Monitor tools.

More: https://github.com/nigoh/pipe-in (guide: docs/guide/plugin.md).

## 日本語

pipe-in は、要件定義・設計・テスト先行・実装・検証の開発フローや、自分で作ったパイプを、Claude Agent SDK で順に流す道具です。このプラグインを入れると、会話の中でパイプを作る・直す、SDK を起こせない場所でパイプを流す、成果物を検査・審査する、ターミナルの実行の進み具合を Claude のアーティファクトで見る、ことができます。プラグイン自身は文書とフックの定義だけで、実際の仕事は別に入れる `pipe-in-gen` コマンドがします。

### 入れ方

会話の中で（Claude Code v2.1.275 以降）：

```
/plugin install pipe-in --marketplace nigoh/pipe-in
```

新しいマーケットプレイスの確認と、入れる範囲（scope）の選択が出ます。シェルでは `claude plugin install pipe-in --marketplace nigoh/pipe-in`（v2.1.292 以降）。それより前の版では2段で入れます：シェルなら `claude plugin marketplace add nigoh/pipe-in` のあと `claude plugin install pipe-in@pipe-in`、会話の中なら `/plugin marketplace add nigoh/pipe-in` のあと `/plugin install pipe-in@pipe-in`。

そのあと `pipe-in-gen` を入れます。守りのフックとコマンドは手元の Python のプログラムなので、プラグインには入っていません。`pip install -e .` で、`pipe-in-gen` と `pipe-in` の2つのコマンドが入ります。

```
git clone https://github.com/nigoh/pipe-in.git
cd pipe-in
pip install -e .
pipe-in-gen --help
```

`pipe-in-gen --help` でコマンドの一覧が出れば準備完了です。PATH に `pipe-in-gen` が無いと、フックが起動できず、下の書き込みの制限が効きません。道具を呼ぶたびに、フックのエラーの知らせが出ることもあります。出たら `pipe-in-gen --help` が動くかを確かめてください。

### 入るもの

| スキル | すること |
| --- | --- |
| `/pipe-in:pipe-build` | 目的を聞き、段の表を見せて確認を取り、エージェントにパイプを書かせて検査する |
| `/pipe-in:pipe-eval` | 流し終えたパイプの検査のコマンドを流し、項目ごとの合否を返す |
| `/pipe-in:pipe-judge` | 成果物をルーブリックに照らして審査する。点の計算はコマンドがする |
| `/pipe-in:pipe-live` | ターミナルで流している pipe-in の進み具合を、アーティファクトで見る。見るだけ |
| `/pipe-in:pipe-run` | SDK を起こせない場所で、パイプを会話の中で流す |

| エージェント | すること |
| --- | --- |
| `pipe-builder` | パイプのファイルを書く。書けるのは、パイプのフォルダの決まったファイルだけ |
| `pipe-judge` | 読む道具だけで採点する |
| `pipe-stage` | `pipe-run` から呼ばれ、パイプの段を1つ受け持つ |
| `pipe-probe` | 流す前に、範囲外への書き込みを1回だけ試して、守りが効くか確かめる |

ほかにフック（PreToolUse）が1つ入り、これらのエージェントができることを絞ります。

### 動かすもの・送るもの・取ってくるもの

動かすもの。道具を呼ぶたびに、フックが `pipe-in-gen guard-hook` を起こします（シェルは通しません）。通すか止めるかを答えるだけで、ほかのことはしません。スキルとエージェントは、手元で次のコマンドを流します：`pipe-in-gen list`・`pipe-in-gen new`・`pipe-in-gen design`・`pipe-in-gen check`・`pipe-in-gen judge-score`・`pipe-in-gen chat`、そして `pipe-in live page` と `pipe-in live watch`。パイプの説明には `pipe-in-gen findings-check` と `pipe-in-gen quorum` も出てきます。`/pipe-in:pipe-eval` は、パイプに書かれた、または渡した検査のコマンドを、答えを待ってから流します。

送るもの。プラグイン自身は、作者や第三者のサーバーへ何も送りません。記録は利用者のプロジェクトの中に残ります。`/pipe-in:pipe-eval` が流す検査のコマンドと、段の中のシェルのコマンドは、利用者のパイプの定義のとおりに動くので、何を送るかはその定義によります。人が `/pipe-in:pipe-live` を呼んだときだけ、Claude Code の Artifact と Monitor の道具で、進み具合の写しを claude.ai のアーティファクトのデータ（`ArtifactData`）に書きます。ほかのサービスは使いません。

取ってくるもの。`WebFetch` も `WebSearch` も使いません。スキルの中のリンクは入れ方の github.com/nigoh/pipe-in だけで、人が読むための案内です。プラグインは開きません。作るパイプの段で Web を許すのは、頼んだときだけです。

利用料。`pipe-run` の段・作る役・審査役は、Claude の利用料がかかります。`pipe-eval`・`pipe-live`・フックは、pipe-in の段を流しません。

### 使える場所

スキルは claude.ai のチャット・Cowork・Claude Code で読み込まれます。エージェントとフックはチャットでは無視されます。`/pipe-in:pipe-build`・`/pipe-in:pipe-judge`・`/pipe-in:pipe-run` は `pipe-in-gen` が、`/pipe-in:pipe-live` は `pipe-in` が要り、`/pipe-in:pipe-eval` はどちらも要りません。守りのフックは、道具を呼ぶたびに `pipe-in-gen` を使います。そのため、ちゃんと使えるのは2つのコマンドを入れた Claude Code です。`/pipe-in:pipe-live` は、claude.ai にログインした Claude Code と、Artifact・`ArtifactData`・Monitor の道具も要ります。

くわしくは https://github.com/nigoh/pipe-in（ガイド：docs/guide/plugin.md）にあります。
