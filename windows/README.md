# Windows Build Instructions

This directory contains the files needed to build the Windows desktop version of ZORA.

## Prerequisites

1. **Python 3.x** with the following packages:
   - `flet`
   - `PyInstaller`

   Install with: `pip install flet pyinstaller`

2. **AutoIt3** (for compiling the Zelda Randomizer interface script)
   - Download from: https://www.autoitscript.com/site/autoit/downloads/
   - Install the full version (includes the script editor and compiler)

## Build Steps

### Step 1: Compile AutoIt Script to EXE

The `zrinterface.au3` script automates interaction with the Zelda Randomizer application. You need to compile it to an executable:

1. Right-click on `zrinterface.au3`
2. Select **"Compile Script (x64)"** from the context menu
   - Use x64 for modern Windows 10/11 systems
   - Use x86 only if targeting very old 32-bit Windows installations
3. This will generate `zrinterface.exe` in the same directory

**Note:** You must recompile `zrinterface.exe` whenever you make changes to `zrinterface.au3`.

### Step 2: Build ZORA Windows Application

Once you have `zrinterface.exe` compiled, build the main ZORA application:

```bash
# Navigate to the windows directory
cd C:\Users\Tetra\Documents\GitHub\zora\windows

# Build with PyInstaller
python -m PyInstaller app.spec
```

### Step 3: Locate the Built Application

After the build completes successfully:

- The executable will be located at: `windows/dist/ZORA.exe`
- This is a single-file executable that includes:
  - All Python dependencies
  - `zrinterface.exe` (bundled internally)
  - Assets and resources

You can distribute just this single `ZORA.exe` file to users.

## How It Works

When `ZORA.exe` runs:
1. PyInstaller extracts bundled files (including `zrinterface.exe`) to a temporary directory
2. The application finds `zrinterface.exe` using `sys._MEIPASS`
3. When the user clicks "Generate Base ROM with Zelda Randomizer":
   - It writes parameters to a temp file
   - Launches `zrinterface.exe`
   - `zrinterface.exe` automates the Zelda Randomizer 3.5.22 window
   - The generated ROM is saved to disk

## Troubleshooting

### Build Warnings
- Warnings about `flet.map` can be safely ignored (this module is excluded in `app.spec`)
- Other warnings are usually safe unless the build fails

### Runtime Issues
- **"Cannot find Zelda Randomizer"**: Make sure Zelda Randomizer 3.5.22 is running and visible
- **"zrinterface.exe not found"**: Recompile the AutoIt script before building with PyInstaller
- **Version mismatch**: Update the version in `version.py` at the repository root

## Version Management

All version numbers are managed centrally in `/version.py`. When you update the version:
- Window title updates automatically
- UI header updates automatically
- ROM title screen updates automatically
- macOS bundle version updates automatically

No need to update version numbers in multiple files!
