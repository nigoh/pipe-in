# D0095 プラグインを Anthropic のディレクトリの事前チェックに通る形に整える（README・アイコン・表示の項目・LICENSE・見張るテスト・申請の手順）

## 目的

pipe-in のプラグイン（`plugin/`）を、自前のマーケットプレイス（`nigoh/pipe-in`）で1行で入れられ、Anthropic のディレクトリ（claude.ai/directory）の事前チェックに通る形に整える。中身（5つのスキル・4つのエージェント・フック）と、`pipe-in-gen` を別に入れてもらう形は変えない。申請そのもの（ポータルの操作）は人がする。

### 要求と前提

- UR-01 プラグインを入れたい人として、1行の案内でプラグインを入れ、何が入り、何を動かし・送り・取ってくるかを、入れる前に読みたい。
- UR-02 pipe-in の保守者として、ディレクトリの事前チェックの決まりを、リポジトリの検査（pytest）で見張りたい。
- UR-03 pipe-in の保守者として、ディレクトリへ申請するときの手順と、データの扱いの問いへの答えの下書きを、文書で読みたい。
- UR-04 プラグインを入れた人として、ディレクトリや一覧で、名前・説明・アイコン・ホームページが見えるようにしたい。
- 前提：事前チェックの内容は、2026-11-12 に読んだ公式の文書のとおりである（https://claude.com/docs/plugins/pre-submission-checklist ・https://claude.com/docs/plugins/submit ・https://claude.com/docs/plugins/platform-support ・https://code.claude.com/docs/en/plugins/publish.md ）。文書が変わったら崩れる。
- 前提：README の「40 語以上」の数え方は文書に書かれていない。空白区切りの語数で、余裕をつけて書く。
- 前提：`claude plugin validate` は事前チェックと同じ種類の指摘を出すが、同じ検査そのものではない。ポータルの「Validate」が最後の確かめになる。
- 前提：フックの `"command": "pipe-in-gen"`（PATH のコマンド名）がポータルの検査で止められるかは、確かめていない。
- 前提：入れた人に届くのはプラグインのフォルダ（`plugin/`）だけである。
- 前提：ちゃんと使えるのは、`pipe-in-gen` と `pipe-in` を入れた Claude Code だけである（チャットではフックとエージェントが無視される）。
- 状態を持ち、操作や出来事で移り変わるか
  - 答え：いいえ
  - 理由：README・アイコン・マニフェストは置いておく静的なファイルで、状態を持たない。README と実物のずれは pytest が見張る。

## 機能要件と受け入れ基準

テストは `tests/test_plugin_directory.py`（検査の関数は同じファイルの中）と `tests/test_plugin.py::test_plugin_version`。

- FR-01（UR-01）`plugin/README.md` を置く。英語の節と日本語の節を持ち、1行の入れ方・`pipe-in-gen` の入れ方・入るもの・動かすもの／送るもの／取ってくるもの・使える場所を含む。
  - D0095-AC-01（FR-01）コードの囲みを除いた語数が 40 以上で、英語の節だけでも 60 以上（`ac01_*`）。
  - D0095-AC-02（FR-01・NFR-03）英語の節と日本語の節に、4つの見出しがある（`ac02_*`）。
  - D0095-AC-03（FR-01）どちらの節にも、1行の入れ方と `pip install -e .` の行がある（`ac03_*`）。
  - D0095-AC-04（FR-01・NFR-04）実物のスキル・エージェントの名前が両方の節に出て、実物に無い名前が無い（`ac04_*`）。
  - D0095-AC-05（FR-01・NFR-04）「動かすもの」に、実物の文書に出る `pipe-in-gen` のサブコマンドと `pipe-in live` の形が全部あり、書いたサブコマンドは本物で、`ArtifactData`・`Artifact`・外部の URL が「送るもの・取ってくるもの」に書かれている（`ac05_*`）。
- FR-02（UR-01）根の `README.md` と `README.en.md` に1行の入れ方を足す。
  - D0095-AC-06（FR-02）両方に `/plugin install pipe-in --marketplace nigoh/pipe-in` がある（`ac06_*`）。
- FR-03（UR-04）`plugin/.claude-plugin/icon.png` を置く。
  - D0095-AC-07（FR-03）PNG で、正方形で、512〜2048 で、2,000,000 バイト未満。実物は 1024×1024。`plugin.json` の `icon` が `./.claude-plugin/icon.png` で、プラグインのフォルダの中の実在するその PNG を指す（監査と助言のあとで広げた。`ac07_*`）。
- FR-04（UR-04）`plugin.json` と `marketplace.json` の項目に、表示の項目を足す。
  - D0095-AC-08（FR-04）`plugin.json` に `displayName`・`homepage`・`repository`・`keywords`・`author.url` があり、名前の形が合う。`documentationUrl`（ガイド）と `supportUrl`（issue）が `https://` で始まり、`privacyPolicyUrl`・`termsOfServiceUrl` は無い（後半は監査と助言のあとで広げた。`ac08_*`）。
  - D0095-AC-09（FR-04）`marketplace.json` の項目に `displayName`・`homepage`・`repository`・`keywords`・`tags`・`category`（`development`）があり、`owner.url` がある。`source` は `./plugin` のまま。項目に `icon`・`documentationUrl`・`supportUrl`・`privacyPolicyUrl`・`termsOfServiceUrl` が無く、項目と `plugin.json` の両方にある `displayName`・`homepage`・`repository`・`keywords`・`license`・`author` は同じ値（後半は監査と助言のあとで広げた。`ac09_*`）。
- FR-05（UR-04）プラグインの版を上げる。
  - D0095-AC-10（FR-05）`plugin.json` の `version` が 0.6.0 で、`marketplace.json` の項目に `version` が無い（`ac10_*`・`test_plugin.py::test_plugin_version`）。
- FR-06（UR-02）ディレクトリの決まりを pytest で見張る。
  - D0095-AC-11（FR-06・NFR-01）画像・フォント以外のファイルが 256 KiB 未満、各ファイルが 5 MiB 未満、ファイル数が 512 未満。上限を超える入力で違反を返す（`ac11_*`）。
  - D0095-AC-12（FR-06・NFR-02）シンボリックリンク・不要なファイルが無く、ファイル名に使えない文字・予約名・大文字小文字だけの違いが無い（`ac12_*`）。
  - D0095-AC-13（FR-06）`plugin/LICENSE` があり根の `LICENSE` と同じ。`.gitattributes` に `export-ignore`・`export-subst`・`filter` が無い（`ac13_*`）。
  - D0095-AC-14（FR-06）`hooks.json` が公式のイベント名と型だけで、その場のプログラム・別の変数・ワイルドカードなどが無い（`ac14_*`）。
  - D0095-AC-15（FR-06）スキルとエージェントの前書きの `description` が1つの文字列として読める（`ac15_*`）。
- FR-07（UR-03）`docs/guide/plugin.md` に「ディレクトリへの申請」の節を足す。
  - D0095-AC-16（FR-07）ポータルの順番・答えの下書き4項目・版を上げる決まり・アイコン・pytest が見る範囲がある（`ac16_*`）。
- FR-08（UR-02）`claude plugin validate --strict` は CI で流さず、リリース前に手で流す手順を書く。
  - D0095-AC-17（FR-08）申請の節に2つのコマンドの行があり、CI に validate が無い（`ac17_*`）。
- D0095-AC-18（FR-04・FR-07）（手で）申請の前に、`claude plugin validate --strict ./plugin` と `claude plugin validate --strict .` を実機で流し、どちらも終了コード 0 で、`ICON_MISSING` と README の警告が出ない。
- D0095-AC-19（FR-01）（実機）main に入ったあと、新しい環境で `/plugin install pipe-in --marketplace nigoh/pipe-in` を流し、入って `/pipe-in:pipe-build` が見えることを確かめる。まだ。

### 非機能要件

- NFR-01（UR-02）
  - きっかけ：プラグインのフォルダにファイルを足す・直す変更が入る。
  - 状況：`pytest -q` を流す。
  - 応答：画像・フォント以外のファイルが 256 KiB 以上、ファイルが 512 個以上、各ファイルが 5 MiB 以上なら落ちる。
  - 測り方：AC-11 のテストが今の値で通り、小さな上限に差し替えると落ちる。
- NFR-02（UR-02）
  - きっかけ：シンボリックリンク・`.DS_Store`・`Thumbs.db`・`desktop.ini`・`__MACOSX` が入る。
  - 状況：`pytest -q` を流す。
  - 応答：落ちて、見つかったパスを出す。
  - 測り方：AC-12 のテストが、一時のフォルダに置いた入力で見つける。
- NFR-03（UR-01）
  - きっかけ：利用者が `plugin/README.md` を開く。
  - 状況：英語の節だけ、または日本語の節だけを読む。
  - 応答：どちらの節だけでも、入れ方・入るもの・動かすもの／送るもの／取ってくるもの・使える場所が分かる。
  - 測り方：AC-02 のテストが、両方の節の見出しを確かめる。
- NFR-04（UR-02）
  - きっかけ：スキル・エージェント・フックを足す・消す変更が入る。
  - 状況：README を直し忘れている。
  - 応答：落ちて、README に無い（または実物に無い）名前を出す。
  - 測り方：AC-04・AC-05 のテスト。

## 決めたことと理由

人が決めたこと：

- **版**：`plugin.json` だけ 0.5.2 → 0.6.0。`marketplace.json` の項目に `version` は書かない（二重にしない）。`pyproject.toml` の版（`pipe-in-gen`）は上げない（別物）。リリースのたびに上げる決まりを `docs/guide/plugin.md` に書いた。
- **`plugin/LICENSE`**：根の `LICENSE` と同じ中身（バイト単位）。入れた人に届くのはプラグインのフォルダだけで、ライセンスの文が読めるようにするため。
- **表示の項目**：`displayName: "pipe-in"`・`homepage` と `repository`（`https://github.com/nigoh/pipe-in`）・`keywords`・`author.url`・`owner.url`（`https://github.com/nigoh`）。`marketplace.json` の項目には `tags` と `category: "development"` も。`source` は `./plugin` のまま。
- **掲載ページが読む欄**（助言 V-01・V-02）：公式の manifest-reference に、ディレクトリは `plugin.json` の `icon`・`documentationUrl`・`supportUrl`・`privacyPolicyUrl`・`termsOfServiceUrl` を読む、とある。`icon`（`./.claude-plugin/icon.png`）・`documentationUrl`（`docs/guide/plugin.md`）・`supportUrl`（issue）を `plugin.json` にだけ書いた。`privacyPolicyUrl`・`termsOfServiceUrl` は書く先が無いので書かない。項目に書くと知らない欄の警告になるので、`marketplace.json` には書かない。`claude plugin validate` がこれらを警告しないのは v2.1.281 以降。
- **README の言語**：英語の節（先）と日本語の節（後）の両方。ディレクトリは英語の利用者も読み、日本語は空白で数えると語数が少なく出るおそれがあるため。
- **アイコン**：元は `docs/assets/pipe-in-logo-dark.svg`、地の色は `#0D1117`（白・ほぼ黒・薄いグレーの3つを人が見比べて決めた。白は明るいページで縁が溶け込む）。1024×1024、約 26 KB。ポータルで使われるのは最初の保存・申請の1回だけ。作り方は `docs/assets/README.md`。
- **CI では validate を流さない**：Claude Code を CI に入れると依存が増え、版も動き、検査の中身も変わりうる。代わりに pytest で見張れる決まりを見張り、リリース前に手で2つのコマンドを流す手順を書いた。
- **フックの `"command": "pipe-in-gen"` は今の形のまま**：`${CLAUDE_PLUGIN_ROOT}` の下に守りのフックは同梱しないと人が決めている。pytest はこの形を許す。ポータルの Validate で止められたら、別の機能で見直す。

README の「動かすもの・送るもの・取ってくるもの」は、スキル・参照・エージェント・フックを読んで確かめた事実だけを書いた。プラグイン自身が作者や第三者のサーバーへ送るものは無い。`/pipe-in:pipe-live` だけが、人が呼んだときに claude.ai のアーティファクトのデータへ進み具合の写しを書く。`WebFetch`・`WebSearch` は使わない。ただし `/pipe-in:pipe-eval` が流す検査のコマンドと段の中のシェルのコマンドは、利用者のパイプの定義のとおりに動くので、何を送るかはその定義による（README とデータの扱いの答えの下書きに、そう限定して書いた）。

選ばなかった形：

- 英語だけ・日本語だけの README：リポジトリの「文書は日本語」の決まりから外れる、または語の数え方次第で Blocks になるおそれがある。
- 版を 0.5.3 にする：README・アイコン・マニフェストの項目を足す変更は、見た目だけの扱いより大きいと見た。
- `claude plugin validate` を版を固定して CI で流す：確かさは上がるが、依存の理由を記録に書く必要があり、今は見送る。
- 検査の関数を `pipe_in/` に置く：本番のコードではないので、テストのファイルの中に置いた。

受け入れたリスク：

- ポータルの検査は、`claude plugin validate` と pytest より多くを見る。申請の前の手の確かめが通っても、ポータルで止まることがある。
- 公式の文書は変わる。決まりの定数はテストの先頭にまとめ、変わったらそこと申請の節だけ直す。

## 対象外・残った課題

- ポータルでの申請そのもの、申請後の人の審査・セキュリティの検査への対応。
- `pipe-in-gen` の PyPI への公開・uvx で起こす形・守りのフックの同梱。
- アイコンの登録後の変更（登録後は変わらない）。
- README の第3の言語。
- スキル・エージェント・フックの中身の変更。
- AC-19（main に入ったあとの実機の確かめ）は、まだ。1 行の入れ方が通らなければ、別の機能で README 2つ・`plugin/README.md`・ガイドを直す。
- フックの `"command": "pipe-in-gen"` がポータルの Validate で止められたときの逃げ道（助言 V-03）：公式の hooks の文書では、`args` があると `command` は PATH から探して直接起こされ、`${CLAUDE_PLUGIN_ROOT}` の決まりはプラグインの中のファイルを指すときの話なので、今の形は文書どおり。止められたら、プラグインの中に薄い起動用のスクリプトを置いて `${CLAUDE_PLUGIN_ROOT}` から呼ぶ形を考える。`bin/` に置く形は、claude.ai と Cowork がそのプラグインを入れなくなるので向かない。
- `category: "development"` がディレクトリの分類で許される値かは、公式の文書で確かめられていない（free-form）。
- 監査 A-05（README の 1 行の入れ方にも「実機は未確認」を添える）は、人が選ばなかったので直していない。未確認の注意はガイドとこの記録にだけ残す。
- `privacyPolicyUrl`・`termsOfServiceUrl` は書く先が無いので書いていない。ポータルで求められたら、別の機能で足す。

## 確かめたこと

- テスト：監査と助言で直したあと、全体の `pytest -q tests` が 18344 passed・8 skipped で通った（拡張は触っていないので流していない）。`tests/test_plugin_directory.py` は、実物に当てるテストと、一時のフォルダや辞書の入力で違反を見つけるテストを組にした。
- 古いテスト2件（D0077-AC-34・D0045-AC-14）が版 0.5.2 を期待して落ちたので、人の判断でテスト先行に戻り、期待を 0.6.0 に直した（D0076 で 0.5.2 に上げたときと同じやり方）。
- 手で流す確かめ（D0095-AC-18）：このコンテナの Claude Code 2.1.322 で、`claude plugin validate --strict ./plugin`（ディレクトリの検査の部分も「found nothing to report」）と `claude plugin validate --strict .` がどちらも通った。`ICON_MISSING` も、README を根から取った旨の知らせも、入れ方の行が無いという助言も出なかった。
- 実機の確かめ（D0095-AC-19）：まだ（main に入ったあと）。
- ポータルの Validate・セキュリティの検査・人の審査は、申請するまで分からない。

### 監査と助言で直したもの

監査 7 件・助言 8 件のうち、人が選んだもの：

- A-01・A-02：`plugin/README.md` の「どのスキルも `pipe-in-gen` が要る」を、スキルごとに直した（`pipe-build`・`pipe-judge`・`pipe-run` は `pipe-in-gen`、`pipe-live` は `pipe-in`、`pipe-eval` はどちらも要らない。`pip install -e .` で両方入る）。
- A-03・A-04・A-06：ガイドの見出しを「0.5.x から更新するとき」にし、1 行の形で入れた人の更新を足し、チャットではエージェントとフックが無視されることを入れ方の所と `pipe-run` の「使える場所と使えない場所」に足した。
- A-07：文書係の案のとおり、`CLAUDE.md` のプラグインの段落と `/pipe-help` に 1 行の入れ方を足した（`CLAUDE.md` には版を上げる決まりと申請の節も）。
- V-01・V-02・V-06：`plugin.json` に `icon`・`documentationUrl`・`supportUrl` を足し、AC-07・08・09 を広げてテストを足した（テスト先行に戻した）。
- V-04・V-05：README とガイドに、`pipe-in-gen` が無いと道具を呼ぶたびにフックのエラーの知らせが出ること、入れるときに確認と範囲（scope）の選択が出ること、古い版のシェルの 2 段の形を足した。
- 助言の参考：データの扱いの「送らない」を「プラグイン自身は送らない。検査のコマンドと段のシェルのコマンドはパイプの定義による」と限定した。
- 直さなかったもの：A-05（人が選ばなかった）、V-03（逃げ道を上の「残った課題」に書いた）、V-07・V-08（直す所なし）。
- 審査：助言の報告の採点は overall 0.9・pass（網羅性 0.5。助言役は claude.com の 3 ページを開けなかった）。
