# Road design automation

Civil 3D workflow driven by **CSV + JSON**: alignments, profiles, corridors, volumes, markings, signage, BOQ, and DPR sheet manifests via **Dynamo (IronPython 2)** and **Python 3** validation tools.

> Engineering sign-off, template DWGs, and QA remain your responsibility.

## Documentation

| Document | Use when |
|----------|----------|
| **[testing_guide.html](testing_guide.html)** | **Testing the complete system** — open in a browser |
| **[civil3d_automation/TESTING.md](civil3d_automation/TESTING.md)** | Same procedures in Markdown (CI, editors) |
| **[civil3d_automation/README.md](civil3d_automation/README.md)** | Package layout and M8 run order |

Nothing at runtime reads the HTML file; Civil 3D and tools use `civil3d_automation/` only.

## Quick start

1. **Install tools (Windows):** double-click [`install.bat`](install.bat) or [`civil3d_automation/install_tools.bat`](civil3d_automation/install_tools.bat).
2. **Install Civil 3D** (2022+) with Dynamo and **IronPython 2**.
3. Copy [`civil3d_automation/config/project.example.json`](civil3d_automation/config/project.example.json) → `config/project.json`; edit CSVs under `civil3d_automation/csv/`.
4. **Validate (no Civil):** see [testing_guide.html](testing_guide.html) — `run_tests.bat` + preflight.
5. **Run pipeline:** Dynamo Player → `m8_run_all.py` → absolute path to `config/project.json`.

## Repository layout

```
road-desgin-automation/
  README.md                 ← you are here
  testing_guide.html        ← how to test end-to-end
  install.bat
  civil3d_automation/       ← runnable package
    README.md
    TESTING.md
    config/  csv/  python/  tools/  dynamo/  template/
```

## Tests (no Civil 3D)

```bat
cd civil3d_automation
run_tests.bat
python tools\road_automation_preflight.py --validate config\project.json
```

Full checklist: **[testing_guide.html](testing_guide.html)**.

## Author

Maintained by **[aitrivesh-ui](https://github.com/aitrivesh-ui)** — upstream repo: **[Road-desgin-automation](https://github.com/aitrivesh-ui/Road-desgin-automation)**.
