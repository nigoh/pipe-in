# 決定の記録

機能ごとに、何を作り、何をなぜ決めたかを1つのファイルに残します。書き方は [../development/specs.md](../development/specs.md) の「決定の記録」にあります。

| 記録 | 題 |
| --- | --- |
| [D0001](D0001-plugin-pipe-build.md) | パイプを会話で作る・直すプラグイン（/devpipe:pipe-build と pipe-builder）と、対象の .devpipe/pipes/ |
| [D0002](D0002-dev-rules.md) | 開発のルール（docs/development/）と、それを守らせるテスト |
| [D0003](D0003-rebase-on-main-change.md) | main が進んだら、機能のブランチを載せ直す |
| [D0004](D0004-pipe-in-guard-worktree.md) | /pipe-in のサブエージェントが、報告を返し、worktree の中でも書けるようにする |
| [D0005](D0005-judge-switch.md) | 作業台の判定をスイッチで入り切りし、自分をやり直す判定はケーブルを描かずに札で示す |
| [D0006](D0006-rename-pipe-in.md) | 製品の名前を pipe-in に変える（前半：製品） |
| [D0007](D0007-cable-physics.md) | コンセントの上で離しても差さる・流線型のケーブル・引くときはひものように動く |
| [D0008](D0008-audit-advisor.md) | 読むだけの矛盾監査とアドバイザー（/pipe-audit・/pipe-advise と /pipe-in の検証のあと） |
| [D0009](D0009-readme-screens.md) | README を分かりやすく作り直し、動いている画面とロゴを載せる |

## ひな形

ファイルの名前は `Dnnnn-<英小文字・数字・->.md`。番号は上の表の次。足したら上の表にも1行足す。

```markdown
# Dnnnn <何ができるようになったか>

## 目的

<誰の何が良くなるかを1〜2文で>

## 機能要件と受け入れ基準

- FR-01 <すること>
  - Dnnnn-AC-01 <入力と、期待する結果>（`tests/test_xxx.py::test_yyy`）
  - Dnnnn-AC-02（手で）<手順と、期待する結果>

## 決めたことと理由

- <選んだ形>。<選ばなかった形>より<理由>。
- <受け入れたリスク>。<どこで補うか>。

## 対象外・残った課題

- <しなかったこと・あとでやること>

## 確かめたこと

- <テストの結果の要約>
- <手で・実機で確かめたこと。確かめていないものは「まだ」と書く>
```
