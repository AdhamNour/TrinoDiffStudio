#!/usr/bin/env python3
"""
Convenience launcher for the Trino Database Diff Studio GUI.
Usage:
    python run_gui.py
"""

import os
import sys

# Add current workspace root to sys.path
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

from trino_diff.app import main

if __name__ == "__main__":
    main()
