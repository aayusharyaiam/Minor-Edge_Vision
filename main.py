"""Launcher: python main.py  →  http://127.0.0.1:8000"""

import logging

import uvicorn

from backend.config import Settings
from backend.main import create_app

settings = Settings()
app = create_app(settings)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    uvicorn.run(app, host=settings.server_host, port=settings.server_port, workers=1, log_level="info")
