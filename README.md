# Road design automation

Civil 3D–centric workflow: **CSV + JSON** drive alignments, profiles, corridors, volumes, signage, and BOQ-style rollups via **Dynamo (IronPython 2)** scripts—plus HTML documentation and small **Python 3** helpers for data checks outside Civil.

> **Note:** This repo is tooling and documentation, not a substitute for engineering sign-off. You supply standards, template DWGs, and QA.

## What is in this repository

| Area | Description |
|------|-------------|
| **[`civil3d_automation/`](civil3d_automation/)** | M1–M8 Python scripts for Dynamo, sample CSVs, `project.json`, Dynamo graph notes, preflight/clone/export tools, unit tests |
| **HTML guides** (repo root) | User guide, beginner primer, markings hub, advanced playbook |

Start with **[`road_automation_user_guide.html`](road_automation_user_guide.html)** in a browser (installation, run order, manual vs automated).

## Quick start

1. Install **Autodesk Civil 3D** (2022+ recommended) with **Dynamo** and **IronPython 2** for Python Script nodes.
2. Clone this repo and keep `civil3d_automation/` next to the HTML files so links work.
3. Prepare a **template DWG/DWT** once (layers, styles, assemblies, blocks)—see [`civil3d_automation/template/README.md`](civil3d_automation/template/README.md).
4. Copy [`civil3d_automation/config/project.example.json`](civil3d_automation/config/project.example.json) to `config/project.json`, edit names/paths, fill CSVs (or use [`csv/templates/`](civil3d_automation/csv/templates/) as blanks).
5. Optional: run [`civil3d_automation/tools/run_preflight.bat`](civil3d_automation/tools/run_preflight.bat) or `python road_automation_preflight.py --validate path\to\project.json [--strict]`.
6. In Civil 3D, run **M8** from Dynamo Player with the **absolute path** to `config/project.json`.

## Documentation map

- **[Beginner primer](road_automation_beginners.html)** — plain-language concepts, glossary, common `ERROR:` fixes  
- **[User guide](road_automation_user_guide.html)** — full install, folder layout, Dynamo setup, troubleshooting  
- **[Markings hub](road_marking_dynamo.html)** — pavement marking solids from feature lines / 3D polylines  
- **[Advanced playbook](road_automation_advanced.html)** — extended automation narrative  
- **[Package README](civil3d_automation/README.md)** — M1–M8 layout, run order, testing, version control tips  
- **[API notes](civil3d_automation/API_NOTES.md)** — Civil 3D / Dynamo assumptions after upgrades  

## Tools (Python 3, not Civil’s IronPython)

| Script | Purpose |
|--------|---------|
| `civil3d_automation/tools/road_automation_preflight.py` | Validate `project.json` paths and CSV headers; optional `--strict` data checks |
| `civil3d_automation/tools/clone_new_job.py` | Clone a fresh package folder with blank CSVs + `project.json` |
| `civil3d_automation/tools/export_workbook_to_csv.py` | Export starter `.xlsx` sheets to CSV (needs `openpyxl`) |
| `civil3d_automation/tools/design_check_outputs.py` | Quick read of volumes / BOQ CSVs after a run |

Details: [`civil3d_automation/tools/README.md`](civil3d_automation/tools/README.md).

## Tests

From `civil3d_automation/`:

```bat
run_tests.bat
```

## License

Add a `LICENSE` file if you want to open-source this repo explicitly; until then, all rights reserved unless you state otherwise.

## Author

Maintained by **[aitrivesh-ui](https://github.com/aitrivesh-ui)** — upstream repo: **[Road-desgin-automation](https://github.com/aitrivesh-ui/Road-desgin-automation)**.
