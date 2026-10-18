"""動画を作るパイプの手元の受付（examples/video/review_server.py）の検査。SDK も本物の pipe-in も呼ばない。

- 受付は examples/ の中にありパッケージではないので、compile + exec で ModuleType に読み込む
  （importlib の spec は .pyc を作ってしまうため使わない。examples/ に __pycache__ を作らない）。
- pipe-in の呼び出し（run_command）は、モジュールの属性を偽物に差し替える。
- HTTP の検査は ThreadingHTTPServer(("127.0.0.1", 0), …) を別スレッドで立てて、http.client で自分に送る。
  プロジェクトは tmp_path で、実物には書かない。

テストが決めた受付の口（設計の「…」の部分。実装はこれに合わせる）：
- HOST = "127.0.0.1"（定数）。Action(kind, feedback)。NONE_OF_THEM・MAX_NOTE・TAIL_LINES は定数。
- check_request(method, path, host_header, port, token_header, token) -> int | None
    問題が無ければ None、断るときは HTTP の状態（403・405）を返す。
- resolve_served_path(project, rel) の rel は「/files/ の後ろの相対パス」（例 "video/mock/1/a.png"）。
- make_handler(*, project, work_dir, template, exe, base_args, token, controller=None) -> ハンドラのクラス。
    work_dir は state.json の入っているフォルダ。run_command はモジュールの属性を呼び出しのたびに引く
    （差し替えが効くように）。Host の port は self.server.server_address[1] から取る。
- main(argv) は --port（既定 8765）・--project・--work-dir・--pipe-in を読み、"--" より後ろを起動時の引数にする。
    待ち受けは serve(...) に HOST を渡して始める（テストは serve を差し替える）。
- POST /action は、断るなら 4xx、受け付けたら 200 か 202、実行中の2つ目は 409。
"""

from __future__ import annotations

import http.client
import inspect
import json
import re
import sys
import threading
import types
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "examples" / "video" / "review_server.py"

_loaded: types.ModuleType | None = None


def rs() -> types.ModuleType:
    """受付を compile + exec で読み込む（.pyc を作らない）。まだ無ければ、その旨で失敗にする。"""
    global _loaded
    assert SERVER_PATH.is_file(), f"{SERVER_PATH.relative_to(ROOT)} がありません（受付をまだ作っていない）"
    if _loaded is None:
        module = types.ModuleType("review_server")
        module.__file__ = str(SERVER_PATH)
        sys.modules["review_server"] = module
        exec(compile(SERVER_PATH.read_text(encoding="utf-8"), str(SERVER_PATH), "exec"), module.__dict__)
        _loaded = module
    return _loaded


BASE = ["--pipe", "video", "--pipes-dir", "examples/video/pipes"]
TEMPLATE = '<!doctype html><script type="application/json" id="page-data"><!--PAGE-DATA--></script><p>t</p>'
TOKEN = "tok-for-test"
STATE_NAME = "state.json"


# ---- コマンドの並び（AC-41〜45） ---------------------------------------------------------


def test_build_command_shapes():
    """D0011-AC-41: 3種類の操作が [実行ファイル, 起動時の引数, --review, 種類, …] になる。revise だけ --feedback と値が続く。"""
    m = rs()
    assert m.build_command("pipe-in", BASE, "approve") == ["pipe-in", *BASE, "--review", "approve"]
    assert m.build_command("pipe-in", BASE, "quit") == ["pipe-in", *BASE, "--review", "quit"]
    assert m.build_command("pipe-in", BASE, "revise", "2案目にする。") == [
        "pipe-in", *BASE, "--review", "revise", "--feedback", "2案目にする。",
    ]  # fmt: skip


@pytest.mark.parametrize("kind", ["run", "", "approve; rm -r", "Approve", "APPROVE", " approve", "approve\n", "revise2"])
def test_build_command_rejects_other_kinds(kind):
    """D0011-AC-42: revise・approve・quit 以外の操作名（大文字小文字違い・空・つなげた文）は断る。"""
    with pytest.raises(ValueError):
        rs().build_command("pipe-in", BASE, kind, "x" if kind else None)


def test_build_command_rejects_feedback_for_approve_and_quit():
    """D0011-AC-42: approve・quit に feedback を付けるのは断る。"""
    m = rs()
    for kind in ("approve", "quit"):
        with pytest.raises(ValueError):
            m.build_command("pipe-in", BASE, kind, "1案目にする。")


@pytest.mark.parametrize("word", ["--review", "--feedback", "--yes", "--pause", "--auto"])
def test_build_command_rejects_extra_pipe_in_options(word):
    """D0011-AC-42: 起動時の引数に、受付が決める部分（--review・--feedback・--yes・--pause・--auto）が混ざるのを断る。"""
    with pytest.raises(ValueError):
        rs().build_command("pipe-in", [*BASE, word], "approve")


def test_build_command_has_no_door_for_extra_arguments():
    """D0011-AC-42: 関数の引数に、任意の追加引数を受ける口（*args・**kwargs）が無い。"""
    params = inspect.signature(rs().build_command).parameters
    assert list(params) == ["exe", "base_args", "kind", "feedback"]
    assert not [p for p in params.values() if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD)]


FEEDBACKS = [
    "2案目にする。直す点：; rm -r /",
    "1案目にする。直す点：a && b",
    "1案目にする。直す点：$(touch x)",
    "1案目にする。直す点：一行目\n二行目",
    '1案目にする。直す点："引用" と \'単\'',
    "--yes",
    "--review approve",
    "最後の字幕を短く、色を明るく。日本語の文",
]


@pytest.mark.parametrize("text", FEEDBACKS)
def test_feedback_is_one_argument(text):
    """D0011-AC-43: 直す点に ; && $(…) 改行 引用符 -- で始まる語 日本語が入っていても、文は --feedback の次の1つの要素のまま。"""
    cmd = rs().build_command("pipe-in", BASE, "revise", text)
    assert len(cmd) == 1 + len(BASE) + 4
    assert cmd[-2:] == ["--feedback", text]
    assert cmd[: 1 + len(BASE)] == ["pipe-in", *BASE]


def test_command_is_run_without_shell(monkeypatch, tmp_path):
    """D0011-AC-43: 呼ぶときは、リストのまま shell=False で呼ぶ（偽の subprocess.run で確かめる）。"""
    m = rs()
    seen: list[tuple[tuple, dict]] = []

    def fake_run(*args, **kwargs):
        seen.append((args, kwargs))
        return types.SimpleNamespace(returncode=5, stdout="", stderr="e")

    monkeypatch.setattr(m.subprocess, "run", fake_run)
    cmd = m.build_command("pipe-in", BASE, "revise", "1案目にする。直す点：; touch x #")
    assert m.run_command(cmd, tmp_path) == (5, "e")
    (args, kwargs), = seen
    assert isinstance(args[0], list) and args[0] == cmd
    assert kwargs.get("shell", False) is False
    assert Path(kwargs["cwd"]) == tmp_path


@pytest.mark.parametrize("bad", [0, -1, 1.5, "1", True, None])
def test_parse_action_rejects_bad_numbers(bad):
    """D0011-AC-44: 案の番号は 1 以上の整数だけ。0・負・小数・文字・真偽・空は断る。"""
    with pytest.raises(ValueError):
        rs().parse_action({"op": "choose", "number": bad, "note": ""})


def test_parse_action_number_and_length():
    """D0011-AC-44: 1・3 は通り、直す点は 1000 文字まで（1001 文字は断る）。文は数字で始まる。"""
    m = rs()
    a = m.parse_action({"op": "choose", "number": 3, "note": ""})
    assert (a.kind, a.feedback) == ("revise", "3案目にする。")
    b = m.parse_action({"op": "choose", "number": 1, "note": "最後の字幕を短く"})
    assert (b.kind, b.feedback) == ("revise", "1案目にする。直す点：最後の字幕を短く")
    assert m.MAX_NOTE == 1000
    ok = m.parse_action({"op": "choose", "number": 1, "note": "あ" * 1000})
    assert ok.feedback.startswith("1案目にする。")
    with pytest.raises(ValueError):
        m.parse_action({"op": "choose", "number": 1, "note": "あ" * 1001})
    with pytest.raises(ValueError):
        m.parse_action({"op": "choose", "number": 1, "note": 5})
    with pytest.raises(ValueError):
        m.parse_action({"op": "run", "number": 1, "note": ""})


def test_parse_action_approve_and_quit_have_no_feedback():
    """D0011-AC-41: approve・quit の操作は feedback なしの Action になる。"""
    m = rs()
    assert (m.parse_action({"op": "approve"}).kind, m.parse_action({"op": "approve"}).feedback) == ("approve", None)
    assert (m.parse_action({"op": "quit"}).kind, m.parse_action({"op": "quit"}).feedback) == ("quit", None)


@pytest.mark.parametrize("note", ["", "; rm -r /", "任意の文", "x" * 5000])
def test_none_of_them_uses_fixed_sentence(note):
    """D0011-AC-45: 「どれもびみょう」は、人の入力が何でも決まった文の revise になる（人の文は混ざらない）。"""
    m = rs()
    assert m.NONE_OF_THEM == "どれもびみょう。別の方向で出し直して"
    a = m.parse_action({"op": "none", "number": 2, "note": note})
    assert (a.kind, a.feedback) == ("revise", m.NONE_OF_THEM)


# ---- 待ち受けと受け付ける要求（AC-46・47） ------------------------------------------------


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "localhost", "", "192.168.1.5", "8.8.8.8", "example.com"])
def test_check_bind_rejects_other_addresses(host):
    """D0011-AC-46: 127.0.0.1 以外（0.0.0.0・::・localhost・空・外のアドレス）の待ち受けは断る。"""
    with pytest.raises(ValueError):
        rs().check_bind(host)


def test_bind_address_is_loopback_only(tmp_path, monkeypatch, capsys):
    """D0011-AC-46: 待ち受けは 127.0.0.1 の定数。main は --host の引数を持たず、既定のポートは 8765。"""
    m = rs()
    m.check_bind("127.0.0.1")
    assert m.HOST == "127.0.0.1"

    with pytest.raises(SystemExit):
        m.main(["--help"])
    assert "--host" not in capsys.readouterr().out
    with pytest.raises(SystemExit) as e:
        m.main(["--host", "0.0.0.0", "--", *BASE])
    assert e.value.code not in (0, None)

    seen: list[tuple[tuple, dict]] = []
    monkeypatch.setattr(m, "serve", lambda *a, **k: seen.append((a, k)))
    code = None
    try:
        code = m.main(["--project", str(tmp_path), "--pipe-in", sys.executable, "--", *BASE])
    except SystemExit as exit_:
        code = exit_.code
    assert code in (None, 0)
    values = [*seen[0][0], *seen[0][1].values()]
    assert "127.0.0.1" in values and 8765 in values


def test_main_rejects_forbidden_start_args_and_missing_exe(tmp_path, monkeypatch):
    """D0011-AC-42: 起動時の引数に --review などがあると断る。pipe-in が見つからないときは起動時に終わる。"""
    m = rs()
    monkeypatch.setattr(m, "serve", lambda *a, **k: None)
    for word in ["--review", "--feedback", "--yes", "--pause", "--auto"]:
        with pytest.raises(SystemExit) as e:
            m.main(["--project", str(tmp_path), "--pipe-in", sys.executable, "--", *BASE, word])
        assert e.value.code not in (0, None), word
    with pytest.raises(SystemExit) as e:
        m.main(["--project", str(tmp_path), "--pipe-in", "no-such-pipe-in-xyz", "--", *BASE])
    assert e.value.code not in (0, None)


OK_HOST = "127.0.0.1:8765"


@pytest.mark.parametrize(
    "method,path,host,token_header,expected",
    [
        ("POST", "/action", "127.0.0.1:8765", TOKEN, None),
        ("POST", "/action", "localhost:8765", TOKEN, None),
        ("POST", "/action", "evil.example:8765", TOKEN, 403),
        ("POST", "/action", "127.0.0.1:9999", TOKEN, 403),
        ("POST", "/action", None, TOKEN, 403),
        ("POST", "/action", OK_HOST, None, 403),
        ("POST", "/action", OK_HOST, "wrong", 403),
        ("GET", "/action", OK_HOST, TOKEN, 405),
        ("PUT", "/action", OK_HOST, TOKEN, 405),
        ("GET", "/", OK_HOST, None, None),
        ("GET", "/state", OK_HOST, None, None),
        ("GET", "/files/video/a.png", OK_HOST, None, None),
        ("GET", "/", "evil.example:8765", None, 403),
    ],
)
def test_request_checks_host_token_and_method(method, path, host, token_header, expected):
    """D0011-AC-47: Host が違う・合言葉が無い／違う・/action に POST 以外は、断る（403・405）。正しい組み合わせは通る（None）。"""
    assert rs().check_request(method, path, host, 8765, token_header, TOKEN) == expected


def test_token_is_compared_in_constant_time():
    """D0011-AC-47: 合言葉は hmac.compare_digest で比べる。"""
    assert SERVER_PATH.is_file(), f"{SERVER_PATH.relative_to(ROOT)} がありません（受付をまだ作っていない）"
    assert "hmac.compare_digest" in SERVER_PATH.read_text(encoding="utf-8")


# ---- 配るファイルの道（AC-48・65） ---------------------------------------------------------


@pytest.fixture
def project(tmp_path):
    """tmp_path の中に video/ と、その外のファイルを作る。"""
    p = tmp_path / "proj"
    (p / "video" / "mock" / "1").mkdir(parents=True)
    (p / "video" / "mock" / "1" / "a.png").write_bytes(b"\x89PNG-test")
    (tmp_path / "x.png").write_bytes(b"outside-secret")
    (p / "secret.txt").write_text("outside video", encoding="utf-8")
    return p


@pytest.mark.parametrize(
    "rel",
    [
        "../x.png",
        "video/../secret.txt",
        "/etc/passwd",
        "%2e%2e/x.png",
        "video/%2e%2e/secret.txt",
        "video/mock/1/a\x00.png",
        "video\\mock\\1\\a.png",
        "",
        "video",
        "video/mock",
        "other/a.png",
        "secret.txt",
        "video/missing.png",
    ],
)
def test_served_path_stays_inside_video(project, rel):
    """D0011-AC-48: ..・絶対パス・%2e%2e・NUL・\\・video/ の外・フォルダ・無いファイルは配らない（None）。"""
    assert rs().resolve_served_path(project, rel) is None


def test_served_path_allows_files_inside_video(project):
    """D0011-AC-48: video/ の中のファイルは配る。"""
    got = rs().resolve_served_path(project, "video/mock/1/a.png")
    assert got is not None and got.resolve() == (project / "video/mock/1/a.png").resolve()


def test_served_path_refuses_symlink_leaving_video(project, tmp_path):
    """D0011-AC-48: video/ の中から外のファイル・フォルダを指す記号リンクは配らない。作れない環境では skip。"""
    try:
        (project / "video" / "link.png").symlink_to(tmp_path / "x.png")
        (project / "video" / "linkdir").symlink_to(project, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("記号リンクを作れない環境")
    m = rs()
    assert m.resolve_served_path(project, "video/link.png") is None
    assert m.resolve_served_path(project, "video/linkdir/secret.txt") is None


def test_served_path_rejects_image_outside_video(project):
    """D0011-AC-65: データの frames に ../x.png・/etc/x.png のような video/ の外の場所が入っていても、配る道（AC-48 と同じ）は断る。"""
    m = rs()
    assert m.resolve_served_path(project, "../x.png") is None
    assert m.resolve_served_path(project, "/etc/x.png") is None
    assert m.resolve_served_path(project, "video/../../x.png") is None


# ---- ページに入れる文字（AC-49・60） -------------------------------------------------------

EVIL = "</script><img src=x onerror=alert(1)>&  "


def test_embed_json_escapes_markup():
    """D0011-AC-60: embed_json は < > & と U+2028/2029 をエスケープし、json.loads で元に戻る。"""
    m = rs()
    out = m.embed_json({"x": "</script><img onerror=1>"})
    assert "<" not in out and ">" not in out
    assert json.loads(out) == {"x": "</script><img onerror=1>"}
    out2 = m.embed_json({"x": EVIL})
    assert not any(c in out2 for c in "<>&  ")
    assert json.loads(out2) == {"x": EVIL}


def test_render_page_replaces_marker_only():
    """D0011-AC-49: render_page は目印をデータに置き換える。目印が無いテンプレートは断る。"""
    m = rs()
    page = m.render_page(TEMPLATE, {"error": EVIL})
    assert "<!--PAGE-DATA-->" not in page
    assert page.count("</script>") == 1  # テンプレート自身の閉じタグだけ
    with pytest.raises(ValueError):
        m.render_page("<p>目印なし</p>", {})


def page_data(html: str) -> dict:
    found = re.search(r'<script type="application/json" id="page-data">(.*?)</script>', html, re.DOTALL)
    assert found, html[:300]
    return json.loads(found.group(1))


def test_page_escapes_untrusted_text():
    """D0011-AC-49: <script> を含む案の文と失敗の出力を渡しても、ページの文字列に閉じタグ・生のタグが現れない。"""
    m = rs()
    data = {
        "options_data": {"options": [{"number": 1, "title": "<script>alert(1)</script>", "summary": "s", "frames": []}]},
        "log_tail": ["</script><img onerror=1>"],
        "error": None,
    }
    page = m.render_page(TEMPLATE, data)
    assert page.count("</script>") == 1
    assert "<img" not in page and "alert(1)</script>" not in page
    assert page_data(page)["log_tail"] == ["</script><img onerror=1>"]


# ---- 状態の読み取り（AC-52 の支え・AC-61） -------------------------------------------------


def test_pending_stage_and_options_path():
    """D0011-AC-52: state.json の pending_review.stage を読む。壊れた JSON・形違いは None。script・mock の案のデータの場所を返す。"""
    m = rs()
    assert m.pending_stage(json.dumps({"pending_review": {"stage": "script"}})) == "script"
    assert m.pending_stage(json.dumps({"pending_review": None})) is None
    assert m.pending_stage(json.dumps({"pending_review": "script"})) is None
    assert m.pending_stage(json.dumps([1, 2])) is None
    assert m.pending_stage("{broken") is None
    assert m.pending_stage("") is None
    assert m.options_path("script") == "video/script/options.json"
    assert m.options_path("mock") == "video/mock/options.json"
    assert m.options_path("render") is None
    assert m.options_path("ask") is None


@pytest.mark.parametrize(
    "text",
    ["{not json", "[]", '"x"', "null", json.dumps({"options": 3}), json.dumps({"round": 1}), ""],
    ids=["broken", "list", "string", "null", "options-not-list", "no-options", "empty"],
)
def test_load_options_reports_cause(text):
    """D0011-AC-61: 案のデータが壊れている・オブジェクトでない・options が配列でないときは、(None, 原因の文)。"""
    data, error = rs().load_options(text)
    assert data is None and isinstance(error, str) and error


def test_load_options_reads_good_data():
    """D0011-AC-61: 正しいデータは (データ, None)。"""
    good = {"round": 1, "options": [{"number": 1, "title": "t", "summary": "s", "frames": ["video/mock/1/frames/a.png"]}]}
    assert rs().load_options(json.dumps(good)) == (good, None)


# ---- 状態の遷移（AC-50） -------------------------------------------------------------------


@pytest.mark.parametrize("code,expected", [(5, "next"), (0, "done"), (1, "failed"), (2, "failed"), (137, "failed"), (None, "failed")])
def test_classify_exit(code, expected):
    """D0011-AC-50: 終了コード 5 は次の確認、0 は終わり、ほか（None を含む）は失敗。"""
    assert rs().classify_exit(code) == expected


def tail_text(snapshot: dict) -> str:
    tail = snapshot["log_tail"]
    return "\n".join(tail) if isinstance(tail, list) else str(tail)


def test_controller_serializes_and_classifies():
    """D0011-AC-50: 実行中の2つ目の操作は断る。5・0・1・None で waiting・done・failed に変わる。失敗の出力は末尾 8 行。"""
    m = rs()
    act = m.parse_action({"op": "approve"})
    c = m.Controller()
    assert c.snapshot()["status"] == "waiting"
    assert c.begin(act) is True
    assert c.snapshot()["status"] == "running"
    assert c.begin(act) is False  # 2つ目は断る
    c.finish(5, "")
    assert c.snapshot()["status"] == "waiting"
    assert c.begin(act) is True
    c.finish(0, "")
    assert c.snapshot()["status"] == "done"

    for code in (1, None):
        c = m.Controller()
        assert c.begin(act) is True
        c.finish(code, "\n".join(f"line {i}" for i in range(20)))
        snap = c.snapshot()
        assert snap["status"] == "failed"
        assert m.TAIL_LINES == 8
        assert tail_text(snap).splitlines() == [f"line {i}" for i in range(12, 20)]


# ---- HTTP（AC-47・48・49・50・61・65） -----------------------------------------------------


class Calls:
    """偽の run_command。呼ばれた (cmd, cwd) を記録し、決めた (code, stderr) を返す。block を置くと、release まで待つ。"""

    def __init__(self, code: int = 5, stderr: str = ""):
        self.calls: list[tuple[list[str], Path]] = []
        self.code, self.stderr = code, stderr
        self.called = threading.Event()
        self.release: threading.Event | None = None

    def __call__(self, cmd, cwd):
        self.calls.append((list(cmd), Path(cwd)))
        self.called.set()
        if self.release is not None:
            assert self.release.wait(10)
        return self.code, self.stderr


@contextmanager
def running(m, project: Path, *, state: dict | None = None, options: dict | str | None = None, stage: str = "mock", controller=None):
    """受付を 127.0.0.1 の空きポートで立てる。state は work_dir の state.json、options は stage の案のデータ。"""
    work = project / "docs" / "pipeline" / "video"
    work.mkdir(parents=True, exist_ok=True)
    if state is None:
        state = {"pending_review": {"stage": stage}}
    (work / STATE_NAME).write_text(json.dumps(state), encoding="utf-8")
    if options is not None:
        path = project / m.options_path(stage)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(options if isinstance(options, str) else json.dumps(options), encoding="utf-8")
    handler = m.make_handler(
        project=project, work_dir=work, template=TEMPLATE, exe="pipe-in", base_args=BASE, token=TOKEN, controller=controller
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def request(server, method: str, path: str, body: dict | None = None, headers: dict | None = None):
    host, port = server.server_address[:2]
    conn = http.client.HTTPConnection(host, port, timeout=10)
    try:
        payload = json.dumps(body).encode("utf-8") if body is not None else None
        conn.request(method, path, body=payload, headers=headers or {})
        resp = conn.getresponse()
        return resp.status, dict(resp.getheaders()), resp.read()
    finally:
        conn.close()


def post_action(server, body: dict, token: str | None = TOKEN, host: str | None = None):
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["X-Token"] = token
    if host is not None:
        headers["Host"] = host
    return request(server, "POST", "/action", body, headers)


GOOD_OPTIONS = {
    "round": 1,
    "options": [{"number": 1, "title": "題", "summary": "特徴", "frames": ["video/mock/1/frames/a.png"]}],
}


def test_http_listens_on_loopback_only(project, monkeypatch):
    """D0011-AC-46: make_handler で立てたサーバーは 127.0.0.1 で待ち受ける（受付が使う定数の HOST と同じ）。"""
    m = rs()
    monkeypatch.setattr(m, "run_command", Calls())
    with running(m, project, options=GOOD_OPTIONS) as server:
        assert server.server_address[0] == m.HOST == "127.0.0.1"


def test_http_rejects_bad_requests(project, monkeypatch):
    """D0011-AC-47: Host 違い・合言葉なし／違い・GET /action・中身の悪い操作は 4xx で、pipe-in を呼ばない。正しいものは呼ぶ。"""
    m = rs()
    fake = Calls()
    monkeypatch.setattr(m, "run_command", fake)
    with running(m, project, options=GOOD_OPTIONS) as server:
        port = server.server_address[1]
        approve = {"op": "approve"}
        assert post_action(server, approve, host=f"evil.example:{port}")[0] == 403
        assert post_action(server, approve, token=None)[0] == 403
        assert post_action(server, approve, token="wrong")[0] == 403
        assert request(server, "GET", "/action", headers={"X-Token": TOKEN})[0] == 405
        assert 400 <= post_action(server, {"op": "choose", "number": 0, "note": ""})[0] < 500
        assert 400 <= post_action(server, {"op": "run"})[0] < 500
        assert fake.calls == []

        status, _, _ = post_action(server, approve)
        assert status in (200, 202)
        assert fake.called.wait(10)
    assert fake.calls == [(["pipe-in", *BASE, "--review", "approve"], project)]


def test_http_serves_inside_video_with_security_headers(project, monkeypatch):
    """D0011-AC-48: video/ の中は配り、外を指す道は 4xx で中身を返さない。応答に CSP と nosniff が付き、合言葉は /state に出ない。"""
    m = rs()
    monkeypatch.setattr(m, "run_command", Calls())
    with running(m, project, options=GOOD_OPTIONS) as server:
        status, headers, body = request(server, "GET", "/files/video/mock/1/a.png")
        assert status == 200 and body == b"\x89PNG-test"
        assert headers.get("Content-Type") == "image/png"
        assert headers.get("X-Content-Type-Options") == "nosniff"
        for path in [
            "/files/../x.png",
            "/files/video/../secret.txt",
            "/files//etc/passwd",
            "/files/%2e%2e/x.png",
            "/files/video/%2e%2e/secret.txt",
            "/files/secret.txt",
        ]:
            status, _, body = request(server, "GET", path)
            assert 400 <= status < 500, path
            assert b"outside" not in body, path

        status, headers, body = request(server, "GET", "/")
        assert status == 200
        assert "default-src 'none'" in headers.get("Content-Security-Policy", "")
        assert page_data(body.decode("utf-8"))["token"] == TOKEN
        status, _, body = request(server, "GET", "/state")
        assert status == 200 and TOKEN.encode() not in body


def test_state_never_serves_outside_frames(project, monkeypatch):
    """D0011-AC-65: データの frames に video/ の外（../x.png・/etc/x.png）の場所があっても、その場所を /files/ で取りにいくと配られない。"""
    m = rs()
    monkeypatch.setattr(m, "run_command", Calls())
    evil = {
        "options": [
            {"number": 1, "title": "t", "summary": "s", "frames": ["../x.png", "/etc/x.png", "video/../../x.png"]}
        ]
    }
    with running(m, project, options=evil) as server:
        status, _, body = request(server, "GET", "/state")
        assert status == 200
        assert json.loads(body)["options_data"] == evil  # 検査と表示の判断はテンプレート側
        for frame in evil["options"][0]["frames"]:
            status, _, body = request(server, "GET", "/files/" + frame)
            assert 400 <= status < 500, frame
            assert b"outside-secret" not in body


@pytest.mark.parametrize("stage", ["script", "mock"])
@pytest.mark.parametrize(
    "options",
    [None, "{not json", "[]", json.dumps({"options": 3})],
    ids=["missing", "broken", "not-object", "options-not-list"],
)
def test_page_when_options_missing_or_broken(project, monkeypatch, stage, options):
    """D0011-AC-61: 案のデータが無い・壊れている・配列でないとき、GET / は落ちずに 200 で、データの error に原因の文が入る。"""
    m = rs()
    monkeypatch.setattr(m, "run_command", Calls())
    with running(m, project, options=options, stage=stage) as server:
        status, _, body = request(server, "GET", "/")
        assert status == 200
        data = page_data(body.decode("utf-8"))
        assert data["stage"] == stage
        assert data["options_data"] is None
        assert isinstance(data["error"], str) and data["error"]


def test_page_with_good_options_has_no_error(project, monkeypatch):
    """D0011-AC-35: 正しい案のデータは、そのままページのデータに入り、error は空。状態は waiting。"""
    m = rs()
    monkeypatch.setattr(m, "run_command", Calls())
    with running(m, project, options=GOOD_OPTIONS) as server:
        data = page_data(request(server, "GET", "/")[2].decode("utf-8"))
        assert data["options_data"] == GOOD_OPTIONS
        assert not data["error"]
        assert data["status"] == "waiting" and data["stage"] == "mock"


def test_page_without_pending_review_says_no_review(project, monkeypatch):
    """D0011-AC-52: 止まっている確認が無い（pending_review なし）ときは、状態 no-review のページを返す。"""
    m = rs()
    monkeypatch.setattr(m, "run_command", Calls())
    with running(m, project, state={"pending_review": None}) as server:
        status, _, body = request(server, "GET", "/")
        assert status == 200
        assert page_data(body.decode("utf-8"))["status"] == "no-review"


def test_failure_output_is_escaped_in_page(project, monkeypatch):
    """D0011-AC-49: 失敗した pipe-in の標準エラーに <script> があっても、ページに生のタグ・閉じタグで出ない。"""
    m = rs()
    finished = threading.Event()

    class Watched(m.Controller):
        def finish(self, code, stderr_tail):
            super().finish(code, stderr_tail)
            finished.set()

    fake = Calls(code=1, stderr="</script><img src=x onerror=alert(1)>\n")
    monkeypatch.setattr(m, "run_command", fake)
    with running(m, project, options=GOOD_OPTIONS, controller=Watched()) as server:
        assert post_action(server, {"op": "approve"})[0] in (200, 202)
        assert finished.wait(10)
        status, _, body = request(server, "GET", "/")
        text = body.decode("utf-8")
        assert status == 200
        assert text.count("</script>") == 1 and "<img" not in text
        data = page_data(text)
        assert data["status"] == "failed"
        assert "onerror=alert(1)" in tail_text(data)


def test_second_action_is_refused_while_running(project, monkeypatch):
    """D0011-AC-50: pipe-in を呼んでいる間の2つ目の操作は 409 で断り、呼ばない。終わると状態が変わる。"""
    m = rs()
    finished = threading.Event()

    class Watched(m.Controller):
        def finish(self, code, stderr_tail):
            super().finish(code, stderr_tail)
            finished.set()

    fake = Calls(code=5)
    fake.release = threading.Event()
    monkeypatch.setattr(m, "run_command", fake)
    try:
        with running(m, project, options=GOOD_OPTIONS, controller=Watched()) as server:
            assert post_action(server, {"op": "approve"})[0] in (200, 202)
            assert fake.called.wait(10)
            assert post_action(server, {"op": "quit"})[0] == 409
            assert len(fake.calls) == 1
            data = json.loads(request(server, "GET", "/state")[2])
            assert data["status"] == "running"
            fake.release.set()
            assert finished.wait(10)
            assert json.loads(request(server, "GET", "/state")[2])["status"] == "waiting"
    finally:
        fake.release.set()
