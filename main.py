#!/usr/bin/env python3
"""
main.py — Pokemon FireRed mGBA Tools

Entry point.  Run from the project root:

    python main.py

Delegates to python.main which contains the menu logic.
"""

import sys
import os

# Ensure the project root is on sys.path so "python.*" package imports work
# regardless of where the interpreter was invoked from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from python.main import main

if __name__ == "__main__":
    main()
