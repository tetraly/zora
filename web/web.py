"""Web entry point for Render.com deployment."""
import flet as ft
import flet.fastapi as flet_fastapi
import logging as log
import os
import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from file_cleanup import start_cleanup_service

# CRITICAL: Set PYTHONHASHSEED=0 for deterministic hash functions
# This ensures the same seed/flags always produce the same ROM
if os.environ.get('PYTHONHASHSEED') != '0':
    os.environ['PYTHONHASHSEED'] = '0'
    os.execv(sys.executable, [sys.executable] + sys.argv)

# Add parent directory to path to import ui.main
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from ui import main as ui_main


def main(page: ft.Page):
    """Web application entry point."""
    ui_main.main(page, platform="web")


if __name__ == "__main__":
    # Configure logging
    log.basicConfig(
        level=log.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Set up upload directory
    upload_dir = os.path.abspath("uploads")
    os.makedirs(upload_dir, exist_ok=True)

    # Set up assets directory for downloads
    assets_dir = os.path.abspath("assets")
    os.makedirs(assets_dir, exist_ok=True)
    downloads_dir = os.path.join(assets_dir, "downloads")
    os.makedirs(downloads_dir, exist_ok=True)

    # Create Flet app first with session cleanup configuration
    # session_timeout_seconds: Remove sessions after this many seconds of inactivity
    # This prevents memory leaks from accumulating disconnected sessions
    flet_app = flet_fastapi.app(
        main,
        upload_dir=upload_dir,
        assets_dir=assets_dir,
        session_timeout_seconds=900  # 15 minutes
    )

    # Create FastAPI app
    app = FastAPI()

    # Add download endpoint BEFORE mounting Flet
    @app.get("/download/{filename}")
    async def download_file(filename: str):
        """Serve file for download with proper headers.

        Note: File cleanup happens in the background via file_cleanup service.
        Files are removed after 2 hours by default.
        """
        file_path = Path(downloads_dir) / filename
        if file_path.exists():
            return FileResponse(
                path=str(file_path),
                media_type='application/octet-stream',
                headers={"Content-Disposition": f'attachment; filename="{filename}"'}
            )
        else:
            raise HTTPException(status_code=404, detail=f"{filename} not found")

    # Mount Flet app (this handles everything else including favicon)
    app.mount("/", flet_app)

    # Start background file cleanup service
    # Cleans up files older than 2 hours, runs every hour
    cleanup_interval = int(os.environ.get("CLEANUP_INTERVAL_SECONDS", 3600))  # 1 hour
    max_file_age = int(os.environ.get("MAX_FILE_AGE_SECONDS", 7200))  # 2 hours
    start_cleanup_service(cleanup_interval, max_file_age)
    log.info(f"Started file cleanup service (interval: {cleanup_interval}s, max age: {max_file_age}s)")

    # Run the app
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
