"""Shared test setup that never uses production credentials by default."""

import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "application" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("NEO4J_PASSWORD", "unit-test-only-password")
os.environ.setdefault("LOG_FILE", "")
