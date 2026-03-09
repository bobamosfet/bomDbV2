#!/usr/bin/env python3
"""
BOM Format Converter - Analysis & Conversion Logic
Converts various BOM file formats (SolidWorks CSV/XLSX, Altium XLSX, generic TSV, etc.)
into the standardized CSV format used by BOM Management System v2.

No GUI code — this module provides the data structures and functions.
"""

import csv
import io
import os
import re

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False


# ============================================================
# Column alias definitions
# ============================================================

COLUMN_ALIASES = {
    # MPN-priority columns: these map to the stored part number
    'mpn': [
        'mpn', 'mfg_part_number', 'mfg part number',
        'manufacture part number', 'manufacturer part number',
        'manufacture part number 1', 'manufacturer part number 1',
        'item_part_number',
    ],
    # Generic "Part Number" columns: used as primary when no MPN column exists,
    # or as internal PN / fallback when MPN column is present
    'part_number': [
        'part number', 'part_number', 'part no', 'part no.',
        'designitemid', 'pn',
    ],
    'description': [
        'description', 'desc', 'part description', 'part-desc', 'part_desc',
    ],
    'manufacturer': [
        'manufacturer', 'manufacture', 'mfg', 'manufacturer 1', 'manufacture 1',
    ],
    'quantity': ['quantity', 'qty', 'qty.', 'count'],
    'ref_des': [
        'ref_des', 'reference_designators', 'designator', 'designators',
        'ref des', 'reference designator', 'refdes',
    ],
    'unit_of_measure': ['unit_of_measure', 'uom', 'unit', 'units'],
    'category': ['category', 'cat'],
    'distributor': ['distributor', 'supplier', 'supplier 1', 'vendor'],
    'distributor_pn': [
        'distributor_pn', 'distributor part number', 'supplier part number',
        'supplier part number 1', 'dist_pn', 'vendor part number',
    ],
    'unit_cost': [
        'unit_cost', 'cost', 'price', 'unit price', 'supplier unit price',
        'supplier unit price 1',
    ],
    'notes': ['notes', 'note', 'comment', 'comments'],
    'item_number': [
        'item no.', 'item no', 'item_no', 'item number', 'item_number',
        'item #', 'id', 'line', 'line no',
    ],
    'item_type': ['item_type', 'type'],
}

# The standard output CSV column order
STANDARD_COLUMNS = [
    'item_part_number', 'item_type', 'manufacturer', 'description',
    'category', 'unit_of_measure', 'quantity', 'ref_des',
    'distributor', 'distributor_pn', 'unit_cost', 'notes',
]


# ============================================================
# File reading utilities
# ============================================================

def read_file_raw(filename):
    """Read any supported file and return all rows as list of string lists."""
    ext = os.path.splitext(filename)[1].lower()

    if ext == '.xlsx':
        if not HAS_OPENPYXL:
            raise Exception(
                "The 'openpyxl' package is required to read Excel files.\n"
                "Install it with: pip install openpyxl"
            )
        wb = openpyxl.load_workbook(filename, data_only=True)
        ws = wb.active
        rows = []
        for row in ws.iter_rows(values_only=True):
            str_row = [
                str(cell).replace('\n', ' ').replace('\r', ' ').strip()
                if cell is not None else ''
                for cell in row
            ]
            rows.append(str_row)
        wb.close()
        return rows

    # CSV / TSV
    delimiter = '\t' if ext == '.tsv' else ','

    try:
        with open(filename, 'r', newline='', encoding='utf-8') as f:
            raw = f.read()
    except UnicodeDecodeError:
        with open(filename, 'r', newline='', encoding='latin-1') as f:
            raw = f.read()

    rows = []
    reader = csv.reader(io.StringIO(raw), delimiter=delimiter)
    for row in reader:
        rows.append([cell.strip() for cell in row])
    return rows


def parse_metadata_rows(rows):
    """Extract assembly metadata from the first few rows.

    Looks for rows where cell 0 starts with '#assembly_'.
    Returns dict with part_number, description, revision (or None values).
    Also returns the number of metadata rows consumed.
    """
    metadata = {'part_number': None, 'description': '', 'revision': 'A'}
    meta_count = 0

    for row in rows[:5]:  # only check first 5 rows
        if not row or not row[0].startswith('#'):
            break
        key = row[0][1:].strip().lower()
        value = row[1].strip() if len(row) > 1 else ''

        if key == 'assembly_part_number':
            metadata['part_number'] = value
        elif key == 'assembly_description':
            metadata['description'] = value
        elif key == 'assembly_revision':
            metadata['revision'] = value
        meta_count += 1

    return metadata, meta_count


def find_header_row(rows, start_from=0):
    """Find the first row containing 2+ recognized column names.

    Returns (header_row_index, extra_rows_to_skip) or (None, 0).
    Handles Altium-style double headers (friendly name row + internal name row).
    """
    all_aliases = set()
    for aliases in COLUMN_ALIASES.values():
        for a in aliases:
            all_aliases.add(a.lower())

    for i in range(start_from, len(rows)):
        row = rows[i]
        if not row:
            continue
        matches = sum(1 for cell in row if cell.lower() in all_aliases)

        if matches >= 2:
            # Check for double header (Altium)
            skip = 0
            if i + 1 < len(rows):
                next_matches = sum(
                    1 for cell in rows[i + 1] if cell.lower() in all_aliases
                )
                if next_matches >= 2:
                    skip = 1
            return i, skip

    return None, 0


def build_column_map(header_row):
    """Map header cells to internal field names.

    Returns {internal_name: column_index}.
    """
    col_map = {}

    for col_idx, cell in enumerate(header_row):
        cell_lower = cell.lower().strip()
        if not cell_lower:
            continue
        for field_name, aliases in COLUMN_ALIASES.items():
            if cell_lower in aliases and field_name not in col_map:
                col_map[field_name] = col_idx
                break

    return col_map


# ============================================================
# File analysis
# ============================================================

class FileAnalysis:
    """Result of analyzing a single input file."""

    def __init__(self, filename):
        self.filename = filename
        self.basename = os.path.basename(filename)
        self.rows = []
        self.metadata = {'part_number': None, 'description': '', 'revision': 'A'}
        self.meta_row_count = 0
        self.header_idx = None
        self.header_skip = 0
        self.col_map = {}
        self.data_rows = []        # raw string rows (after header)
        self.is_hierarchical = False
        self.detected_columns = []  # list of (internal_name, original_header_text)
        self.unmapped_columns = []  # original header texts that weren't mapped
        self.data_row_count = 0
        self.error = None

    def analyze(self):
        """Perform full analysis of the file."""
        try:
            self.rows = read_file_raw(self.filename)
        except Exception as e:
            self.error = f"Cannot read file: {str(e)}"
            return

        # Parse metadata
        self.metadata, self.meta_row_count = parse_metadata_rows(self.rows)

        # Find header
        search_from = self.meta_row_count
        self.header_idx, self.header_skip = find_header_row(
            self.rows, start_from=search_from
        )

        if self.header_idx is None:
            self.error = "Could not find recognizable column headers."
            return

        header_row = self.rows[self.header_idx]
        self.col_map = build_column_map(header_row)

        # Track what was detected
        for idx, cell in enumerate(header_row):
            if not cell:
                continue
            internal = None
            for name, col_idx in self.col_map.items():
                if col_idx == idx:
                    internal = name
                    break
            if internal:
                self.detected_columns.append((internal, cell))
            else:
                self.unmapped_columns.append(cell)

        # We need at least a part number column
        if 'mpn' not in self.col_map and 'part_number' not in self.col_map:
            self.error = (
                "No part number column found.\n"
                "Expected: Part Number, MPN, Manufacturer Part Number, etc."
            )
            return

        # Extract data rows
        first_data = self.header_idx + 1 + self.header_skip
        raw_data = self.rows[first_data:]

        # Determine which column indices could hold the part number.
        pn_indices = []
        if 'mpn' in self.col_map:
            pn_indices.append(self.col_map['mpn'])
        if 'part_number' in self.col_map:
            pn_indices.append(self.col_map['part_number'])

        def row_has_pn(row):
            return any(
                idx < len(row) and row[idx] != ''
                for idx in pn_indices
            )

        # Keep only rows that have a non-empty part number.
        self.data_rows = []
        saw_gap = False
        for row in raw_data:
            if not row or all(c == '' for c in row):
                saw_gap = True
                continue

            if row_has_pn(row) and not saw_gap:
                self.data_rows.append(row)
            elif row_has_pn(row) and saw_gap:
                # After a gap, only continue if the quantity column also has
                # a plausible numeric value (filters footer labels)
                qty_idx = self.col_map.get('quantity')
                if qty_idx is not None and qty_idx < len(row):
                    qty_val = row[qty_idx]
                    try:
                        float(qty_val)
                        self.data_rows.append(row)
                        saw_gap = False
                    except (ValueError, TypeError):
                        break
                else:
                    break
            else:
                saw_gap = True

        self.data_row_count = len(self.data_rows)

        # Detect hierarchy
        item_num_idx = self.col_map.get('item_number')
        if item_num_idx is not None:
            for row in self.data_rows:
                if item_num_idx < len(row) and '.' in row[item_num_idx]:
                    self.is_hierarchical = True
                    break

    def get_field(self, row, field_name, default=''):
        """Get a field value from a raw data row using the column map."""
        idx = self.col_map.get(field_name)
        if idx is not None and idx < len(row):
            val = row[idx]
            # Skip Excel formula residue
            if val.startswith('='):
                return default
            return val
        return default


# ============================================================
# Conversion logic
# ============================================================

def convert_flat_bom(analysis):
    """Convert a flat (non-hierarchical) BOM to standard format.

    Returns list of output rows (each a dict with STANDARD_COLUMNS keys).
    """
    output_rows = []

    for row in analysis.data_rows:
        pn = analysis.get_field(row, 'mpn')
        if not pn:
            pn = analysis.get_field(row, 'part_number')
        if not pn:
            continue

        item_type = analysis.get_field(row, 'item_type', 'component').lower()
        if item_type not in ('component', 'assembly'):
            item_type = 'component'

        qty_str = analysis.get_field(row, 'quantity', '1') or '1'
        try:
            float(qty_str)
        except ValueError:
            qty_str = '1'

        output_rows.append({
            'item_part_number': pn,
            'item_type':        item_type,
            'manufacturer':     analysis.get_field(row, 'manufacturer'),
            'description':      analysis.get_field(row, 'description'),
            'category':         analysis.get_field(row, 'category'),
            'unit_of_measure':  analysis.get_field(row, 'unit_of_measure', 'EA') or 'EA',
            'quantity':         qty_str,
            'ref_des':          analysis.get_field(row, 'ref_des'),
            'distributor':      analysis.get_field(row, 'distributor'),
            'distributor_pn':   analysis.get_field(row, 'distributor_pn'),
            'unit_cost':        analysis.get_field(row, 'unit_cost'),
            'notes':            analysis.get_field(row, 'notes'),
        })

    return output_rows


def convert_hierarchical_bom(analysis):
    """Convert a hierarchical (SolidWorks-style) BOM to standard format.

    Returns a dict: { part_number: (metadata_dict, [row_dicts]) }
    """
    item_num_idx = analysis.col_map.get('item_number')

    # Build ordered list of (item_number, row)
    items = []
    for row in analysis.data_rows:
        if item_num_idx is not None and item_num_idx < len(row):
            inum = row[item_num_idx].strip()
        else:
            continue
        if not inum:
            continue
        items.append((inum, row))

    all_inums = set(inum for inum, _ in items)

    # Find which items have direct children → they are assemblies
    assembly_inums = set()
    for inum in all_inums:
        prefix = inum + '.'
        for other in all_inums:
            if other.startswith(prefix) and '.' not in other[len(prefix):]:
                assembly_inums.add(inum)
                break

    # Build a map from item number to its row data
    item_map = {}
    ordered_inums = []
    for inum, row in items:
        if inum not in item_map:
            ordered_inums.append(inum)
        item_map[inum] = row

    def get_pn(row):
        """Get part number from a row, preferring MPN."""
        pn = analysis.get_field(row, 'mpn')
        if not pn:
            pn = analysis.get_field(row, 'part_number')
        return pn or ''

    def get_direct_children(parent_inum):
        prefix = parent_inum + '.'
        seen = set()
        children = []
        for inum in ordered_inums:
            if inum.startswith(prefix) and '.' not in inum[len(prefix):]:
                if inum not in seen:
                    seen.add(inum)
                    children.append(inum)
        return children

    def get_top_level():
        seen = set()
        top = []
        for inum in ordered_inums:
            if '.' not in inum and inum not in seen:
                seen.add(inum)
                top.append(inum)
        return top

    def make_row_dict(row, item_type='component'):
        pn = get_pn(row)
        qty = analysis.get_field(row, 'quantity', '1') or '1'
        try:
            float(qty)
        except ValueError:
            qty = '1'
        return {
            'item_part_number': pn,
            'item_type':        item_type,
            'manufacturer':     analysis.get_field(row, 'manufacturer'),
            'description':      analysis.get_field(row, 'description'),
            'category':         analysis.get_field(row, 'category'),
            'unit_of_measure':  analysis.get_field(row, 'unit_of_measure', 'EA') or 'EA',
            'quantity':         qty,
            'ref_des':          analysis.get_field(row, 'ref_des'),
            'distributor':      analysis.get_field(row, 'distributor'),
            'distributor_pn':   analysis.get_field(row, 'distributor_pn'),
            'unit_cost':        analysis.get_field(row, 'unit_cost'),
            'notes':            analysis.get_field(row, 'notes'),
        }

    # Build output
    assemblies = {}

    # Process each sub-assembly
    for inum in assembly_inums:
        row = item_map[inum]
        assy_pn = get_pn(row)
        if not assy_pn:
            continue

        assy_meta = {
            'part_number': assy_pn,
            'description': analysis.get_field(row, 'description'),
            'revision': 'A',
        }

        assy_rows = []
        for child_inum in get_direct_children(inum):
            child_row = item_map[child_inum]
            child_type = 'assembly' if child_inum in assembly_inums else 'component'
            assy_rows.append(make_row_dict(child_row, child_type))

        assemblies[assy_pn] = (assy_meta, assy_rows)

    # Build top-level assembly
    top_meta = {
        'part_number': analysis.metadata['part_number'],
        'description': analysis.metadata['description'],
        'revision': analysis.metadata['revision'],
    }
    top_rows = []
    for inum in get_top_level():
        row = item_map[inum]
        item_type = 'assembly' if inum in assembly_inums else 'component'
        top_rows.append(make_row_dict(row, item_type))

    assemblies[top_meta['part_number']] = (top_meta, top_rows)

    return assemblies


def write_standard_csv(filepath, metadata, rows):
    """Write a single standardized CSV file with metadata header."""
    with open(filepath, 'w', newline='', encoding='utf-8') as f:
        f.write(f"#assembly_part_number,{metadata['part_number']}\n")
        if metadata.get('description'):
            f.write(f"#assembly_description,{metadata['description']}\n")
        else:
            f.write(f"#assembly_description,\n")
        f.write(f"#assembly_revision,{metadata.get('revision', 'A')}\n")

        writer = csv.DictWriter(f, fieldnames=STANDARD_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
