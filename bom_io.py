#!/usr/bin/env python3
"""
BOM Import/Export Logic
Pure file I/O and CSV processing — no GUI code.
Raises exceptions on errors for the GUI layer to handle.
"""

import csv
import io
import os


# ============================================================
# CSV metadata parsing
# ============================================================

def parse_csv_metadata(filename):
    """Parse assembly metadata from comment rows at the top of a CSV file.

    Metadata rows start with '#' and use the format:
        #key,value

    Supported keys:
        #assembly_part_number,ABC-1234
        #assembly_description,My Assembly Description
        #assembly_revision,A

    Returns a dict with keys: part_number, description, revision.
    Returns None if no assembly_part_number is found.
    """
    metadata = {
        'part_number': None,
        'description': '',
        'revision': 'A'
    }

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line.startswith('#'):
                    break  # Stop at first non-metadata row

                # Remove leading '#' and split on first comma only
                content = line[1:]
                if ',' in content:
                    key, value = content.split(',', 1)
                    key = key.strip().lower()
                    value = value.strip()

                    if key == 'assembly_part_number':
                        metadata['part_number'] = value
                    elif key == 'assembly_description':
                        metadata['description'] = value
                    elif key == 'assembly_revision':
                        metadata['revision'] = value
    except Exception as e:
        raise Exception(f"Error reading metadata from {os.path.basename(filename)}: {str(e)}")

    if not metadata['part_number']:
        return None

    return metadata


def scan_csv_sub_assemblies(filename):
    """Scan a CSV file and return the set of sub-assembly part numbers it references."""
    sub_assemblies = set()
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            lines = [line for line in f.readlines() if not line.strip().startswith('#')]

        reader = csv.DictReader(io.StringIO(''.join(lines)))
        for row in reader:
            if row.get('item_type', '').strip().lower() == 'assembly':
                pn = row.get('item_part_number', '').strip()
                if pn:
                    sub_assemblies.add(pn)
    except Exception:
        pass  # Errors will be caught later during actual import
    return sub_assemblies


def topological_sort_files(file_metadata):
    """Sort files so that sub-assemblies are imported before their parents.

    Uses Kahn's algorithm. Files whose sub-assemblies aren't in the batch
    (i.e. already in the DB or will become placeholders) have no ordering
    constraint and are imported first.

    Args:
        file_metadata: list of (filename, metadata_dict) tuples

    Returns the sorted list, or raises an Exception on circular dependencies.
    """
    # Build a map: part_number -> (filename, metadata)
    pn_to_file = {}
    for fn, metadata in file_metadata:
        pn_to_file[metadata['part_number']] = (fn, metadata)

    # Build dependency graph: for each file, which other files in this batch
    # must be imported first?
    deps = {}
    for fn, metadata in file_metadata:
        pn = metadata['part_number']
        sub_asms = scan_csv_sub_assemblies(fn)
        # Only count dependencies that are in this batch
        deps[pn] = sub_asms & set(pn_to_file.keys())

    # Kahn's algorithm
    sorted_pns = []
    in_degree = {pn: len(pn_deps) for pn, pn_deps in deps.items()}

    queue = [pn for pn, deg in in_degree.items() if deg == 0]

    while queue:
        pn = queue.pop(0)
        sorted_pns.append(pn)

        # For every file that depends on pn, reduce its in-degree
        for other_pn, other_deps in deps.items():
            if pn in other_deps:
                in_degree[other_pn] -= 1
                if in_degree[other_pn] == 0:
                    queue.append(other_pn)

    if len(sorted_pns) != len(deps):
        # Find the cycle participants for a useful error message
        remaining = [pn for pn in deps if pn not in sorted_pns]
        raise Exception(
            f"Circular dependency detected among: {', '.join(remaining)}.\n\n"
            "A sub-assembly cannot reference its own parent."
        )

    return [(pn_to_file[pn][0], pn_to_file[pn][1]) for pn in sorted_pns]


# ============================================================
# Import: read CSV and write to database
# ============================================================

def process_import_to_db(db, filename, import_info):
    """Import a CSV file into the database.

    Args:
        db: BOMDatabase instance
        filename: path to CSV file
        import_info: dict with keys:
            part_number, save_revision (bool), notes (str), is_new (bool),
            and for new assemblies: description, revision

    Returns:
        (imported_components, imported_assemblies) counts

    Raises Exception on any error.
    """
    part_number = import_info['part_number']
    if not part_number:
        raise Exception("No part number specified")

    # Get or create product
    product = db.get_product(part_number)

    if product:
        product_id = product['product_id']

        # Save revision if requested
        if import_info.get('save_revision'):
            db.save_bom_as_revision(
                product_id,
                product['revision'],
                import_info.get('notes', '')
            )

        # Clear existing BOM
        db.clear_product_bom(product_id)
    else:
        # Create new product
        description = import_info.get('description', '')
        revision = import_info.get('revision', 'A')
        product_id = db.add_or_update_product(part_number, description, revision)

    # Read and import CSV (skipping metadata rows that start with '#')
    imported_components = 0
    imported_assemblies = 0

    with open(filename, 'r', newline='', encoding='utf-8') as f:
        # Skip metadata rows at top
        lines = f.readlines()
        data_lines = []
        for line in lines:
            if line.strip().startswith('#'):
                continue
            data_lines.append(line)

        reader = csv.DictReader(io.StringIO(''.join(data_lines)))

        for row_num, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
            try:
                # Sanitize row - CSV reader can return None for missing trailing fields
                row = {k: (v if v is not None else '') for k, v in row.items()}

                if not row.get('item_part_number') or not row.get('item_type'):
                    continue

                item_type = row['item_type'].strip().lower()
                item_pn = row['item_part_number'].strip()

                # Parse quantity with error handling
                qty_str = row.get('quantity', '1').strip()
                if not qty_str:
                    qty_str = '1'
                try:
                    quantity = float(qty_str)
                except ValueError:
                    raise ValueError(f"Invalid quantity '{qty_str}' for {item_pn}")

                ref_des = row.get('ref_des', '').strip()
                notes = row.get('notes', '').strip()

                if item_type == 'component':
                    # Add component
                    manufacturer = row.get('manufacturer', '').strip()
                    description = row.get('description', '').strip()
                    category = row.get('category', '').strip()
                    uom = row.get('unit_of_measure', 'EA').strip()
                    if not uom:
                        uom = 'EA'
                    distributor = row.get('distributor', '').strip()
                    dist_pn = row.get('distributor_pn', '').strip()

                    # Parse cost (handle blank values)
                    cost_str = row.get('unit_cost', '').strip()
                    unit_cost = None
                    if cost_str:
                        try:
                            unit_cost = float(cost_str)
                        except ValueError:
                            print(f"Warning: Invalid cost '{cost_str}' for {item_pn}, skipping cost")

                    component_id = db.add_or_update_component(
                        item_pn, manufacturer, description, category, uom, notes
                    )

                    if distributor:
                        db.add_or_update_component_source(
                            component_id, distributor, dist_pn, unit_cost
                        )

                    db.add_bom_entry(product_id, component_id, quantity, ref_des, notes)
                    imported_components += 1

                elif item_type == 'assembly':
                    # Add sub-assembly
                    child_product = db.get_product(item_pn)
                    if not child_product:
                        # Create placeholder assembly
                        child_product_id = db.add_or_update_product(
                            item_pn,
                            row.get('description', '').strip()
                        )
                    else:
                        child_product_id = child_product['product_id']

                    db.add_sub_assembly(product_id, child_product_id, quantity, ref_des, notes)
                    imported_assemblies += 1

            except Exception as e:
                raise Exception(
                    f"Error on row {row_num} "
                    f"({item_pn if 'item_pn' in locals() else 'unknown'}): {str(e)}"
                )

    # Save initial revision for newly created assemblies
    if import_info.get('is_new', False):
        db.save_bom_as_revision(
            product_id,
            db.get_product(part_number)['revision'],
            "Initial BOM import"
        )

    return imported_components, imported_assemblies


# ============================================================
# Export: write database data to CSV files
# ============================================================

def write_bom_csv(filename, product, components, sub_assemblies):
    """Write a standard BOM CSV with assembly metadata header.

    Args:
        filename: output path
        product: product Row object (needs part_number, description, revision)
        components: list of component Row objects from get_product_bom
        sub_assemblies: list of sub-assembly Row objects from get_product_bom
    """
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        # Write assembly metadata rows
        f.write(f"#assembly_part_number,{product['part_number']}\n")
        if product['description']:
            f.write(f"#assembly_description,{product['description']}\n")
        f.write(f"#assembly_revision,{product['revision']}\n")

        writer = csv.writer(f)
        writer.writerow(['item_part_number', 'item_type', 'manufacturer', 'description',
                         'category', 'unit_of_measure', 'quantity', 'ref_des',
                         'distributor', 'distributor_pn', 'unit_cost', 'notes'])

        for comp in components:
            writer.writerow([
                comp['mfg_part_number'],
                'component',
                comp['manufacturer'],
                comp['description'],
                comp['category'],
                comp['unit_of_measure'],
                comp['quantity'],
                comp['reference_designators'],
                comp['distributor'] or '',
                comp['distributor_part_number'] or '',
                comp['unit_cost'] if comp['unit_cost'] else '',
                comp['notes'] or ''
            ])

        for sub in sub_assemblies:
            writer.writerow([
                sub['part_number'],
                'assembly',
                '',
                sub['description'],
                'Assembly',
                'EA',
                sub['quantity'],
                sub['reference_designators'],
                '',
                '',
                '',
                sub['notes'] or ''
            ])


def write_flattened_csv(filename, flattened):
    """Write a flattened BOM CSV (components only, quantities summed).

    Args:
        filename: output path
        flattened: list of dicts from db.get_flattened_bom()
    """
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['part_number', 'manufacturer', 'description', 'category',
                         'unit_of_measure', 'total_quantity', 'unit_cost', 'extended_cost',
                         'distributor', 'distributor_pn'])

        for item in flattened:
            extended = float(item['unit_cost']) * item['quantity'] if item['unit_cost'] else 0
            writer.writerow([
                item['part_number'],
                item['manufacturer'],
                item['description'],
                item['category'],
                item['unit_of_measure'],
                item['quantity'],
                item['unit_cost'] if item['unit_cost'] else '',
                f"{extended:.2f}" if item['unit_cost'] else '',
                item['distributor'] or '',
                item['distributor_pn'] or ''
            ])


def write_exploded_csv(filename, exploded):
    """Write an exploded BOM CSV (hierarchical with item numbers).

    Args:
        filename: output path
        exploded: list of dicts from db.get_exploded_bom()
    """
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['item_number', 'level', 'indent', 'item_type', 'part_number',
                         'manufacturer', 'description', 'unit_of_measure', 'quantity',
                         'ref_des', 'unit_cost', 'extended_cost', 'notes'])

        for item in exploded:
            writer.writerow([
                item['item_number'],
                item['level'],
                item['indent'],
                item['item_type'],
                item['part_number'],
                item['manufacturer'],
                item['description'],
                item['unit_of_measure'],
                item['quantity'],
                item['ref_des'],
                item['unit_cost'],
                f"{item['extended_cost']:.2f}" if item['extended_cost'] else '',
                item['notes']
            ])


def write_revision_csv(filename, snapshot):
    """Write a revision snapshot BOM to CSV.

    Args:
        filename: output path
        snapshot: dict with 'components' and 'sub_assemblies' lists (from JSON)
    """
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['item_part_number', 'item_type', 'manufacturer', 'description',
                         'category', 'unit_of_measure', 'quantity', 'ref_des',
                         'distributor', 'distributor_pn', 'unit_cost', 'notes'])

        for comp in snapshot['components']:
            writer.writerow([
                comp['mfg_part_number'],
                'component',
                comp['manufacturer'],
                comp['description'],
                comp['category'],
                comp['unit_of_measure'],
                comp['quantity'],
                comp['reference_designators'],
                comp.get('distributor', ''),
                comp.get('distributor_part_number', ''),
                comp.get('unit_cost', ''),
                comp.get('notes', '')
            ])

        for sub in snapshot['sub_assemblies']:
            writer.writerow([
                sub['part_number'],
                'assembly',
                '',
                sub['description'],
                'Assembly',
                'EA',
                sub['quantity'],
                sub['reference_designators'],
                '',
                '',
                '',
                sub.get('notes', '')
            ])
