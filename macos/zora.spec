# -*- mode: python ; coding: utf-8 -*-

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
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': 'True',
        'LSMinimumSystemVersion': '10.13.0',
    },
)
