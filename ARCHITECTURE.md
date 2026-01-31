# Architecture

This document describes the database schema, the code structure, and how the main data flows work.

## Code Structure

The application lives in a single file, `bom_system_v2.py`, and is organised into two classes and an entry point:

```
bom_system_v2.py
├── BOMDatabase          All SQLite operations: schema, queries, inserts, deletes
├── BOMSystemGUI         The tkinter GUI: tabs, dialogs, import/export logic
└── main()               Creates the Tk root window and launches the GUI
```

`BOMDatabase` knows nothing about the GUI. All data access goes through it. `BOMSystemGUI` holds a single `BOMDatabase` instance and calls its methods to read and write data, then updates the interface accordingly.

## Database Schema

The database is a single SQLite file (`bom_system_v2.db`), created automatically on first run. It contains six tables.

### components

Stores each unique component. A component is identified by the combination of its manufacturer part number and manufacturer name.

| Column | Type | Notes |
|--------|------|-------|
| `component_id` | INTEGER PK | Auto-increment, used as the internal reference everywhere |
| `mfg_part_number` | TEXT | Manufacturer's part number |
| `manufacturer` | TEXT | |
| `description` | TEXT | |
| `category` | TEXT | Free-text grouping (e.g. Resistor, Capacitor) |
| `unit_of_measure` | TEXT | Defaults to `EA` |
| `notes` | TEXT | |

Unique constraint on `(mfg_part_number, manufacturer)` — importing the same part twice updates the existing record rather than creating a duplicate.

### component_sources

Stores distributor and pricing information for a component. A component can have multiple sources, but in practice only the lowest-cost source is used for cost calculations.

| Column | Type | Notes |
|--------|------|-------|
| `source_id` | INTEGER PK | |
| `component_id` | INTEGER FK → components | |
| `distributor` | TEXT | |
| `distributor_part_number` | TEXT | |
| `unit_cost` | REAL | Price per unit of measure |
| `last_updated` | TEXT | ISO 8601 timestamp |

Unique constraint on `(component_id, distributor)` — one price record per distributor per component.

### products

Stores assemblies. Every BOM in the system belongs to a product. The word "product" is used internally; the UI labels these as assemblies.

| Column | Type | Notes |
|--------|------|-------|
| `product_id` | INTEGER PK | |
| `part_number` | TEXT UNIQUE | The assembly's part number |
| `description` | TEXT | |
| `revision` | TEXT | Defaults to `A` |
| `created_date` | TEXT | ISO 8601 |
| `modified_date` | TEXT | ISO 8601 |
| `notes` | TEXT | |

### bom_entries

Links components to assemblies. Each row is one line item on a BOM.

| Column | Type | Notes |
|--------|------|-------|
| `entry_id` | INTEGER PK | Used to identify this row for deletion |
| `product_id` | INTEGER FK → products | The assembly this entry belongs to |
| `component_id` | INTEGER FK → components | The component on this line |
| `quantity` | REAL | In the component's unit of measure |
| `reference_designators` | TEXT | e.g. `R1,R2,R3` |
| `notes` | TEXT | |

### sub_assemblies

Links assemblies to other assemblies. Each row represents one sub-assembly line item on a parent BOM.

| Column | Type | Notes |
|--------|------|-------|
| `sub_assembly_id` | INTEGER PK | Used to identify this row for deletion |
| `parent_product_id` | INTEGER FK → products | The assembly that contains the sub-assembly |
| `child_product_id` | INTEGER FK → products | The sub-assembly being included |
| `quantity` | REAL | How many of the sub-assembly are used |
| `reference_designators` | TEXT | e.g. `A1` |
| `notes` | TEXT | |

The same child assembly can appear multiple times in one parent (different reference designators, same or different quantities) or in multiple parents.

### revision_history

Stores BOM snapshots taken before a BOM is replaced during re-import. The entire BOM state is serialised to JSON and stored in a single column.

| Column | Type | Notes |
|--------|------|-------|
| `revision_id` | INTEGER PK | |
| `product_id` | INTEGER FK → products | |
| `revision` | TEXT | The revision letter at the time of the snapshot |
| `change_date` | TEXT | ISO 8601 |
| `change_notes` | TEXT | User-provided notes at import time |
| `bom_snapshot` | TEXT | JSON object containing the full BOM |

The snapshot JSON has this structure:

```json
{
  "components": [
    {
      "entry_id": 1,
      "component_id": 5,
      "mfg_part_number": "RES-10K-0805",
      "manufacturer": "Yageo",
      "description": "10K Resistor 0805 1%",
      "quantity": 8,
      "reference_designators": "R1,R2,R3,R4,R5,R6,R7,R8",
      "unit_cost": 0.10,
      ...
    }
  ],
  "sub_assemblies": [
    {
      "sub_assembly_id": 2,
      "part_number": "PCB-POWER-001",
      "description": "Power Supply PCB",
      "quantity": 1,
      ...
    }
  ]
}
```

## Entity Relationships

```
components  ──────────────────► component_sources
    │                               (one-to-many)
    │
    │ (referenced by)
    ▼
bom_entries ◄──────────────────  products
                                    │
                                    │ (parent in)
                                    ▼
                              sub_assemblies ──► products
                                                (child)

revision_history ◄─────────────  products
```

## Key Data Flows

### Import

1. User selects a CSV file and either picks an existing assembly or creates a new one.
2. If replacing an existing BOM and the user opted to save a revision, the current BOM is serialised to JSON and written to `revision_history`.
3. The existing BOM entries and sub-assembly links for that product are deleted.
4. Each row in the CSV is processed:
   - **component rows:** `add_or_update_component` creates or updates the component record. If a distributor is present, `add_or_update_component_source` creates or updates pricing (preserving existing price if the CSV cost field is blank). A new `bom_entries` row is created.
   - **assembly rows:** The referenced assembly is looked up (or a placeholder is created if it does not exist yet). A new `sub_assemblies` row is created.
5. All GUI lists are refreshed.

### Cost Calculation

`calculate_bom_cost` is recursive. For a given product and build quantity:

1. Fetch all component entries and sub-assembly entries for that product.
2. For each component: multiply `unit_cost × quantity × build_quantity` and add to the total.
3. For each sub-assembly: call `calculate_bom_cost` on the child product with `quantity × build_quantity` as the new build quantity. Add the returned total to the parent total.
4. Return the total cost and a flat list of line-item details for display.

### Flattened BOM

`get_flattened_bom` walks the hierarchy recursively, accumulating all components into a single dictionary keyed by `(mfg_part_number, manufacturer)`. Quantities are summed — if the same component appears at multiple levels or multiple times, the total quantity across the entire assembly tree is returned. No assembly rows appear in the output.

### Exploded BOM

`get_exploded_bom` walks the hierarchy recursively, building item numbers as it goes (`1`, `1.1`, `1.2`, `1.1.1`, …). Every assembly and every component appears as its own row, with its level, indentation, and extended cost. Assembly rows show a calculated extended cost; component rows show unit cost and extended cost.

## GUI Metadata Tracking

The BOM Viewer treeview needs to know which database row each displayed item corresponds to, so that selecting and deleting an item works correctly. This is handled by `bom_item_metadata`, a dictionary that maps each treeview item ID to a tuple of `(type, db_id)`:

- `('component', entry_id)` — points to a `bom_entries` row
- `('assembly', sub_assembly_id)` — points to a `sub_assemblies` row

This is rebuilt each time the BOM viewer is refreshed.
