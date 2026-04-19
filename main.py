"""
Punto de entrada principal – servidor FastAPI.
Ejecutar: python main.py
O con uvicorn: uvicorn main:app --host 0.0.0.0 --port 8000
"""
import logging
import os

import uvicorn
from dotenv import load_dotenv

load_dotenv()

from src.config import get_settings
from src.adapters.input.api.router import app  # noqa: F401 – expone la app

if __name__ == "__main__":
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
        log_level=settings.log_level.lower(),
    )
