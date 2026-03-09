#!/usr/bin/env python3
"""
BOM Format Converter - GUI
Standalone GUI for converting BOM files to standard format.
Can be run standalone or launched from the BOM Management System GUI.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import os
import json
import re

from bom_converter import (
    FileAnalysis, convert_flat_bom, convert_hierarchical_bom, write_standard_csv,
)


class BOMConverterGUI:
    """Standalone GUI for converting BOM files to standard format."""

    def __init__(self, root=None, standalone=True):
        if standalone:
            self.root = root or tk.Tk()
            self.root.title("BOM Format Converter")
        else:
            self.root = tk.Toplevel(root)
            self.root.title("BOM Format Converter")
            self.root.transient(root)

        self.root.geometry("950x850")

        self.analyses = []       # list of FileAnalysis objects
        self.output_dir = None
        self._config_file = 'bom_converter_config.json'

        self._build_ui()
        self._load_config()

    def _build_ui(self):
        # --- Top: file selection ---
        top = ttk.LabelFrame(self.root, text="Input Files", padding=10)
        top.pack(fill=tk.X, padx=10, pady=(10, 5))

        btn_row = ttk.Frame(top)
        btn_row.pack(fill=tk.X)
        ttk.Button(btn_row, text="Select Files...",
                   command=self._select_files).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_row, text="Clear All",
                   command=self._clear_files).pack(side=tk.LEFT, padx=5)

        self.file_list_var = tk.StringVar(value="No files selected")
        ttk.Label(top, textvariable=self.file_list_var,
                  wraplength=850, justify=tk.LEFT).pack(fill=tk.X, pady=5)

        # --- Middle: analysis results ---
        mid = ttk.LabelFrame(self.root, text="Analysis Results", padding=10)
        mid.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        tree_frame = ttk.Frame(mid)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ('File', 'Format', 'Assembly PN', 'Description', 'Rev',
                   'Columns Found', 'Data Rows', 'Hierarchy', 'Status')
        self.tree = ttk.Treeview(tree_frame, columns=columns,
                                 show='headings', height=8)

        widths = {'File': 160, 'Format': 55, 'Assembly PN': 110,
                  'Description': 140, 'Rev': 35, 'Columns Found': 170,
                  'Data Rows': 65, 'Hierarchy': 65, 'Status': 90}
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=widths.get(col, 100), minwidth=30)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL,
                                  command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind('<<TreeviewSelect>>', self._on_select)

        # Detail panel
        detail = ttk.LabelFrame(mid, text="Details", padding=5)
        detail.pack(fill=tk.X, pady=(5, 0))
        self.detail_text = tk.Text(detail, height=5, wrap=tk.WORD,
                                    state=tk.DISABLED, font=('TkFixedFont', 9))
        self.detail_text.pack(fill=tk.X)

        # Data preview panel
        preview_frame = ttk.LabelFrame(mid, text="Data Preview (first 8 rows)", padding=5)
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

        self.preview_tree = ttk.Treeview(preview_frame, show='headings', height=6)
        preview_scroll_x = ttk.Scrollbar(preview_frame, orient=tk.HORIZONTAL,
                                          command=self.preview_tree.xview)
        preview_scroll_y = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL,
                                          command=self.preview_tree.yview)
        self.preview_tree.configure(xscrollcommand=preview_scroll_x.set,
                                     yscrollcommand=preview_scroll_y.set)

        self.preview_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        preview_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        preview_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)

        # --- Metadata override ---
        meta_frame = ttk.LabelFrame(self.root, text="Override / Set Metadata "
                                    "(select a file above, then edit here)",
                                    padding=10)
        meta_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(meta_frame, text="Assembly PN:").grid(
            row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.meta_pn = ttk.Entry(meta_frame, width=30)
        self.meta_pn.grid(row=0, column=1, padx=5, pady=2, sticky=tk.W)

        ttk.Label(meta_frame, text="Description:").grid(
            row=0, column=2, sticky=tk.W, padx=5, pady=2)
        self.meta_desc = ttk.Entry(meta_frame, width=40)
        self.meta_desc.grid(row=0, column=3, padx=5, pady=2, sticky=tk.W)

        ttk.Label(meta_frame, text="Revision:").grid(
            row=0, column=4, sticky=tk.W, padx=5, pady=2)
        self.meta_rev = ttk.Entry(meta_frame, width=8)
        self.meta_rev.grid(row=0, column=5, padx=5, pady=2, sticky=tk.W)

        ttk.Button(meta_frame, text="Apply to Selected",
                   command=self._apply_metadata).grid(
            row=0, column=6, padx=10, pady=2)

        # --- Bottom: output ---
        bot = ttk.Frame(self.root, padding=10)
        bot.pack(fill=tk.X, padx=10, pady=(0, 10))

        ttk.Button(bot, text="Set Output Folder...",
                   command=self._select_output).pack(side=tk.LEFT, padx=5)
        self.output_label = ttk.Label(bot, text="No output folder selected")
        self.output_label.pack(side=tk.LEFT, padx=10)

        ttk.Button(bot, text="Convert All",
                   command=self._convert_all).pack(side=tk.RIGHT, padx=5)

    # --- File selection ---

    def _select_files(self):
        fnames = filedialog.askopenfilenames(
            title="Select BOM files to convert",
            filetypes=[
                ("BOM files", "*.csv *.tsv *.xlsx"),
                ("CSV files", "*.csv"),
                ("TSV files", "*.tsv"),
                ("Excel files", "*.xlsx"),
                ("All files", "*.*"),
            ]
        )
        if not fnames:
            return

        self.analyses = []
        for fn in fnames:
            a = FileAnalysis(fn)
            a.analyze()
            self.analyses.append(a)

        basenames = [a.basename for a in self.analyses]
        self.file_list_var.set(', '.join(basenames))
        self._refresh_tree()

    def _clear_files(self):
        self.analyses = []
        self.file_list_var.set("No files selected")
        self.tree.delete(*self.tree.get_children())
        self._set_detail("")
        self._clear_preview()

    # --- Tree display ---

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())

        for i, a in enumerate(self.analyses):
            ext = os.path.splitext(a.filename)[1].upper().replace('.', '')
            assy_pn = a.metadata.get('part_number', '') or ''
            desc = a.metadata.get('description', '') or ''
            rev = a.metadata.get('revision', '') or ''

            mapped = ', '.join(f"{intl}" for intl, _ in a.detected_columns)
            hier = 'Yes' if a.is_hierarchical else 'No'
            status = 'Error' if a.error else (
                'Needs PN' if not assy_pn else 'Ready')

            tag = 'error' if a.error else ('warn' if not assy_pn else 'ok')

            self.tree.insert('', 'end', iid=str(i), values=(
                a.basename, ext, assy_pn, desc, rev,
                mapped, a.data_row_count, hier, status
            ), tags=(tag,))

        self.tree.tag_configure('error', foreground='red')
        self.tree.tag_configure('warn', foreground='#CC8800')
        self.tree.tag_configure('ok', foreground='black')

    def _on_select(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        a = self.analyses[idx]

        lines = []
        lines.append(f"File: {a.filename}")
        if a.error:
            lines.append(f"ERROR: {a.error}")
        else:
            lines.append(f"Header at row: {a.header_idx + 1}")
            lines.append(
                f"Mapped columns: "
                f"{', '.join(f'{intl} ← \"{orig}\"' for intl, orig in a.detected_columns)}"
            )
            if a.unmapped_columns:
                lines.append(
                    f"Unmapped columns (ignored): {', '.join(a.unmapped_columns)}"
                )
            if a.is_hierarchical:
                lines.append("Hierarchical BOM detected — sub-assemblies will "
                             "be split into separate output files.")

        self._set_detail('\n'.join(lines))

        # Populate preview pane
        self._populate_preview(a)

        # Populate metadata fields
        self.meta_pn.delete(0, tk.END)
        self.meta_pn.insert(0, a.metadata.get('part_number', '') or '')
        self.meta_desc.delete(0, tk.END)
        self.meta_desc.insert(0, a.metadata.get('description', '') or '')
        self.meta_rev.delete(0, tk.END)
        self.meta_rev.insert(0, a.metadata.get('revision', 'A') or 'A')

    def _set_detail(self, text):
        self.detail_text.config(state=tk.NORMAL)
        self.detail_text.delete('1.0', tk.END)
        self.detail_text.insert('1.0', text)
        self.detail_text.config(state=tk.DISABLED)

    def _populate_preview(self, analysis):
        """Show the first 8 data rows from the analyzed file in the preview tree."""
        self._clear_preview()

        if analysis.error or not analysis.data_rows:
            return

        # Use the original header row for column names
        header_row = analysis.rows[analysis.header_idx]
        col_ids = [f"c{i}" for i in range(len(header_row))]

        self.preview_tree['columns'] = col_ids
        for i, hdr in enumerate(header_row):
            display = hdr if hdr else f"(col {i+1})"
            self.preview_tree.heading(col_ids[i], text=display)
            self.preview_tree.column(col_ids[i], width=100, minwidth=50)

        # Insert first 8 data rows
        for row in analysis.data_rows[:8]:
            # Pad row to match column count
            padded = list(row) + [''] * (len(col_ids) - len(row))
            self.preview_tree.insert('', 'end', values=padded[:len(col_ids)])

    def _clear_preview(self):
        """Clear the preview tree."""
        self.preview_tree.delete(*self.preview_tree.get_children())
        self.preview_tree['columns'] = ()

    # --- Config persistence ---

    def _load_config(self):
        """Load converter settings (last output folder)."""
        try:
            if os.path.exists(self._config_file):
                with open(self._config_file, 'r') as f:
                    config = json.load(f)
                saved_dir = config.get('last_output_folder', '')
                if saved_dir and os.path.isdir(saved_dir):
                    self.output_dir = saved_dir
                    self.output_label.config(text=saved_dir)
        except Exception:
            pass  # Silently ignore corrupt config

    def _save_config(self):
        """Save converter settings."""
        try:
            config = {}
            if self.output_dir:
                config['last_output_folder'] = self.output_dir
            with open(self._config_file, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception:
            pass  # Non-critical, silently ignore

    # --- Metadata editing ---

    def _apply_metadata(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("No Selection",
                                    "Select a file in the list first.")
            return

        idx = int(sel[0])
        a = self.analyses[idx]
        a.metadata['part_number'] = self.meta_pn.get().strip() or None
        a.metadata['description'] = self.meta_desc.get().strip()
        a.metadata['revision'] = self.meta_rev.get().strip() or 'A'
        self._refresh_tree()
        # Re-select to keep focus
        self.tree.selection_set(sel[0])

    # --- Output ---

    def _select_output(self):
        d = filedialog.askdirectory(title="Select output folder",
                                     initialdir=self.output_dir or os.getcwd())
        if d:
            self.output_dir = d
            self.output_label.config(text=d)
            self._save_config()

    def _convert_all(self):
        # Validate
        if not self.analyses:
            messagebox.showwarning("No Files", "Select input files first.")
            return

        if not self.output_dir:
            messagebox.showwarning("No Output", "Select an output folder first.")
            return

        errors = []
        for a in self.analyses:
            if a.error:
                errors.append(f"{a.basename}: {a.error}")
            elif not a.metadata.get('part_number'):
                errors.append(
                    f"{a.basename}: Missing assembly part number. "
                    "Select it and use 'Apply to Selected'."
                )

        if errors:
            messagebox.showerror(
                "Cannot Convert",
                "Fix these issues before converting:\n\n" +
                '\n'.join(errors)
            )
            return

        # Convert
        total_files_written = 0
        files_written = []

        try:
            for a in self.analyses:
                if a.is_hierarchical:
                    assemblies = convert_hierarchical_bom(a)
                    for assy_pn, (meta, rows) in assemblies.items():
                        safe_pn = re.sub(r'[<>:"/\\|?*]', '_', assy_pn)
                        out_path = os.path.join(
                            self.output_dir, f"{safe_pn}_bom.csv")
                        write_standard_csv(out_path, meta, rows)
                        files_written.append(
                            f"  {os.path.basename(out_path)}  "
                            f"({len(rows)} items)")
                        total_files_written += 1
                else:
                    rows = convert_flat_bom(a)
                    safe_pn = re.sub(r'[<>:"/\\|?*]', '_',
                                     a.metadata['part_number'])
                    out_path = os.path.join(
                        self.output_dir, f"{safe_pn}_bom.csv")
                    write_standard_csv(out_path, a.metadata, rows)
                    files_written.append(
                        f"  {os.path.basename(out_path)}  ({len(rows)} items)")
                    total_files_written += 1

        except Exception as e:
            messagebox.showerror("Conversion Error",
                                  f"Error during conversion:\n\n{str(e)}")
            return

        summary = (
            f"Successfully created {total_files_written} file(s) in:\n"
            f"{self.output_dir}\n\n" +
            '\n'.join(files_written)
        )
        messagebox.showinfo("Conversion Complete", summary)


# ============================================================
# Entry point
# ============================================================

def launch_converter(parent_root=None):
    """Launch the converter GUI.  Call from the BOM system or standalone."""
    if parent_root:
        BOMConverterGUI(root=parent_root, standalone=False)
    else:
        root = tk.Tk()
        app = BOMConverterGUI(root=root, standalone=True)
        root.mainloop()


if __name__ == "__main__":
    launch_converter()
