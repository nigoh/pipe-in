"""D0044：確認用ページの補助（tests/live_page_preview.py）の自己検査。画面の確認（AC-54〜56。Playwright）で使う。

補助は build_page() の前に偽の claude を足すだけで、ページ本体は変えない。リポジトリの中には書かない。SDK は呼ばない。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import live_page_preview as pv
from pipe_in.engine import live_page

ROOT = Path(__file__).resolve().parents[1]


def test_d0044_ac54_preview_page_is_the_real_page_with_a_fake_claude_in_front():
    """D0044-AC-54: 確認用ページは、本物の build_page()（変えない）の前に、偽の claude の <script> を足したもの。写しは JSON で1回だけ埋める。今のままで通る（補助の自己検査）。"""
    page = live_page.build_page()
    html = pv.preview_html(pv.showcase_snapshot())
    assert html.count("<script>") == 2 and html.count("</script>") == 2
    assert page.split("<script>", 1)[1] in html, "ページ本体の script が変わっている"
    assert html.index("window.claude") < html.index(page.split("<script>", 1)[1][:200])
    assert html.replace(html[html.index("<script>") : html.index("</script>\n<script>") + len("</script>\n")], "", 1) == page


def test_d0044_ac54_preview_snapshot_has_a_review_and_the_next_one_does_not():
    """D0044-AC-54: 確認用の写し：見本（確認待ち）は review がある。2つ目（承認後の次の段）は review が null で、動いている段がある。"""
    first, second = pv.showcase_snapshot(), pv.next_snapshot()
    assert first["review"] is not None and first["review"]["stage"] == "requirements"
    assert second["review"] is None and any(s["status"] == "running" for s in second["stages"])
    assert first["schema"] == second["schema"] == 1


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_d0044_ac55_preview_theme_is_set_on_the_root(theme):
    """D0044-AC-55: ライト・ダークは <html data-theme> で切り替える（ページの CSS にある仕組み）。"""
    html = pv.preview_html(None, theme=theme)
    assert f'<html lang="ja" data-theme="{theme}">' in html
    assert "data-theme" not in pv.preview_html(None).split("<style>")[0].replace('<html lang="ja">', "")


def test_d0044_ac56_preview_options_reach_the_fake_comments():
    """D0044-AC-56: can・send・comments の指定が、偽の comments の設定に入る（reject・pending・null の画面を作れる）。"""
    html = pv.preview_html(pv.showcase_snapshot(), can="writers_only", send="reject:forbidden", comments=False)
    cfg = json.loads(re.search(r"var cfg = (\{.*?\});", html).group(1))
    assert cfg == {"can": "writers_only", "send": "reject:forbidden", "comments": False}
    assert "window.__sent" in html and "window.__push" in html and "window.__settle" in html


def test_d0044_ac54_preview_escapes_closing_tags_in_the_snapshot():
    """D0044-AC-54: 写しの中の </script> が、確認用ページの script を閉じない（< > & は \\u 形）。"""
    snap = pv.showcase_snapshot()
    snap["name"] = "</script><script>alert(1)</script>"
    html = pv.preview_html(snap)
    assert html.count("<script>") == 2 and html.count("</script>") == 2
    assert "alert(1)" in html and "<script>alert(1)" not in html


def test_d0059_preview_has_all_states(tmp_path):
    """D0059-AC-26: 確認用ページに all-states がある：6つの状態（完了・作業中・確認待ち・まだ・失敗・差し戻し）の段と generated_at を持つ写しで、
    ライト・ダークの2つが書かれ、写しが埋まっている。白黒にして状態を見分ける画面の確認（D0059-AC-21〜26）はこのページを開く。"""
    snap = pv.all_states_snapshot()
    assert snap["schema"] == 1 and snap["empty"] is False and snap["final"] is None
    assert {s["status"] for s in snap["stages"]} == {"done", "running", "review", "waiting", "failed", "revised"} and len(snap["stages"]) == 6
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}", snap["generated_at"])
    assert "all-states" in pv.PREVIEWS
    written = {p.name: p for p in pv.write_previews(tmp_path / "out")}
    for theme in ("light", "dark"):
        html = written[f"answer-all-states-{theme}.html"].read_text(encoding="utf-8")
        assert f'data-theme="{theme}"' in html
        assert json.dumps(snap["name"])[1:-1] in html and "generated_at" in html and html.count("<script>") == 2
    from datetime import datetime, timezone

    pinned = pv.all_states_snapshot(datetime(2026, 7, 1, 3, 40, 5, tzinfo=timezone.utc))
    assert pinned["generated_at"] == "2026-07-01T03:40:05+00:00"


def test_d0044_ac54_preview_files_are_written_outside_the_repository(tmp_path):
    """D0044-AC-54: 確認用ページは指定した出力先に、項目ごとにライト・ダークで書く。リポジトリの中には書かない（書こうとすると断る）。"""
    written = pv.write_previews(tmp_path / "out")
    names = {p.name for p in written}
    assert len(written) == len(pv.PREVIEWS) * 2 + 4
    assert "answer-available-light.html" in names and "answer-can-writers_only-dark.html" in names and "answer-comments-null-light.html" in names
    assert all(p.is_file() and p.parent == (tmp_path / "out").resolve() for p in written)
    with pytest.raises(SystemExit):
        pv.write_previews(ROOT / "docs" / "not-here")
    with pytest.raises(SystemExit):
        pv.write_previews(ROOT)
    assert not (ROOT / "docs" / "not-here").exists()
