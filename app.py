#!/usr/bin/env python3
"""
Trino Database Diff Studio — Root Application Entry Point
=========================================================
Allows launching the application directly via:
    python app.py
"""

import os
import sys

# Ensure workspace root is in sys.path
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
if WORKSPACE_DIR not in sys.path:
    sys.path.insert(0, WORKSPACE_DIR)

from trino_diff.app import main

if __name__ == "__main__":
    main()
