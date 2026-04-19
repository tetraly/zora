#!/usr/bin/env python3
"""Local dev server."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from zora.api import create_app

if __name__ == "__main__":
    create_app().run(port=5003, debug=True)
