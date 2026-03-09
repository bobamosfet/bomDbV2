#!/usr/bin/env python3
"""
BOM Dialogs
All popup/Toplevel dialog windows used by the BOM Management System.
Each dialog is a standalone function that creates a Toplevel window.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import json
import os


# ============================================================
# Replace BOM dialog (blocking)
# ============================================================

def show_replace_dialog(root, db, part_number, filename, imported_so_far, total_files):
    """Show dialog for replacing an existing BOM. Blocks until user responds.

    Returns a dict with keys:
        part_number, save_revision (bool), notes (str), cancelled (bool)
    """
    result = {'part_number': part_number, 'save_revision': False, 'notes': '', 'cancelled': False}

    dialog = tk.Toplevel(root)
    dialog.title("Replace Existing BOM")
    dialog.geometry("550x300")
    dialog.transient(root)
    dialog.grab_set()

    product = db.get_product(part_number)

    ttk.Label(dialog, text=f"Assembly {part_number} Rev {product['revision']} already exists",
              font=('TkDefaultFont', 11, 'bold')).pack(pady=10)

    progress_text = f"File: {os.path.basename(filename)}"
    if total_files > 1:
        progress_text += f"  ({imported_so_far + 1} of {total_files})"
    ttk.Label(dialog, text=progress_text,
              font=('TkDefaultFont', 9, 'italic')).pack(pady=2)

    ttk.Label(dialog, text="The current BOM will be deleted and replaced\nwith the imported BOM.").pack(pady=5)

    save_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(dialog, text="Save current BOM as revision before replacing",
                    variable=save_var).pack(pady=10)

    ttk.Label(dialog, text="Revision notes (optional):").pack(pady=5)
    notes_entry = ttk.Entry(dialog, width=50)
    notes_entry.pack(pady=5)

    def proceed():
        result['save_revision'] = save_var.get()
        result['notes'] = notes_entry.get().strip()
        result['cancelled'] = False
        dialog.destroy()

    def cancel():
        result['cancelled'] = True
        dialog.destroy()

    btn_frame = ttk.Frame(dialog)
    btn_frame.pack(pady=20)

    ttk.Button(btn_frame, text="Cancel Import",
               command=cancel).pack(side=tk.LEFT, padx=5)
    ttk.Button(btn_frame, text="Replace BOM",
               command=proceed).pack(side=tk.LEFT, padx=5)

    # Handle window close (X button) as cancel
    dialog.protocol("WM_DELETE_WINDOW", cancel)

    dialog.wait_window()
    return result


# ============================================================
# Edit component dialog
# ============================================================

def show_edit_component_dialog(root, db, component_id):
    """Show dialog to edit a component's details.

    Returns True if the component was saved, False if cancelled.
    """
    comp = db.get_component_details(component_id)
    if not comp:
        messagebox.showerror("Error", "Component not found")
        return False

    saved = {'value': False}

    dialog = tk.Toplevel(root)
    dialog.title(f"Edit Component: {comp['mfg_part_number']}")
    dialog.geometry("500x350")
    dialog.transient(root)
    dialog.grab_set()

    ttk.Label(dialog, text=f"Editing: {comp['mfg_part_number']} ({comp['manufacturer']})",
              font=('TkDefaultFont', 11, 'bold')).pack(pady=10)

    form = ttk.Frame(dialog)
    form.pack(padx=20, pady=10, fill=tk.BOTH, expand=True)

    ttk.Label(form, text="Description:").grid(row=0, column=0, sticky=tk.W, pady=5)
    desc_entry = ttk.Entry(form, width=50)
    desc_entry.insert(0, comp['description'] or '')
    desc_entry.grid(row=0, column=1, pady=5)

    ttk.Label(form, text="Category:").grid(row=1, column=0, sticky=tk.W, pady=5)
    cat_entry = ttk.Entry(form, width=50)
    cat_entry.insert(0, comp['category'] or '')
    cat_entry.grid(row=1, column=1, pady=5)

    ttk.Label(form, text="Unit of Measure:").grid(row=2, column=0, sticky=tk.W, pady=5)
    uom_entry = ttk.Entry(form, width=20)
    uom_entry.insert(0, comp['unit_of_measure'] or 'EA')
    uom_entry.grid(row=2, column=1, sticky=tk.W, pady=5)

    ttk.Label(form, text="Distributor:").grid(row=3, column=0, sticky=tk.W, pady=5)
    dist_entry = ttk.Entry(form, width=50)
    dist_entry.insert(0, comp['distributor'] or '')
    dist_entry.grid(row=3, column=1, pady=5)

    ttk.Label(form, text="Dist. Part Number:").grid(row=4, column=0, sticky=tk.W, pady=5)
    dpn_entry = ttk.Entry(form, width=50)
    dpn_entry.insert(0, comp['distributor_part_number'] or '')
    dpn_entry.grid(row=4, column=1, pady=5)

    ttk.Label(form, text="Unit Cost:").grid(row=5, column=0, sticky=tk.W, pady=5)
    cost_entry = ttk.Entry(form, width=20)
    cost_entry.insert(0, str(comp['unit_cost']) if comp['unit_cost'] else '')
    cost_entry.grid(row=5, column=1, sticky=tk.W, pady=5)

    ttk.Label(form, text="Notes:").grid(row=6, column=0, sticky=tk.W, pady=5)
    notes_entry = ttk.Entry(form, width=50)
    notes_entry.insert(0, comp['notes'] or '')
    notes_entry.grid(row=6, column=1, pady=5)

    def save():
        try:
            db.update_component(
                component_id,
                desc_entry.get().strip(),
                cat_entry.get().strip(),
                uom_entry.get().strip() or 'EA',
                notes_entry.get().strip()
            )

            cost_str = cost_entry.get().strip()
            if cost_str:
                db.update_component_source(
                    component_id,
                    dist_entry.get().strip(),
                    dpn_entry.get().strip(),
                    float(cost_str)
                )

            saved['value'] = True
            messagebox.showinfo("Success", "Component updated")
            dialog.destroy()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to update component:\n{str(e)}")

    btn_frame = ttk.Frame(dialog)
    btn_frame.pack(pady=10)

    ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    ttk.Button(btn_frame, text="Save", command=save).pack(side=tk.LEFT, padx=5)

    dialog.wait_window()
    return saved['value']


# ============================================================
# Usage dialogs (component and assembly)
# ============================================================

def show_component_usage_dialog(root, usage_list, comp_name):
    """Show dialog listing assemblies that use a component.

    Args:
        root: parent window
        usage_list: list of Row objects with part_number, description
        comp_name: display name of the component
    """
    dialog = tk.Toplevel(root)
    dialog.title(f"Where Used: {comp_name}")
    dialog.geometry("500x400")
    dialog.transient(root)

    ttk.Label(dialog, text=f"Assemblies using {comp_name}:",
              font=('TkDefaultFont', 11, 'bold')).pack(pady=10)

    listbox = tk.Listbox(dialog, width=60, height=20)
    listbox.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

    for assy in usage_list:
        listbox.insert(tk.END, f"{assy['part_number']} - {assy['description']}")

    ttk.Button(dialog, text="Close", command=dialog.destroy).pack(pady=10)


def show_assembly_usage_dialog(root, usage_list, assy_name):
    """Show dialog listing parent assemblies that contain a sub-assembly.

    Args:
        root: parent window
        usage_list: list of Row objects with part_number, description
        assy_name: display name of the assembly
    """
    dialog = tk.Toplevel(root)
    dialog.title(f"Where Used: {assy_name}")
    dialog.geometry("500x400")
    dialog.transient(root)

    ttk.Label(dialog, text=f"Assemblies containing {assy_name}:",
              font=('TkDefaultFont', 11, 'bold')).pack(pady=10)

    listbox = tk.Listbox(dialog, width=60, height=20)
    listbox.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

    for parent in usage_list:
        listbox.insert(tk.END, f"{parent['part_number']} - {parent['description']}")

    ttk.Button(dialog, text="Close", command=dialog.destroy).pack(pady=10)


# ============================================================
# Revision BOM viewer dialog
# ============================================================

def show_revision_bom_dialog(root, db, revision_id):
    """Show dialog displaying a revision's BOM snapshot."""
    revision = db.get_revision(revision_id)
    if not revision:
        messagebox.showerror("Error", "Revision not found")
        return

    snapshot = json.loads(revision['bom_snapshot'])

    dialog = tk.Toplevel(root)
    dialog.title(f"Revision {revision['revision']} BOM")
    dialog.geometry("1000x600")
    dialog.transient(root)

    ttk.Label(dialog, text=f"Revision {revision['revision']} - {revision['change_date'][:10]}",
              font=('TkDefaultFont', 12, 'bold')).pack(pady=10)

    if revision['change_notes']:
        ttk.Label(dialog, text=f"Notes: {revision['change_notes']}").pack(pady=5)

    # Create tree
    columns = ('Type', 'Part Number', 'Mfr/Product', 'Description', 'Qty', 'Ref Des')
    tree = ttk.Treeview(dialog, columns=columns, show='headings', height=25)

    for col in columns:
        tree.heading(col, text=col)

    scrollbar = ttk.Scrollbar(dialog, orient=tk.VERTICAL, command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)

    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # Load snapshot data
    for comp in snapshot['components']:
        tree.insert('', 'end', values=(
            'Component',
            comp['mfg_part_number'],
            comp['manufacturer'],
            comp['description'],
            comp['quantity'],
            comp['reference_designators']
        ))

    for sub in snapshot['sub_assemblies']:
        tree.insert('', 'end', values=(
            'Sub-Assembly',
            sub['part_number'],
            'Assembly',
            sub['description'],
            sub['quantity'],
            sub['reference_designators']
        ))

    ttk.Button(dialog, text="Close", command=dialog.destroy).pack(pady=10)


# ============================================================
# Flattened BOM viewer dialog
# ============================================================

def show_flattened_bom_dialog(root, db, product_id, export_callback=None):
    """Show dialog displaying a flattened BOM.

    Args:
        root: parent window
        db: BOMDatabase instance
        product_id: ID of the product to flatten
        export_callback: optional callable to trigger CSV export
    """
    product = db.get_product_by_id(product_id)
    flattened = db.get_flattened_bom(product_id)

    dialog = tk.Toplevel(root)
    dialog.title(f"Flattened BOM: {product['part_number']}")
    dialog.geometry("1200x600")
    dialog.transient(root)

    ttk.Label(dialog, text=f"Flattened BOM for {product['part_number']} - {product['description']}",
              font=('TkDefaultFont', 12, 'bold')).pack(pady=10)

    ttk.Label(dialog, text="(All components from all sub-assembly levels, quantities summed)",
              font=('TkDefaultFont', 9, 'italic')).pack(pady=5)

    # Bottom frame with total and buttons - pack BEFORE tree so it anchors to bottom
    bottom_frame = ttk.Frame(dialog)
    bottom_frame.pack(fill=tk.X, padx=10, pady=10, side=tk.BOTTOM)

    total_label = ttk.Label(bottom_frame, text="Total Cost: $0.00",
                            font=('TkDefaultFont', 12, 'bold'))
    total_label.pack(side=tk.LEFT)

    ttk.Button(bottom_frame, text="Close",
               command=dialog.destroy).pack(side=tk.RIGHT, padx=5)
    if export_callback:
        ttk.Button(bottom_frame, text="Export to CSV",
                   command=lambda: (dialog.destroy(), export_callback())).pack(side=tk.RIGHT, padx=5)

    # Create tree - pack after bottom frame so it fills remaining space
    tree_frame = ttk.Frame(dialog)
    tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    columns = ('Part Number', 'Manufacturer', 'Description', 'Category', 'UOM',
               'Total Qty', 'Unit Cost', 'Extended Cost', 'Distributor')
    tree = ttk.Treeview(tree_frame, columns=columns, show='headings')

    for col in columns:
        tree.heading(col, text=col)
        if col == 'Description':
            tree.column(col, width=200)
        elif col in ['Part Number', 'Manufacturer']:
            tree.column(col, width=150)
        else:
            tree.column(col, width=100)

    scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)

    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # Populate tree
    total_cost = 0.0
    for item in flattened:
        extended = float(item['unit_cost']) * item['quantity'] if item['unit_cost'] else 0
        total_cost += extended

        tree.insert('', 'end', values=(
            item['part_number'],
            item['manufacturer'],
            item['description'],
            item['category'],
            item['unit_of_measure'],
            f"{item['quantity']:.2f}",
            f"${item['unit_cost']:.4f}" if item['unit_cost'] else '',
            f"${extended:.2f}" if item['unit_cost'] else '',
            item['distributor'] or ''
        ))

    # Update total label now that we have the actual cost
    total_label.config(text=f"Total Cost: ${total_cost:.2f}")


# ============================================================
# Exploded BOM viewer dialog
# ============================================================

def show_exploded_bom_dialog(root, db, product_id, export_callback=None):
    """Show dialog displaying an exploded (hierarchical) BOM.

    Args:
        root: parent window
        db: BOMDatabase instance
        product_id: ID of the product to explode
        export_callback: optional callable to trigger CSV export
    """
    product = db.get_product_by_id(product_id)
    exploded = db.get_exploded_bom(product_id)

    dialog = tk.Toplevel(root)
    dialog.title(f"Exploded BOM: {product['part_number']}")
    dialog.geometry("1400x600")
    dialog.transient(root)

    ttk.Label(dialog, text=f"Exploded BOM for {product['part_number']} - {product['description']}",
              font=('TkDefaultFont', 12, 'bold')).pack(pady=10)

    ttk.Label(dialog, text="(Hierarchical view with item numbers - indented by level)",
              font=('TkDefaultFont', 9, 'italic')).pack(pady=5)

    # Bottom frame with buttons - pack BEFORE tree so it anchors to bottom
    btn_frame = ttk.Frame(dialog)
    btn_frame.pack(fill=tk.X, padx=10, pady=10, side=tk.BOTTOM)

    ttk.Button(btn_frame, text="Close",
               command=dialog.destroy).pack(side=tk.RIGHT, padx=5)
    if export_callback:
        ttk.Button(btn_frame, text="Export to CSV",
                   command=lambda: (dialog.destroy(), export_callback())).pack(side=tk.RIGHT, padx=5)

    # Create tree - pack after bottom frame so it fills remaining space
    tree_frame = ttk.Frame(dialog)
    tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    columns = ('Item #', 'Level', 'Type', 'Part Number', 'Manufacturer',
               'Description', 'UOM', 'Qty', 'Ref Des', 'Unit Cost', 'Ext Cost')
    tree = ttk.Treeview(tree_frame, columns=columns, show='headings')

    for col in columns:
        tree.heading(col, text=col)
        if col == 'Description':
            tree.column(col, width=200)
        elif col == 'Part Number':
            tree.column(col, width=150)
        elif col in ['Item #', 'Level', 'Type', 'UOM']:
            tree.column(col, width=80)
        else:
            tree.column(col, width=100)

    scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=tree.yview)
    tree.configure(yscrollcommand=scrollbar.set)

    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    # Populate tree
    for item in exploded:
        indented_pn = item['indent'] + item['part_number']

        tree.insert('', 'end', values=(
            item['item_number'],
            item['level'],
            item['item_type'],
            indented_pn,
            item['manufacturer'],
            item['description'],
            item['unit_of_measure'],
            f"{item['quantity']:.2f}",
            item['ref_des'],
            f"${item['unit_cost']:.4f}" if item['unit_cost'] else 'Calculated',
            f"${item['extended_cost']:.2f}" if item['extended_cost'] else ''
        ), tags=('assembly' if item['item_type'] == 'assembly' else 'component',))

    tree.tag_configure('assembly', background='#e8f4f8')


# ============================================================
# Quick edit dialog (inline edit for BOM items)
# ============================================================

def show_quick_edit_dialog(root, db, item_type, db_id, component_id=None):
    """Show a compact dialog for editing a BOM line item in-place.

    Args:
        root: parent window
        db: BOMDatabase instance
        item_type: 'component' or 'assembly'
        db_id: entry_id (component) or sub_assembly_id (assembly)
        component_id: component_id (only for components, needed for cost edit)

    Returns True if changes were saved, False otherwise.
    """
    saved = {'value': False}

    if item_type == 'component':
        entry = db.get_bom_entry(db_id)
        if not entry:
            messagebox.showerror("Error", "BOM entry not found")
            return False
        title_text = f"{entry['mfg_part_number']} ({entry['manufacturer']})"
        current_qty = entry['quantity']
        current_ref = entry['reference_designators'] or ''
        current_notes = entry['notes'] or ''
        # Get current cost from primary source
        source = db.get_primary_source(component_id) if component_id else None
        current_cost = str(source['unit_cost']) if source and source['unit_cost'] else ''
        current_distributor = source['distributor'] if source else ''
    else:
        entry = db.get_sub_assembly_entry(db_id)
        if not entry:
            messagebox.showerror("Error", "Sub-assembly entry not found")
            return False
        title_text = f"{entry['part_number']} (Assembly)"
        current_qty = entry['quantity']
        current_ref = entry['reference_designators'] or ''
        current_notes = entry['notes'] or ''
        current_cost = None  # Not editable for assemblies

    dialog = tk.Toplevel(root)
    dialog.title("Edit BOM Item")
    dialog.geometry("450x280" if item_type == 'component' else "450x220")
    dialog.transient(root)
    dialog.grab_set()

    ttk.Label(dialog, text=title_text,
              font=('TkDefaultFont', 10, 'bold')).pack(pady=(10, 5))

    form = ttk.Frame(dialog)
    form.pack(padx=20, pady=5, fill=tk.X)

    row = 0
    ttk.Label(form, text="Quantity:").grid(row=row, column=0, sticky=tk.W, pady=4)
    qty_entry = ttk.Entry(form, width=15)
    qty_entry.insert(0, str(current_qty))
    qty_entry.grid(row=row, column=1, sticky=tk.W, pady=4, padx=(10, 0))

    row += 1
    ttk.Label(form, text="Ref Des:").grid(row=row, column=0, sticky=tk.W, pady=4)
    ref_entry = ttk.Entry(form, width=40)
    ref_entry.insert(0, current_ref)
    ref_entry.grid(row=row, column=1, sticky=tk.W, pady=4, padx=(10, 0))

    row += 1
    ttk.Label(form, text="Notes:").grid(row=row, column=0, sticky=tk.W, pady=4)
    notes_entry = ttk.Entry(form, width=40)
    notes_entry.insert(0, current_notes)
    notes_entry.grid(row=row, column=1, sticky=tk.W, pady=4, padx=(10, 0))

    cost_entry = None
    if item_type == 'component':
        row += 1
        ttk.Label(form, text="Unit Cost:").grid(row=row, column=0, sticky=tk.W, pady=4)
        cost_entry = ttk.Entry(form, width=15)
        cost_entry.insert(0, current_cost)
        cost_entry.grid(row=row, column=1, sticky=tk.W, pady=4, padx=(10, 0))

        row += 1
        ttk.Label(form, text="(Cost change applies everywhere\n this component is used)",
                  font=('TkDefaultFont', 8, 'italic'),
                  foreground='#666666').grid(row=row, column=0, columnspan=2, sticky=tk.W, pady=(0, 4))

    def save():
        try:
            qty = float(qty_entry.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Invalid quantity")
            return

        ref = ref_entry.get().strip()
        notes = notes_entry.get().strip()

        try:
            if item_type == 'component':
                db.update_bom_entry(db_id, qty, ref, notes)
                # Update cost if changed
                if cost_entry:
                    cost_str = cost_entry.get().strip()
                    if cost_str:
                        try:
                            new_cost = float(cost_str)
                        except ValueError:
                            messagebox.showerror("Error", "Invalid cost value")
                            return
                        distributor = current_distributor or ''
                        db.update_component_source(component_id, distributor, '', new_cost)
            else:
                db.update_sub_assembly_entry(db_id, qty, ref, notes)

            saved['value'] = True
            dialog.destroy()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save changes:\n{str(e)}")

    btn_frame = ttk.Frame(dialog)
    btn_frame.pack(pady=10)
    ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    ttk.Button(btn_frame, text="Save", command=save).pack(side=tk.LEFT, padx=5)

    # Focus the quantity field and select its contents
    qty_entry.focus_set()
    qty_entry.select_range(0, tk.END)

    dialog.wait_window()
    return saved['value']


# ============================================================
# Add item to BOM dialog
# ============================================================

def show_add_item_dialog(root, db, product_id):
    """Show dialog to add a component or sub-assembly to a BOM.

    Args:
        root: parent window
        db: BOMDatabase instance
        product_id: the product to add to

    Returns True if an item was added, False otherwise.
    """
    added = {'value': False}

    dialog = tk.Toplevel(root)
    dialog.title("Add Item to BOM")
    dialog.geometry("750x550")
    dialog.transient(root)
    dialog.grab_set()

    # --- Type selector ---
    type_frame = ttk.LabelFrame(dialog, text="Item Type", padding=5)
    type_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

    type_var = tk.StringVar(value='component')

    comp_frame = ttk.Frame(dialog)
    assy_frame = ttk.Frame(dialog)

    def on_type_change():
        if type_var.get() == 'component':
            assy_frame.pack_forget()
            comp_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5, before=common_frame)
        else:
            comp_frame.pack_forget()
            assy_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5, before=common_frame)

    ttk.Radiobutton(type_frame, text="Component", variable=type_var,
                    value='component', command=on_type_change).pack(side=tk.LEFT, padx=10)
    ttk.Radiobutton(type_frame, text="Sub-Assembly", variable=type_var,
                    value='assembly', command=on_type_change).pack(side=tk.LEFT, padx=10)

    # --- Component selection panel ---
    comp_frame_inner = ttk.LabelFrame(comp_frame, text="Select or Create Component", padding=5)
    comp_frame_inner.pack(fill=tk.BOTH, expand=True)

    search_row = ttk.Frame(comp_frame_inner)
    search_row.pack(fill=tk.X, pady=(0, 5))

    ttk.Label(search_row, text="Search:").pack(side=tk.LEFT, padx=5)
    comp_search_entry = ttk.Entry(search_row, width=30)
    comp_search_entry.pack(side=tk.LEFT, padx=5)

    selected_component_id = {'value': None}

    comp_columns = ('Part Number', 'Manufacturer', 'Description', 'Cost')
    comp_list = ttk.Treeview(comp_frame_inner, columns=comp_columns,
                             show='headings', height=8)
    for col in comp_columns:
        comp_list.heading(col, text=col)
        comp_list.column(col, width=150 if col == 'Description' else 100)

    comp_scroll = ttk.Scrollbar(comp_frame_inner, orient=tk.VERTICAL, command=comp_list.yview)
    comp_list.configure(yscrollcommand=comp_scroll.set)

    comp_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    comp_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def do_comp_search(event=None):
        term = comp_search_entry.get().strip()
        if not term:
            return
        comp_list.delete(*comp_list.get_children())
        results = db.search_components(term)
        for c in results:
            cost_str = f"${c['unit_cost']:.4f}" if c['unit_cost'] else ''
            comp_list.insert('', 'end', values=(
                c['mfg_part_number'], c['manufacturer'],
                c['description'] or '', cost_str
            ), tags=(str(c['component_id']),))

    def on_comp_select(event=None):
        sel = comp_list.selection()
        if sel:
            selected_component_id['value'] = int(comp_list.item(sel[0], 'tags')[0])

    comp_search_entry.bind('<Return>', do_comp_search)
    ttk.Button(search_row, text="Search", command=do_comp_search).pack(side=tk.LEFT, padx=5)
    comp_list.bind('<<TreeviewSelect>>', on_comp_select)

    # Create New Component button + inline fields
    create_frame = ttk.LabelFrame(comp_frame, text="Or Create New Component", padding=5)
    create_frame.pack(fill=tk.X, pady=(5, 0))

    cf = ttk.Frame(create_frame)
    cf.pack(fill=tk.X)

    ttk.Label(cf, text="PN:").grid(row=0, column=0, sticky=tk.W, padx=2, pady=2)
    new_pn_entry = ttk.Entry(cf, width=20)
    new_pn_entry.grid(row=0, column=1, padx=2, pady=2)

    ttk.Label(cf, text="Mfr:").grid(row=0, column=2, sticky=tk.W, padx=2, pady=2)
    new_mfr_entry = ttk.Entry(cf, width=20)
    new_mfr_entry.grid(row=0, column=3, padx=2, pady=2)

    ttk.Label(cf, text="Desc:").grid(row=1, column=0, sticky=tk.W, padx=2, pady=2)
    new_desc_entry = ttk.Entry(cf, width=20)
    new_desc_entry.grid(row=1, column=1, padx=2, pady=2)

    ttk.Label(cf, text="UOM:").grid(row=1, column=2, sticky=tk.W, padx=2, pady=2)
    new_uom_entry = ttk.Entry(cf, width=8)
    new_uom_entry.insert(0, 'EA')
    new_uom_entry.grid(row=1, column=3, sticky=tk.W, padx=2, pady=2)

    def create_and_select():
        pn = new_pn_entry.get().strip()
        mfr = new_mfr_entry.get().strip()
        if not pn or not mfr:
            messagebox.showwarning("Required Fields", "Part Number and Manufacturer are required.")
            return
        desc = new_desc_entry.get().strip()
        uom = new_uom_entry.get().strip() or 'EA'
        cid = db.add_or_update_component(pn, mfr, desc, '', uom, '')
        selected_component_id['value'] = cid
        # Show it in the search results
        comp_list.delete(*comp_list.get_children())
        comp_list.insert('', 'end', values=(pn, mfr, desc, ''),
                         tags=(str(cid),))
        comp_list.selection_set(comp_list.get_children()[0])
        messagebox.showinfo("Created", f"Component {pn} created and selected.")

    ttk.Button(cf, text="Create & Select", command=create_and_select).grid(
        row=0, column=4, rowspan=2, padx=10, pady=2)

    # --- Sub-Assembly selection panel ---
    assy_frame_inner = ttk.LabelFrame(assy_frame, text="Select Assembly", padding=5)
    assy_frame_inner.pack(fill=tk.BOTH, expand=True)

    products = db.get_all_products()
    # Exclude the current product to prevent self-reference
    product_options = [f"{p['part_number']} - {p['description']}"
                       for p in products if p['product_id'] != product_id]

    ttk.Label(assy_frame_inner, text="Assembly:").pack(anchor=tk.W, padx=5, pady=5)
    assy_combo_var = tk.StringVar()
    assy_combo = ttk.Combobox(assy_frame_inner, textvariable=assy_combo_var,
                              values=product_options, width=60, state='readonly')
    assy_combo.pack(padx=5, pady=5, anchor=tk.W)

    # --- Common fields ---
    common_frame = ttk.LabelFrame(dialog, text="BOM Entry Details", padding=5)
    common_frame.pack(fill=tk.X, padx=10, pady=5)

    cf2 = ttk.Frame(common_frame)
    cf2.pack(fill=tk.X)

    ttk.Label(cf2, text="Quantity:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=4)
    qty_entry = ttk.Entry(cf2, width=10)
    qty_entry.insert(0, '1')
    qty_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=4)

    ttk.Label(cf2, text="Ref Des:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=4)
    ref_entry = ttk.Entry(cf2, width=30)
    ref_entry.grid(row=0, column=3, sticky=tk.W, padx=5, pady=4)

    ttk.Label(cf2, text="Notes:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=4)
    notes_entry = ttk.Entry(cf2, width=50)
    notes_entry.grid(row=1, column=1, columnspan=3, sticky=tk.W, padx=5, pady=4)

    # --- Buttons ---
    def do_add():
        try:
            qty = float(qty_entry.get().strip())
        except ValueError:
            messagebox.showerror("Error", "Invalid quantity")
            return

        ref = ref_entry.get().strip()
        notes = notes_entry.get().strip()

        if type_var.get() == 'component':
            cid = selected_component_id['value']
            if not cid:
                messagebox.showwarning("No Component",
                                        "Please search and select a component, or create a new one.")
                return
            try:
                db.add_bom_entry(product_id, cid, qty, ref, notes)
                added['value'] = True
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to add component:\n{str(e)}")
        else:
            sel = assy_combo_var.get()
            if not sel:
                messagebox.showwarning("No Assembly", "Please select an assembly.")
                return
            child_pn = sel.split(' - ')[0]
            child = db.get_product(child_pn)
            if not child:
                messagebox.showerror("Error", f"Assembly {child_pn} not found")
                return
            try:
                db.add_sub_assembly(product_id, child['product_id'], qty, ref, notes)
                added['value'] = True
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to add sub-assembly:\n{str(e)}")

    btn_frame = ttk.Frame(dialog)
    btn_frame.pack(pady=10)
    ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
    ttk.Button(btn_frame, text="Add to BOM", command=do_add).pack(side=tk.LEFT, padx=5)

    # Show component panel by default
    comp_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5, before=common_frame)

    dialog.wait_window()
    return added['value']


# ============================================================
# Database configuration dialog
# ============================================================

def show_database_config_dialog(root, on_confirmed):
    """Show dialog to select or create a database.

    Args:
        root: parent window
        on_confirmed: callback(db_path) called when user confirms a valid path.
                      Not called if user exits.
    """
    from tkinter import filedialog

    dialog = tk.Toplevel(root)
    dialog.title("Database Configuration")

    # Center the dialog on screen
    dialog.update_idletasks()
    width = 600
    height = 250
    x = (dialog.winfo_screenwidth() // 2) - (width // 2)
    y = (dialog.winfo_screenheight() // 2) - (height // 2)
    dialog.geometry(f"{width}x{height}+{x}+{y}")

    dialog.transient(root)

    ttk.Label(dialog, text="BOM Database Configuration",
              font=('TkDefaultFont', 12, 'bold')).pack(pady=15)

    ttk.Label(dialog, text="Select an existing database or create a new one:").pack(pady=5)

    # Current path display
    path_frame = ttk.Frame(dialog)
    path_frame.pack(pady=10, padx=20, fill=tk.X)

    ttk.Label(path_frame, text="Database:").pack(side=tk.LEFT, padx=5)
    path_var = tk.StringVar(value="bom_system_v2.db")
    path_entry = ttk.Entry(path_frame, textvariable=path_var, width=50)
    path_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

    # Buttons
    btn_frame = ttk.Frame(dialog)
    btn_frame.pack(pady=10)

    def browse_existing():
        filename = filedialog.askopenfilename(
            title="Select Existing Database",
            filetypes=[("SQLite Database", "*.db"), ("All files", "*.*")],
            initialdir=os.getcwd()
        )
        if filename:
            path_var.set(filename)

    def browse_new():
        filename = filedialog.asksaveasfilename(
            title="Create New Database",
            filetypes=[("SQLite Database", "*.db"), ("All files", "*.*")],
            defaultextension=".db",
            initialfile="bom_system_v2.db",
            initialdir=os.getcwd()
        )
        if filename:
            path_var.set(filename)

    def confirm_selection():
        db_path = path_var.get().strip()

        if not db_path:
            messagebox.showerror("Error", "Please specify a database path")
            return

        # Check if file exists and validate
        if os.path.exists(db_path):
            from bom_database import BOMDatabase
            try:
                test_db = BOMDatabase(db_path)
                valid, msg = test_db.verify_database_schema()
                test_db.close()

                if not valid:
                    if messagebox.askyesno("Invalid Database",
                                           f"The selected database has schema errors:\n\n{msg}\n\n"
                                           "Would you like to create a new database at this location?\n"
                                           "(This will DELETE the existing file!)",
                                           icon='warning'):
                        try:
                            os.remove(db_path)
                        except Exception:
                            pass
                    else:
                        return
            except Exception as e:
                if messagebox.askyesno("Invalid Database",
                                       f"The selected file is not a valid database:\n{str(e)}\n\n"
                                       "Create a new database at this location?\n"
                                       "(This will DELETE the existing file!)",
                                       icon='warning'):
                    try:
                        os.remove(db_path)
                    except Exception:
                        pass
                else:
                    return

        dialog.destroy()
        on_confirmed(db_path)

    ttk.Button(btn_frame, text="Browse Existing...",
               command=browse_existing).pack(side=tk.LEFT, padx=5)
    ttk.Button(btn_frame, text="Create New...",
               command=browse_new).pack(side=tk.LEFT, padx=5)

    ttk.Separator(dialog, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=15)

    confirm_frame = ttk.Frame(dialog)
    confirm_frame.pack(pady=10)

    ttk.Button(confirm_frame, text="Confirm",
               command=confirm_selection).pack(side=tk.LEFT, padx=5)
    ttk.Button(confirm_frame, text="Exit",
               command=root.quit).pack(side=tk.LEFT, padx=5)

    # Make dialog modal but don't block with wait_window
    dialog.grab_set()
    dialog.focus_set()

    # Disable closing with X button - must use Confirm or Exit
    dialog.protocol("WM_DELETE_WINDOW", lambda: None)
