"""Application configuration constants."""

import os
from pathlib import Path
from typing import List

# backend/app/config.py -> backend/
BACKEND_DIR: Path = Path(__file__).resolve().parent.parent
DB_PATH: Path = BACKEND_DIR / "data" / "app.db"
DATABASE_URL: str = f"sqlite:///{DB_PATH}"

ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL: str = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5")

CORS_ORIGINS: List[str] = ["http://localhost:5173"]
