"""python -m pipe_in の入口（中身は pipe_in/cli.py）。"""

import sys

from .cli import main

sys.exit(main())
