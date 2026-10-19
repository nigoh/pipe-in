# pipe-in を開発する

[ガイドの目次](README.md) · [README](../../README.md) — pipe-in そのものを直す・機能を足すときの説明です。

## 中身を直したいとき

| やりたいこと | 場所 |
|---|---|
| 開発フローの各段への指示（文書の構成、守ること） | `pipe_in/dev/prompts/*.md` |
| 開発フローの段の順番、確認、差し戻しの流れ | `pipe_in/dev/pipeline.py` |
| 開発フローの段ごとのツールと書き込み範囲 | `pipe_in/dev/specs.py` |
| どのパイプにも共通の流れ（記録・確認・まとめ） | `pipe_in/engine/pipeline.py` |
| 止める操作 | `pipe_in/engine/guard.py` の `DANGEROUS_BASH` |
| SDK の呼び出し | `pipe_in/engine/runner.py` |
| パイプの読み込み・検査・流れ・権限の型 | `pipe_in/pipe/` |
| パイプの生成・環境の検出・ひな形 | `generator/`（`pipe-in-gen`）・`generator/templates/` |

```bash
# テストを流す（SDK を呼ばずに、段の順番・確認・差し戻し・書き込み制限を確かめる）
pip install -e '.[dev]' && pytest
```

直す・機能を足すときの決まり（原則・仕様の書き方・設計・テスト・進め方）は [docs/development/](../development/) に、機能ごとに何をなぜ決めたかは [docs/decisions/](../decisions/) にあります。README とガイドの画像の撮り直し方は [docs/assets/README.md](../assets/README.md) にあります。

## Claude Code で開発するとき

このリポジトリの開発用スキル `/pipe-audit`（文書・定義・コードの食い違いの監査）と `/pipe-advise`（公式の文書と照らした助言）は、会話を開かずに `claude -p` でも流せます。プロンプトの先頭を `/pipe-audit` か `/pipe-advise` にして、このリポジトリ（または worktree）の中で呼びます。

```bash
claude -p "/pipe-audit <範囲>" --max-budget-usd 5 --permission-mode dontAsk --tools "Agent,Read,Grep,Glob" --allowedTools "Agent(pipe-in-auditor)" Read Grep Glob
claude -p "/pipe-advise <テーマ>" --max-budget-usd 5 --permission-mode dontAsk --tools "Agent,Read,Grep,Glob,WebFetch,WebSearch" --allowedTools "Agent(pipe-in-advisor)" Read Grep Glob WebSearch "WebFetch(domain:code.claude.com)" "WebFetch(domain:docs.claude.com)" "WebFetch(domain:docs.anthropic.com)" "WebFetch(domain:platform.claude.com)" "WebFetch(domain:github.com)" "WebFetch(domain:raw.githubusercontent.com)"
```

- 読むだけに絞るのは `--tools` です。使える組み込みの道具そのものを絞るので、Bash・Write・Edit などは出てきません。`Read Grep Glob` を `--allowedTools` にも書くのは、Linux・macOS では Glob と Grep が初めの道具に入らず、名前を書くと戻るためです。
- `--allowedTools` は「確認なしで通す」許可で、制限ではありません。`--permission-mode dontAsk` が断るのは、確認が要る呼び出しのうち許可に当たらないものです（許可に無い道具を全部断るわけではありません）。読むだけ・行き先の絞りの保証は、`.claude/hooks/pipe_in_guard.py` とサブエージェントの `tools:` が担います。
- 助言は WebSearch と、公式の文書の場所の WebFetch を許します（ガードの `DOC_HOSTS`・`GITHUB_HOSTS` と同じ）。WebSearch の行き先や、github の `anthropics/` の下への絞りはガードが受け持ちます（許可の書き方では絞れません）。
- `--max-budget-usd 5` は目安の上限で、超えることがあります（サブエージェントの費用も数えます）。好みで変えてください。`--model sonnet` なども任意です。回数の上限は `--max-turns`、断られたときに再試行させないのは `--permission-prompts none`（v2.1.259 以降。どちらも任意）。
- `--bare`・`--disable-slash-commands` は付けません。付けるとスキルが開かれず、`/pipe-audit …` がふつうの文としてモデルに渡ります。公式の文書に「`--bare` は将来 `-p` の既定になる」とあり、そうなると開かれなくなるので、下の見分け方で確かめてください。
- 信頼していない作業フォルダ（新しい worktree など）では、`.claude/settings.json` の allow が無視されます。さらに `.mcp.json` のサーバーは確認なしでつながります。入れている MCP の道具（プラグインのものを含む）は `--tools` では消えませんが、`dontAsk` で許可に無ければ断られます。`--allowedTools` は省かないでください。
- 会話を開かない呼び方では、報告を出して止まります。直すのは、人が承認したあと、会話（`/pipe-audit` を対話で開く、またはメインに頼む）でします。
- 開かれたか確かめるときだけ、末尾に `--output-format stream-json --verbose` を足し、最初の `system/init` の `slash_commands`（と `skills`）に `pipe-audit`（`/pipe-advise` のときは `pipe-advise`）があるかを見ます。あれば開かれています。サブエージェントが動いたかは `parent_tool_use_id` で追えます。無ければ、作業フォルダがこのリポジトリか、`--bare`・`--disable-slash-commands` を付けていないか、`claude --version` を確かめます。
