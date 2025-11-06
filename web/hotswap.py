"""Development entry point with hot reload enabled."""

from __future__ import annotations

import logging as log
import os
import sys
from pathlib import Path

import flet as ft
import flet.fastapi as flet_fastapi
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

# Allow importing the shared UI module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from ui import main as ui_main  # noqa: E402


def _build_app() -> FastAPI:
    upload_dir = Path(os.path.abspath("uploads"))
    assets_dir = Path(os.path.abspath("assets"))
    downloads_dir = assets_dir / "downloads"

    for path in (upload_dir, assets_dir, downloads_dir):
        path.mkdir(parents=True, exist_ok=True)

    def main(page: ft.Page) -> None:
        ui_main.main(page, platform="web")

    flet_app = flet_fastapi.app(
        main,
        upload_dir=str(upload_dir),
        assets_dir=str(assets_dir),
    )

    fastapi_app = FastAPI()

    @fastapi_app.get("/download/{filename}")
    async def download_file(filename: str):
        file_path = downloads_dir / filename
        if file_path.exists():
            return FileResponse(
                path=str(file_path),
                media_type="application/octet-stream",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        raise HTTPException(status_code=404, detail=f"{filename} not found")

    fastapi_app.mount("/", flet_app)
    return fastapi_app


app = _build_app()


def _configure_logging() -> None:
    if not log.getLogger().handlers:
        log.basicConfig(
            level=log.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )


def run(host: str = "0.0.0.0", port: int | None = None) -> None:
    _configure_logging()

    import uvicorn

    resolved_port = port if port is not None else int(os.environ.get("PORT", 8080))
    log.info("Starting web server with hot reload enabled.")
    uvicorn.run(
        "web.hotswap:app",
        host=host,
        port=resolved_port,
        reload=True,
        factory=False,
    )


if __name__ == "__main__":
    run()
