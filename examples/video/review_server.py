"""動画を作るパイプの、手元の受付（見本）。

pipe-in が確認で止まった（終了コード 5）あとの答えを、ブラウザから押せるようにする小さなサーバー。
押された操作を `pipe-in --review approve|revise|quit` に変えて呼ぶだけで、pipe-in 本体は import しない。

- 標準ライブラリだけで動く。待ち受けは 127.0.0.1 だけ（アドレスを選ぶ引数は無い）
- 合言葉（起動のたびに作る）・Host・POST を確かめ、video/ の外のファイルは配らない
- 記録（state.json）も video/ も読むだけで、書かない
- 同時に動かす操作は1つ

使い方（最初の実行は端末で `pipe-in --pause …` を打つ）：
    python examples/video/review_server.py [--port 8765] [--project .] [--work-dir docs/pipeline] \\
        [--pipe-in pipe-in] -- --pipe video --pipes-dir examples/video/pipes
"""

from __future__ import annotations

import argparse
import hmac
import json
import re
import secrets
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

HOST = "127.0.0.1"  # 待ち受けのアドレス。変える引数は作らない
DEFAULT_PORT = 8765
MAX_NOTE = 1000  # 「直す点」の文字数の上限
TAIL_LINES = 8  # 失敗したときに画面へ出す、出力の末尾の行数
MAX_LINE = 500  # 1行の長さの上限（長すぎる行は切る）
MAX_BODY = 64 * 1024  # POST の本文の上限（バイト）
NONE_OF_THEM = "どれもびみょう。別の方向で出し直して"
MARKER = "<!--PAGE-DATA-->"
TEMPLATE_NAME = "compare-template.html"
STATE_NAME = "state.json"
KINDS = ("revise", "approve", "quit")
# 受付が決める部分。起動時の引数に混ざっていたら断る
FORBIDDEN_ARGS = ("--review", "--feedback", "--yes", "--pause", "--auto")
OPTIONS_PATHS = {"script": "video/script/options.json", "mock": "video/mock/options.json"}
IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}
# インラインだけ許し、外へは出さない
CSP = (
    "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
    "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


@dataclass(frozen=True)
class Action:
    """ページの操作を、pipe-in への答えに直したもの。"""

    kind: str
    feedback: str | None = None


# ---- コマンドの並びと操作（AC-41〜45） ------------------------------------------------------


def build_command(exe, base_args, kind, feedback=None):
    """pipe-in を呼ぶ引数の並び。人の文は --feedback の次の1つの要素になり、シェルは通らない。"""
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValueError(f"操作は {' / '.join(KINDS)} のどれかです")
    if kind == "revise":
        if not isinstance(feedback, str) or not feedback or "\0" in feedback:
            raise ValueError("revise には直す点の文が要ります")
    elif feedback is not None:
        raise ValueError(f"{kind} には直す点を付けられません")
    args = list(base_args)
    if not all(isinstance(a, str) for a in args):
        raise ValueError("起動時の引数は文字だけです")
    for a in args:
        if a.split("=", 1)[0] in FORBIDDEN_ARGS:
            raise ValueError(f"起動時の引数に {a} は使えません（受付が決める部分です）")
    cmd = [exe, *args, "--review", kind]
    if kind == "revise":
        cmd += ["--feedback", feedback]
    return cmd


def parse_action(payload) -> Action:
    """ページから来た操作 {"op": …, "number": …, "note": …} を Action にする。悪い入力は ValueError。"""
    if not isinstance(payload, dict):
        raise ValueError("操作の形が違います")
    op = payload.get("op")
    if op == "approve":
        return Action("approve")
    if op == "quit":
        return Action("quit")
    if op == "none":
        return Action("revise", NONE_OF_THEM)  # 人の入力は読まない
    if op == "choose":
        number = payload.get("number")
        if type(number) is not int or number < 1:  # bool・小数・文字は断る
            raise ValueError("案の番号は 1 以上の整数です")
        note = payload.get("note", "")
        if note is None:
            note = ""
        if not isinstance(note, str):
            raise ValueError("直す点は文字です")
        if len(note) > MAX_NOTE:
            raise ValueError(f"直す点は {MAX_NOTE} 文字までです")
        note = note.strip()
        # 文は数字で始まるので、`--` で始まらない（別の引数と取り違えない）
        return Action("revise", f"{number}案目にする。直す点：{note}" if note else f"{number}案目にする。")
    raise ValueError("知らない操作です")


def run_command(cmd, cwd):
    """pipe-in を呼ぶ（シェルを通さない）。(終了コード, 出力) を返す。テストでは差し替える。"""
    r = subprocess.run(
        cmd,
        cwd=cwd,
        shell=False,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return r.returncode, (r.stderr or r.stdout or "")


# ---- 待ち受けと要求の確認（AC-46・47） ------------------------------------------------------


def check_bind(host) -> None:
    if host != HOST:
        raise ValueError(f"待ち受けは {HOST} だけです")


def check_request(method, path, host_header, port, token_header, token):
    """断るなら HTTP の状態（403・405）、問題が無ければ None。"""
    if host_header not in (f"127.0.0.1:{port}", f"localhost:{port}"):
        return 403
    route = (path or "").split("?", 1)[0]
    if route == "/action":
        if method != "POST":
            return 405
        if not isinstance(token_header, str) or not hmac.compare_digest(token_header.encode(), token.encode()):
            return 403
        return None
    if method != "GET":
        return 405
    return None


# ---- 配るファイルの道（AC-48・65） ----------------------------------------------------------


def resolve_served_path(project, rel):
    """/files/ の後ろの相対パスを、video/ の中の実在するファイルに直す。外へ出るもの・ファイルでないものは None。"""
    if not isinstance(rel, str):
        return None
    rel = unquote(rel)
    if not rel or "\0" in rel or "\\" in rel or rel.startswith("/") or re.match(r"[A-Za-z]:", rel):
        return None
    parts = rel.split("/")
    if parts[0] != "video" or any(p in ("", ".", "..") for p in parts):
        return None
    try:
        base = (Path(project) / "video").resolve()
        target = (Path(project) / rel).resolve()  # 記号リンクはここで実体に直る
        if base not in target.parents or not target.is_file():
            return None
    except (OSError, ValueError):
        return None
    return target


# ---- ページに入れるデータ（AC-49・52・60・61） ----------------------------------------------


def embed_json(obj) -> str:
    """<script type="application/json"> の中に入れても、閉じタグや HTML として読まれない JSON にする。"""
    text = json.dumps(obj, ensure_ascii=False)
    for ch, esc in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"), (" ", "\\u2028"), (" ", "\\u2029")):
        text = text.replace(ch, esc)
    return text


def render_page(template, data) -> str:
    if MARKER not in template:
        raise ValueError(f"テンプレートに目印 {MARKER} がありません")
    return template.replace(MARKER, embed_json(data), 1)


def pending_stage(state_text):
    """state.json の文字から、止まっている確認の段の名前。読めない・形違いは None。"""
    try:
        data = json.loads(state_text)
    except (TypeError, ValueError):
        return None
    pending = data.get("pending_review") if isinstance(data, dict) else None
    stage = pending.get("stage") if isinstance(pending, dict) else None
    return stage if isinstance(stage, str) and stage else None


def options_path(stage):
    return OPTIONS_PATHS.get(stage)


def load_options(text):
    """案のデータを読む。(データ, None) か (None, 原因の文)。項目の細かい検査はテンプレート側。"""
    try:
        data = json.loads(text)
    except (TypeError, ValueError) as e:
        return None, f"案のデータを JSON として読めません（{e}）"
    if not isinstance(data, dict):
        return None, "案のデータがオブジェクトではありません"
    if not isinstance(data.get("options"), list):
        return None, "案のデータの options が配列ではありません"
    return data, None


# ---- 状態の遷移（AC-50） --------------------------------------------------------------------


def classify_exit(code) -> str:
    """pipe-in の終了コード → 次の確認(next)・終わり(done)・失敗(failed)。"""
    if code == 5:
        return "next"
    if code == 0:
        return "done"
    return "failed"


class Controller:
    """操作を1つずつ通すための状態。プロセスも時計も持たない（ロックだけ持つ）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._status = "waiting"
        self._log_tail: list[str] = []

    def begin(self, action: Action) -> bool:
        with self._lock:
            if self._status == "running":
                return False
            self._status = "running"
            self._log_tail = []
            return True

    def finish(self, code, stderr_tail) -> None:
        kind = classify_exit(code)
        with self._lock:
            self._status = {"next": "waiting", "done": "done", "failed": "failed"}[kind]
            lines = (stderr_tail or "").splitlines()[-TAIL_LINES:] if kind == "failed" else []
            self._log_tail = [line[:MAX_LINE] for line in lines]

    def snapshot(self) -> dict:
        with self._lock:
            return {"status": self._status, "log_tail": list(self._log_tail)}


# ---- HTTP -----------------------------------------------------------------------------------


def make_handler(*, project, work_dir, template, exe, base_args, token, controller=None):
    """ハンドラのクラスを返す。project は pipe-in を流すフォルダ、work_dir は state.json のあるフォルダ。"""
    ctl = controller if controller is not None else Controller()
    project = Path(project)
    work_dir = Path(work_dir)

    def page_data(with_token: bool) -> dict:
        snap = ctl.snapshot()
        try:
            state_text = (work_dir / STATE_NAME).read_text(encoding="utf-8")
        except (OSError, ValueError):
            state_text = ""
        stage = pending_stage(state_text)
        status = snap["status"]
        if status == "waiting" and stage is None:
            status = "no-review"
        data = {
            "status": status,
            "stage": stage,
            "error": None,
            "options_data": None,
            "log_tail": snap["log_tail"],
            "round_note": None,
        }
        rel = options_path(stage) if stage else None
        if rel:
            found = resolve_served_path(project, rel)
            if found is None:
                data["error"] = f"{rel} がありません（この段の案のデータを、まだ書いていません）"
            else:
                try:
                    options, error = load_options(found.read_text(encoding="utf-8"))
                except (OSError, ValueError) as e:
                    options, error = None, f"{rel} を読めません（{e}）"
                data["options_data"], data["error"] = options, error
                if options is not None and type(options.get("round")) is int:
                    data["round_note"] = f"{options['round']}回目の案"
        if with_token:
            data["token"] = token
        return data

    def run_job(cmd) -> None:
        try:
            code, err = run_command(cmd, project)
        except Exception as e:  # noqa: BLE001 - 呼べなかったことを画面に出す
            code, err = None, f"pipe-in を呼べません: {e}"
        ctl.finish(code, err)

    class Handler(BaseHTTPRequestHandler):
        server_version = "pipe-in-review"

        def log_message(self, format, *args):  # noqa: A002 - 標準のログは出さない
            pass

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, obj) -> None:
            self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _guard(self, method: str) -> bool:
            """断るなら応答を返して False。"""
            port = self.server.server_address[1]
            refused = check_request(
                method, self.path, self.headers.get("Host"), port, self.headers.get("X-Token"), token
            )
            if refused is not None:
                self._json(refused, {"error": "forbidden" if refused == 403 else "method not allowed"})
                return False
            return True

        def do_GET(self):
            if not self._guard("GET"):
                return
            route = self.path.split("?", 1)[0]
            if route == "/":
                page = render_page(template, page_data(True))
                self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
            elif route == "/state":
                self._json(200, page_data(False))
            elif route.startswith("/files/"):
                found = resolve_served_path(project, route[len("/files/") :])
                if found is None:
                    self._json(404, {"error": "not found"})
                    return
                try:
                    body = found.read_bytes()
                except OSError:
                    self._json(404, {"error": "not found"})
                    return
                self._send(200, body, IMAGE_TYPES.get(found.suffix.lower(), "application/octet-stream"))
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):
            if not self._guard("POST"):
                return
            if self.path.split("?", 1)[0] != "/action":
                self._json(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = -1
            if length < 0 or length > MAX_BODY:
                self._json(413, {"error": "本文が大きすぎます"})
                return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                action = parse_action(payload)
                cmd = build_command(exe, base_args, action.kind, action.feedback)
            except (ValueError, UnicodeDecodeError) as e:
                self._json(400, {"error": str(e)})
                return
            if not ctl.begin(action):
                self._json(409, {"error": "いま実行中です。終わるまで待ってください"})
                return
            threading.Thread(target=run_job, args=(cmd,), daemon=True).start()
            self._json(202, {"ok": True})

        def _refuse(self):
            # GET・POST 以外は、check_request が必ず 405（Host 違いは 403）で断る
            self._guard(self.command)

        do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = _refuse

    return Handler


def serve(host, port, handler) -> None:
    check_bind(host)
    server = ThreadingHTTPServer((host, port), handler)
    print(f"受付を開きました: http://{host}:{port}/（止めるときは Ctrl+C）")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


# ---- 入口 -----------------------------------------------------------------------------------


def _pipe_name(base_args) -> str | None:
    """起動時の引数の --pipe の値から、記録のフォルダ名（パイプの名前）を求める。"""
    value = None
    for i, a in enumerate(base_args):
        if a == "--pipe" and i + 1 < len(base_args):
            value = base_args[i + 1]
        elif a.startswith("--pipe="):
            value = a.split("=", 1)[1]
    if not value:
        return None
    name = Path(value.rstrip("/\\")).name
    return name[len("pipe-in-") :] if name.startswith("pipe-in-") else name


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    own, base = (argv[: argv.index("--")], argv[argv.index("--") + 1 :]) if "--" in argv else (argv, [])
    parser = argparse.ArgumentParser(
        prog="review_server.py",
        allow_abbrev=False,
        description=(
            "pipe-in の確認の答えを、ブラウザから押せるようにする手元の受付。127.0.0.1 だけで待ち受ける。"
            " `--` より後ろは、pipe-in にそのまま渡す起動時の引数（例: --pipe video --pipes-dir examples/video/pipes）。"
        ),
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"待ち受けのポート（既定: {DEFAULT_PORT}）")
    parser.add_argument("--project", type=Path, default=Path("."), help="pipe-in を流す対象のフォルダ（既定: 今のフォルダ）")
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=Path("docs/pipeline"),
        help="pipe-in の記録の置き場所（既定: docs/pipeline。パイプの記録はその下のパイプ名のフォルダ）",
    )
    parser.add_argument("--pipe-in", default="pipe-in", help="pipe-in の実行ファイル（既定: pipe-in）")
    args = parser.parse_args(own)

    exe = shutil.which(args.pipe_in)
    if exe is None:
        parser.exit(1, f"{args.pipe_in} が見つかりません。--pipe-in で指定してください\n")
    try:
        build_command(exe, base, "approve")  # 起動時の引数に、受付が決める部分が混ざっていないかを確かめる
    except ValueError as e:
        parser.error(str(e))

    project = args.project.resolve()
    work = args.work_dir if args.work_dir.is_absolute() else project / args.work_dir
    name = _pipe_name(base)
    work_dir = work / name if name and ((work / name).is_dir() or not (work / STATE_NAME).is_file()) else work
    template_path = Path(__file__).with_name(TEMPLATE_NAME)
    try:
        template = template_path.read_text(encoding="utf-8")
    except OSError:
        parser.exit(1, f"{TEMPLATE_NAME} を読めません（review_server.py と同じフォルダに置いてください）\n")
    token = secrets.token_urlsafe(16)  # 画面にもログにも出さない（ページのデータにだけ入る）
    handler = make_handler(project=project, work_dir=work_dir, template=template, exe=exe, base_args=base, token=token)
    try:
        serve(HOST, args.port, handler)
    except OSError as e:
        parser.exit(1, f"待ち受けを始められません: {e}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
