"""インストールせずにテストを流せるよう、generator/ を devpipe_generator として読み込めるようにする。

pip install -e . 済みなら、そちらを使う（pyproject.toml の package-dir で同じ名前に対応づけている）。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "generator"

try:
    import devpipe_generator  # noqa: F401
except ImportError:
    if (GENERATOR / "__init__.py").is_file():
        spec = importlib.util.spec_from_file_location(
            "devpipe_generator", GENERATOR / "__init__.py", submodule_search_locations=[str(GENERATOR)]
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules["devpipe_generator"] = module
        spec.loader.exec_module(module)
