# 記録のコマンド（/pipe-in）

最初の `record start` の前に1回読む（全段で使う。旗の綴りに迷ったら読み直す）。

拡張の「pipe-in: 実行を見る」とステータスバーに、動いている段・確認待ち・差し戻し・最後の結果が出る（並列の実行や別の worktree の確認待ちがあるときは、ステータスバーは `動き N・確認待ち M` の件数になり、段や結果は説明に出る）。

| いつ | コマンド |
| --- | --- |
| 始めるとき（要件メモを渡す） | `python -m pipe_in record start --text "<要件メモ>" --name "<セッション名>"`（長いときは `--input <ファイル>`。`--name` を省くと要件メモの最初の行から作る） |
| 段を任せる直前 | `python -m pipe_in record begin <段> --agent <サブエージェント>`（要件定義と設計は `pipe-in-analyst`、テスト先行は `pipe-in-tester`、実装は `pipe-in-coder`、検証は `pipe-in-verifier`。VSCode の時系列の行とエージェント・スキルの表に出る。実装と検証は `--attempt N`。直してもらうときは `--note 指摘を反映`） |
| サブエージェントが返ったあと | `python -m pipe_in record done <段> --summary "<ひとこと>"`（失敗なら `--error`） |
| 人の確認を待つとき | `python -m pipe_in record wait <段>` |
| 人が答えたとき | `python -m pipe_in record review <段> approved`（`revise --feedback "<直してほしい点>"`・`quit`） |
| テスト先行の結果 | `python -m pipe_in record red red --summary "<要約>" --test Dnnnn-AC-01=<テスト> --command "<流したコマンド>"`（流せないなら `blocked`） |
| 検証の判定 | `python -m pipe_in record verdict pass --attempt N --summary "<要約>"`（不合格は `fail --failure Dnnnn-AC-01=<中身>`） |
| 終わるとき | `python -m pipe_in record finish PASSED`（`TEST_FAILED`・`STOPPED_BY_HUMAN`・`STAGE_ERROR`・`BLOCKED`） |

- セッション ID（`--session-id`）は、SKILL.md の「1. 要件定義」の `record start` で渡す（補助ファイルでは置き換えが効かないものとして扱う）。`--session-id` と `begin` の `--agent` は、空白や制御文字を含む値と 100 文字を超える値が断られる。
- 段の名前は `requirements`・`design`・`red`・`implement`・`test`。
- `start` は途中の記録があると断る。前の記録が途中のまま残っていたら、人にどうするか（`finish STOPPED_BY_HUMAN` で閉じるか）聞く。終わった記録は `docs/pipeline/archive/` に移る。
- この記録は `pipe-in --review` では続けられない（記録に `driver` があるので `pipe-in` が断る）。続きはこの会話で進める。
- PushNotification の文は段の名前（段でなければ「監査と助言」など）と固定の言葉だけにし、要件メモ・パス・秘密を入れない。`--auto` で止まらずに進むところでは知らせない（働きは公式の文書 tools-reference、引数 message・status はツールの説明で確かめた）。
