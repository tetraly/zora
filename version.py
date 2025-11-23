"""
ZORA (Zelda One Randomizer Add-ons) Version Information

This file contains the single source of truth for the ZORA version number.
All version references throughout the codebase should import from this file.
"""

# Version number (semantic versioning)
__version__ = "1.0.1"

# Display name for UI
__version_display__ = f"v{__version__}"

# Short version for ROM (limited space - 17 characters max for the title screen)
# Format: "  ZORA  V1.0-RC1"
__version_rom__ = f"V{__version__}  "
