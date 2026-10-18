# D0011 人と確かめながら紹介動画を作るパイプの見本（examples/video）

## 目的

SNS 向けの短い紹介動画を、段の区切りで人が確かめながら作れるようにする。台本と見本は案を並べて人が選び、選んだ案だけを作り込む。最初の題材は pipe-in 自身の紹介で、「pipe-in の紹介動画を pipe-in で作った」と言える見本にする。

## 機能要件と受け入れ基準

- FR-01 `examples/video/pipes/pipe-in-video/` に、`聞く（ask）→ 台本（script）→ 見本（mock）→ 書き出し（render）→ 確かめる（verify）` の5段のパイプを置く。`ask`〜`render` のあとで人が確かめ、`verify` は検証で合否を決めて、不合格なら `render` へ戻す
  - D0011-AC-01 定義の検査（`pipe-in-gen check` と同じ）が問題なしになる（`tests/test_video_example.py::test_video_pipe_passes_check`）
  - D0011-AC-02 段の名前と順番、`ask`〜`render` の `review = true`（`::test_video_pipe_stage_order_and_review`）
  - D0011-AC-03 `ask` は読むだけ。`script` が書けるのは自分の成果物・`video/choices.md`・`video/script/options.json` だけ（`::test_ask_is_read_only_and_script_writes_only_choices`）
  - D0011-AC-04 `verify` に `verdict`・`command`・`on_fail = "render"`・`max_retries` がある（`::test_verify_has_verdict_command_and_retry`）
  - D0011-AC-05 Bash は `mock`・`render`・`verify` だけで、その指示文に `curl`・`wget` を使わないと書いてある（`::test_bash_only_on_allowed_stages`・`::test_bash_stage_prompts_forbid_downloads`）
  - D0011-AC-06 `web`・`mcp`・`mcp_servers` が無い（`::test_video_pipe_opens_no_outside_route`）
- FR-02 段の指示文に、動画づくりで分かった進め方を書く
  - D0011-AC-07 `ask`：意図・見せたいもの・長さ・画面の形・音・終わりの文・告知（ロゴ）・ファイルの大きさの上限を、推しの答えを添えて聞く（`::test_ask_prompt_mentions_required_words`）
  - D0011-AC-08 `script`：開始秒・終わり秒・見せるもの・字幕の表、字幕は 1.5〜3.5 秒（`::test_script_prompt_mentions_required_words`）
  - D0011-AC-09 `mock`：台本に無い場面を足さない、外部を読み込まない HTML（`::test_mock_prompt_mentions_required_words`）
  - D0011-AC-10 `render`：1こまずつ時刻を進めて撮る、H.264・yuv420p、ビットレートの上限、上限指定時の2パス、事前の環境確認（`::test_render_prompt_mentions_required_words`）
  - D0011-AC-11 `verify`：こまの取り出し、文字の切れ・重なり・はみ出し、`ffprobe`（`::test_verify_prompt_mentions_required_words`）
  - D0011-AC-12 全部の段：ロゴを描かず人が渡したものだけを使う、他人の録音・サンプルを使わない（`::test_every_prompt_forbids_drawing_logo_and_borrowed_audio`）
  - D0011-AC-13 ファイルの大きさの確認のコマンドが、上限を超えると 0 以外、以内なら 0 を返し、危ない操作の検査に通る（`::test_size_command_exit_codes`・`::test_size_command_is_not_dangerous`）
- FR-03 公開リポジトリの見本として、手元の情報と素材を入れない
  - D0011-AC-14 動画・音声・画像・ロゴの実ファイルが無い（`::test_no_media_or_logo_files_in_video_example`）
  - D0011-AC-15 公開前提の検査が見本に掛かり、通る（`::test_video_example_has_no_local_info`）
  - D0011-AC-16 見本は既定の探す場所に無く、今までのパイプの探し方を変えない（`::test_video_example_does_not_change_pipe_lookup`・`::test_video_pipe_found_in_old_and_new_places`）
- FR-04 流し方の見本と案内を置く
  - D0011-AC-23 `examples/video/pipes` を探す場所に指すと `video` が見つかる（`::test_video_pipe_found_with_pipes_dir`）。`pipe-in` 本体には `--pipe` にフォルダのパスを渡す
  - D0011-AC-24 台本の見本（縦長 15 秒）があり、字幕は 1.5〜3.5 秒。`.py` は受付の1本、`.html` はテンプレートの1枚だけ（`::test_script_sample_table_is_valid`・`::test_no_scripts_or_html_in_video_example`）
  - D0011-AC-25 利用料の上限が `ask`・`script` 0.5、`mock` 3.0、`render` 2.0、`verify` 1.0 ドル（`::test_budget_limits`）
  - D0011-AC-26 README に入力例・ロゴの置き場所 `video/assets/logo.svg`・定義の検査のしかた、`ask` にロゴの決まりの場所を毎回聞くこと（`::test_video_readme_has_input_example_and_paths`・`::test_ask_prompt_asks_logo_rules_every_time`）
- FR-05 台本は2〜3案、見本は3案を出して人が選び、選んだ案だけを作り込む。「どれもびみょう」なら別の方向で出し直す。選んだ記録は `video/choices.md` に残す
  - D0011-AC-27・D0011-AC-28・D0011-AC-29・D0011-AC-30 指示文に、案の数と番号・選ばれた案だけを直す・出し直し・選んだ記録を読む／書く・選ばれていなければ止まる、が書いてある（`::test_script_prompt_asks_for_options`・`::test_mock_prompt_asks_for_three_options_and_compare_page`・`::test_script_and_mock_prompts_redo_when_none_chosen`・`::test_prompts_use_choices_record`）
  - D0011-AC-31 選んだ記録を書けるのは `script`・`mock` だけ（`::test_choices_write_scope`）
  - D0011-AC-32 案の指示文を入れた版でも定義の検査が通る（`::test_video_pipe_passes_check`）
  - D0011-AC-33 README に選んだ記録の書き方の例がある（`::test_readme_has_choices_example`）
- FR-06 ページはテンプレート1枚にし、段はデータ（`options.json`）だけを書く
  - D0011-AC-58・D0011-AC-59・D0011-AC-60・D0011-AC-61 テンプレートは1枚、外部を読み込まない、データの文字をエスケープして出す、形が違えば原因を出す（`::test_template_is_single_html`・`::test_template_has_no_external_loads`・`::test_template_never_uses_html_injection`・`::test_template_has_validation_and_alert`、受付側は `tests/test_video_review.py::test_load_options_reports_cause`・`::test_page_when_options_missing_or_broken`）
  - D0011-AC-62・D0011-AC-63・D0011-AC-64 README にデータの形の例、指示文に「HTML を書かずデータだけ」、`writes` にデータの置き場所（`tests/test_video_example.py::test_readme_shows_options_json_shapes`・`::test_script_and_mock_prompts_write_data_not_html`・`::test_options_json_write_scope`）
  - D0011-AC-65 `video/` の外を指すこまは配らない（`::test_template_rejects_images_outside_video`、`tests/test_video_review.py::test_served_path_rejects_image_outside_video`・`::test_state_never_serves_outside_frames`）
- FR-07 手元の小さな受付（`examples/video/review_server.py`、標準ライブラリだけ）で、ページのボタンから `pipe-in --review` を呼んで先へ進める。端末で `--review` を打つ道も残す
  - D0011-AC-41・D0011-AC-42・D0011-AC-43・D0011-AC-44・D0011-AC-45 呼べるのは `revise`・`approve`・`quit` だけで、人の文は `--feedback` の次の1つの引数としてシェルを通さずに渡る。番号は 1 以上の整数、文の長さに上限、「どれもびみょう」は決まった文（`tests/test_video_review.py` の `test_build_command_*`・`::test_feedback_is_one_argument`・`::test_command_is_run_without_shell`・`test_parse_action_*`・`::test_none_of_them_uses_fixed_sentence`）
  - D0011-AC-46・D0011-AC-47・D0011-AC-48 `127.0.0.1` だけで待ち受け、`Host`・合言葉・POST を確かめ、`video/` の外のファイルを配らない（`::test_check_bind_rejects_other_addresses`・`::test_bind_address_is_loopback_only`・`::test_request_checks_host_token_and_method`・`::test_token_is_compared_in_constant_time`・`test_served_path_*`・`test_http_*`）
  - D0011-AC-49 ページに出す外から来た文字をエスケープし、外部の URL を含まない（`::test_embed_json_escapes_markup`・`::test_page_escapes_untrusted_text`・`::test_failure_output_is_escaped_in_page`）
  - D0011-AC-50 同時に動かすのは1つ。終了コード 5 は次の確認、0 は終わり、ほかは失敗（`::test_classify_exit`・`::test_controller_serializes_and_classifies`・`::test_second_action_is_refused_while_running`）
  - D0011-AC-51 受付は標準ライブラリだけを import し、`pipe_in` に依存しない（`tests/test_video_example.py::test_server_uses_only_standard_library`）
- 手で・実機で確かめるもの（利用料がかかる、または Playwright・ffmpeg が要る）
  - D0011-AC-17（実機）最後まで流すと、縦長 1080×1920・30fps・H.264・yuv420p の MP4 が1本できる
  - D0011-AC-18・D0011-AC-19（実機）`ask` の答えが字幕に、直した台本がこまに反映される
  - D0011-AC-20（手で）10MB 以内の版が上限以内になる
  - D0011-AC-21（実機）単語の途中で改行された字幕を `verify` が不合格にし、`render` へ戻す
  - D0011-AC-22（手で）ロゴが無ければ止まって置くように言い、置けば描き直さずに使う
  - D0011-AC-34・D0011-AC-35・D0011-AC-36・D0011-AC-37・D0011-AC-38・D0011-AC-39・D0011-AC-40（実機・手で）案の出し方・選び方・出し直し・選んだ記録・選んだ1案だけの書き出し・`mock` の利用料が 3.0 ドルに収まる
  - D0011-AC-52・D0011-AC-53・D0011-AC-54（実機）受付のページから、台本と見本の案を選び、決定・中止まで進める
  - D0011-AC-55・D0011-AC-56・D0011-AC-57（手で）受付なしでも端末で答えられる、ほかの機械から届かない、直す点に命令を入れても実行されない

## 決めたことと理由

- **pipe-in 本体・拡張・ジェネレーター・guard は変えず、パイプの定義だけで組む。** `bash = true` で Playwright と ffmpeg を動かせ、確認・検証・差し戻しは今の仕組みで足りる。依存も足さない。
- **台本を決めてから見本を作り込む。** この見本の元になった会話で、台本を決めずに作り込んだ見本が「びみょう」になった。`script` で止まって確かめ、`mock` は確かめた台本に無い場面を足さない。
- **案を並べて選ぶ。** 台本は流れの違う2〜3案、見本は見せ方の違う3案。選んだ案だけを作り込み、「どれもびみょう」なら別の方向で出し直す。選んだ記録 `video/choices.md` は `script` と `mock` が自分の分だけ書き、次の回と後の段が読む。
- **比較のページはテンプレート1枚にし、段はデータだけを書く。** 毎回 LLM にページを作らせると、形が揺れ、エスケープを守らせにくく、利用料もかさむ。テンプレートはデータの形を確かめ、違えば原因を出す。
- **ボタンで答えて先へ進める受付は、手元の小さなものにする。** 標準ライブラリだけで、`127.0.0.1` だけで待ち受け、起動のたびに作る合言葉・`Host`・POST を確かめる。呼べるのは `pipe-in --review` の3種類だけで、引数のリストでシェルを通さずに呼ぶ。受付は記録にも `video/` にも書かない。`--pause`・`--yes` などは受付が決める部分なので、起動時の引数には渡せない（`--review` が付けば次の確認でまた止まる）。
- **`verify` が不合格なら `render` へ戻す。** 要件では「見本の崩れなら `mock`」としていたが、設計で `render` だけにした（監査 A-04）。崩れが見本の HTML にあるときも、`render` は `video/mock/<番号>/` の下を直せる。戻し先を1つにすると、差し戻しの道が単純になる。
- **書ける範囲を段ごとに絞る。** `script` は `video/choices.md` と `video/script/options.json`、`mock` は `video/mock/options.json`・`video/mock/<番号>/` の下・`video/choices.md`、`render` は `video/mock/<番号>/` の下・`video/render/`・`video/out/`。受け入れたリスク：書き込みの絞り込みは Bash の中には掛からない。指示文と README にそう書いて、範囲の外に書かないように言う。
- **見本は既定の探す場所に置かない。** ひな形ではなく、Playwright・ffmpeg に頼り、題材も pipe-in に寄っているため。`pipe-in` には `--pipe examples/video/pipes/pipe-in-video` のようにフォルダのパスを渡す。`pipe-in` 本体には `--pipes-dir` が無いので、要件と設計で書いていた `pipe-in --pipe video --pipes-dir …` の形を README で直した（監査 A-01）。端末で答えるときは要件メモ（`--text`）を外す（`--review` と一緒に使えないため。監査 A-02）。
- **段の記録は `docs/pipeline/video/` に出る。** pipe-in はパイプごとに記録のフォルダを分けるため（設計の表の `docs/pipeline/` は誤り。監査 A-06）。受付は既定でここを読む。
- **ロゴは人から受け取り、描かない。音は既定で無し。** 付けるときも他人の録音・サンプルを使わない。動画・画像・ロゴの実ファイルは見本に入れない。
- **利用料の上限は `ask`・`script` 0.5、`mock` 3.0、`render` 2.0、`verify` 1.0 ドル。** `mock` は3案を作るので高くした。
- 監査で見つかった、指示文が書ける範囲を広く書いていたところ（A-05）と、台本の見本のパイプの場所（A-03）を直した。

## 対象外・残った課題

- 音楽の生成・同梱、ロゴの作成、Playwright・ffmpeg の入れ方の自動化、素材のダウンロード。
- 受付の認証・外への公開・複数人での利用・書き込み。
- ひな形（`generator/templates/`）への追加。使われ方を見てから考える。
- 書き出しの手本のスクリプトと、動画の場面の動く HTML（環境ごとに直す部分が大きく、古びやすいため）。
- 実機の受け入れ基準（AC-17〜22・34・36〜40・52〜57）はまだ。本物の `pipe-in` を流すと利用料（約 7 ドル）がかかるので、人が決めてから流す。

## 確かめたこと

- 足したテスト（`tests/test_video_example.py`・`tests/test_video_review.py`）は、見本を作る前に期待した理由で落ち、作ったあと 164 件すべて通った。`pytest` は全件通る。定義の検査（`pipe-in-gen check video --pipes-dir examples/video/pipes`）も問題なし。
- 受付を、手元に作った偽のプロジェクトと、引数を書き残すだけの偽の `pipe-in` で立て、Playwright で開いた。3案が明暗どちらでも出て、題に入れたタグは文字のまま出た。「この案にする」で `--review revise --feedback "2案目にする。直す点：…"` が1つの引数で渡り、直す点に `"; touch /tmp/… #` を入れてもファイルは作られなかった（AC-57 を偽物で確かめた）。「どれもびみょう」は決まった文になった。呼んでいる間はボタンが押せず、`video/` の外のこまは `<img>` を出さずに `role="alert"` で原因を出した。合言葉の無い POST は 403、`video/` の外へ出る道は 404、コンソールのエラーは0件だった。
- 本物の `pipe-in` と SDK を使う確かめはまだ（上の課題）。
