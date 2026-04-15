#!/usr/bin/env python3
"""Local dev server."""
from zora.api import create_app

if __name__ == "__main__":
    create_app().run(port=5003, debug=True)
