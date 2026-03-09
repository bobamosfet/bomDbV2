#!/usr/bin/env python3
"""
BOM System GUI
Main application window with tabs for BOM viewing, cost analysis,
component management, assembly management, and revision history.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
import shutil
from datetime import datetime

from bom_database import BOMDatabase
from bom_io import (
    parse_csv_metadata, topological_sort_files,
    process_import_to_db,
    write_bom_csv, write_flattened_csv, write_exploded_csv, write_revision_csv,
)
from bom_dialogs import (
    show_replace_dialog, show_edit_component_dialog,
    show_component_usage_dialog, show_assembly_usage_dialog,
    show_revision_bom_dialog,
    show_flattened_bom_dialog, show_exploded_bom_dialog,
    show_database_config_dialog,
    show_quick_edit_dialog, show_add_item_dialog,
)

try:
    from bom_converter_gui import launch_converter
    HAS_CONVERTER = True
except ImportError:
    HAS_CONVERTER = False

try:
    from bom_pricing_gui import launch_pricing_update
    HAS_PRICING = True
except ImportError:
    HAS_PRICING = False


class BOMSystemGUI:
    """Main GUI application"""

    def __init__(self, root):
        self.root = root
        self.root.title("BOM Management System v2")
        self.root.geometry("1400x900")

        self.db = None
        self.current_product_id = None
        self.bom_item_metadata = {}

        # Cached BOM data for filtering
        self._bom_components = []
        self._bom_sub_assemblies = []

        # Cached assembly list for type-ahead combos
        self._all_product_options = []

        # Column sort tracking
        self.assy_sort_column = None
        self.assy_sort_reverse = False
        self.comp_sort_column = None
        self.comp_sort_reverse = False

        # Setup UI first, then load database
        self._setup_ui()

        # Load database after UI is ready
        self.root.after_idle(self._load_database_config)

    # ================================================================
    # Database loading / configuration
    # ================================================================

    def _load_database_config(self):
        """Load database configuration from settings file or prompt user"""
        config_file = "bom_config.json"

        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    db_path = config.get('database_path', 'bom_system_v2.db')

                    if os.path.exists(db_path):
                        self.db = BOMDatabase(db_path)
                        valid, msg = self.db.verify_database_schema()
                        if not valid:
                            messagebox.showerror("Database Schema Error",
                                                 f"The database at {db_path} has an invalid schema:\n\n{msg}\n\n"
                                                 "Please select a valid database or create a new one.")
                            self._prompt_database_selection()
                        else:
                            self._update_db_status()
                            self._set_status("Database loaded")
                            self._refresh_all()
                        return
            except Exception as e:
                messagebox.showwarning("Config Error",
                                       f"Error loading configuration:\n{str(e)}\n\nPlease select database location.")

        self._prompt_database_selection()

    def _prompt_database_selection(self):
        """Show dialog to select or create database"""
        def on_confirmed(db_path):
            try:
                self.db = BOMDatabase(db_path)

                # Save configuration
                config = {'database_path': db_path}
                with open('bom_config.json', 'w') as f:
                    json.dump(config, f, indent=2)

                self._update_db_status()
                self._set_status("Database loaded")
                self._refresh_all()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to create/open database:\n{str(e)}")

        show_database_config_dialog(self.root, on_confirmed)

    def change_database(self):
        """Allow user to change database location"""
        if messagebox.askyesno("Change Database",
                               "Changing the database will close the current database.\n\nContinue?"):
            if self.db:
                self.db.close()
            self._prompt_database_selection()

    def _refresh_all(self):
        """Refresh all views after database load/change"""
        self.refresh_assembly_lists()
        self.refresh_assemblies()
        self.refresh_components(False)

    def _backup_database(self):
        """Create a timestamped backup of the database file before destructive operations.

        Returns the backup path on success, or None if backup failed/skipped.
        """
        if not self.db or not self.db.db_path:
            return None
        if not os.path.exists(self.db.db_path):
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        db_dir = os.path.dirname(os.path.abspath(self.db.db_path))
        db_name = os.path.splitext(os.path.basename(self.db.db_path))[0]
        backup_path = os.path.join(db_dir, f"{db_name}_backup_{timestamp}.db")

        try:
            shutil.copy2(self.db.db_path, backup_path)
            return backup_path
        except Exception as e:
            messagebox.showwarning("Backup Warning",
                                    f"Could not create database backup:\n{str(e)}\n\n"
                                    "The import will continue without a backup.")
            return None

    # ================================================================
    # UI setup
    # ================================================================

    def _setup_ui(self):
        """Create the user interface"""
        # Menu bar
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Change Database...", command=self.change_database)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)

        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)
        tools_menu.add_command(label="Update Pricing...", command=self._launch_pricing)
        tools_menu.add_command(label="Clean Up Duplicates", command=self.cleanup_duplicates)

        # Notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Tab 1: BOM Viewer
        self.bom_viewer_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.bom_viewer_tab, text="BOM Viewer")
        self._setup_bom_viewer_tab()

        # Tab 2: Cost Analysis
        self.cost_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.cost_tab, text="Cost Analysis")
        self._setup_cost_tab()

        # Tab 3: Component Management
        self.component_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.component_tab, text="Component Management")
        self._setup_component_tab()

        # Tab 4: Assembly Management
        self.assembly_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.assembly_tab, text="Assembly Management")
        self._setup_assembly_tab()

        # Tab 5: Revision History
        self.revision_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.revision_tab, text="Revision History")
        self._setup_revision_tab()

        # Status bar at bottom of window
        self._setup_status_bar()

    def _setup_bom_viewer_tab(self):
        """Setup BOM viewer tab"""
        top_frame = ttk.Frame(self.bom_viewer_tab)
        top_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(top_frame, text="Assembly:").pack(side=tk.LEFT, padx=5)
        self.bom_assembly_var = tk.StringVar()
        self.bom_assembly_combo = ttk.Combobox(top_frame, textvariable=self.bom_assembly_var,
                                                width=60)
        self.bom_assembly_combo.pack(side=tk.LEFT, padx=5)
        self.bom_assembly_combo.bind('<<ComboboxSelected>>', self.load_bom_viewer)
        self._setup_typeahead_combo(self.bom_assembly_combo, self.bom_assembly_var,
                                    self.load_bom_viewer)

        ttk.Button(top_frame, text="Refresh List",
                   command=self.refresh_assembly_lists).pack(side=tk.LEFT, padx=5)

        # Button frame
        btn_frame = ttk.Frame(self.bom_viewer_tab)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(btn_frame, text="Import BOM",
                   command=self.import_bom).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Convert BOM Files...",
                   command=self._launch_converter).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Update Pricing...",
                   command=self._launch_pricing).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Export BOM",
                   command=self.export_bom).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Export Flattened BOM",
                   command=self.export_flattened_bom).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Export Exploded BOM",
                   command=self.export_exploded_bom).pack(side=tk.LEFT, padx=5)

        # View buttons
        view_btn_frame = ttk.Frame(self.bom_viewer_tab)
        view_btn_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(view_btn_frame, text="View Flattened BOM",
                   command=self.view_flattened_bom).pack(side=tk.LEFT, padx=5)
        ttk.Button(view_btn_frame, text="View Exploded BOM",
                   command=self.view_exploded_bom).pack(side=tk.LEFT, padx=5)

        # Filter bar
        filter_frame = ttk.Frame(self.bom_viewer_tab)
        filter_frame.pack(fill=tk.X, padx=5, pady=(0, 5))

        ttk.Label(filter_frame, text="Filter:").pack(side=tk.LEFT, padx=5)
        self.bom_filter_var = tk.StringVar()
        bom_filter_entry = ttk.Entry(filter_frame, textvariable=self.bom_filter_var, width=30)
        bom_filter_entry.pack(side=tk.LEFT, padx=5)
        bom_filter_entry.bind('<Return>', lambda e: self._apply_bom_filter())
        ttk.Button(filter_frame, text="Apply",
                   command=self._apply_bom_filter).pack(side=tk.LEFT, padx=2)
        ttk.Button(filter_frame, text="Clear",
                   command=self._clear_bom_filter).pack(side=tk.LEFT, padx=2)

        # BOM tree
        tree_frame = ttk.LabelFrame(self.bom_viewer_tab, text="Bill of Materials", padding=10)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        columns = ('Type', 'Part Number', 'Mfr/Product', 'Description', 'UOM',
                   'Qty', 'Ref Des', 'Unit Cost')
        self.bom_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=20)

        for col in columns:
            self.bom_tree.heading(col, text=col)
            if col == 'Description':
                self.bom_tree.column(col, width=250)
            elif col in ['Type', 'UOM']:
                self.bom_tree.column(col, width=80)
            else:
                self.bom_tree.column(col, width=120)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.bom_tree.yview)
        self.bom_tree.configure(yscrollcommand=scrollbar.set)
        self.bom_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Double-click to inline-edit
        self.bom_tree.bind('<Double-1>', self._on_bom_double_click)

        # Action buttons
        action_frame = ttk.Frame(self.bom_viewer_tab)
        action_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(action_frame, text="Add Item...",
                   command=self._add_bom_item).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="Delete Selected Item",
                   command=self.delete_bom_item).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="Clear Entire BOM",
                   command=self.clear_entire_bom).pack(side=tk.LEFT, padx=5)

        self.bom_cost_label = ttk.Label(action_frame, text="Total Cost: $0.00",
                                         font=('TkDefaultFont', 11, 'bold'))
        self.bom_cost_label.pack(side=tk.RIGHT, padx=20)

    def _setup_cost_tab(self):
        """Setup cost analysis tab"""
        top_frame = ttk.LabelFrame(self.cost_tab, text="Cost Analysis", padding=10)
        top_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(top_frame, text="Assembly:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.cost_assembly_var = tk.StringVar()
        self.cost_assembly_combo = ttk.Combobox(top_frame, textvariable=self.cost_assembly_var,
                                                 width=50)
        self.cost_assembly_combo.grid(row=0, column=1, padx=5)
        self._setup_typeahead_combo(self.cost_assembly_combo, self.cost_assembly_var)

        ttk.Label(top_frame, text="Quantity:").grid(row=0, column=2, padx=5)
        self.cost_qty_entry = ttk.Entry(top_frame, width=10)
        self.cost_qty_entry.insert(0, "1")
        self.cost_qty_entry.grid(row=0, column=3, padx=5)

        ttk.Button(top_frame, text="Calculate Cost",
                   command=self.calculate_cost).grid(row=0, column=4, padx=5)

        # Results frame
        results_frame = ttk.LabelFrame(self.cost_tab, text="Cost Breakdown", padding=10)
        results_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        cost_summary = ttk.Frame(results_frame)
        cost_summary.pack(fill=tk.X, pady=5)

        ttk.Label(cost_summary, text="Total Cost:",
                  font=('TkDefaultFont', 14, 'bold')).pack(side=tk.LEFT, padx=5)
        self.total_cost_label = ttk.Label(cost_summary, text="$0.00",
                                           font=('TkDefaultFont', 14, 'bold'))
        self.total_cost_label.pack(side=tk.LEFT, padx=10)

        columns = ('Item', 'Quantity', 'UOM', 'Unit Cost', 'Total Cost')
        self.cost_tree = ttk.Treeview(results_frame, columns=columns, show='headings', height=25)

        for col in columns:
            self.cost_tree.heading(col, text=col)
            if col == 'Item':
                self.cost_tree.column(col, width=400)
            else:
                self.cost_tree.column(col, width=120)

        scrollbar = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.cost_tree.yview)
        self.cost_tree.configure(yscrollcommand=scrollbar.set)
        self.cost_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _setup_component_tab(self):
        """Setup component management tab"""
        top_frame = ttk.Frame(self.component_tab)
        top_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(top_frame, text="Show All Components",
                   command=lambda: self.refresh_components(False)).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="Show Unused Only",
                   command=lambda: self.refresh_components(True)).pack(side=tk.LEFT, padx=5)

        tree_frame = ttk.LabelFrame(self.component_tab, text="Components", padding=10)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        columns = ('Part Number', 'Manufacturer', 'Description', 'UOM',
                   'Cost', 'Distributor', 'Used In')
        self.comp_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=25)

        for col in columns:
            self.comp_tree.heading(col, text=col,
                                    command=lambda c=col: self._sort_components_by_column(c))
            if col == 'Description':
                self.comp_tree.column(col, width=250)
            else:
                self.comp_tree.column(col, width=120)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.comp_tree.yview)
        self.comp_tree.configure(yscrollcommand=scrollbar.set)
        self.comp_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        action_frame = ttk.Frame(self.component_tab)
        action_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(action_frame, text="Edit Selected",
                   command=self.edit_component).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="Delete Selected",
                   command=self.delete_component).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="View Where Used",
                   command=self.view_component_usage).pack(side=tk.LEFT, padx=5)

    def _setup_assembly_tab(self):
        """Setup assembly management tab"""
        top_frame = ttk.Frame(self.assembly_tab)
        top_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(top_frame, text="Search:").pack(side=tk.LEFT, padx=5)
        self.assy_search_entry = ttk.Entry(top_frame, width=30)
        self.assy_search_entry.pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="Search",
                   command=self.search_assemblies).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="Show All",
                   command=self.refresh_assemblies).pack(side=tk.LEFT, padx=5)

        tree_frame = ttk.LabelFrame(self.assembly_tab, text="Assemblies", padding=10)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        columns = ('Part Number', 'Description', 'Revision', 'Modified', '# Items', 'Cost')
        self.assy_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=25)

        for col in columns:
            self.assy_tree.heading(col, text=col,
                                    command=lambda c=col: self._sort_assemblies_by_column(c))
            if col == 'Description':
                self.assy_tree.column(col, width=300)
            else:
                self.assy_tree.column(col, width=120)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.assy_tree.yview)
        self.assy_tree.configure(yscrollcommand=scrollbar.set)
        self.assy_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        action_frame = ttk.Frame(self.assembly_tab)
        action_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(action_frame, text="View BOM",
                   command=self.view_assembly_bom).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="View Where Used",
                   command=self.view_assembly_usage).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="View Revision History",
                   command=self.view_assembly_revisions).pack(side=tk.LEFT, padx=5)

        self.refresh_assemblies()

    def _setup_revision_tab(self):
        """Setup revision history tab"""
        top_frame = ttk.Frame(self.revision_tab)
        top_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(top_frame, text="Assembly:").pack(side=tk.LEFT, padx=5)
        self.rev_assembly_var = tk.StringVar()
        self.rev_assembly_combo = ttk.Combobox(top_frame, textvariable=self.rev_assembly_var,
                                                width=50)
        self.rev_assembly_combo.pack(side=tk.LEFT, padx=5)
        self.rev_assembly_combo.bind('<<ComboboxSelected>>', self.load_revisions)
        self._setup_typeahead_combo(self.rev_assembly_combo, self.rev_assembly_var,
                                    self.load_revisions)

        ttk.Button(top_frame, text="Refresh",
                   command=self.load_revisions).pack(side=tk.LEFT, padx=5)

        tree_frame = ttk.LabelFrame(self.revision_tab, text="Revision History", padding=10)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        columns = ('Revision', 'Date', 'Notes')
        self.rev_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=25)

        for col in columns:
            self.rev_tree.heading(col, text=col)
            if col == 'Notes':
                self.rev_tree.column(col, width=500)
            else:
                self.rev_tree.column(col, width=150)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.rev_tree.yview)
        self.rev_tree.configure(yscrollcommand=scrollbar.set)
        self.rev_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        action_frame = ttk.Frame(self.revision_tab)
        action_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(action_frame, text="View Revision BOM",
                   command=self.view_revision_bom).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="Export Revision BOM",
                   command=self.export_revision_bom).pack(side=tk.LEFT, padx=5)

    # ================================================================
    # Type-ahead combo helper
    # ================================================================

    def _setup_typeahead_combo(self, combo, var, on_select_callback=None):
        """Configure a combobox for type-ahead filtering.

        When the user types, the dropdown values are filtered to matching entries.
        When they select an item or press Enter, the callback fires.
        """
        combo.config(state='normal')  # Allow typing

        def on_keyrelease(event):
            # Ignore navigation/modifier keys
            if event.keysym in ('Return', 'Escape', 'Tab', 'Up', 'Down',
                                'Shift_L', 'Shift_R', 'Control_L', 'Control_R',
                                'Alt_L', 'Alt_R'):
                if event.keysym == 'Return' and on_select_callback:
                    on_select_callback()
                return

            typed = var.get().strip().lower()
            if not typed:
                combo['values'] = self._all_product_options
            else:
                filtered = [p for p in self._all_product_options
                            if typed in p.lower()]
                combo['values'] = filtered

        combo.bind('<KeyRelease>', on_keyrelease)

    # ================================================================
    # Status bar
    # ================================================================

    def _setup_status_bar(self):
        """Create the status bar at the bottom of the main window"""
        status_frame = ttk.Frame(self.root, relief=tk.SUNKEN)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=2, pady=(0, 2))

        self._status_db_label = ttk.Label(status_frame, text="Database: (none)",
                                           font=('TkDefaultFont', 9), anchor=tk.W)
        self._status_db_label.pack(side=tk.LEFT, padx=5)

        ttk.Separator(status_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)

        self._status_action_label = ttk.Label(status_frame, text="Ready",
                                               font=('TkDefaultFont', 9), anchor=tk.W)
        self._status_action_label.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

    def _set_status(self, message):
        """Update the last-action portion of the status bar"""
        self._status_action_label.config(text=message)

    def _update_db_status(self):
        """Update the database path portion of the status bar"""
        if self.db and self.db.db_path:
            display = self.db.db_path
            # Shorten if too long
            if len(display) > 80:
                display = "..." + display[-77:]
            self._status_db_label.config(text=f"Database: {display}")
        else:
            self._status_db_label.config(text="Database: (none)")

    # ================================================================
    # Sorting
    # ================================================================

    def _sort_assemblies_by_column(self, col):
        """Sort assembly tree by clicked column"""
        items = [(self.assy_tree.set(item, col), item) for item in self.assy_tree.get_children('')]

        reverse = False
        if self.assy_sort_column == col:
            reverse = not self.assy_sort_reverse
        self.assy_sort_column = col
        self.assy_sort_reverse = reverse

        try:
            if col == '# Items':
                items.sort(key=lambda x: int(x[0]) if x[0] and x[0].isdigit() else 0, reverse=reverse)
            elif col == 'Cost':
                items.sort(key=lambda x: float(x[0].replace('$', '')) if x[0] and x[0] != '' else 0, reverse=reverse)
            else:
                items.sort(key=lambda x: x[0].lower() if x[0] else '', reverse=reverse)
        except Exception:
            items.sort(key=lambda x: str(x[0]).lower(), reverse=reverse)

        for index, (val, item) in enumerate(items):
            self.assy_tree.move(item, '', index)

        for column in self.assy_tree['columns']:
            heading = column
            if column == col:
                heading = f"{column} {'▼' if reverse else '▲'}"
            self.assy_tree.heading(column, text=heading,
                                    command=lambda c=column: self._sort_assemblies_by_column(c))

    def _sort_components_by_column(self, col):
        """Sort component tree by clicked column"""
        items = [(self.comp_tree.set(item, col), item) for item in self.comp_tree.get_children('')]

        reverse = False
        if self.comp_sort_column == col:
            reverse = not self.comp_sort_reverse
        self.comp_sort_column = col
        self.comp_sort_reverse = reverse

        try:
            if col == 'Cost':
                items.sort(key=lambda x: float(x[0].replace('$', '')) if x[0] and x[0] != '' else 0, reverse=reverse)
            else:
                items.sort(key=lambda x: x[0].lower() if x[0] else '', reverse=reverse)
        except Exception:
            items.sort(key=lambda x: str(x[0]).lower(), reverse=reverse)

        for index, (val, item) in enumerate(items):
            self.comp_tree.move(item, '', index)

        for column in self.comp_tree['columns']:
            heading = column
            if column == col:
                heading = f"{column} {'▼' if reverse else '▲'}"
            self.comp_tree.heading(column, text=heading,
                                    command=lambda c=column: self._sort_components_by_column(c))

    # ================================================================
    # Refresh helpers
    # ================================================================

    def refresh_assembly_lists(self):
        """Refresh all assembly dropdown lists"""
        if self.db is None:
            return
        products = self.db.get_all_products()
        product_list = [f"{p['part_number']} - {p['description']} (Rev {p['revision']})"
                        for p in products]

        # Cache the full list for type-ahead filtering
        self._all_product_options = product_list

        self.bom_assembly_combo['values'] = product_list
        self.cost_assembly_combo['values'] = product_list
        self.rev_assembly_combo['values'] = product_list

    def refresh_assemblies(self):
        """Refresh assembly list in the Assembly Management tab"""
        if self.db is None:
            return

        for item in self.assy_tree.get_children():
            self.assy_tree.delete(item)

        products = self.db.get_all_products()

        for product in products:
            components, sub_assemblies = self.db.get_product_bom(product['product_id'])
            item_count = len(components) + len(sub_assemblies)
            total_cost, _ = self.db.calculate_bom_cost(product['product_id'])
            modified = product['modified_date'][:10] if product['modified_date'] else ''

            self.assy_tree.insert('', 'end', values=(
                product['part_number'],
                product['description'],
                product['revision'],
                modified,
                item_count,
                f"${total_cost:.2f}"
            ), tags=(str(product['product_id']),))

    def refresh_components(self, unused_only):
        """Refresh component list in the Component Management tab"""
        if self.db is None:
            return

        for item in self.comp_tree.get_children():
            self.comp_tree.delete(item)

        if unused_only:
            components = self.db.get_unused_components()
        else:
            components = self.db.get_all_components()

        for comp in components:
            usage = self.db.get_component_usage(comp['component_id'])
            used_in = f"{len(usage)} assemblies" if usage else "None"
            cost_str = f"${comp['unit_cost']:.2f}" if comp['unit_cost'] else ''

            self.comp_tree.insert('', 'end', values=(
                comp['mfg_part_number'],
                comp['manufacturer'],
                comp['description'] or '',
                comp['unit_of_measure'],
                cost_str,
                comp['distributor'] or '',
                used_in
            ), tags=(str(comp['component_id']),))

    # ================================================================
    # BOM Viewer actions
    # ================================================================

    def load_bom_viewer(self, event=None):
        """Load BOM in viewer"""
        selected = self.bom_assembly_var.get()
        if not selected:
            return

        part_number = selected.split(' - ')[0]
        product = self.db.get_product(part_number)
        if not product:
            return

        self.current_product_id = product['product_id']

        # Fetch and cache BOM data
        self._bom_components, self._bom_sub_assemblies = self.db.get_product_bom(product['product_id'])

        # Clear filter and populate tree
        self.bom_filter_var.set('')
        self._populate_bom_tree()

        # Calculate and display cost
        total_cost, _ = self.db.calculate_bom_cost(product['product_id'])
        self.bom_cost_label.config(text=f"Total Cost: ${total_cost:.2f}")

        count = len(self._bom_components) + len(self._bom_sub_assemblies)
        self._set_status(f"Loaded BOM for {part_number} — {count} items, cost ${total_cost:.2f}")

    def _populate_bom_tree(self, filter_term=None):
        """Populate the BOM tree from cached data, optionally filtering."""
        self.bom_item_metadata = {}

        for item in self.bom_tree.get_children():
            self.bom_tree.delete(item)

        for comp in self._bom_components:
            # Apply filter if active
            if filter_term:
                searchable = ' '.join([
                    comp['mfg_part_number'] or '',
                    comp['manufacturer'] or '',
                    comp['description'] or '',
                    comp['reference_designators'] or '',
                ]).lower()
                if filter_term not in searchable:
                    continue

            cost_str = f"${comp['unit_cost']:.2f}" if comp['unit_cost'] else ''
            item_id = self.bom_tree.insert('', 'end', values=(
                'Component',
                comp['mfg_part_number'],
                comp['manufacturer'],
                comp['description'],
                comp['unit_of_measure'],
                comp['quantity'],
                comp['reference_designators'],
                cost_str
            ))
            self.bom_item_metadata[item_id] = ('component', comp['entry_id'], comp['component_id'])

        for sub in self._bom_sub_assemblies:
            if filter_term:
                searchable = ' '.join([
                    sub['part_number'] or '',
                    sub['description'] or '',
                    sub['reference_designators'] or '',
                ]).lower()
                if filter_term not in searchable:
                    continue

            item_id = self.bom_tree.insert('', 'end', values=(
                'Sub-Assembly',
                sub['part_number'],
                'Assembly',
                sub['description'],
                'EA',
                sub['quantity'],
                sub['reference_designators'],
                'Calculated'
            ), tags=('assembly',))
            self.bom_item_metadata[item_id] = ('assembly', sub['sub_assembly_id'], sub['product_id'])

        self.bom_tree.tag_configure('assembly', background='#e8f4f8')

    def _apply_bom_filter(self):
        """Filter BOM tree by search term"""
        term = self.bom_filter_var.get().strip().lower()
        if not term:
            self._clear_bom_filter()
            return
        self._populate_bom_tree(filter_term=term)

    def _clear_bom_filter(self):
        """Clear BOM filter and show all items"""
        self.bom_filter_var.set('')
        self._populate_bom_tree()

    def _on_bom_double_click(self, event):
        """Handle double-click on BOM tree row to open inline edit"""
        item_id = self.bom_tree.identify_row(event.y)
        if not item_id or item_id not in self.bom_item_metadata:
            return

        item_type, db_id, extra_id = self.bom_item_metadata[item_id]
        component_id = extra_id if item_type == 'component' else None

        if show_quick_edit_dialog(self.root, self.db, item_type, db_id, component_id):
            # Refresh the BOM data and re-populate (preserving filter)
            self._bom_components, self._bom_sub_assemblies = self.db.get_product_bom(
                self.current_product_id)
            term = self.bom_filter_var.get().strip().lower() or None
            self._populate_bom_tree(filter_term=term)
            # Update cost
            total_cost, _ = self.db.calculate_bom_cost(self.current_product_id)
            self.bom_cost_label.config(text=f"Total Cost: ${total_cost:.2f}")
            self._set_status("BOM item updated")

    def _add_bom_item(self):
        """Add a new component or sub-assembly to the current BOM"""
        if not self.current_product_id:
            messagebox.showwarning("No BOM", "Please select an assembly first")
            return

        if show_add_item_dialog(self.root, self.db, self.current_product_id):
            # Refresh everything
            self._bom_components, self._bom_sub_assemblies = self.db.get_product_bom(
                self.current_product_id)
            self._clear_bom_filter()
            total_cost, _ = self.db.calculate_bom_cost(self.current_product_id)
            self.bom_cost_label.config(text=f"Total Cost: ${total_cost:.2f}")
            self.refresh_components(False)
            self._set_status("Item added to BOM")

    def delete_bom_item(self):
        """Delete selected BOM item"""
        selected = self.bom_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select an item to delete")
            return

        item_id = selected[0]
        if item_id not in self.bom_item_metadata:
            messagebox.showerror("Error", "Cannot find item metadata")
            return

        item_type, db_id, _extra = self.bom_item_metadata[item_id]
        values = self.bom_tree.item(item_id, 'values')
        item_name = f"{values[1]} ({values[2]})"

        if not messagebox.askyesno("Confirm Delete", f"Delete {item_name} from this BOM?"):
            return

        success = False
        if item_type == 'component':
            success = self.db.delete_bom_entry(db_id)
        elif item_type == 'assembly':
            success = self.db.delete_sub_assembly_entry(db_id)

        if success:
            messagebox.showinfo("Success", "Item deleted from BOM")
            self._set_status(f"Deleted {item_name} from BOM")
            self.load_bom_viewer()
        else:
            messagebox.showerror("Error", "Failed to delete item")

    def clear_entire_bom(self):
        """Clear all items from current BOM"""
        if not self.current_product_id:
            messagebox.showwarning("No BOM", "Please select an assembly first")
            return

        product = self.db.get_product_by_id(self.current_product_id)
        if not messagebox.askyesno("Confirm Clear BOM",
                                    f"Delete ALL items from {product['part_number']}?\n\n"
                                    "This cannot be undone!", icon='warning'):
            return

        self.db.clear_product_bom(self.current_product_id)
        messagebox.showinfo("Success", "BOM cleared")
        self._set_status(f"Cleared BOM for {product['part_number']}")
        self.load_bom_viewer()

    # ================================================================
    # Import
    # ================================================================

    def import_bom(self):
        """Import BOM from one or more CSV files with embedded assembly metadata."""
        filenames = filedialog.askopenfilenames(
            title="Select BOM CSV file(s)",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if not filenames:
            return

        # Phase 1: Validate all files have assembly metadata
        file_metadata = []
        for fn in filenames:
            try:
                metadata = parse_csv_metadata(fn)
            except Exception as e:
                messagebox.showerror("Import Error", str(e))
                return

            if metadata is None:
                messagebox.showerror(
                    "Missing Assembly Info",
                    f"File '{os.path.basename(fn)}' does not contain assembly metadata.\n\n"
                    "Each CSV file must include metadata rows at the top, e.g.:\n\n"
                    "  #assembly_part_number,ABC-1234\n"
                    "  #assembly_description,My Assembly\n"
                    "  #assembly_revision,A\n\n"
                    "Import aborted."
                )
                return
            file_metadata.append((fn, metadata))

        # Phase 2: Sort files by dependency order
        if len(file_metadata) > 1:
            try:
                file_metadata = topological_sort_files(file_metadata)
            except Exception as e:
                messagebox.showerror("Import Error", str(e))
                return

        # Phase 3: Backup database before making changes
        backup_path = self._backup_database()

        # Phase 4: Process each file sequentially
        imported_count = 0
        total_files = len(file_metadata)

        for fn, metadata in file_metadata:
            part_number = metadata['part_number']
            existing_product = self.db.get_product(part_number)

            if existing_product:
                result = show_replace_dialog(
                    self.root, self.db, part_number, fn, imported_count, total_files
                )

                if result['cancelled']:
                    if imported_count > 0:
                        messagebox.showinfo(
                            "Import Cancelled",
                            f"Import cancelled by user at file '{os.path.basename(fn)}'.\n\n"
                            f"{imported_count} of {total_files} file(s) were imported before cancellation."
                        )
                    return

                import_info = {
                    'part_number': part_number,
                    'save_revision': result['save_revision'],
                    'notes': result['notes'],
                    'is_new': False
                }
            else:
                import_info = {
                    'part_number': part_number,
                    'description': metadata['description'],
                    'revision': metadata['revision'],
                    'save_revision': False,
                    'notes': '',
                    'is_new': True
                }

            try:
                comp_count, assy_count = process_import_to_db(self.db, fn, import_info)

                messagebox.showinfo("Import Complete",
                                     f"Successfully imported BOM for {part_number}\n\n"
                                     f"Components: {comp_count}\n"
                                     f"Sub-assemblies: {assy_count}")
            except Exception as e:
                error_msg = (
                    f"Error importing file '{os.path.basename(fn)}':\n\n{str(e)}\n\n"
                    f"{imported_count} of {total_files} file(s) were imported before this error."
                )
                if backup_path:
                    error_msg += f"\n\nDatabase backup saved to:\n{backup_path}"
                messagebox.showerror("Import Error", error_msg)
                return

            imported_count += 1

        # Refresh everything
        self._refresh_all()

        # Load the last imported BOM in viewer
        if file_metadata:
            last_pn = file_metadata[-1][1]['part_number']
            product = self.db.get_product(last_pn)
            if product:
                self.bom_assembly_var.set(
                    f"{product['part_number']} - {product['description']} (Rev {product['revision']})"
                )
                self.load_bom_viewer()

        if total_files > 1:
            messagebox.showinfo("Batch Import Complete",
                                 f"Successfully imported all {total_files} file(s).")
            self._set_status(f"Imported {total_files} BOM file(s)")
        elif total_files == 1:
            self._set_status(f"Imported BOM for {file_metadata[0][1]['part_number']}")

    # ================================================================
    # Exports
    # ================================================================

    def export_bom(self):
        """Export BOM to CSV"""
        if not self.current_product_id:
            messagebox.showwarning("No BOM", "Please select an assembly first")
            return
        product = self.db.get_product_by_id(self.current_product_id)

        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"{product['part_number']}_bom.csv"
        )
        if not filename:
            return

        try:
            components, sub_assemblies = self.db.get_product_bom(self.current_product_id)
            write_bom_csv(filename, product, components, sub_assemblies)
            messagebox.showinfo("Success", f"BOM exported to {filename}")
            self._set_status(f"Exported BOM to {os.path.basename(filename)}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Error exporting BOM:\n{str(e)}")

    def export_flattened_bom(self):
        """Export flattened BOM (components only)"""
        if not self.current_product_id:
            messagebox.showwarning("No BOM", "Please select an assembly first")
            return
        product = self.db.get_product_by_id(self.current_product_id)

        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"{product['part_number']}_flattened.csv"
        )
        if not filename:
            return

        try:
            flattened = self.db.get_flattened_bom(self.current_product_id)
            write_flattened_csv(filename, flattened)
            messagebox.showinfo("Success", f"Flattened BOM exported to {filename}")
            self._set_status(f"Exported flattened BOM to {os.path.basename(filename)}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Error exporting flattened BOM:\n{str(e)}")

    def export_exploded_bom(self):
        """Export exploded BOM (hierarchical with item numbers)"""
        if not self.current_product_id:
            messagebox.showwarning("No BOM", "Please select an assembly first")
            return
        product = self.db.get_product_by_id(self.current_product_id)

        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"{product['part_number']}_exploded.csv"
        )
        if not filename:
            return

        try:
            exploded = self.db.get_exploded_bom(self.current_product_id)
            write_exploded_csv(filename, exploded)
            messagebox.showinfo("Success", f"Exploded BOM exported to {filename}")
            self._set_status(f"Exported exploded BOM to {os.path.basename(filename)}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Error exporting exploded BOM:\n{str(e)}")

    def export_revision_bom(self):
        """Export revision BOM to CSV"""
        selected = self.rev_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a revision")
            return

        tags = self.rev_tree.item(selected[0], 'tags')
        revision_id = int(tags[0])

        revision = self.db.get_revision(revision_id)
        product = self.db.get_product_by_id(revision['product_id'])

        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"{product['part_number']}_rev{revision['revision']}.csv"
        )
        if not filename:
            return

        try:
            snapshot = json.loads(revision['bom_snapshot'])
            write_revision_csv(filename, snapshot)
            messagebox.showinfo("Success", f"Revision BOM exported to {filename}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Error exporting revision BOM:\n{str(e)}")

    # ================================================================
    # View dialogs (delegates to bom_dialogs)
    # ================================================================

    def view_flattened_bom(self):
        """View flattened BOM in a dialog"""
        if not self.current_product_id:
            messagebox.showwarning("No BOM", "Please select an assembly first")
            return
        show_flattened_bom_dialog(self.root, self.db, self.current_product_id,
                                  export_callback=self.export_flattened_bom)

    def view_exploded_bom(self):
        """View exploded BOM in a dialog"""
        if not self.current_product_id:
            messagebox.showwarning("No BOM", "Please select an assembly first")
            return
        show_exploded_bom_dialog(self.root, self.db, self.current_product_id,
                                  export_callback=self.export_exploded_bom)

    # ================================================================
    # Cost analysis
    # ================================================================

    def calculate_cost(self):
        """Calculate and display cost breakdown"""
        selected = self.cost_assembly_var.get()
        if not selected:
            messagebox.showerror("Error", "Please select an assembly")
            return

        try:
            qty = int(self.cost_qty_entry.get())
        except ValueError:
            messagebox.showerror("Error", "Invalid quantity")
            return

        part_number = selected.split(' - ')[0]
        product = self.db.get_product(part_number)
        if not product:
            return

        total_cost, breakdown = self.db.calculate_bom_cost(product['product_id'], qty)

        self.total_cost_label.config(text=f"${total_cost:.2f}")

        for item in self.cost_tree.get_children():
            self.cost_tree.delete(item)

        for item in breakdown:
            if item['type'] == 'assembly':
                self.cost_tree.insert('', 'end', values=(
                    item['item'],
                    f"{item['quantity']:.2f}",
                    item['uom'],
                    'Calculated',
                    f"${item['total']:.2f}"
                ), tags=('assembly',))
            else:
                self.cost_tree.insert('', 'end', values=(
                    item['item'],
                    f"{item['quantity']:.2f}",
                    item['uom'],
                    f"${item['unit_cost']:.4f}",
                    f"${item['total']:.2f}"
                ))

        self.cost_tree.tag_configure('assembly', background='#e8f4f8')

    # ================================================================
    # Component management actions
    # ================================================================

    def edit_component(self):
        """Edit selected component"""
        selected = self.comp_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a component")
            return
        component_id = int(self.comp_tree.item(selected[0], 'tags')[0])

        if show_edit_component_dialog(self.root, self.db, component_id):
            self.refresh_components(False)

    def delete_component(self):
        """Delete selected component"""
        selected = self.comp_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a component")
            return

        component_id = int(self.comp_tree.item(selected[0], 'tags')[0])

        usage = self.db.get_component_usage(component_id)
        if usage:
            messagebox.showerror("Cannot Delete",
                                  f"Component is used in {len(usage)} assemblies.\n"
                                  "Remove it from all BOMs before deleting.")
            return

        values = self.comp_tree.item(selected[0], 'values')
        if not messagebox.askyesno("Confirm Delete",
                                    f"Delete component {values[0]} ({values[1]})?"):
            return

        if self.db.delete_component(component_id):
            messagebox.showinfo("Success", "Component deleted")
            self.refresh_components(False)
        else:
            messagebox.showerror("Error", "Failed to delete component")

    def view_component_usage(self):
        """Show where component is used"""
        selected = self.comp_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a component")
            return

        component_id = int(self.comp_tree.item(selected[0], 'tags')[0])
        usage = self.db.get_component_usage(component_id)
        values = self.comp_tree.item(selected[0], 'values')
        comp_name = f"{values[0]} ({values[1]})"

        if not usage:
            messagebox.showinfo("Not Used", f"{comp_name} is not used in any assemblies")
            return

        show_component_usage_dialog(self.root, usage, comp_name)

    # ================================================================
    # Assembly management actions
    # ================================================================

    def search_assemblies(self):
        """Search assemblies"""
        search_term = self.assy_search_entry.get().strip().lower()
        if not search_term:
            self.refresh_assemblies()
            return

        for item in self.assy_tree.get_children():
            self.assy_tree.delete(item)

        products = self.db.get_all_products()

        for product in products:
            if (search_term in product['part_number'].lower() or
                    search_term in (product['description'] or '').lower()):
                components, sub_assemblies = self.db.get_product_bom(product['product_id'])
                item_count = len(components) + len(sub_assemblies)
                total_cost, _ = self.db.calculate_bom_cost(product['product_id'])
                modified = product['modified_date'][:10] if product['modified_date'] else ''

                self.assy_tree.insert('', 'end', values=(
                    product['part_number'],
                    product['description'],
                    product['revision'],
                    modified,
                    item_count,
                    f"${total_cost:.2f}"
                ), tags=(str(product['product_id']),))

    def view_assembly_bom(self):
        """View BOM for selected assembly"""
        selected = self.assy_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select an assembly")
            return

        product_id = int(self.assy_tree.item(selected[0], 'tags')[0])
        product = self.db.get_product_by_id(product_id)

        self.notebook.select(0)
        self.bom_assembly_var.set(
            f"{product['part_number']} - {product['description']} (Rev {product['revision']})")
        self.load_bom_viewer()

    def view_assembly_usage(self):
        """Show where assembly is used as sub-assembly"""
        selected = self.assy_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select an assembly")
            return

        product_id = int(self.assy_tree.item(selected[0], 'tags')[0])
        usage = self.db.get_assembly_usage(product_id)
        assy_name = self.assy_tree.item(selected[0], 'values')[0]

        if not usage:
            messagebox.showinfo("Not Used", f"{assy_name} is not used as a sub-assembly")
            return

        show_assembly_usage_dialog(self.root, usage, assy_name)

    def view_assembly_revisions(self):
        """View revision history for selected assembly"""
        selected = self.assy_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select an assembly")
            return

        product_id = int(self.assy_tree.item(selected[0], 'tags')[0])
        product = self.db.get_product_by_id(product_id)

        self.notebook.select(4)
        self.rev_assembly_var.set(
            f"{product['part_number']} - {product['description']} (Rev {product['revision']})")
        self.load_revisions()

    # ================================================================
    # Revision history
    # ================================================================

    def load_revisions(self, event=None):
        """Load revision history"""
        selected = self.rev_assembly_var.get()
        if not selected:
            return

        part_number = selected.split(' - ')[0]
        product = self.db.get_product(part_number)
        if not product:
            return

        for item in self.rev_tree.get_children():
            self.rev_tree.delete(item)

        revisions = self.db.get_revision_history(product['product_id'])

        for rev in revisions:
            date = rev['change_date'][:10] if rev['change_date'] else ''
            self.rev_tree.insert('', 'end', values=(
                rev['revision'],
                date,
                rev['change_notes'] or ''
            ), tags=(str(rev['revision_id']),))

    def view_revision_bom(self):
        """View BOM for selected revision"""
        selected = self.rev_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a revision")
            return
        revision_id = int(self.rev_tree.item(selected[0], 'tags')[0])
        show_revision_bom_dialog(self.root, self.db, revision_id)

    # ================================================================
    # Tools
    # ================================================================

    def _launch_converter(self):
        """Launch the BOM Format Converter tool."""
        if not HAS_CONVERTER:
            messagebox.showerror(
                "Converter Not Found",
                "The bom_converter_gui.py file was not found.\n\n"
                "Make sure bom_converter_gui.py is in the same directory."
            )
            return
        launch_converter(self.root)

    def _launch_pricing(self):
        """Launch the pricing update tool."""
        if not HAS_PRICING:
            messagebox.showerror(
                "Pricing Tool Not Found",
                "The bom_pricing_gui.py file was not found.\n\n"
                "Make sure bom_pricing_gui.py and bom_pricing.py "
                "are in the same directory."
            )
            return
        pricing_window = launch_pricing_update(self.root, self.db, self.current_product_id)
        # Refresh after pricing window is closed (prices may have changed)
        if pricing_window:
            pricing_window.bind('<Destroy>', lambda e: self._refresh_after_pricing())

    def _refresh_after_pricing(self):
        """Refresh views that display pricing data after the pricing tool runs."""
        try:
            if self.current_product_id:
                self.load_bom_viewer()
            self.refresh_components(False)
            self._set_status("Pricing views refreshed")
        except Exception:
            pass  # Window may already be closing

    def cleanup_duplicates(self):
        """Clean up duplicate component sources"""
        if not messagebox.askyesno("Clean Up Duplicates",
                                    "This will remove duplicate component sources.\n\nContinue?"):
            return

        duplicates = self.db.find_duplicate_sources()

        removed_count = 0
        for dup in duplicates:
            all_sources = self.db.get_sources_for_component_distributor(
                dup['component_id'], dup['distributor']
            )
            # Keep first (most recent), delete others
            for source in all_sources[1:]:
                self.db.delete_source(source['source_id'])
                removed_count += 1

        if removed_count > 0:
            messagebox.showinfo("Cleanup Complete", f"Removed {removed_count} duplicate sources")
            self.refresh_components(False)
        else:
            messagebox.showinfo("No Duplicates", "No duplicate sources found")
