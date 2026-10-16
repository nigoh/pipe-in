"""python -m devpipe の入口（中身は devpipe/cli.py）。"""

import sys

from .cli import main

sys.exit(main())
