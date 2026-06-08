# road_design.spec — PyInstaller build spec for Road Design Automation
# Build: pyinstaller road_design.spec
# Output: dist/RoadDesign/

import os

block_cipher = None

TOOLS = os.path.join(os.path.dirname(SPEC), 'civil3d_automation', 'tools')
ROOT_DIR = os.path.join(os.path.dirname(SPEC), 'civil3d_automation')

a = Analysis(
    [os.path.join(TOOLS, 'main_dispatch.py')],
    pathex=[TOOLS],
    binaries=[],
    datas=[
        (os.path.join(ROOT_DIR, 'config'), 'config'),
        (os.path.join(ROOT_DIR, 'csv'),    'csv'),
    ],
    hiddenimports=[
        # local tool modules (loaded dynamically via importlib in dispatch)
        'alignment_qc',
        'dashboard',
        'pavement_design',
        'drainage_design',
        'intersection_design',
        'report_generator',
        'design_verifier',
        'm21_curve_schedule',
        'road_automation_preflight',
        'preflight_validate',
        'build_starter_workbook',
        'clone_new_job',
        'design_check_outputs',
        'export_workbook_to_csv',
        # openpyxl sub-packages (used by M19 Report and Workbook builder)
        'openpyxl',
        'openpyxl.styles',
        'openpyxl.styles.stylesheet',
        'openpyxl.utils',
        'openpyxl.chart',
        'openpyxl.chart.series',
        'openpyxl.worksheet.datavalidation',
        'openpyxl.comments',
        'openpyxl.reader.excel',
        'openpyxl.writer.excel',
        # tkinter is stdlib but declare explicitly for clarity
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.scrolledtext',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'pandas', 'scipy'],
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
    name='RoadDesign',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,   # keep console for subprocess log streaming; set False for silent launch
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
    upx=False,
    upx_exclude=[],
    name='RoadDesign',
)
