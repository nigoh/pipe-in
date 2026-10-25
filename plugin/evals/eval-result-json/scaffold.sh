#!/usr/bin/env bash
# claude plugin eval の --scaffold で、Claude が始まる前に空のワークスペースで流れる。
# 見本は同じフォルダの scaffold.py が作る（標準ライブラリだけ）。cwd がそのままワークスペース。
set -eu

if command -v python3 >/dev/null 2>&1; then
  py=python3
elif command -v python >/dev/null 2>&1; then
  py=python
else
  echo "python3 も python も見つかりません。" >&2
  exit 1
fi

"$py" "$(dirname "$0")/scaffold.py"
