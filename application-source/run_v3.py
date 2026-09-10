#!/usr/bin/env python3
"""Launch the unified OpenVLC System Suite application."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui_dev_v3.app import main


if __name__ == "__main__":
    raise SystemExit(main())
