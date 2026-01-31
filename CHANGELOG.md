# Changelog

All notable changes to this project will be documented here.

## [2.0.0] - 2025-01-31

Initial release of v2. Complete rewrite as a single-file, import-driven application with no external dependencies beyond Python and tkinter.

### Added

- CSV import as the primary way to create and update BOMs
- Import dialog with two modes: create a new assembly or replace an existing one
- Option to save a BOM snapshot as a revision before replacing it
- Hierarchical BOM support: assemblies can contain components and other assemblies at any depth
- Recursive cost calculation that rolls up through all sub-assembly levels
- Three export formats: Standard, Flattened, and Exploded
- In-app Flattened BOM and Exploded BOM viewer dialogs (in addition to CSV export)
- Five-tab GUI: BOM Viewer, Cost Analysis, Component Management, Assembly Management, Revision History
- Component editing: update description, category, unit of measure, distributor, and pricing directly in the GUI
- Unused component detection and deletion
- Where-used tracking for both components and sub-assemblies
- Assembly search and filter
- Revision history viewer with export of historical BOM snapshots
- Duplicate source cleanup tool under the Tools menu
- Price preservation on re-import: a blank `unit_cost` field in CSV does not overwrite the existing price
- SQLite database auto-created on first run — no setup required
- Sample CSV files for quick testing
- Comprehensive test suite with 15-step test procedure (TEST_INSTRUCTIONS.md)

### Fixed

- CSV rows with blank trailing fields no longer cause `NoneType` errors — all fields are sanitised to empty strings before processing
- Import dialog now correctly selects and loads the newly imported assembly in the BOM Viewer after import completes
- Component Management tab now refreshes after every import
- BOM Viewer column header correctly reads "Unit Cost" rather than "Cost"
- Flattened and Exploded BOM viewer dialogs now show the Close and Export buttons without requiring the user to resize the window
- Import dialog sized appropriately so all controls and buttons are visible without resizing
- Sample CSV files corrected: blank manufacturer fields no longer contain extra commas that shift subsequent columns
