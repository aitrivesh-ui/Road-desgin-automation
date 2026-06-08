"""
PyInstaller entry point for the Road Design Automation suite.

Normal launch  : RoadDesign            → opens the Dashboard GUI
Tool dispatch  : RoadDesign --run-tool <module_name> [args...]
                 e.g.  RoadDesign --run-tool pavement_design --cli in.csv --out out.csv

The dispatch mechanism lets frozen subprocess calls (dashboard → tool panels)
work without needing a separate Python interpreter.
"""

import os
import sys


def _setup():
    """Set ROAD_ROOT so all tool modules find their data directories."""
    if getattr(sys, "frozen", False):
        root = os.path.dirname(sys.executable)
    else:
        # dev mode: main_dispatch.py lives in tools/, ROOT is one level up
        root = os.path.normpath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
        )
    os.environ.setdefault("ROAD_ROOT", root)

    # Ensure the tools directory is importable
    tools_dir = os.path.dirname(os.path.abspath(__file__)) if not getattr(sys, "frozen", False) \
                else os.path.dirname(sys.executable)
    if tools_dir not in sys.path:
        sys.path.insert(0, tools_dir)


def main():
    _setup()

    args = sys.argv[1:]

    if len(args) >= 2 and args[0] == "--run-tool":
        # Subprocess dispatch: run a tool module's main() with remaining argv
        tool_name = args[1]
        sys.argv = [tool_name + ".py"] + args[2:]
        import importlib
        try:
            mod = importlib.import_module(tool_name)
        except ImportError as exc:
            print(f"[ERROR] Cannot import tool '{tool_name}': {exc}", file=sys.stderr)
            sys.exit(1)
        if not hasattr(mod, "main"):
            print(f"[ERROR] Tool '{tool_name}' has no main() entry point.", file=sys.stderr)
            sys.exit(1)
        mod.main()
    else:
        # Default: launch the dashboard GUI
        from dashboard import main as dashboard_main
        dashboard_main()


if __name__ == "__main__":
    main()
