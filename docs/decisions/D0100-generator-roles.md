# D0100 generator/ は下位パッケージに分けず、作ると裏の道具の import の向きを検査で固める（両向きを禁じ、入口の cli.py の関数の中だけ例外）

## 目的

`generator/` には「作る（new・design・check・list）」と「プラグインの裏の道具（guard-hook・chat・judge-score）」の2つの役がある（D0099 の地図）。分けるかを事実で決め、推しの案（分けずに、境目を依存の向きの検査で守る）では、直す人が境目の崩れにテストで気づけ、なぜ分けなかったかを決定の記録で後から読めるようにする。コマンド名 `pipe-in-gen` と、プラグインのフックの動きは変えない。

### 要求と前提

- UR-01 pipe-in を直す人（人と Claude Code）として、`generator/` の「作る」と「プラグインの裏の道具」の境目が崩れたら（片方が、入口でないのに他方を読み込むようになったら）、テストで気づきたい。
- UR-02 pipe-in を直す人として、`generator/` を2つの下位パッケージに分けるかの判断と、その理由と、分け直す条件を、決定の記録で後から読みたい。
- UR-03 プラグインと `pipe-in-gen` を使う人として、この整理のあとも、プラグインのフック（`pipe-in-gen guard-hook` と前の名前のコマンドの `guard-hook`）と入れ済みの `pipe-in-gen` が、今までどおり動いてほしい。

- 前提：プラグインのフックは、モジュールの名前でなく、コマンドの名前 `pipe-in-gen guard-hook` で起こされる（`plugin/hooks/hooks.json:10-11`）。崩れると、モジュールの名前を変えない案でも、フックの動きが変わりうる。
- 前提：フックが起動できない・0 と 2 以外の終了コードで終わると、Claude Code は止めない失敗として道具の呼び出しを通す（D0089。公式の文書による。実機は未確認）。崩れると（止める側に倒れるなら）、守りのファイルを動かす危うさの見立てが小さくなる。
- 前提：`generator/` の直下の `.py` の品の分け方は、D0099 の地図（`docs/development/design.md:14-15`）と `tests/test_repo_map.py:158-162` で決まっていて、今回は変えない。崩れると、検査の一覧が地図と食い違う。
- 前提：import の向きは、ソースの `import` 文で決まる（`importlib` で名前を組み立てて読む・`sys.modules` を直に触る形は、今の `generator/` に無い）。崩れると、ソースを読む検査ではすり抜ける。

### 状態の問い

状態を持ち、操作や出来事で移り変わるか

答え：いいえ
理由：足すのはソースを読むだけの検査と文書で、記録（`state.json`）・設定・パイプの形や、新しい状態を足さない。

### 調べた事実

### 1. generator/ の中の import の向き

| ファイル | generator/ の中で読むもの | 本体・外で読むもの |
| --- | --- | --- |
| `cli.py`（入口・2つの役） | 先頭：`.detect`（:24）・`.render`（:25）。分岐の中だけ：`.chat_hook`・`.guard_hook`（:216-217。guard-hook）・`.chat_cmd`（:226）・`.judge_score`（:231）・`.findings_check`（:236）・`.quorum`（:241）・`.design`（:253） | 先頭：`pipe_in.pipe.definition`（:21）・`pipe_in.pipe.lint`（:22） |
| `design.py`（作る） | `.cli` の `refuse_clash`（:22）・`.detect`（:23） | `pipe_in.engine.config`・`engine.runner`（SDK を読む）・`engine.spec`・`pipe_in.pipe.definition`（:17-20） |
| `render.py`（作る） | `.detect`（:7） | 無し |
| `detect.py`（作る） | 無し | 標準ライブラリだけ（:7-12） |
| `legacy.py`（作る） | 関数の中で `.cli`（:15） | 無し |
| `findings_check.py`（作る） | 無し | 標準ライブラリだけ（:10-19） |
| `quorum.py`（作る） | `.findings_check`（:18） | 無し |
| `guard_hook.py`（裏の道具） | 無し | 標準ライブラリだけ（:23-31） |
| `chat_hook.py`（裏の道具） | `from . import guard_hook`（:19） | 関数の中で `pipe_in.pipe.chat_record`・`engine.clock`・`engine.config`・`engine.guard`・`pipe_in.pipe.definition`（:38・59・70・80-82・146） |
| `chat_cmd.py`（裏の道具） | 無し | `pipe_in.pipe.chat`（:16） |
| `judge_score.py`（裏の道具） | 無し | 標準ライブラリだけ（:9-15） |

- 裏の道具 → 作る の import は **0 件**。裏の道具どうしは `chat_hook` → `guard_hook` の1件だけ。
- 作る → 裏の道具 の import は、入口 `cli.py` の分岐の中の4件（:216・217・226・231）だけ。`cli.py` のほかの作るの部品は、裏の道具を読まない。
- 入口は1つ：`pyproject.toml:14` の `pipe-in-gen = "pipe_in_generator.cli:main"`。`cli.main`（:210-256）が、`guard-hook`・`chat`・`judge-score`・`findings-check`・`quorum` を引数の解釈より前に振り分け、残り（list・check・new・design）を `argparse` で解く。前の名前のコマンドも `pipe_in_generator.legacy` の前の名前の入口（`pyproject.toml:17`）から同じ `cli.main` に入る。
- `design.py` と `cli.py` は互いを読む（`design.py:22` が先頭で `.cli`、`cli.py:253` が分岐の中で `.design`）。
- 付け足しの事実：`guard_hook.py` は標準ライブラリだけだが、`pipe-in-gen guard-hook` の起動では、入口の `cli.py` が先頭で `pipe_in.pipe.definition`・`pipe_in.pipe.lint`・`detect`・`render` を読む（:21-25）。`definition.py:18-19` は `pipe_in.engine.config`・`engine.guard` を読む。SDK は読まないが、本体の一部はフックの起動のたびに読み込まれる。

#### 2. パッケージの形と、分けたときに直す場所の量

- `pyproject.toml:25-26`：`packages` は名前を一つずつ並べた一覧で、`pipe_in_generator` は1つだけ。`package-dir = { "pipe_in_generator" = "generator" }`。`package-data`（:31）は `*.md`（`design_rules.md`）・`templates/*/…`・`schemas/*.json`。下位パッケージを足すと、`packages` と `package-data` の両方に書き足す必要がある。
- `generator/` の中の場所の決め打ち：`cli.py:31` の `templates_dir()` が `Path(__file__).parent / "templates"`、`design.py:80` が `resources.files("pipe_in_generator").joinpath("design_rules.md")`。
- テストの読み方：`tests/conftest.py:14・25` が `generator/` を `tests/gen_loader.py` で `pipe_in_generator` として読む。`gen_loader.py:77` は `submodule_search_locations=[generator/]` で読むので、下位パッケージは置けば読める。そのかわり、**テストは `pyproject.toml` の `packages` の書き漏れに気づかない**（入れたときのパッケージを読まないため）。
- プラグインのフック：`plugin/hooks/hooks.json:10-11` は `command "pipe-in-gen"`・`args ["guard-hook"]`。モジュールの名前やパスは書いていない。`plugin/` の中に `generator/`・`pipe_in_generator` の語は無い（Grep で0件）。`hooks.json` の形は D0089-AC-05 のテストが固定している。
- 文書の中の `generator/`（`*.md` を Grep。行の数）：159 行・68 ファイル。うち決定の記録が 111 行・46 ファイル（書き換えない）、それ以外が 48 行・22 ファイル。`generator/<名前>.py` の形に絞ると 71 行・37 ファイルで、決定の記録を除くと **18 行・9 ファイル**（`docs/development/design.md` 10 行、`CLAUDE.md:51`・`SECURITY.md:9`・`docs/development/principles.md:27`・`docs/development/workflow.md:51`・`docs/guide/safety.md:128`・`.claude/skills/pipe-in/SKILL.md:172`・`.claude/agents/pipe-in-advisor.md:34`・`docs/research/specialist-on-the-fly/README.md:159` が1行ずつ）。ほかに地図の箇条書き（`design.md:14-15・21`、`README.md:116・120-121`、`README.en.md:116・120-121`）と、地図の SVG 4枚の文字、コードの docstring（`pipe_in/pipe/chat_record.py:1`・`pipe_in/pipe/judge.py:5`・`generator/__init__.py:3`・`generator/schemas/*.json:4`）。
- テストが `generator/` のファイルを名指しする所：
  - `tests/test_architecture.py`：`RULES` の `("generator", "pipe_in_generator", …)`（:23）、標準ライブラリだけの検査のパス `generator/guard_hook.py`・`judge_score.py`・`findings_check.py`（:145・156・167）、`SOURCES`（:250）。
  - `tests/test_architecture_chat.py:26-27・32-33・98・107`（`generator/chat_cmd.py`・`chat_hook.py` のパスとモジュールの名前）。
  - `tests/test_architecture_quorum.py:16・37・45`（`GENERATOR / "quorum.py"`）。
  - `tests/test_repo_map.py:158-162` の `GENERATOR_KINDS` と、`:615` の `(ROOT / "generator").glob("*.py")`（直下だけを数え、11 個以上を求める。下のフォルダに移すと落ちる）。
  - `tests/test_rename.py:43`（`package-dir` が `{"pipe_in_generator": "generator"}`）・`:180・182`（古い名前の出てよいファイルの一覧に `generator/legacy.py`・`generator/guard_hook.py`）。
  - `tests/test_plugin.py:280-281`（design.md の表に `generator/judge_score.py`・`generator/guard_hook.py` の行がある）。
  - `tests/test_rules.py` の D0002-AC-04（design.md の表のパスの実在）。
  - モジュールを import する行：裏の道具（`guard_hook`・`chat_hook`・`chat_cmd`・`judge_score`）が 15 行・12 ファイル、作るの部品（`detect`・`design`・`render`・`findings_check`・`quorum`）が 15 行・11 ファイル。`cli` を読む行は 30 行ほど（`cli.py` を上に残せば直さない）。
  - ひな形と指摘の形の場所（ひな形を動かすときだけ）：`tests/test_examples.py:24`・`test_plugin_eval_rounds.py:48`・`test_default_protected.py:428`・`test_mcp_json_protected.py:338`・`test_chat_output_name.py:60`・`test_findings_check.py:17`。
- 見積もり（分ける案 C。`cli.py`・`legacy.py` は上に残し、ひな形も動かさない形）：コード 10 行ほど（`cli.py` の import 8 行・`design.py:22-23・80`・`render.py:7`・`quorum.py:18`・`chat_hook.py:19`）と `pyproject.toml` の2か所。テスト 40 行ほど・20 ファイルほど。文書 18 行・9 ファイルと地図の箇条書き3か所・SVG 4枚・docstring 5か所。うち `CLAUDE.md` と `.claude/` の2か所は文書係が書けず、案を返してメインが人の承認で直す。決定の記録の 53 行は書き換えず、古いパスのまま残る。

#### 3. 守りの仕組みを動かすことの危うさ

- フックが起動できない・0 と 2 以外の終了コードで終わると、Claude Code は「止めない失敗」として道具の呼び出しを通す（D0089 の目的と「公式の文書で確かめたこと」。`onFailure` は付けていない。D0089-AC-05）。`guard_hook` を動かして import が壊れると、Python は終了コード 1 で終わるので、**pipe-builder と pipe-judge の守りが黙って外れる**。会話の中の段（`/pipe-in:pipe-run`）は流す前に `pipe-probe` で確かめるが（D0077）、pipe-builder と pipe-judge にはその確かめが無い（D0089-AC-07）。
- 壊れ方の主な道は、`pyproject.toml` の `packages` の書き漏れ（入れたパッケージに下位パッケージが入らない）。上のとおり、テストはこれに気づかない。
- pip で入れた利用者：古い版は、入れ直すまで古いファイルのまま動く。入れ直すと pip が古いファイルを消して新しい形にするので、パスが混ざることはふつう無い。プラグインのフックはコマンドの名前で起こすので、プラグインの版と `pipe-in-gen` の版がずれても、モジュールの名前の変更は効かない（前の名前のコマンドの `guard-hook` も同じ入口）。
- `pipe_in_generator.guard_hook` などのモジュールの名前を外から直に import する使い方は、文書に書いていない（Grep で `python -m pipe_in_generator` は D0086 の「今は動かない」の記述だけ）。それでも、名前を変えると、そう使っている人は ImportError になる。前の名前の写し（再輸出のモジュール）を置けば防げるが、守りのコードに名前が2つでき、テストの差し替え（`monkeypatch`）が写しのほうに効いて本物に効かない、という取り違えが起きうる。
- 開発の手元：`pip install -e` で入れた `pipe-in-gen` が新しい下位パッケージを見つけるかは、setuptools の入れ方による（確かめていない）。見つけないと、このリポジトリの会話でもプラグインのフックが止めない失敗になる。
- 開発用の決まりがパスで書かれている：助言を流すかの判断が `generator/guard_hook.py` のパスを見る（`.claude/skills/pipe-in/SKILL.md:172`・`docs/development/workflow.md:51`）。直し忘れると、フックを直しても助言が流れない（黙って確かめが減る）。

#### 4. ファイルを動かさずに依存の向きの検査を足せるか

- 足せる。`tests/test_architecture.py` の `_imports`（:35-52。相対の import を絶対の名前に直す）と `_module_name`（:27-32）は、モジュールの名前の一覧と組み合わせるだけで、作る ↔ 裏の道具 の向きを見られる。`tests/test_architecture_quorum.py:13` がすでに同じ部品を import して使っている。
- 今の検査で塞がっていない道：`chat_cmd.py`・`chat_hook.py` は `pipe_in_generator` のどれを読んでもよい形になっている（`tests/test_architecture_chat.py:26-27` の許す一覧が `pipe_in_generator` まるごと）。SDK を読み込む部品（`design.py`）を読むと子プロセスの検査（:104-113）が落とすが、`cli`・`render`・`detect`・`findings_check`・`quorum`・`legacy` を読んでも落ちない。作る → 裏の道具（`cli.py` 以外）は、どの検査も見ていない。`guard_hook.py`・`judge_score.py` は標準ライブラリだけの検査（`test_architecture.py:141-160`）で、作るを読めば落ちる。
- 分け方の一覧は、D0099 の `tests/test_repo_map.py:158-162` の `GENERATOR_KINDS`（プラグイン4つ・作る7つ）と同じものを使える。

## 機能要件と受け入れ基準

テストは新しいファイル `tests/test_architecture_generator_roles.py`（36 件）。AC-11 は手で確かめるもの。

### 機能要件

人が選んだ案 B（分けない・依存の向きの検査だけ足す）で書く。案の比べは「決めたこと（人の答え）」に残す。

- FR-01（UR-01）`generator/` の `.py`（`__init__.py` を除く）を、モジュールの名前の2つの一覧に分ける：作る（`cli`・`design`・`render`・`detect`・`legacy`・`findings_check`・`quorum`）と、裏の道具（`guard_hook`・`chat_cmd`・`chat_hook`・`judge_score`）。一覧は新しいアーキテクチャの検査のファイル（`tests/test_architecture_<名前>.py`。D0075）に置き、分け方は D0099 の `GENERATOR_KINDS` と同じにする（食い違えば落ちる）。
- FR-02（UR-01）裏の道具 → 作る の import を禁じる。相対（`from . import render`・`from .cli import main`）と絶対（`import pipe_in_generator.design`・`from pipe_in_generator import detect`）の両方を見る。裏の道具どうし（`chat_hook` → `guard_hook`）は許す。
- FR-03（UR-01）作る → 裏の道具 の import を禁じる。例外は入口 `cli.py` だけで、`cli.py` が裏の道具を読むのは関数の中（コマンドの分岐の中）だけにする。モジュールの先頭で読むと落ちる。
- FR-04（UR-01）`generator/` の下の `.py`（下のフォルダも含む。`__init__.py` と `__pycache__` を除く）が、2つの一覧のどちらかにちょうど1回ずつ入っていることを確かめる。一覧に無いファイルがあると、そのファイルのパスと直し方（どちらかの一覧に足し、D0099 の地図と `GENERATOR_KINDS` も直す）を出して落ちる。一覧にあってファイルが無いときも落ちる。
- FR-05（UR-01）検査そのものが働くことを、`tmp_path` に作った偽の `generator/` で確かめる（止める形は見つけ、許す形は通す）。
- FR-06（UR-02）決定の記録 `docs/decisions/D0100-<名前>.md` に、分けない（案 B）と決めた理由、調べた事実（import の向き・直す量の数・フックが動かないと止めない失敗になること・テストが `packages` の書き漏れに気づかないこと）、選ばなかった案（A・C）とその理由、分け直す条件を書き、一覧（`docs/decisions/README.md`）に1行足す。D0099 の「対象外・残った課題」の2項（分けるか・依存の向きの検査を品の単位に広げるか）に答えたことを書く（D0099 は書き換えない）。
- FR-07（UR-01・UR-02）`docs/development/design.md` の「## 本体の依存の向き」の節に、`generator/` の中の向き（作ると裏の道具は互いに読まない・入口 `cli.py` だけが両方を分岐の中で読む・検査のファイルの名前）を1〜2行足す。文字の図は変えない（D0099-AC-04）。
- FR-08（UR-03）ファイルを動かさず、名前を変えない。`generator/` の中のファイル・`pyproject.toml`（`scripts`・`packages`・`package-dir`・`package-data`）・`plugin/hooks/hooks.json`・`generator/guard_hook.py`・`generator/chat_hook.py`・`pipe_in/engine/guard.py`・`.claude/hooks/pipe_in_guard.py` は変えない。

### 受け入れ基準

- D0100-AC-01（FR-01・FR-04）今の `generator/` の `.py`（`__init__.py` を除く 11 個）が、作るか裏の道具のどちらかの一覧に、ちょうど1回ずつ入る。2つの一覧の分け方が `tests/test_repo_map.py` の `GENERATOR_KINDS`（プラグイン ↔ 裏の道具、作る ↔ 作る）と同じ。（今のまま通る。守る）
- D0100-AC-02（FR-02）今の裏の道具の4つ（`guard_hook.py`・`chat_cmd.py`・`chat_hook.py`・`judge_score.py`）のどれも、作るの7つのどれも import しない。（今のまま通る。守る）
- D0100-AC-03（FR-03）今の作るのうち `cli.py` を除く6つは、裏の道具の4つのどれも import しない。`cli.py` が裏の道具を読む import は、どれも関数の中にあり、モジュールの先頭（`tree.body` の直下）には無い。（今のまま通る。守る）
- D0100-AC-04（FR-02・FR-05）偽の `generator/` で、裏の道具のファイルが `from .cli import main`・`from . import render`・`import pipe_in_generator.design`・`from pipe_in_generator import detect` のそれぞれで作るを読むと、4つとも見つける。`from . import guard_hook`（裏の道具どうし）と、標準ライブラリ・`pipe_in.pipe` の import は見逃す。
- D0100-AC-05（FR-03・FR-05）偽の `generator/` で、作るのファイル（`design.py` など）が `from .guard_hook import decide`・`from . import chat_hook`・`import pipe_in_generator.judge_score` で裏の道具を読むと、3つとも見つける。偽の `cli.py` が先頭で裏の道具を読むと見つけ、関数の中で読む形は通す。
- D0100-AC-06（FR-04・FR-05）偽の `generator/` に、一覧に無い `.py` を直下に1つと下のフォルダに1つ置くと、どちらもパスと「どちらかの一覧に足す」直し方を含む文で見つける。一覧にあってファイルが無い名前も見つける。`__init__.py` と `__pycache__` の中は数えない。
- D0100-AC-07（FR-06）`docs/decisions/D0100-<名前>.md` があり、決定の記録の形の検査（`tests/test_rules.py`。D0085 以降の ID のつながりを含む）が通る。「決めたことと理由」に、選んだ案（分けない・検査だけ足す）と、選ばなかった案（何もしない・下位パッケージに分ける）とその理由、分け直す条件があり、調べた事実として「止めない失敗」と `packages` の語がある。一覧 `docs/decisions/README.md` に D0100 の行があり、`tests/test_doc_shape.py` が通る。
- D0100-AC-08（FR-07）`docs/development/design.md` の「## 本体の依存の向き」の節に、作ると裏の道具の向きの文と、新しい検査のファイルの名前（実在する）がある。文字の図は今のまま（D0099-AC-04 のテストが書き換えずに通る）。design.md の表の行は 800 字以内のまま（`tests/test_doc_shape.py`）。
- D0100-AC-09（FR-08・NFR-01）既存のテスト（`tests/test_architecture.py`・`test_architecture_chat.py`・`test_architecture_quorum.py`・`test_repo_map.py`・`test_guard_matrix.py`・`test_hook_failure.py`・`test_plugin.py`）が書き換えずに通り、`pytest -q` の全体が緑。
- D0100-AC-10（FR-08・NFR-01）前の名前の入口が今までどおり動く：前の名前のコマンドと `pipe-in-gen` の `guard-hook` の標準出力が、止めるときも止めないときもバイト単位で同じ（`tests/test_rename.py` の D0006-AC-04 のテストが書き換えずに通る）。`pyproject.toml` の `scripts` が `pipe_in_generator.cli:main` と `pipe_in_generator.legacy` の前の名前の入口 のまま（D0006-AC-01 のテストが書き換えずに通る）。
- D0100-AC-11（FR-08・NFR-01）（手で）検証の段で `git diff --stat main...HEAD` を見て、`generator/` の中・`pyproject.toml`・`plugin/hooks/hooks.json`・`pipe_in/engine/guard.py`・`.claude/hooks/pipe_in_guard.py` に差分が無い。

### 非機能要件

- NFR-01（UR-03）守りの仕組みが変わらない
  - きっかけ：この変更（検査と文書の足し）を入れる。
  - 状況：プラグインを有効にした会話で、道具を呼ぶたびに `pipe-in-gen guard-hook` が動く。利用者の手元には、前の版の `pipe-in-gen` と前の名前のコマンドもありうる。
  - 応答：守りのファイル（FR-08 の一覧）に差分が無く、止める範囲も止め方も今と同じ。`pipe-in-gen guard-hook` と前の名前のコマンドの `guard-hook` の標準出力は今までどおりバイト単位で同じ。
  - 測り方：検証の段で `git diff --stat main...HEAD` を見る（手で）。守りの比較表（`tests/test_guard_matrix.py`）・`tests/test_hook_failure.py`・`tests/test_rename.py` が書き換えずに通る。

## 決めたことと理由

- **`generator/` は下位パッケージに分けない（案 B：分けないで、依存の向きの検査だけ足す）。** D0099 で「地図を見てから決める」とした件をここで決めた。
  - 下位パッケージに分ける案（C）は、コード 10 行ほど・`pyproject.toml` の `packages` と `package-dir`・テスト 20 ファイルほど・文書と地図と SVG を直す量に比べて、得るもの（フォルダで境目が見える）が小さい。いちばんの危うさは守りの仕組み：`packages` に書き漏れがあるとフック `pipe-in-gen guard-hook` の import が壊れて終了コード 1 で終わり、Claude Code はそれを止めない失敗として扱う（D0089）。pipe-builder と pipe-judge には流す前の確かめが無いので、守りが黙って外れる。テストはソースのパスから読むので、この書き漏れに気づかない。
  - 何もしない案（A）は、今は違反が 0 件でも、`chat_cmd`・`chat_hook` が `pipe_in_generator` のどれを読んでも落ちない道と、作る → 裏の道具の向きをどの検査も見ていない道の2つが開いたままになる。
  - 案 B は、ファイル・名前・守り・`pyproject.toml` を動かさず、今の形を検査で固める。直すのはテスト1つと文書だけ。
- **禁じる向きは両方。** 裏の道具は作るを読まない（関数の中でも）。作るが裏の道具を読んでよいのは入口 `cli.py` の関数の中だけ（今はコマンドの分岐。人の答えで「どの関数の中でも」にした。入口を関数に分けても検査を直さずに済む）。裏の道具から作るへ読めると、守りの周りに本体が入りやすくなるため。
- **役の一覧は1つだけを元にする。** D0099 の `tests/test_repo_map.py` の `GENERATOR_KINDS`（作る・プラグイン）を読み、写さない。数と名前も一覧から作る（監査の A-02）。照らすのは `generator/` の直下の `.py` だけで、下のフォルダの `.py`（`templates/`・`schemas/`・`__pycache__` の中は除く）は「分けないと決めた」の文で落とす（監査の A-01）。
- **分け直す条件。** 次のどれかが起きたら、分け直すかを決定の記録で決め直す：裏の道具を別の配布物に分けたくなった（`pipe-in-gen` を pip で入れずにプラグインだけで動かしたいなど）、裏の道具が作るの部品を読む必要が出た、役の境目をこの検査が守りきれなくなった。分け直すときは、`packages` の書き漏れを見る検査（入れた配布物の中に下位パッケージがそろっているか）と、守りが黙って外れないことを示すテストを先に足す。

## 対象外・残った課題

- `pipe-in-gen guard-hook` を起こすたびに、入口 `generator/cli.py` の先頭の import（`pipe_in.pipe`）で本体の一部が読み込まれる。「標準ライブラリだけ」が成り立つのは `guard_hook.py`・`judge_score.py` のモジュールの中だけ。入口を軽くするかは別の件として計画ボードに置いた（文書は実物に合わせて直した。監査の A-04）。
- 依存の向きの検査を、品（アプリ・作る・プラグイン・開発用）の単位に広げること（D0099 の残り）。
- `tests/test_architecture_chat.py` の `CHAT_FILES` は `pipe_in_generator` 全体を許したまま。新しい検査がその中の 裏の道具 → 作る を止めるので食い違いはないが、絞るかは別の件。

## 確かめたこと

- `python -m pytest -q` の全体が通る（決定の記録を書いたあと）。拡張（`vscode/`）は触っていない。
- `python -m pipe_in skill spec-check`：UR 3・FR 8・NFR 1・AC 11、問題 0 件。
- AC-11（手で）：`generator/`・`pipe_in/`・`plugin/`・`.claude/`・`pyproject.toml` に差分が無い（`origin/main` と比べた）。CLAUDE.md の差分は、依存の向きの括弧の1句（`pipe_in_generator` は `pipe_in.dev` を読まない）だけ。

### 監査で直したもの

- 監査（8 件）から承認して直した：検査の照らす範囲を直下の `.py` に絞り、下のフォルダは分けない決まりの文で落とす（A-01）。テストの中の数と名前の写しをやめて `GENERATOR_KINDS` から作る（A-02）。`generator/` の直下に `.py` を足したときは地図の箇条書きにも書く例外を workflow.md の「8.」に書いた（A-03）。守りの入口の「標準ライブラリだけ」を実物に合わせた（A-04）。`pipe_in_generator` は `pipe_in.dev` を読まないことを design.md と CLAUDE.md に書いた（A-05）。検査していない「cli.py が先頭で読む部品」を「今は」にした（A-06）。例外を「関数の中（今はコマンドの分岐）」にした（A-07）。SVG 4枚の説明を「主な中身は」にそろえた（D0099 の直し漏れ。A-08）。A-01・A-02 はテスト先行の段に戻して直した。
- 助言と審査は流さなかった（理由：変えたファイルに `.claude/`・`plugin/`・守りのファイルが無い）。
