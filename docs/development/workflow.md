# 進め方

## 1. 始める：ブランチと worktree

機能ごとに、ブランチを切って、別の作業フォルダ（worktree）で進めます。いくつかの会話や人が同時に作業しても、変更が混ざらないようにするためです。

```bash
git worktree add ../devpipe-<名前> -b feat/<名前>     # 文書だけなら docs/<名前>、直しなら fix/<名前>
cd ../devpipe-<名前>
```

- 同じファイルを大きく触る機能は、同時に進めません（あとで合わせるのが難しくなる）。
- 拡張を触るなら、その worktree で `cd vscode && npm ci` をします（`node_modules/` は worktree ごとに要る）。
- 終わったら、人が main に入れたあとで `git worktree remove ../devpipe-<名前>` で片付けます。

## 2. 進める：5つの段

Claude Code では `/pipe-in <要件メモ>` が、この順に進め、段の区切りで止まって確認を取ります（止まらずに進めるのは `--auto` のときだけ）。
段の中身は段ごとのサブエージェント（`.claude/agents/pipe-in-*`）が受け持ち、書ける場所と Bash は `.claude/hooks/pipe_in_guard.py` が絞ります。人とのやり取りと、決定の記録を書くのはメインの会話です。

| 段 | 受け持つ | すること | 書けるもの |
| --- | --- | --- | --- |
| 1. 要件定義 | `pipe-in-analyst` | 目的・FR・AC・対象外・触る側を書く（[specs.md](specs.md)） | `docs/pipeline/01_requirements.md` |
| 2. 設計 | `pipe-in-analyst` | 変えるファイル・形が変わるか（互換）・AC とテストの対応表（[design.md](design.md)） | `docs/pipeline/02_design.md` |
| 3. テスト先行（赤） | `pipe-in-tester` | 対応表どおりにテストを書き、期待した理由で落ちることを確かめる（[testing.md](testing.md)） | テストと `03_red_tests.md` |
| 4. 実装（緑 → 整理） | `pipe-in-coder` | テストを通す最小の変更をしてから整える。承認されたテストは書き換えない | 製品コードと文書と `04_implementation.md` |
| 5. 検証 | `pipe-in-verifier` とメイン | 触った側のテストを全部流す。画面・手で・実機の確認。公開してよいかを見る。メインが決定の記録を書く | `05_test_report.md`、決定の記録（メイン） |

### 段の成果物（docs/pipeline/）と決定の記録の分け方

| | 段の成果物 | 決定の記録 |
| --- | --- | --- |
| 置き場所 | `docs/pipeline/`（`01_requirements.md`〜`05_test_report.md`・`state.json`・`logs/`。`python -m devpipe record` が書く） | `docs/decisions/Dnnnn-<名前>.md` |
| 追跡 | **しない**（`.gitignore` 済み）。手元の作業の記録 | する |
| 何のため | 段から段への受け渡しと、VSCode の拡張で進み具合を見るため | あとから読む人が「何を、なぜ決めたか」を知るため |
| 中身 | 段の文書そのもの。セッション ID・手元のパス・読んだコードの中身が入る | 目的・FR と AC・決めたことと理由・対象外・確かめたこと（[specs.md](specs.md)） |
| いつまで | 次の `record start` で `docs/pipeline/archive/` に移る。いらなくなったら消してよい | ずっと |

- 決定の記録には、段の成果物の中身をそのまま貼りません。要るところだけを、手元の事情を消して書き直します。
- 段の成果物は worktree ごとにできます（`docs/pipeline/` は作業フォルダの中にあるため）。

## 3. そろえる：文書

変えたものに合わせて、次の文書も直します。

| 変えたもの | 直す文書 |
| --- | --- |
| 使い方（コマンド・オプション・設定） | `README.md`、拡張なら `vscode/README.md`、`/pipe-help`（`.claude/skills/pipe-help/SKILL.md`） |
| 置き場所（ファイルを足した・動かした） | [design.md](design.md) の「置き場所」の表、必要なら `CLAUDE.md` |
| 層・依存の向き | [design.md](design.md) と、それを検査するテスト |
| 開発の決まり | `docs/development/` と、それを検査するテスト、`CLAUDE.md` の要約、`/pipe-in` |

## 4. 終える：確かめてコミット

1. 触った側のテストを全部流す。Python と拡張の両方に触れたら両方。拡張なら `npm run typecheck` も。
2. `git status` で、自分の変更だけがあることを確かめる（ほかの作業のファイルが無いか）。
3. `git add` してから `git diff --cached` を読み、[principles.md](principles.md) の「7. 公開する前提で書く」のものが入っていないかを見る。
4. **1つの機能を1つのコミット**にする。文の形は既存に合わせる：
   - `feat(devpipe): …`・`feat(devpipe-vscode): …`・`fix(…): …`・`docs: …`・`chore: …`
   - 1行目は日本語で、何ができるようになるか。本文に、変えた点を箇条書きで。決定の記録があれば、その番号を書く
5. main へ入れる（マージ・push）のは人がする。Claude Code は、言われるまでコミットも push もしない。
