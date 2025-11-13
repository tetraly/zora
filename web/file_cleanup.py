"""Background task for cleaning up old uploaded and downloaded ROM files.

This module provides automatic cleanup of temporary files to prevent memory leaks
from accumulating files in uploads/ and assets/downloads/ directories.
"""

import os
import time
import threading
import logging as log
from pathlib import Path


class FileCleanupService:
    """Background service that periodically cleans up old temporary files."""

    def __init__(self, cleanup_interval_seconds=3600, max_file_age_seconds=7200):
        """Initialize the cleanup service.

        Args:
            cleanup_interval_seconds: How often to run cleanup (default: 1 hour)
            max_file_age_seconds: Remove files older than this (default: 2 hours)
        """
        self.cleanup_interval = cleanup_interval_seconds
        self.max_file_age = max_file_age_seconds
        self.running = False
        self.thread = None

    def cleanup_directory(self, directory):
        """Remove files older than max_file_age from directory.

        Args:
            directory: Directory path to clean up
        """
        if not os.path.exists(directory):
            return

        removed_count = 0
        removed_size = 0
        current_time = time.time()

        for file_path in Path(directory).rglob('*'):
            if not file_path.is_file():
                continue

            try:
                file_age = current_time - file_path.stat().st_mtime

                if file_age > self.max_file_age:
                    file_size = file_path.stat().st_size
                    file_path.unlink()
                    removed_count += 1
                    removed_size += file_size
                    log.debug(f"Removed old file: {file_path} (age: {file_age/3600:.1f} hours)")

            except Exception as e:
                log.error(f"Failed to remove {file_path}: {e}")

        if removed_count > 0:
            removed_size_mb = removed_size / 1024 / 1024
            log.info(f"Cleanup: Removed {removed_count} files ({removed_size_mb:.1f} MB) from {directory}")

    def run_cleanup(self):
        """Run cleanup for all temporary directories."""
        log.debug("Running scheduled file cleanup")
        self.cleanup_directory("uploads")
        self.cleanup_directory("assets/downloads")

    def _background_task(self):
        """Background thread that runs cleanup periodically."""
        log.info(f"File cleanup service started (interval: {self.cleanup_interval}s, max age: {self.max_file_age}s)")

        while self.running:
            try:
                self.run_cleanup()
            except Exception as e:
                log.error(f"Error during cleanup: {e}")

            # Sleep in small increments to allow quick shutdown
            for _ in range(int(self.cleanup_interval)):
                if not self.running:
                    break
                time.sleep(1)

        log.info("File cleanup service stopped")

    def start(self):
        """Start the background cleanup service."""
        if self.running:
            log.warning("Cleanup service is already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._background_task, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop the background cleanup service."""
        if not self.running:
            return

        log.info("Stopping cleanup service...")
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)


# Global cleanup service instance
_cleanup_service = None


def start_cleanup_service(cleanup_interval_seconds=3600, max_file_age_seconds=7200):
    """Start the global file cleanup service.

    Args:
        cleanup_interval_seconds: How often to run cleanup (default: 1 hour)
        max_file_age_seconds: Remove files older than this (default: 2 hours)
    """
    global _cleanup_service

    if _cleanup_service is not None:
        log.warning("Cleanup service already started")
        return

    _cleanup_service = FileCleanupService(cleanup_interval_seconds, max_file_age_seconds)
    _cleanup_service.start()


def stop_cleanup_service():
    """Stop the global file cleanup service."""
    global _cleanup_service

    if _cleanup_service is not None:
        _cleanup_service.stop()
        _cleanup_service = None
