"""リンク（symlink）を使うテストの補助。リンクは tmp_path の下にだけ作る。作れない環境（権限の無い Windows など）では skip する。"""

from __future__ import annotations

from pathlib import Path

import pytest


def link_or_skip(link: Path, target: Path, *, directory: bool = False) -> None:
    """link から target へのリンクを作る。親のフォルダも作る。作れない環境では、そのテストを skip する。"""
    try:
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(target, target_is_directory=directory)
    except (OSError, NotImplementedError):
        pytest.skip("この環境ではリンクを作れない")
