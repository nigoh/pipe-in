"""D0044：進み具合のページの「答えのボタン」を、ブラウザ（Playwright）で見て確かめるための確認用ページを作る（テストの補助。本体には入らない）。

build_page() の HTML の前に、偽の `claude`（use("db") が写しを1回届ける・use("comments") が偽の comments）を足すだけ。
ページ本体は変えない。出力先は引数で、リポジトリの中には書かない（書こうとしたら断る）。

  python tests/live_page_preview.py <出力先フォルダ>      ← 一覧は PREVIEWS。ライト・ダークの2つずつ
                                                          （ほかに answer-long-names-*・answer-no-review-*・D0059 の answer-progress-*）

偽の comments の動き（window に目印を残す。Playwright の evaluate で読める）:
  window.__sent       sendToClaude に渡された {text, anchor} の一覧
  window.__canCalls   canSendToClaude を呼んだ回数
  window.__anchorCalls anchorFor を呼んだ回数
  window.__push(写し)  購読している画面に、別の写しを届ける（確認待ちが次の段に替わる動きを見る）
  window.__settle(結果) can="pending" / send="pending" で待たせた呼び出しを終わらせる（resolve か reject）
"""

from __future__ import annotations

import json
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

import live_support as ls
from pipe_in.engine import live, live_page

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "showcase_waiting"
NOW = ls.NOW

# 画面の確認の項目（決定の記録 D0044・D0059 の画面の AC）。名前 → 偽の comments の設定
PREVIEWS: dict[str, dict[str, Any]] = {
    "available": {"can": "available", "send": "resolve"},
    "send-pending": {"can": "available", "send": "pending"},
    "send-reject": {"can": "available", "send": "reject:claude_unavailable"},
    "send-forbidden": {"can": "available", "send": "reject:forbidden"},
    "can-writers_only": {"can": "writers_only"},
    "can-no_session": {"can": "no_session"},
    "can-off": {"can": "off"},
    "can-unknown": {"can": "something-new"},
    "can-reject": {"can": "reject"},
    "comments-null": {"comments": False},
}


def showcase_snapshot() -> dict[str, Any]:
    """tests/fixtures/showcase_waiting/ の記録（要件定義が確認待ち。since あり）から作った写し（review が入る）。"""
    state = live.read_state(FIXTURE)
    assert state is not None, "見本の記録が読めない"
    return live.build_snapshot(state, None, now=NOW, local_tz=ls.UTC)


def next_snapshot() -> dict[str, Any]:
    """要件定義が承認されて、設計が動いている写し（review は null）。確認待ちが次の段に替わる動きを見るための2つ目。"""
    state = ls.base_state(
        name="確認用のセッション",
        open=ls.opened("design", seq=2),
        runs=[ls.run("requirements", seq=1, cost=0.5, turns=3, duration=12.5), ls.review("requirements", "approved")],
    )
    return live.build_snapshot(state, "2026-10-17T11:59:30+00:00", now=NOW, local_tz=ls.UTC)


def long_name_snapshot() -> dict[str, Any]:
    """幅 360px の確認用：60 文字のセッション名と長い段の表示名の写し。"""
    snap = showcase_snapshot()
    snap["name"] = "とても長いセッション名" * 5 + "ABCDEFGHIJ"
    snap["stages"][0]["label"] = "長い段の表示名" * 6
    return snap


def progress_snapshot() -> dict[str, Any]:
    """D0059：帯の塗り分けと確認待ちの色の確認用。完了・差し戻し・確認待ち・失敗（2回目）・まだの段がある写し（review は null）。
    帯は完了 20%・すき間・確認待ち 20% になり、差し戻しの印と失敗の印が並ぶ（AC-33・AC-42）。"""
    base = showcase_snapshot()
    since = ls.utc_text(NOW - timedelta(minutes=3))

    def row(name: str, status: str, **kw: Any) -> dict[str, Any]:
        r: dict[str, Any] = {"name": name, "label": ls.LABELS[name], "status": status, "attempt": None, "started_at": None, "pending_since": None,
                             "verdict": None, "cost_usd": None, "turns": None, "duration_sec": None}
        r.update(kw)
        return r

    snap = dict(base)
    snap["name"] = "進みの帯の確認"
    snap["final"] = None
    snap["review"] = None
    snap["stages"] = [
        row("requirements", "done", cost_usd=0.42, turns=9, duration_sec=190),
        row("design", "revised", duration_sec=168),
        row("red", "review", pending_since=since),
        row("implement", "failed", attempt=2, duration_sec=300),
        row("test", "waiting"),
    ]
    return snap


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, allow_nan=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


_FAKE = r"""
(function () {
  var snap = %(snap)s;
  var cfg = %(cfg)s;
  var subs = [];
  var held = { can: [], send: [] };
  window.__sent = [];
  window.__canCalls = 0;
  window.__anchorCalls = 0;
  function wrap(v) { return { exists: v !== null, data: function () { return v; } }; }
  var db = {
    doc: function (path) {
      return {
        onSnapshot: function (next) {
          subs.push(next);
          setTimeout(function () { next(wrap(snap)); }, 0);
          return function () {};
        }
      };
    }
  };
  window.__push = function (value) { snap = value; subs.forEach(function (next) { next(wrap(value)); }); };
  window.__settle = function (how) {
    var list = held.send.length ? held.send : held.can;
    var item = list.shift();
    if (!item) return false;
    if (how === "resolve") item.resolve(item.value); else item.reject({ code: String(how).replace("reject:", "") });
    return true;
  };
  function rejectWith(spec) {
    var code = String(spec).split(":")[1];
    return Promise.reject({ code: code === undefined ? "claude_unavailable" : code, message: "FAKE-REJECT-MESSAGE" });
  }
  var comments = {
    canSendToClaude: function () {
      window.__canCalls += 1;
      var can = cfg.can === undefined ? "available" : cfg.can;
      if (can === "reject") return Promise.reject(new Error("fake"));
      if (can === "pending") return new Promise(function (resolve, reject) { held.can.push({ resolve: resolve, reject: reject, value: "available" }); });
      return Promise.resolve(can);
    },
    anchorFor: function (el) {
      window.__anchorCalls += 1;
      return Promise.resolve({ path: el.tagName.toLowerCase() + "." + el.className, x: 1, y: 2 });
    },
    sendToClaude: function (arg) {
      window.__sent.push({ text: arg.text, anchor: arg.anchor });
      var send = cfg.send === undefined ? "resolve" : cfg.send;
      if (send === "pending") return new Promise(function (resolve, reject) { held.send.push({ resolve: resolve, reject: reject, value: undefined }); });
      if (send.indexOf("reject") === 0) return rejectWith(send);
      return Promise.resolve();
    }
  };
  window.claude = {
    use: function (name) {
      if (name === "db") return Promise.resolve(db);
      if (name === "comments") return Promise.resolve(cfg.comments === false ? null : comments);
      return Promise.resolve(null);
    }
  };
})();
"""


def preview_html(snapshot: dict[str, Any] | None, *, can: str = "available", send: str = "resolve", comments: bool = True, theme: str | None = None) -> str:
    """build_page() の前に偽の claude を足した、確認用の HTML。snapshot は購読の直後に1回届く（None なら記録なし）。
    can は canSendToClaude の答え（"reject"・"pending" も）、send は sendToClaude の動き（"resolve"・"pending"・"reject:<コード>"）。"""
    cfg: dict[str, Any] = {"can": can, "send": send}
    if not comments:
        cfg["comments"] = False
    page = live_page.build_page()
    assert page.count("<script>") == 1
    fake = "<script>" + _FAKE % {"snap": _json(snapshot), "cfg": _json(cfg)} + "</script>\n"
    html = page.replace("<script>", fake + "<script>", 1)
    if theme is not None:
        assert theme in ("light", "dark")
        html = html.replace('<html lang="ja">', f'<html lang="ja" data-theme="{theme}">', 1)
    return html


def write_previews(out_dir: Path) -> list[Path]:
    """PREVIEWS の各項目を、ライト・ダークの2つずつ out_dir に書く（リポジトリの中は断る）。書いたファイルの一覧を返す。"""
    out = Path(out_dir).resolve()
    if out == ROOT or ROOT in out.parents:
        raise SystemExit(f"リポジトリの中には書けません: {out}")
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, cfg in PREVIEWS.items():
        for theme in ("light", "dark"):
            path = out / f"answer-{name}-{theme}.html"
            path.write_text(preview_html(showcase_snapshot(), theme=theme, can=cfg.get("can", "available"), send=cfg.get("send", "resolve"), comments=cfg.get("comments", True)), encoding="utf-8")
            written.append(path)
    for theme in ("light", "dark"):
        path = out / f"answer-long-names-{theme}.html"
        path.write_text(preview_html(long_name_snapshot(), theme=theme), encoding="utf-8")
        written.append(path)
        path = out / f"answer-no-review-{theme}.html"
        path.write_text(preview_html(next_snapshot(), theme=theme), encoding="utf-8")
        written.append(path)
        path = out / f"answer-progress-{theme}.html"
        path.write_text(preview_html(progress_snapshot(), theme=theme), encoding="utf-8")
        written.append(path)
    return written


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("使い方: python tests/live_page_preview.py <出力先フォルダ>")
    for p in write_previews(Path(sys.argv[1])):
        print(p)
