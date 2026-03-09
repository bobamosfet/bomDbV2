#!/usr/bin/env python3
"""
BOM Pricing Update - GUI
Toplevel window for querying DigiKey/Mouser pricing and updating the database.
Launched from the BOM Management System main GUI.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import threading

from bom_pricing import (
    load_config, save_config,
    DigiKeyClient, MouserClient,
    prepare_component_list, prepare_all_components,
    query_pricing, apply_results_to_database,
    HAS_REQUESTS,
)


class PricingUpdateGUI:
    """GUI for updating component pricing from distributor APIs."""

    def __init__(self, root, db, current_product_id=None):
        self.db = db
        self.current_product_id = current_product_id
        self._results = []
        self._running = False

        self.window = tk.Toplevel(root)
        self.window.title("Update Component Pricing")
        self.window.geometry("1050x750")
        self.window.transient(root)

        self._config = load_config()

        self._build_ui()

        # Pre-select assembly if one is active
        if current_product_id:
            product = db.get_product_by_id(current_product_id)
            if product:
                target = f"{product['part_number']} - {product['description']} (Rev {product['revision']})"
                self._assy_var.set(target)

    def _build_ui(self):
        # ---- API Configuration ----
        config_frame = ttk.LabelFrame(self.window, text="API Configuration", padding=8)
        config_frame.pack(fill=tk.X, padx=10, pady=(10, 5))

        # Warning label
        ttk.Label(config_frame,
                  text="\u26a0 Credentials are stored in plaintext on disk (bom_pricing_config.json)",
                  foreground='#CC6600',
                  font=('TkDefaultFont', 9, 'italic')).grid(
            row=0, column=0, columnspan=6, sticky=tk.W, pady=(0, 6))

        # DigiKey
        ttk.Label(config_frame, text="DigiKey Client ID:").grid(
            row=1, column=0, sticky=tk.W, padx=3, pady=2)
        self._dk_id_entry = ttk.Entry(config_frame, width=35)
        self._dk_id_entry.insert(0, self._config.get('digikey_client_id', ''))
        self._dk_id_entry.grid(row=1, column=1, padx=3, pady=2)

        ttk.Label(config_frame, text="Client Secret:").grid(
            row=1, column=2, sticky=tk.W, padx=3, pady=2)
        self._dk_secret_entry = ttk.Entry(config_frame, width=35, show='*')
        self._dk_secret_entry.insert(0, self._config.get('digikey_client_secret', ''))
        self._dk_secret_entry.grid(row=1, column=3, padx=3, pady=2)

        # Mouser
        ttk.Label(config_frame, text="Mouser Part Search API Key:").grid(
            row=2, column=0, sticky=tk.W, padx=3, pady=2)
        self._mouser_key_entry = ttk.Entry(config_frame, width=35, show='*')
        self._mouser_key_entry.insert(0, self._config.get('mouser_api_key', ''))
        self._mouser_key_entry.grid(row=2, column=1, padx=3, pady=2)

        ttk.Button(config_frame, text="Save Keys",
                   command=self._save_keys).grid(row=2, column=3, sticky=tk.E, padx=3, pady=2)

        # ---- Scope selector ----
        scope_frame = ttk.LabelFrame(self.window, text="Scope", padding=5)
        scope_frame.pack(fill=tk.X, padx=10, pady=5)

        self._scope_var = tk.StringVar(value='assembly')

        scope_row1 = ttk.Frame(scope_frame)
        scope_row1.pack(fill=tk.X)

        ttk.Radiobutton(scope_row1, text="Selected Assembly:",
                        variable=self._scope_var, value='assembly',
                        command=self._on_scope_change).pack(side=tk.LEFT, padx=5)

        self._assy_var = tk.StringVar()
        products = self.db.get_all_products()
        product_list = [f"{p['part_number']} - {p['description']} (Rev {p['revision']})"
                        for p in products]
        self._assy_combo = ttk.Combobox(scope_row1, textvariable=self._assy_var,
                                         values=product_list, width=55, state='readonly')
        self._assy_combo.pack(side=tk.LEFT, padx=5)

        scope_row2 = ttk.Frame(scope_frame)
        scope_row2.pack(fill=tk.X, pady=(3, 0))

        ttk.Radiobutton(scope_row2, text="All Components in Database",
                        variable=self._scope_var, value='all',
                        command=self._on_scope_change).pack(side=tk.LEFT, padx=5)

        # Run button
        btn_row = ttk.Frame(scope_frame)
        btn_row.pack(fill=tk.X, pady=(5, 0))

        self._run_btn = ttk.Button(btn_row, text="Update Pricing",
                                    command=self._start_update)
        self._run_btn.pack(side=tk.LEFT, padx=5)

        self._progress_var = tk.StringVar(value="")
        ttk.Label(btn_row, textvariable=self._progress_var,
                  font=('TkDefaultFont', 9, 'italic')).pack(side=tk.LEFT, padx=10)

        # ---- Progress log ----
        log_frame = ttk.LabelFrame(self.window, text="Progress", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self._log_text = tk.Text(log_frame, height=10, wrap=tk.WORD,
                                  font=('TkFixedFont', 9), state=tk.DISABLED)
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL,
                                    command=self._log_text.yview)
        self._log_text.configure(yscrollcommand=log_scroll.set)
        self._log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # ---- Results table ----
        results_frame = ttk.LabelFrame(self.window, text="Results", padding=5)
        results_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        columns = ('Apply', 'Part Number', 'Manufacturer', 'DigiKey Price',
                   'Mouser Price', 'Best Price', 'Best Source', 'Status')
        self._results_tree = ttk.Treeview(results_frame, columns=columns,
                                           show='headings', height=10)

        widths = {'Apply': 45, 'Part Number': 150, 'Manufacturer': 120,
                  'DigiKey Price': 100, 'Mouser Price': 100,
                  'Best Price': 100, 'Best Source': 90, 'Status': 120}
        for col in columns:
            self._results_tree.heading(col, text=col)
            self._results_tree.column(col, width=widths.get(col, 100),
                                       anchor=tk.CENTER if col == 'Apply' else tk.W)

        res_scroll = ttk.Scrollbar(results_frame, orient=tk.VERTICAL,
                                    command=self._results_tree.yview)
        self._results_tree.configure(yscrollcommand=res_scroll.set)
        self._results_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        res_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Click to toggle checkmark
        self._results_tree.bind('<ButtonRelease-1>', self._on_results_click)

        # ---- Bottom buttons ----
        btn_frame = ttk.Frame(self.window)
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        ttk.Button(btn_frame, text="Select All",
                   command=self._select_all).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="Select None",
                   command=self._select_none).pack(side=tk.LEFT, padx=3)
        ttk.Button(btn_frame, text="Select Found Only",
                   command=self._select_found).pack(side=tk.LEFT, padx=3)

        ttk.Separator(btn_frame, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)

        self._apply_btn = ttk.Button(btn_frame, text="Apply Selected to Database",
                                      command=self._apply_to_db, state=tk.DISABLED)
        self._apply_btn.pack(side=tk.LEFT, padx=5)

        self._summary_label = ttk.Label(btn_frame, text="",
                                         font=('TkDefaultFont', 9))
        self._summary_label.pack(side=tk.LEFT, padx=15)

        ttk.Button(btn_frame, text="Close",
                   command=self.window.destroy).pack(side=tk.RIGHT, padx=5)

    # ---- Config management ----

    def _save_keys(self):
        self._config['digikey_client_id'] = self._dk_id_entry.get().strip()
        self._config['digikey_client_secret'] = self._dk_secret_entry.get().strip()
        self._config['mouser_api_key'] = self._mouser_key_entry.get().strip()
        try:
            save_config(self._config)
            messagebox.showinfo("Saved", "API credentials saved to bom_pricing_config.json",
                                parent=self.window)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save config:\n{str(e)}",
                                 parent=self.window)

    # ---- Scope handling ----

    def _on_scope_change(self):
        """Enable/disable the assembly combo based on scope selection."""
        if self._scope_var.get() == 'all':
            self._assy_combo.config(state='disabled')
        else:
            self._assy_combo.config(state='readonly')

    # ---- Selection handling ----

    def _on_results_click(self, event):
        """Toggle checkmark when user clicks on the Apply column."""
        region = self._results_tree.identify_region(event.x, event.y)
        if region != 'cell':
            return
        col = self._results_tree.identify_column(event.x)
        if col != '#1':  # First column = 'Apply'
            return

        item_id = self._results_tree.identify_row(event.y)
        if not item_id:
            return

        values = list(self._results_tree.item(item_id, 'values'))
        if values[0] == '\u2713':
            values[0] = ''
        else:
            values[0] = '\u2713'
        self._results_tree.item(item_id, values=values)
        self._update_apply_button_state()

    def _select_all(self):
        """Check all rows."""
        for item_id in self._results_tree.get_children():
            values = list(self._results_tree.item(item_id, 'values'))
            values[0] = '\u2713'
            self._results_tree.item(item_id, values=values)
        self._update_apply_button_state()

    def _select_none(self):
        """Uncheck all rows."""
        for item_id in self._results_tree.get_children():
            values = list(self._results_tree.item(item_id, 'values'))
            values[0] = ''
            self._results_tree.item(item_id, values=values)
        self._update_apply_button_state()

    def _select_found(self):
        """Check only rows that have pricing data."""
        for i, item_id in enumerate(self._results_tree.get_children()):
            if i < len(self._results) and self._results[i].found_anywhere:
                values = list(self._results_tree.item(item_id, 'values'))
                values[0] = '\u2713'
                self._results_tree.item(item_id, values=values)
            else:
                values = list(self._results_tree.item(item_id, 'values'))
                values[0] = ''
                self._results_tree.item(item_id, values=values)
        self._update_apply_button_state()

    def _get_selected_indices(self):
        """Return list of indices for checked rows."""
        selected = []
        for i, item_id in enumerate(self._results_tree.get_children()):
            values = self._results_tree.item(item_id, 'values')
            if values[0] == '\u2713':
                selected.append(i)
        return selected

    def _update_apply_button_state(self):
        """Enable Apply button only if at least one row is checked."""
        indices = self._get_selected_indices()
        has_applicable = any(
            i < len(self._results) and self._results[i].found_anywhere
            for i in indices
        )
        self._apply_btn.config(state=tk.NORMAL if has_applicable else tk.DISABLED)

    # ---- Logging ----

    def _log(self, message):
        """Append message to the progress log (thread-safe via after())."""
        def _do():
            self._log_text.config(state=tk.NORMAL)
            self._log_text.insert(tk.END, message + '\n')
            self._log_text.see(tk.END)
            self._log_text.config(state=tk.DISABLED)
        self.window.after(0, _do)

    # ---- Pricing update ----

    def _start_update(self):
        """Validate inputs and start the pricing update in a background thread."""
        if self._running:
            return

        if not HAS_REQUESTS:
            messagebox.showerror(
                "Missing Library",
                "The 'requests' library is required.\n\n"
                "Install it with: pip install requests",
                parent=self.window)
            return

        scope = self._scope_var.get()

        if scope == 'assembly':
            selected = self._assy_var.get()
            if not selected:
                messagebox.showwarning("No Assembly", "Please select an assembly.",
                                        parent=self.window)
                return

        # Read current credentials from entries (in case user edited but didn't save)
        dk_id = self._dk_id_entry.get().strip()
        dk_secret = self._dk_secret_entry.get().strip()
        mouser_key = self._mouser_key_entry.get().strip()

        if not dk_id and not mouser_key:
            messagebox.showwarning(
                "No API Keys",
                "At least one distributor API key is required.\n\n"
                "Enter your DigiKey client ID/secret and/or Mouser API key.",
                parent=self.window)
            return

        # Build clients
        dk_client = DigiKeyClient(dk_id, dk_secret) if dk_id and dk_secret else None
        mouser_client = MouserClient(mouser_key) if mouser_key else None

        # Clear previous results
        self._results_tree.delete(*self._results_tree.get_children())
        self._log_text.config(state=tk.NORMAL)
        self._log_text.delete('1.0', tk.END)
        self._log_text.config(state=tk.DISABLED)
        self._apply_btn.config(state=tk.DISABLED)
        self._summary_label.config(text="")
        self._results = []

        # Disable controls during run
        self._running = True
        self._run_btn.config(state=tk.DISABLED)

        active = []
        if dk_client and dk_client.is_configured():
            active.append('DigiKey')
        if mouser_client and mouser_client.is_configured():
            active.append('Mouser')

        # Prepare component list on the MAIN thread (all database access here)
        if scope == 'all':
            self._log("Starting pricing update for ALL components in database")
            self._log(f"Active distributors: {', '.join(active)}\n")
            self._log("Gathering all components...")
            component_list = prepare_all_components(self.db)
        else:
            part_number = self._assy_var.get().split(' - ')[0]
            product = self.db.get_product(part_number)
            if not product:
                messagebox.showerror("Error", f"Assembly {part_number} not found",
                                     parent=self.window)
                self._running = False
                self._run_btn.config(state=tk.NORMAL)
                return
            self._log(f"Starting pricing update for {part_number}")
            self._log(f"Active distributors: {', '.join(active)}\n")
            self._log("Gathering components from flattened BOM...")
            component_list = prepare_component_list(self.db, product['product_id'])

        if not component_list:
            self._log("No components found.")
            self._running = False
            self._run_btn.config(state=tk.NORMAL)
            return

        self._log(f"Found {len(component_list)} unique components.\n")

        # Run network queries in background thread (NO database access)
        def _worker():
            try:
                results = query_pricing(
                    component_list,
                    digikey_client=dk_client,
                    mouser_client=mouser_client,
                    progress_callback=self._log
                )
                self.window.after(0, lambda: self._on_update_complete(results))
            except Exception as e:
                self._log(f"\nERROR: {str(e)}")
                self.window.after(0, self._on_update_error)

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

    def _on_update_complete(self, results):
        """Called on the main thread when pricing update finishes."""
        self._results = results
        self._running = False
        self._run_btn.config(state=tk.NORMAL)

        # Populate results table
        found_count = 0
        not_found_count = 0

        for pr in results:
            dk_price = ''
            mouser_price = ''
            best_price = ''
            best_source = ''
            status = pr.status

            if pr.digikey and pr.digikey.get('unit_price') is not None:
                dk_price = f"${pr.digikey['unit_price']:.4f}"
            elif pr.digikey and pr.digikey.get('error'):
                dk_price = 'Error'

            if pr.mouser and pr.mouser.get('unit_price') is not None:
                mouser_price = f"${pr.mouser['unit_price']:.4f}"
            elif pr.mouser and pr.mouser.get('error'):
                mouser_price = 'Error'

            if pr.best_price is not None:
                best_price = f"${pr.best_price:.4f}"
                best_source = pr.best_distributor or ''

            if pr.found_anywhere:
                found_count += 1
                tag = 'found'
            else:
                not_found_count += 1
                tag = 'notfound'

            # Auto-check items that have pricing
            check = '\u2713' if pr.found_anywhere else ''

            self._results_tree.insert('', 'end', values=(
                check,
                pr.mfg_part_number, pr.manufacturer,
                dk_price, mouser_price, best_price, best_source, status
            ), tags=(tag,))

        self._results_tree.tag_configure('found', foreground='black')
        self._results_tree.tag_configure('notfound', foreground='#CC0000')

        # Summary
        total = len(results)
        self._summary_label.config(
            text=f"Total: {total} | Priced: {found_count} | Not found: {not_found_count}"
        )

        self._log(f"\n{'='*50}")
        self._log(f"Complete: {found_count} priced, {not_found_count} not found, {total} total")

        if found_count > 0:
            self._update_apply_button_state()
            self._log("Check the items you want to apply, then click 'Apply Selected to Database'.")
        else:
            self._log("No pricing found to apply.")

    def _on_update_error(self):
        """Called on the main thread if the worker thread crashes."""
        self._running = False
        self._run_btn.config(state=tk.NORMAL)
        self._progress_var.set("Error occurred")

    # ---- Apply results to DB ----

    def _apply_to_db(self):
        """Write pricing for selected items to the database."""
        if not self._results:
            return

        selected_indices = self._get_selected_indices()
        selected_results = [self._results[i] for i in selected_indices
                            if i < len(self._results) and self._results[i].found_anywhere]

        if not selected_results:
            messagebox.showwarning("No Selection",
                                    "No items with pricing are selected.\n\n"
                                    "Check the items you want to apply.",
                                    parent=self.window)
            return

        if not messagebox.askyesno(
                "Apply Pricing",
                f"This will update pricing for {len(selected_results)} component(s).\n\n"
                "Components not found at any distributor will be left untouched.\n\n"
                "Continue?",
                parent=self.window):
            return

        self._log(f"\nApplying pricing for {len(selected_results)} selected component(s)...")

        updated, skipped = apply_results_to_database(
            self.db, selected_results, progress_callback=self._log
        )

        self._log(f"\nDone: {updated} source(s) updated, {skipped} component(s) skipped.")
        self._apply_btn.config(state=tk.DISABLED)

        messagebox.showinfo(
            "Pricing Applied",
            f"Updated {updated} component source(s) in the database.\n"
            f"Skipped {skipped} component(s) (not found or missing ID).",
            parent=self.window)


# ============================================================
# Launch function
# ============================================================

def launch_pricing_update(root, db, current_product_id=None):
    """Launch the pricing update window.

    Args:
        root: parent Tk window
        db: BOMDatabase instance
        current_product_id: optional pre-selected assembly

    Returns:
        The Toplevel window widget (for event binding).
    """
    gui = PricingUpdateGUI(root, db, current_product_id)
    return gui.window
