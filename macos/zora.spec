# -*- mode: python ; coding: utf-8 -*-
import sys
import os

# Add parent directory to path to import version module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath('.'))))
from version import __version__

block_cipher = None

a = Analysis(
    ['macos.py'],
    pathex=['..'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'flet',
        'flet.core',
        'flet.utils',
        'common.flags',
        'common.constants',
#        'windows.zrinterface',
        'ui.main',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ZORA',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ZORA',
)

app = BUNDLE(
    coll,
    name='ZORA.app',
    icon='../zora.icns',
    bundle_identifier='com.zora.randomizer',
    info_plist={
        'CFBundleName': 'ZORA',
        'CFBundleDisplayName': 'Zelda One Randomizer Add-ons',
        'CFBundleVersion': __version__,
        'CFBundleShortVersionString': __version__,
        'NSHighResolutionCapable': 'True',
        'LSMinimumSystemVersion': '10.13.0',
    },
)
