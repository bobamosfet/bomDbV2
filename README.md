# BOM Management System

A desktop application for managing hierarchical Bills of Materials. Import BOMs from CSV, track component costs across nested sub-assemblies, manage pricing, and export in multiple formats suited to different workflows.

![Python](https://img.shields.io/badge/Python-3.6%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![Dependencies](https://img.shields.io/badge/Dependencies-None-brightgreen)

## Features

- **Import-driven workflow** — BOMs are created and updated by importing CSV files
- **Hierarchical assemblies** — Assemblies can contain components and other assemblies, to any depth
- **Automatic cost rollup** — Costs calculate recursively through all sub-assembly levels
- **Three export formats** — Standard (round-trip editable), Flattened (purchasing), Exploded (documentation)
- **Revision history** — Snapshot any BOM before replacing it; view or export any past revision
- **Component management** — Edit pricing in the GUI, find and clean up unused parts
- **Where-used tracking** — See every assembly that references a given component or sub-assembly
- **Price preservation** — Leaving `unit_cost` blank in an import CSV keeps the existing price intact

## Requirements

- Python 3.6 or later
- tkinter (included with standard Python on Windows and macOS; on Linux: `sudo apt install python3-tk`)
- No other dependencies

## Running

```bash
python bom_system_v2.py
```

The application creates `bom_system_v2.db` in the current working directory on first run. No configuration is needed.

## Quick Start

1. Click **Import BOM** on the BOM Viewer tab
2. Select a CSV file
3. Choose **Create new assembly**, fill in the part number, and click **Import**
4. The BOM populates in the viewer and the total cost calculates automatically

Sample CSV files are included in the repository. See [TESTING.md](TESTING.md) for a full walkthrough using the provided test files.

## CSV Format

Import and standard export share the same format, so you can export a BOM, edit it in a spreadsheet, and re-import it without any conversion.

| Column | Required | Description |
|--------|----------|-------------|
| `item_part_number` | Yes | The part number or assembly number |
| `item_type` | Yes | `component` or `assembly` |
| `manufacturer` | No | Leave blank if unknown |
| `description` | No | |
| `category` | No | Free-text grouping label |
| `unit_of_measure` | No | Defaults to `EA` if blank |
| `quantity` | Yes | In the component's unit of measure |
| `ref_des` | No | Reference designators, e.g. `R1` or `"C1,C2,C3"` |
| `distributor` | No | |
| `distributor_pn` | No | Distributor part number |
| `unit_cost` | No | **Leave blank to preserve the existing price on re-import** |
| `notes` | No | |

> **Comma handling:** A blank field is a single comma. Do not double up commas for blank fields. Correct: `PART,component,,Description` — Incorrect: `PART,component,,,Description`

## Application Layout

The application is organised into five tabs:

| Tab | What it does |
|-----|--------------|
| **BOM Viewer** | Browse any assembly's BOM. Import, export, delete individual items, or view the Flattened and Exploded formats in a popup |
| **Cost Analysis** | Select an assembly and a build quantity to see a full cost breakdown, with sub-assembly costs rolled up recursively |
| **Component Management** | List all components or filter to unused ones. Edit details and pricing, delete unused parts, or check where any component is used |
| **Assembly Management** | Search and browse assemblies. Check where an assembly appears as a sub-assembly in other BOMs |
| **Revision History** | View saved revisions for any assembly. Each revision stores a full BOM snapshot that can be viewed or exported |

## Export Formats

**Standard** — Same structure as the import format. Edit in a spreadsheet and re-import to update the BOM.

**Flattened** — Components only, no assemblies. Quantities are summed across all sub-assembly levels. Useful for purchasing or inventory planning.

**Exploded** — Full hierarchy with item numbers (`1`, `1.1`, `1.2`, `1.1.1`, …) and costs at every level. Useful for manufacturing documentation.

## Unit of Measure

The system uses whatever unit you specify. If a part is sold in a different package size than how it is consumed, enter the per-unit cost and note the packaging in the notes field.

Example — wire sold in 100 ft spools at $25.00:

| Field | Value |
|-------|-------|
| unit_of_measure | FT |
| unit_cost | 0.25 |
| notes | Sold in 100ft spools at $25 |

Quantities in the BOM are recorded in feet, and all cost calculations use $0.25/ft.

## Repository Contents

| File | Description |
|------|-------------|
| `bom_system_v2.py` | The application — single file, no build step required |
| `sample_bom_import.csv` | A simple 10-component BOM for a quick first test |
| `sample_psu_bom.csv` | A BOM that references sub-assemblies |
| `test_pcb_power.csv` | Test file: power supply PCB (17 components) |
| `test_pcb_display.csv` | Test file: display PCB (10 components) |
| `test_cable_assy.csv` | Test file: cable assembly with mixed units (9 components) |
| `test_main_enclosure.csv` | Test file: top-level assembly referencing all sub-assemblies |
| `test_pcb_power_rev_b.csv` | Test file: updated power PCB for testing revision workflow |
| `TEST_INSTRUCTIONS.md` | Step-by-step test procedure covering all features |
| `ARCHITECTURE.md` | Database schema and code structure |
| `CHANGELOG.md` | Version history |
| `LICENSE` | MIT license |

## License

MIT — see [LICENSE](LICENSE).
