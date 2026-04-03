"""
Central configuration — loads .env and exposes typed settings.
All other modules import from here instead of calling os.getenv directly.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

CONSUMER_URL: str = os.getenv("CONSUMER_URL", "ws://localhost:9000/stream")
MASSIVE_API_KEY: str = os.getenv("MASSIVE_API_KEY")
DATABASE_URL: str = os.getenv("DATABASE_URL")
JWT_SECRET: str = os.getenv("JWT_SECRET")
