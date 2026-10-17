# devpipe

要件メモから 要件定義 → 設計 → テスト先行 → 実装 → 検証 を Claude Agent SDK（Python）で順に流すパイプラインと、その実行を図で見る VSCode 拡張（`vscode/`）。
使い方と設定の説明は README.md にある。開発のルールは `docs/development/` にあり、ここにはその要約と、必ず守ることだけを書く。

**このリポジトリは公開する。** 書いたもの・コミットしたものはすべて誰でも読める前提で扱う。

## コマンド

```bash
# Python（devpipe 本体）
python -m venv .venv && . .venv/Scripts/activate   # Windows の Git Bash。macOS / Linux は .venv/bin/activate
pip install -e '.[dev]'
pytest -q                     # SDK を呼ばない。段の順番・確認・差し戻し・書き込み制限を確かめる

# VSCode 拡張
cd vscode
npm ci                        # 型検査・ビルドに使う。テストだけなら不要
npm test                      # node:test（Node 22 以上）
npm run typecheck
npm run build
npm run preview               # 画面の確認用のページ（out/preview/）。Playwright（MCP）で開いて確かめる。手順は /pipe-in の「5. 検証」
```

変更したら、触った側のテストを流してから終える。Python と拡張の両方に触れたら両方流す。

機能を足す・直すときは `/pipe-in <要件メモ>` を使う（`.claude/skills/pipe-in/`）。始めに `feat/<名前>` のブランチを worktree で切る（`docs/development/workflow.md`）。要件定義 → 設計 → テスト先行 → 実装 → 検証 を、段ごとにサブエージェント（`.claude/agents/pipe-in-*`）へ任せて順に進め、段の区切りで止まって確認を取る。サブエージェントの書ける範囲は `.claude/hooks/pipe_in_guard.py` が止める。進み具合は `python -m pipe_in record` で `docs/pipeline/`（手元の作業の記録。`.gitignore` 済み）に書かれ、VSCode の拡張で見られる。追跡して残すのは決定の記録（`docs/decisions/`）だけ。止まらずに最後まで進めるのは `/pipe-in --auto <要件メモ>` のときだけ。
使いかたの一覧は `/pipe-help`（`.claude/skills/pipe-help/`）。
devpipe で流すパイプ（図を作る・仕様とソースの突き合わせなど）を作る・直すときは、プラグインのスキル `/devpipe:pipe-build <目的か直したい点>`（`plugin/`。入れ方は README の「Claude Code のプラグイン」。このリポジトリでも `/plugin marketplace add ./` → `/plugin install devpipe@devpipe` で入れて使う）。

## 開発のルール（docs/development/）

| 文書 | 中身 |
| --- | --- |
| `docs/development/principles.md` | 原則：テスト先行・関心の分離・変えやすさ・安全側に倒す・明示する・利用料・公開前提 |
| `docs/development/specs.md` | 要件定義の形、決定の記録（`docs/decisions/Dnnnn-<名前>.md`）、AC の ID `Dnnnn-AC-xx` |
| `docs/development/design.md` | 置き場所の表、本体の依存の向き、拡張の層、形を変えるときの互換、依存を足す基準 |
| `docs/development/testing.md` | テストの種類、偽物、やってはいけないこと、赤の確かめ方、名前と粒度 |
| `docs/development/workflow.md` | ブランチと worktree、5つの段、文書をそろえる範囲、コミット |

## 必ず守ること

- テストを先に書く（赤 → 緑 → 整理）。赤は、期待した理由で落ちたことを、失敗の文まで読んで確かめる（出力を切らない）。
- テストは SDK を呼ばず（`runner` を差し替える）、リポジトリの実物（`pipes/`・`.devpipe/`・`docs/pipeline/`）に書かない（`tests/conftest.py` が見張る）。
- `pipe_in/engine/guard.py` と `generator/guard_hook.py` は利用者のプロジェクトを守る仕組み。許すものの一覧で書く。止める範囲を狭める変更は、理由をコミットと決定の記録に書き、すり抜けの道（PowerShell・MCP・サブエージェントなど）が開かないことをテストで示す。
- 依存の向き（`pipe_in_generator` → `pipe_in.pipe` / `pipe_in.dev` → `pipe_in.engine` → `pipe_in.usage`）と拡張の層を守る（`tests/test_architecture.py`・`vscode/src/architecture.test.ts` が検査する）。`vscode` を import してよいのは `vscode/src/extension.ts` だけ。
- 拡張は work_dir を読むだけで書かない。書いてよいのは作業台の「保存」での、パイプの置き場所の中の決まったファイルだけ（`vscode/src/infra/fsPipes.ts` が絞る）と、拡張の保存場所（storageUri）の保存した版だけ（`fsVersions.ts` が絞る）。外から来た文字は必ず `escapeHtml` を通し、外部から何も読み込まない。
- 依存を足すときは、必要な理由を決定の記録に書く。`package-lock.json` も一緒にコミットする。
- 機能ごとに決定の記録（`docs/decisions/`）を書く。置き場所が変わったら `docs/development/design.md` の表を直す。
- 1つの機能を1つのコミットにする。コミット・push は人に言われるまでしない。
- 文書・コメント・コミットの文は日本語で、平易に書く（既存の文に合わせる）。

## 公開リポジトリとしての注意

- 秘密（API キー・トークン・`.env`・鍵ファイル）と手元の事情（ユーザー名の入った絶対パス・社内や私的なプロジェクトの名前・メールアドレス）を書かない・コミットしない（`tests/test_rules.py` が検査する）。
- devpipe を実際に流した記録（`docs/pipeline/`）は載せない。サンプルにするときは、手元の情報を消してから `examples/` に置く。
- 手元だけの設定は `.claude/settings.local.json` と `CLAUDE.local.md` に書く（どちらも `.gitignore` 済み）。
- コミットの前に `git diff --cached` で、上のものが入っていないか見る。
- くわしくは `docs/development/principles.md` の「7. 公開する前提で書く」。
