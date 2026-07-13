#!/usr/bin/env python3
"""Launch the unified VLC System Suite (TX & RX launcher) — PySide6 v3 app."""

import sys
import os

# Ensure we can import gui_dev_v3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui_dev_v3.app import main

if __name__ == "__main__":
    raise SystemExit(main())
