# Claude Code のプラグイン

[ガイドの目次](README.md) · [README](../../README.md) — どのプロジェクトでも会話で[パイプ](pipes.md)を作る・直すためのプラグインの説明です。

このリポジトリは Claude Code のプラグインのマーケットプレイスにもなっています（`.claude-plugin/marketplace.json` → `plugin/`）。
入れると、どのプロジェクトでも会話でパイプを作る・直すことができます。`pipe-in-gen` が使えること（`pip install -e .`）が前提です。

```
/plugin marketplace add <pipe-in のリポジトリのフォルダか GitHub の nigoh/pipe-in>
/plugin install pipe-in@pipe-in
```

| 入るもの | すること |
| --- | --- |
| スキル `/pipe-in:pipe-build` | 目的か直したい点を聞き、段の表（直すときは「前 → 後」の表）を見せて確認を取り、pipe-builder に任せ、`pipe-in-gen check` の結果と流し方を伝える。流すのは言われてから |
| エージェント `pipe-builder` | 確認が取れた表どおりに `pipe.toml`・`prompts/`・`README.md` を書き、`pipe-in-gen check` が通るまで直す。表に無い権限の拡大はせず差し戻す |
| フック（`pipe-in-gen guard-hook`） | pipe-builder が書けるのを、パイプのフォルダ（`…/pipes/pipe-in-<名前>/`。前の版のフォルダ名も）の `pipe.toml`・`README.md`・`prompts/*.md` だけに、Bash を `pipe-in-gen list / new / check` だけに絞る。PowerShell・MCP・Web・ほかのエージェントの呼び出しも止める。ほかのエージェントには何もしない |

フックは `pipe-in-gen` で動くので、`pipe-in-gen` が無い環境では効きません（スキルは、はじめに `pipe-in-gen` を確かめて、無ければ止まります）。
