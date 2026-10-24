# 進み具合をアーティファクトで見る手順（/pipe-in の `--artifact`）

引数に `--artifact` があるときに読む（段の途中でも、写しの手順に迷ったら読み直す）。

進み具合を claude.ai のアーティファクト（会話の横のページ）でも見られるようにする（D0027）。`--auto` と一緒に使える。Artifact と ArtifactData のツールがある会話でだけ使える（claude.ai にログインした Claude Code の CLI・デスクトップアプリ・claude.ai/code。API キー・Bedrock・Vertex・`-p`・Agent SDK では使えない。https://code.claude.com/docs/en/artifacts ）。ページは見るだけで、承認・直してほしい点・中止は、これまでどおり会話で聞く。

1. `record start` の直後に、ページの HTML を作る：`python -m pipe_in live page --out <一時フォルダ>/pipe-in-live.html`。一時フォルダは会話の作業用の場所（scratchpad。無ければ OS の一時フォルダ）で、リポジトリの中には置かない。
2. その HTML を Artifact で1回だけ公開する。`capabilities` は `{"db": {}}`、`icon` は `chart`。HTML は書き換えない。公開した URL を覚えておき、人に伝える（はじめは持ち主だけが見られ、共有するかは人が決める、と添える）。公開し直さない（ページは db の変更を受けて自分で描き直す）。
3. `python -m pipe_in record …` を実行するたびに（`start`・`begin`・`done`・`wait`・`review`・`red`・`verdict`・`finish`）、すぐあとに写しを作る：`python -m pipe_in live snapshot --out <一時フォルダ>/pipe-in-live.json`（`--out` は `docs/pipeline/` の中を断る）。
4. その写しを ArtifactData の `set` で書く：`url` は 2. の URL、`collection` は `runs`、`doc_id` は `current`、`file_path` は 3. の JSON。毎回、同じドキュメントを丸ごと置き換える。最初の1回は `if_version` を付けず、2回目からは前の `set` の結果の `version` を `if_version` に渡す。版が合わないと断られたら、`get` で今の `version` を読んで1回だけやり直す。
5. 写しや書き込みに失敗しても段は止めず、人に一言伝えて続ける（記録の本体は `docs/pipeline/` にある）。
6. 写しには、要件メモの本文・セッション ID・パス・段の要約や差し戻しの理由などの自由な文・ログの中身は入らない（`docs/guide/records.md` の「アーティファクトに出す写し」）。中身を足したくなったら、写しの形を変える `/pipe-in` にする（ここで写しを手で書き足さない）。
