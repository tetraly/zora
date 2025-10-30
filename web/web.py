"""Web entry point for Render.com deployment."""
import flet as ft
import flet.fastapi as flet_fastapi
import logging as log
import os
import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

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

    # Create Flet app first
    flet_app = flet_fastapi.app(
        main,
        upload_dir=upload_dir,
        assets_dir=assets_dir
    )

    # Create FastAPI app
    app = FastAPI()

    # Add download endpoint BEFORE mounting Flet
    @app.get("/download/{filename}")
    async def download_file(filename: str):
        """Serve file for download with proper headers."""
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

    # Run the app
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
