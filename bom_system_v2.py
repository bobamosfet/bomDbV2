#!/usr/bin/env python3
"""
BOM Management System v2
A streamlined system for managing hierarchical bills of materials
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3
from datetime import datetime
import csv
import json
import os
from decimal import Decimal


class BOMDatabase:
    """Handles all database operations"""
    
    def __init__(self, db_path="bom_system_v2.db"):
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self.connect()
        self.create_tables()
    
    def connect(self):
        """Establish database connection"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
    
    
    def verify_database_schema(self):
        """Verify that the database has the correct schema"""
        required_tables = [
            'components', 'component_sources', 'products', 
            'bom_entries', 'sub_assemblies', 'revision_history'
        ]
        
        # Check if all required tables exist
        self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing_tables = [row['name'] for row in self.cursor.fetchall()]
        
        missing_tables = [t for t in required_tables if t not in existing_tables]
        
        if missing_tables:
            return False, f"Missing tables: {', '.join(missing_tables)}"
        
        # Verify key columns exist in each table
        table_columns = {
            'components': ['component_id', 'mfg_part_number', 'manufacturer'],
            'component_sources': ['source_id', 'component_id', 'distributor'],
            'products': ['product_id', 'part_number', 'description', 'revision'],
            'bom_entries': ['entry_id', 'product_id', 'component_id', 'quantity'],
            'sub_assemblies': ['sub_assembly_id', 'parent_product_id', 'child_product_id', 'quantity'],
            'revision_history': ['revision_id', 'product_id', 'revision', 'bom_snapshot']
        }
        
        for table, required_cols in table_columns.items():
            self.cursor.execute(f"PRAGMA table_info({table})")
            existing_cols = [row['name'] for row in self.cursor.fetchall()]
            missing_cols = [c for c in required_cols if c not in existing_cols]
            
            if missing_cols:
                return False, f"Table '{table}' missing columns: {', '.join(missing_cols)}"
        
        return True, "Database schema is valid"

    def create_tables(self):
        """Create database schema"""
        
        # Components table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS components (
                component_id INTEGER PRIMARY KEY AUTOINCREMENT,
                mfg_part_number TEXT NOT NULL,
                manufacturer TEXT NOT NULL,
                description TEXT,
                category TEXT,
                unit_of_measure TEXT DEFAULT 'EA',
                notes TEXT,
                UNIQUE(mfg_part_number, manufacturer)
            )
        """)
        
        # Component sources table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS component_sources (
                source_id INTEGER PRIMARY KEY AUTOINCREMENT,
                component_id INTEGER,
                distributor TEXT,
                distributor_part_number TEXT,
                unit_cost REAL,
                last_updated TEXT,
                FOREIGN KEY (component_id) REFERENCES components(component_id),
                UNIQUE(component_id, distributor)
            )
        """)
        
        # Products/Assemblies table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                product_id INTEGER PRIMARY KEY AUTOINCREMENT,
                part_number TEXT UNIQUE NOT NULL,
                description TEXT,
                revision TEXT DEFAULT 'A',
                created_date TEXT,
                modified_date TEXT,
                notes TEXT
            )
        """)
        
        # BOM entries table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS bom_entries (
                entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                component_id INTEGER,
                quantity REAL NOT NULL,
                reference_designators TEXT,
                notes TEXT,
                FOREIGN KEY (product_id) REFERENCES products(product_id),
                FOREIGN KEY (component_id) REFERENCES components(component_id)
            )
        """)
        
        # Sub-assemblies table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS sub_assemblies (
                sub_assembly_id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_product_id INTEGER,
                child_product_id INTEGER,
                quantity REAL NOT NULL,
                reference_designators TEXT,
                notes TEXT,
                FOREIGN KEY (parent_product_id) REFERENCES products(product_id),
                FOREIGN KEY (child_product_id) REFERENCES products(product_id)
            )
        """)
        
        # Revision history table
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS revision_history (
                revision_id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id INTEGER,
                revision TEXT,
                change_date TEXT,
                change_notes TEXT,
                bom_snapshot TEXT,
                FOREIGN KEY (product_id) REFERENCES products(product_id)
            )
        """)
        
        self.conn.commit()
    
    def add_or_update_component(self, mfg_part_number, manufacturer, description="", 
                                category="", unit_of_measure="EA", notes=""):
        """Add or update a component"""
        self.cursor.execute("""
            SELECT component_id FROM components 
            WHERE mfg_part_number = ? AND manufacturer = ?
        """, (mfg_part_number, manufacturer))
        
        existing = self.cursor.fetchone()
        
        if existing:
            # Update existing component (but don't overwrite with blank values)
            component_id = existing['component_id']
            if description:
                self.cursor.execute("UPDATE components SET description = ? WHERE component_id = ?",
                                  (description, component_id))
            if category:
                self.cursor.execute("UPDATE components SET category = ? WHERE component_id = ?",
                                  (category, component_id))
            if unit_of_measure:
                self.cursor.execute("UPDATE components SET unit_of_measure = ? WHERE component_id = ?",
                                  (unit_of_measure, component_id))
            if notes:
                self.cursor.execute("UPDATE components SET notes = ? WHERE component_id = ?",
                                  (notes, component_id))
            self.conn.commit()
            return component_id
        else:
            # Create new component
            self.cursor.execute("""
                INSERT INTO components (mfg_part_number, manufacturer, description, category,
                                      unit_of_measure, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (mfg_part_number, manufacturer, description, category, unit_of_measure, notes))
            self.conn.commit()
            return self.cursor.lastrowid
    
    def add_or_update_component_source(self, component_id, distributor, distributor_pn="",
                                      unit_cost=None):
        """Add or update a component source (preserve existing price if new price is None)"""
        if not distributor:
            return None
        
        self.cursor.execute("""
            SELECT source_id, unit_cost FROM component_sources 
            WHERE component_id = ? AND distributor = ?
        """, (component_id, distributor))
        
        existing = self.cursor.fetchone()
        now = datetime.now().isoformat()
        
        if existing:
            # Update existing source
            source_id = existing['source_id']
            # Only update cost if a new cost was provided
            if unit_cost is not None:
                self.cursor.execute("""
                    UPDATE component_sources 
                    SET distributor_part_number = ?, unit_cost = ?, last_updated = ?
                    WHERE source_id = ?
                """, (distributor_pn, unit_cost, now, source_id))
            else:
                # Just update part number and date, keep existing cost
                self.cursor.execute("""
                    UPDATE component_sources 
                    SET distributor_part_number = ?, last_updated = ?
                    WHERE source_id = ?
                """, (distributor_pn, now, source_id))
            self.conn.commit()
            return source_id
        else:
            # Create new source (only if we have a cost)
            if unit_cost is not None:
                self.cursor.execute("""
                    INSERT INTO component_sources (component_id, distributor, distributor_part_number,
                                                  unit_cost, last_updated)
                    VALUES (?, ?, ?, ?, ?)
                """, (component_id, distributor, distributor_pn, unit_cost, now))
                self.conn.commit()
                return self.cursor.lastrowid
        return None
    
    def add_or_update_product(self, part_number, description="", revision="A", notes=""):
        """Add or update a product/assembly"""
        self.cursor.execute("SELECT product_id FROM products WHERE part_number = ?", (part_number,))
        existing = self.cursor.fetchone()
        
        now = datetime.now().isoformat()
        
        if existing:
            # Update existing product
            product_id = existing['product_id']
            self.cursor.execute("""
                UPDATE products 
                SET description = ?, revision = ?, modified_date = ?, notes = ?
                WHERE product_id = ?
            """, (description, revision, now, notes, product_id))
            self.conn.commit()
            return product_id
        else:
            # Create new product
            self.cursor.execute("""
                INSERT INTO products (part_number, description, revision, created_date, 
                                    modified_date, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (part_number, description, revision, now, now, notes))
            self.conn.commit()
            return self.cursor.lastrowid
    
    def get_product(self, part_number):
        """Get product by part number"""
        self.cursor.execute("SELECT * FROM products WHERE part_number = ?", (part_number,))
        return self.cursor.fetchone()
    
    def get_product_by_id(self, product_id):
        """Get product by ID"""
        self.cursor.execute("SELECT * FROM products WHERE product_id = ?", (product_id,))
        return self.cursor.fetchone()
    
    def get_all_products(self):
        """Get all products"""
        self.cursor.execute("SELECT * FROM products ORDER BY part_number")
        return self.cursor.fetchall()
    
    def save_bom_as_revision(self, product_id, revision, notes=""):
        """Save current BOM as a revision snapshot"""
        # Get current BOM
        components, sub_assemblies = self.get_product_bom(product_id)
        
        # Create snapshot
        snapshot = {
            'components': [dict(c) for c in components],
            'sub_assemblies': [dict(s) for s in sub_assemblies]
        }
        
        now = datetime.now().isoformat()
        
        self.cursor.execute("""
            INSERT INTO revision_history (product_id, revision, change_date, change_notes, bom_snapshot)
            VALUES (?, ?, ?, ?, ?)
        """, (product_id, revision, now, notes, json.dumps(snapshot)))
        self.conn.commit()
        return self.cursor.lastrowid
    
    def clear_product_bom(self, product_id):
        """Delete all BOM entries for a product"""
        self.cursor.execute("DELETE FROM bom_entries WHERE product_id = ?", (product_id,))
        self.cursor.execute("DELETE FROM sub_assemblies WHERE parent_product_id = ?", (product_id,))
        self.conn.commit()
    
    def add_bom_entry(self, product_id, component_id, quantity, ref_des="", notes=""):
        """Add a component to a product's BOM"""
        self.cursor.execute("""
            INSERT INTO bom_entries (product_id, component_id, quantity, reference_designators, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (product_id, component_id, quantity, ref_des, notes))
        self.conn.commit()
        return self.cursor.lastrowid
    
    def add_sub_assembly(self, parent_product_id, child_product_id, quantity, ref_des="", notes=""):
        """Add a sub-assembly to a product's BOM"""
        self.cursor.execute("""
            INSERT INTO sub_assemblies (parent_product_id, child_product_id, quantity,
                                       reference_designators, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (parent_product_id, child_product_id, quantity, ref_des, notes))
        self.conn.commit()
        return self.cursor.lastrowid
    
    def get_product_bom(self, product_id):
        """Get the BOM for a product"""
        # Get components
        self.cursor.execute("""
            SELECT 
                c.component_id,
                be.entry_id,
                c.mfg_part_number,
                c.manufacturer,
                c.description,
                c.category,
                c.unit_of_measure,
                be.quantity,
                be.reference_designators,
                be.notes,
                (SELECT distributor FROM component_sources 
                 WHERE component_id = c.component_id 
                 ORDER BY unit_cost ASC LIMIT 1) as distributor,
                (SELECT distributor_part_number FROM component_sources 
                 WHERE component_id = c.component_id 
                 ORDER BY unit_cost ASC LIMIT 1) as distributor_part_number,
                (SELECT unit_cost FROM component_sources 
                 WHERE component_id = c.component_id 
                 ORDER BY unit_cost ASC LIMIT 1) as unit_cost
            FROM bom_entries be
            JOIN components c ON be.component_id = c.component_id
            WHERE be.product_id = ?
            ORDER BY be.reference_designators, c.mfg_part_number
        """, (product_id,))
        components = self.cursor.fetchall()
        
        # Get sub-assemblies
        self.cursor.execute("""
            SELECT 
                sa.sub_assembly_id,
                p.product_id,
                p.part_number,
                p.description,
                sa.quantity,
                sa.reference_designators,
                sa.notes
            FROM sub_assemblies sa
            JOIN products p ON sa.child_product_id = p.product_id
            WHERE sa.parent_product_id = ?
            ORDER BY sa.reference_designators, p.part_number
        """, (product_id,))
        sub_assemblies = self.cursor.fetchall()
        
        return components, sub_assemblies
    
    def calculate_bom_cost(self, product_id, quantity=1):
        """Calculate total cost of a BOM recursively"""
        components, sub_assemblies = self.get_product_bom(product_id)
        
        total_cost = 0.0
        breakdown = []
        
        # Add component costs
        for comp in components:
            if comp['unit_cost']:
                comp_total = float(comp['unit_cost']) * float(comp['quantity']) * quantity
                total_cost += comp_total
                breakdown.append({
                    'type': 'component',
                    'item': f"{comp['mfg_part_number']} ({comp['manufacturer']})",
                    'quantity': float(comp['quantity']) * quantity,
                    'uom': comp['unit_of_measure'],
                    'unit_cost': float(comp['unit_cost']),
                    'total': comp_total
                })
        
        # Add sub-assembly costs recursively
        for sub in sub_assemblies:
            sub_cost, sub_breakdown = self.calculate_bom_cost(
                sub['product_id'], 
                float(sub['quantity']) * quantity
            )
            total_cost += sub_cost
            breakdown.append({
                'type': 'assembly',
                'item': f"[ASSEMBLY] {sub['part_number']} - {sub['description']}",
                'quantity': float(sub['quantity']) * quantity,
                'uom': 'EA',
                'unit_cost': sub_cost / (float(sub['quantity']) * quantity) if float(sub['quantity']) * quantity > 0 else 0,
                'total': sub_cost
            })
        
        return total_cost, breakdown
    
    def get_flattened_bom(self, product_id, quantity=1):
        """Get a flattened BOM with all components (no assemblies)"""
        flattened = {}
        
        def flatten_recursive(prod_id, qty):
            components, sub_assemblies = self.get_product_bom(prod_id)
            
            # Add components
            for comp in components:
                key = f"{comp['mfg_part_number']}|{comp['manufacturer']}"
                if key in flattened:
                    flattened[key]['quantity'] += float(comp['quantity']) * qty
                else:
                    flattened[key] = {
                        'part_number': comp['mfg_part_number'],
                        'manufacturer': comp['manufacturer'],
                        'description': comp['description'],
                        'category': comp['category'],
                        'unit_of_measure': comp['unit_of_measure'],
                        'quantity': float(comp['quantity']) * qty,
                        'unit_cost': comp['unit_cost'],
                        'distributor': comp['distributor'],
                        'distributor_pn': comp['distributor_part_number']
                    }
            
            # Recurse into sub-assemblies
            for sub in sub_assemblies:
                flatten_recursive(sub['product_id'], float(sub['quantity']) * qty)
        
        flatten_recursive(product_id, quantity)
        return list(flattened.values())
    
    def get_exploded_bom(self, product_id, quantity=1):
        """Get exploded BOM with hierarchical item numbers"""
        exploded = []
        
        def explode_recursive(prod_id, qty, level, item_number, indent):
            product = self.get_product_by_id(prod_id)
            components, sub_assemblies = self.get_product_bom(prod_id)
            
            # Calculate cost for this assembly
            assembly_cost, _ = self.calculate_bom_cost(prod_id, qty)
            
            # Add this assembly to the list
            exploded.append({
                'item_number': item_number,
                'level': level,
                'indent': indent,
                'item_type': 'assembly',
                'part_number': product['part_number'],
                'manufacturer': '',
                'description': product['description'] or '',
                'unit_of_measure': 'EA',
                'quantity': qty,
                'ref_des': '',
                'unit_cost': '',
                'extended_cost': assembly_cost,
                'notes': product['notes'] or ''
            })
            
            child_index = 1
            
            # Add components
            for comp in components:
                child_item_number = f"{item_number}.{child_index}"
                extended_cost = float(comp['unit_cost']) * float(comp['quantity']) * qty if comp['unit_cost'] else 0
                
                exploded.append({
                    'item_number': child_item_number,
                    'level': level + 1,
                    'indent': indent + '  ',
                    'item_type': 'component',
                    'part_number': comp['mfg_part_number'],
                    'manufacturer': comp['manufacturer'],
                    'description': comp['description'] or '',
                    'unit_of_measure': comp['unit_of_measure'],
                    'quantity': float(comp['quantity']) * qty,
                    'ref_des': comp['reference_designators'] or '',
                    'unit_cost': comp['unit_cost'] if comp['unit_cost'] else '',
                    'extended_cost': extended_cost,
                    'notes': comp['notes'] or ''
                })
                child_index += 1
            
            # Add sub-assemblies recursively
            for sub in sub_assemblies:
                child_item_number = f"{item_number}.{child_index}"
                explode_recursive(
                    sub['product_id'],
                    float(sub['quantity']) * qty,
                    level + 1,
                    child_item_number,
                    indent + '  '
                )
                child_index += 1
        
        # Start explosion
        explode_recursive(product_id, quantity, 0, '1', '')
        return exploded
    
    def delete_bom_entry(self, entry_id):
        """Delete a BOM entry"""
        self.cursor.execute("DELETE FROM bom_entries WHERE entry_id = ?", (entry_id,))
        self.conn.commit()
        return self.cursor.rowcount > 0
    
    def delete_sub_assembly_entry(self, sub_assembly_id):
        """Delete a sub-assembly entry"""
        self.cursor.execute("DELETE FROM sub_assemblies WHERE sub_assembly_id = ?", (sub_assembly_id,))
        self.conn.commit()
        return self.cursor.rowcount > 0
    
    def get_all_components(self):
        """Get all components with their primary source"""
        self.cursor.execute("""
            SELECT 
                c.component_id,
                c.mfg_part_number,
                c.manufacturer,
                c.description,
                c.category,
                c.unit_of_measure,
                c.notes,
                cs.distributor,
                cs.distributor_part_number,
                cs.unit_cost
            FROM components c
            LEFT JOIN component_sources cs ON c.component_id = cs.component_id
            ORDER BY c.mfg_part_number
        """)
        return self.cursor.fetchall()
    
    def get_unused_components(self):
        """Get components not used in any BOM"""
        self.cursor.execute("""
            SELECT 
                c.component_id,
                c.mfg_part_number,
                c.manufacturer,
                c.description,
                c.category,
                c.unit_of_measure,
                cs.distributor,
                cs.unit_cost
            FROM components c
            LEFT JOIN component_sources cs ON c.component_id = cs.component_id
            WHERE c.component_id NOT IN (SELECT DISTINCT component_id FROM bom_entries)
            ORDER BY c.mfg_part_number
        """)
        return self.cursor.fetchall()
    
    def delete_component(self, component_id):
        """Delete a component and its sources"""
        self.cursor.execute("DELETE FROM component_sources WHERE component_id = ?", (component_id,))
        self.cursor.execute("DELETE FROM components WHERE component_id = ?", (component_id,))
        self.conn.commit()
        return self.cursor.rowcount > 0
    
    def update_component(self, component_id, description, category, uom, notes):
        """Update component details"""
        self.cursor.execute("""
            UPDATE components 
            SET description = ?, category = ?, unit_of_measure = ?, notes = ?
            WHERE component_id = ?
        """, (description, category, uom, notes, component_id))
        self.conn.commit()
    
    def update_component_source(self, component_id, distributor, dist_pn, unit_cost):
        """Update or create component source"""
        self.cursor.execute("""
            SELECT source_id FROM component_sources 
            WHERE component_id = ? AND distributor = ?
        """, (component_id, distributor))
        
        existing = self.cursor.fetchone()
        now = datetime.now().isoformat()
        
        if existing:
            self.cursor.execute("""
                UPDATE component_sources 
                SET distributor_part_number = ?, unit_cost = ?, last_updated = ?
                WHERE source_id = ?
            """, (dist_pn, unit_cost, now, existing['source_id']))
        else:
            self.cursor.execute("""
                INSERT INTO component_sources 
                (component_id, distributor, distributor_part_number, unit_cost, last_updated)
                VALUES (?, ?, ?, ?, ?)
            """, (component_id, distributor, dist_pn, unit_cost, now))
        
        self.conn.commit()
    
    def get_component_usage(self, component_id):
        """Get list of assemblies using this component"""
        self.cursor.execute("""
            SELECT DISTINCT p.part_number, p.description
            FROM bom_entries be
            JOIN products p ON be.product_id = p.product_id
            WHERE be.component_id = ?
            ORDER BY p.part_number
        """, (component_id,))
        return self.cursor.fetchall()
    
    def get_assembly_usage(self, product_id):
        """Get list of assemblies using this assembly as a sub-assembly"""
        self.cursor.execute("""
            SELECT p.part_number, p.description
            FROM sub_assemblies sa
            JOIN products p ON sa.parent_product_id = p.product_id
            WHERE sa.child_product_id = ?
            ORDER BY p.part_number
        """, (product_id,))
        return self.cursor.fetchall()
    
    def get_revision_history(self, product_id):
        """Get revision history for a product"""
        self.cursor.execute("""
            SELECT * FROM revision_history
            WHERE product_id = ?
            ORDER BY change_date DESC
        """, (product_id,))
        return self.cursor.fetchall()
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()


class BOMSystemGUI:
    """Main GUI application"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("BOM Management System v2")
        self.root.geometry("1400x900")
        
        self.db = None
        self.current_product_id = None
        self.bom_item_metadata = {}
        
        # Column sort tracking for Assembly Management tab
        self.assy_sort_column = None
        self.assy_sort_reverse = False
        
        # Column sort tracking for Component Management tab
        self.comp_sort_column = None
        self.comp_sort_reverse = False
        
        # CRITICAL FIX: Setup UI first, then load database
        self.setup_ui()
        
        # Load database after UI is ready - use after_idle to ensure window is drawn
        self.root.after_idle(self.load_database_config)
    
    
    def load_database_config(self):
        """Load database configuration from settings file or prompt user"""
        config_file = "bom_config.json"
        
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    db_path = config.get('database_path', 'bom_system_v2.db')
                    
                    # Check if the database file exists
                    if os.path.exists(db_path):
                        self.db = BOMDatabase(db_path)
                        # Verify schema
                        valid, msg = self.db.verify_database_schema()
                        if not valid:
                            messagebox.showerror("Database Schema Error", 
                                f"The database at {db_path} has an invalid schema:\n\n{msg}\n\n"
                                "Please select a valid database or create a new one.")
                            self.prompt_database_selection()
                        else:
                            # Database is valid, refresh UI
                            self.refresh_assembly_lists()
                            self.refresh_assemblies()
                            self.refresh_components(False)
                        return
            except Exception as e:
                messagebox.showwarning("Config Error", 
                    f"Error loading configuration:\n{str(e)}\n\nPlease select database location.")
        
        # No config or database doesn't exist - prompt user
        self.prompt_database_selection()
    
    def prompt_database_selection(self):
        """Show dialog to select or create database"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Database Configuration")
        
        # Center the dialog on screen
        dialog.update_idletasks()
        width = 600
        height = 250
        x = (dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (dialog.winfo_screenheight() // 2) - (height // 2)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        
        dialog.transient(self.root)
        
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
            
            # Check if file exists
            if os.path.exists(db_path):
                # Verify it's a valid database
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
                            except:
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
                        except:
                            pass
                    else:
                        return
            
            # Create or open database
            try:
                self.db = BOMDatabase(db_path)
                
                # Save configuration
                config = {'database_path': db_path}
                with open('bom_config.json', 'w') as f:
                    json.dump(config, f, indent=2)
                
                dialog.destroy()
                
                # Refresh UI after database is loaded
                self.refresh_assembly_lists()
                self.refresh_assemblies()
                self.refresh_components(False)
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to create/open database:\n{str(e)}")
        
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
                  command=self.root.quit).pack(side=tk.LEFT, padx=5)
        
        # Make dialog modal but don't block with wait_window
        # This allows the main window to remain responsive
        dialog.grab_set()
        dialog.focus_set()
        
        # Disable closing with X button - must use Confirm or Exit
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)
    
    def change_database(self):
        """Allow user to change database location"""
        if messagebox.askyesno("Change Database", 
            "Changing the database will close the current database.\n\n"
            "Continue?"):
            if self.db:
                self.db.close()
            self.prompt_database_selection()
            # Refresh all views
            self.refresh_assembly_lists()
            self.refresh_assemblies()
            self.refresh_components(False)

    def setup_ui(self):
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
        tools_menu.add_command(label="Clean Up Duplicates", command=self.cleanup_duplicates)
        
        # Notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Tab 1: BOM Viewer
        self.bom_viewer_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.bom_viewer_tab, text="BOM Viewer")
        self.setup_bom_viewer_tab()
        
        # Tab 2: Cost Analysis
        self.cost_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.cost_tab, text="Cost Analysis")
        self.setup_cost_tab()
        
        # Tab 3: Component Management
        self.component_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.component_tab, text="Component Management")
        self.setup_component_tab()
        
        # Tab 4: Assembly Management
        self.assembly_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.assembly_tab, text="Assembly Management")
        self.setup_assembly_tab()
        
        # Tab 5: Revision History
        self.revision_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.revision_tab, text="Revision History")
        self.setup_revision_tab()
        
        # Refresh assembly lists after all tabs are created
        # Do not call it here as db is not yet initialized
    
    def setup_bom_viewer_tab(self):
        """Setup BOM viewer tab"""
        # Top frame
        top_frame = ttk.Frame(self.bom_viewer_tab)
        top_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(top_frame, text="Assembly:").pack(side=tk.LEFT, padx=5)
        self.bom_assembly_var = tk.StringVar()
        self.bom_assembly_combo = ttk.Combobox(top_frame, textvariable=self.bom_assembly_var,
                                               width=60, state='readonly')
        self.bom_assembly_combo.pack(side=tk.LEFT, padx=5)
        self.bom_assembly_combo.bind('<<ComboboxSelected>>', self.load_bom_viewer)
        
        ttk.Button(top_frame, text="Refresh List", 
                  command=self.refresh_assembly_lists).pack(side=tk.LEFT, padx=5)
        
        # Button frame
        btn_frame = ttk.Frame(self.bom_viewer_tab)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(btn_frame, text="Import BOM", 
                  command=self.import_bom).pack(side=tk.LEFT, padx=5)
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
        
        # Action buttons
        action_frame = ttk.Frame(self.bom_viewer_tab)
        action_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(action_frame, text="Delete Selected Item", 
                  command=self.delete_bom_item).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="Clear Entire BOM", 
                  command=self.clear_entire_bom).pack(side=tk.LEFT, padx=5)
        
        # Cost label
        self.bom_cost_label = ttk.Label(action_frame, text="Total Cost: $0.00", 
                                        font=('TkDefaultFont', 11, 'bold'))
        self.bom_cost_label.pack(side=tk.RIGHT, padx=20)
    
    def setup_cost_tab(self):
        """Setup cost analysis tab"""
        # Top frame
        top_frame = ttk.LabelFrame(self.cost_tab, text="Cost Analysis", padding=10)
        top_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(top_frame, text="Assembly:").grid(row=0, column=0, sticky=tk.W, padx=5)
        self.cost_assembly_var = tk.StringVar()
        self.cost_assembly_combo = ttk.Combobox(top_frame, textvariable=self.cost_assembly_var,
                                                width=50, state='readonly')
        self.cost_assembly_combo.grid(row=0, column=1, padx=5)
        
        ttk.Label(top_frame, text="Quantity:").grid(row=0, column=2, padx=5)
        self.cost_qty_entry = ttk.Entry(top_frame, width=10)
        self.cost_qty_entry.insert(0, "1")
        self.cost_qty_entry.grid(row=0, column=3, padx=5)
        
        ttk.Button(top_frame, text="Calculate Cost", 
                  command=self.calculate_cost).grid(row=0, column=4, padx=5)
        
        # Results frame
        results_frame = ttk.LabelFrame(self.cost_tab, text="Cost Breakdown", padding=10)
        results_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Total cost
        cost_summary = ttk.Frame(results_frame)
        cost_summary.pack(fill=tk.X, pady=5)
        
        ttk.Label(cost_summary, text="Total Cost:", 
                 font=('TkDefaultFont', 14, 'bold')).pack(side=tk.LEFT, padx=5)
        self.total_cost_label = ttk.Label(cost_summary, text="$0.00", 
                                          font=('TkDefaultFont', 14, 'bold'))
        self.total_cost_label.pack(side=tk.LEFT, padx=10)
        
        # Cost tree
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
    
    def setup_component_tab(self):
        """Setup component management tab"""
        # Top frame
        top_frame = ttk.Frame(self.component_tab)
        top_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(top_frame, text="Show All Components", 
                  command=lambda: self.refresh_components(False)).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="Show Unused Only", 
                  command=lambda: self.refresh_components(True)).pack(side=tk.LEFT, padx=5)
        
        # Component tree
        tree_frame = ttk.LabelFrame(self.component_tab, text="Components", padding=10)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        columns = ('Part Number', 'Manufacturer', 'Description', 'UOM', 
                  'Cost', 'Distributor', 'Used In')
        self.comp_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=25)
        
        for col in columns:
            self.comp_tree.heading(col, text=col, 
                                   command=lambda c=col: self.sort_components_by_column(c))
            if col == 'Description':
                self.comp_tree.column(col, width=250)
            else:
                self.comp_tree.column(col, width=120)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.comp_tree.yview)
        self.comp_tree.configure(yscrollcommand=scrollbar.set)
        
        self.comp_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Action buttons
        action_frame = ttk.Frame(self.component_tab)
        action_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(action_frame, text="Edit Selected", 
                  command=self.edit_component).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="Delete Selected", 
                  command=self.delete_component).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="View Where Used", 
                  command=self.view_component_usage).pack(side=tk.LEFT, padx=5)
        
        # self.refresh_components(False)  # Will be called after database loads
    
    def setup_assembly_tab(self):
        """Setup assembly management tab"""
        # Top frame
        top_frame = ttk.Frame(self.assembly_tab)
        top_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(top_frame, text="Search:").pack(side=tk.LEFT, padx=5)
        self.assy_search_entry = ttk.Entry(top_frame, width=30)
        self.assy_search_entry.pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="Search", 
                  command=self.search_assemblies).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="Show All", 
                  command=self.refresh_assemblies).pack(side=tk.LEFT, padx=5)
        
        # Assembly tree
        tree_frame = ttk.LabelFrame(self.assembly_tab, text="Assemblies", padding=10)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        columns = ('Part Number', 'Description', 'Revision', 'Modified', '# Items', 'Cost')
        self.assy_tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=25)
        
        for col in columns:
            self.assy_tree.heading(col, text=col,
                                   command=lambda c=col: self.sort_assemblies_by_column(c))
            if col == 'Description':
                self.assy_tree.column(col, width=300)
            else:
                self.assy_tree.column(col, width=120)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.assy_tree.yview)
        self.assy_tree.configure(yscrollcommand=scrollbar.set)
        
        self.assy_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Action buttons
        action_frame = ttk.Frame(self.assembly_tab)
        action_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(action_frame, text="View BOM", 
                  command=self.view_assembly_bom).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="View Where Used", 
                  command=self.view_assembly_usage).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="View Revision History", 
                  command=self.view_assembly_revisions).pack(side=tk.LEFT, padx=5)
        
        self.refresh_assemblies()
    
    def setup_revision_tab(self):
        """Setup revision history tab"""
        # Top frame
        top_frame = ttk.Frame(self.revision_tab)
        top_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(top_frame, text="Assembly:").pack(side=tk.LEFT, padx=5)
        self.rev_assembly_var = tk.StringVar()
        self.rev_assembly_combo = ttk.Combobox(top_frame, textvariable=self.rev_assembly_var,
                                               width=50, state='readonly')
        self.rev_assembly_combo.pack(side=tk.LEFT, padx=5)
        self.rev_assembly_combo.bind('<<ComboboxSelected>>', self.load_revisions)
        
        ttk.Button(top_frame, text="Refresh", 
                  command=self.load_revisions).pack(side=tk.LEFT, padx=5)
        
        # Revision tree
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
        
        # Action buttons
        action_frame = ttk.Frame(self.revision_tab)
        action_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(action_frame, text="View Revision BOM", 
                  command=self.view_revision_bom).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="Export Revision BOM", 
                  command=self.export_revision_bom).pack(side=tk.LEFT, padx=5)
    
    
    def sort_assemblies_by_column(self, col):
        """Sort assembly tree by clicked column"""
        # Get all items with their values
        items = [(self.assy_tree.set(item, col), item) for item in self.assy_tree.get_children('')]
        
        # Determine if we're reversing the sort
        reverse = False
        if self.assy_sort_column == col:
            reverse = not self.assy_sort_reverse
        
        self.assy_sort_column = col
        self.assy_sort_reverse = reverse
        
        # Sort items
        try:
            # Try numeric sort for # Items and Cost columns
            if col == '# Items':
                items.sort(key=lambda x: int(x[0]) if x[0] and x[0].isdigit() else 0, 
                          reverse=reverse)
            elif col == 'Cost':
                items.sort(key=lambda x: float(x[0].replace('$', '')) if x[0] and x[0] != '' else 0, 
                          reverse=reverse)
            else:
                items.sort(key=lambda x: x[0].lower() if x[0] else '', reverse=reverse)
        except:
            items.sort(key=lambda x: str(x[0]).lower(), reverse=reverse)
        
        # Rearrange items in sorted order
        for index, (val, item) in enumerate(items):
            self.assy_tree.move(item, '', index)
        
        # Update column heading to show sort direction
        for column in self.assy_tree['columns']:
            heading = column
            if column == col:
                heading = f"{column} {'▼' if reverse else '▲'}"
            self.assy_tree.heading(column, text=heading,
                                   command=lambda c=column: self.sort_assemblies_by_column(c))
    
    def sort_components_by_column(self, col):
        """Sort component tree by clicked column"""
        # Get all items with their values
        items = [(self.comp_tree.set(item, col), item) for item in self.comp_tree.get_children('')]
        
        # Determine if we're reversing the sort
        reverse = False
        if self.comp_sort_column == col:
            reverse = not self.comp_sort_reverse
        
        self.comp_sort_column = col
        self.comp_sort_reverse = reverse
        
        # Sort items
        try:
            # Try numeric sort for Cost column
            if col == 'Cost':
                items.sort(key=lambda x: float(x[0].replace('$', '')) if x[0] and x[0] != '' else 0, 
                          reverse=reverse)
            else:
                items.sort(key=lambda x: x[0].lower() if x[0] else '', reverse=reverse)
        except:
            items.sort(key=lambda x: str(x[0]).lower(), reverse=reverse)
        
        # Rearrange items in sorted order
        for index, (val, item) in enumerate(items):
            self.comp_tree.move(item, '', index)
        
        # Update column heading to show sort direction
        for column in self.comp_tree['columns']:
            heading = column
            if column == col:
                heading = f"{column} {'▼' if reverse else '▲'}"
            self.comp_tree.heading(column, text=heading,
                                   command=lambda c=column: self.sort_components_by_column(c))

    def refresh_assembly_lists(self):
        """Refresh all assembly dropdown lists"""
        if self.db is None:
            return  # Database not loaded yet
        
        products = self.db.get_all_products()
        product_list = [f"{p['part_number']} - {p['description']} (Rev {p['revision']})" 
                       for p in products]
        
        self.bom_assembly_combo['values'] = product_list
        self.cost_assembly_combo['values'] = product_list
        self.rev_assembly_combo['values'] = product_list
    
    def import_bom(self):
        """Import BOM from CSV"""
        filename = filedialog.askopenfilename(
            title="Select BOM CSV file",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        
        if not filename:
            return
        
        # Create dialog for assembly selection
        dialog = tk.Toplevel(self.root)
        dialog.title("Import BOM")
        dialog.geometry("600x400")
        dialog.transient(self.root)
        dialog.grab_set()
        
        ttk.Label(dialog, text="Select Assembly for BOM Import:", 
                 font=('TkDefaultFont', 11, 'bold')).pack(pady=10)
        
        # Radio button to choose mode
        mode_var = tk.StringVar(value="existing")
        
        mode_frame = ttk.Frame(dialog)
        mode_frame.pack(pady=10)
        
        ttk.Radiobutton(mode_frame, text="Import to existing assembly", 
                       variable=mode_var, value="existing").pack(anchor=tk.W)
        ttk.Radiobutton(mode_frame, text="Create new assembly", 
                       variable=mode_var, value="new").pack(anchor=tk.W)
        
        # Existing assembly selection
        existing_frame = ttk.LabelFrame(dialog, text="Existing Assembly", padding=10)
        existing_frame.pack(fill=tk.X, padx=20, pady=5)
        
        ttk.Label(existing_frame, text="Assembly:").pack(side=tk.LEFT, padx=5)
        existing_var = tk.StringVar()
        existing_combo = ttk.Combobox(existing_frame, textvariable=existing_var,
                                      width=50, state='readonly')
        
        products = self.db.get_all_products()
        product_list = [f"{p['part_number']} - {p['description']} (Rev {p['revision']})" 
                       for p in products]
        existing_combo['values'] = product_list
        existing_combo.pack(side=tk.LEFT, padx=5)
        
        # New assembly entry
        new_frame = ttk.LabelFrame(dialog, text="New Assembly", padding=10)
        new_frame.pack(fill=tk.X, padx=20, pady=5)
        
        ttk.Label(new_frame, text="Part Number:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        new_pn_entry = ttk.Entry(new_frame, width=30)
        new_pn_entry.grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(new_frame, text="Description:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        new_desc_entry = ttk.Entry(new_frame, width=30)
        new_desc_entry.grid(row=1, column=1, padx=5, pady=2)
        
        ttk.Label(new_frame, text="Revision:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        new_rev_entry = ttk.Entry(new_frame, width=10)
        new_rev_entry.insert(0, "A")
        new_rev_entry.grid(row=2, column=1, sticky=tk.W, padx=5, pady=2)
        
        result = {'part_number': None, 'save_revision': False, 'notes': '', 'is_new': False}
        
        def proceed():
            mode = mode_var.get()
            
            if mode == "existing":
                selected = existing_var.get()
                if not selected:
                    messagebox.showerror("Error", "Please select an assembly")
                    return
                
                part_number = selected.split(' - ')[0]
                product = self.db.get_product(part_number)
                
                if product:
                    # Assembly exists - show replace dialog
                    dialog.destroy()
                    self.show_replace_dialog(part_number, filename, result)
                else:
                    messagebox.showerror("Error", "Selected assembly not found")
                    
            elif mode == "new":
                part_number = new_pn_entry.get().strip()
                description = new_desc_entry.get().strip()
                revision = new_rev_entry.get().strip() or "A"
                
                if not part_number:
                    messagebox.showerror("Error", "Part number is required")
                    return
                
                # Check if it already exists
                existing_product = self.db.get_product(part_number)
                if existing_product:
                    messagebox.showerror("Error", 
                        f"Assembly {part_number} already exists!\n\n"
                        "Use 'Import to existing assembly' option to replace its BOM.")
                    return
                
                # Create new product
                result['part_number'] = part_number
                result['description'] = description
                result['revision'] = revision
                result['is_new'] = True
                dialog.destroy()
                self.process_import(filename, result)
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=20)
        
        ttk.Button(btn_frame, text="Cancel", 
                  command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Import", 
                  command=proceed).pack(side=tk.LEFT, padx=5)
        
        dialog.wait_window()
    
    def show_replace_dialog(self, part_number, filename, result):
        """Show dialog for replacing existing BOM"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Replace Existing BOM")
        dialog.geometry("500x250")
        dialog.transient(self.root)
        dialog.grab_set()
        
        product = self.db.get_product(part_number)
        
        ttk.Label(dialog, text=f"Assembly {part_number} Rev {product['revision']} already exists", 
                 font=('TkDefaultFont', 11, 'bold')).pack(pady=10)
        
        ttk.Label(dialog, text="The current BOM will be deleted and replaced\nwith the imported BOM.").pack(pady=5)
        
        save_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(dialog, text="Save current BOM as revision before replacing", 
                       variable=save_var).pack(pady=10)
        
        ttk.Label(dialog, text="Revision notes (optional):").pack(pady=5)
        notes_entry = ttk.Entry(dialog, width=50)
        notes_entry.pack(pady=5)
        
        def proceed():
            result['part_number'] = part_number
            result['save_revision'] = save_var.get()
            result['notes'] = notes_entry.get().strip()
            dialog.destroy()
            self.process_import(filename, result)
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=20)
        
        ttk.Button(btn_frame, text="Cancel", 
                  command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Replace BOM", 
                  command=proceed).pack(side=tk.LEFT, padx=5)
        
        dialog.wait_window()
    
    def process_import(self, filename, import_info):
        """Process the CSV import"""
        part_number = import_info['part_number']
        if not part_number:
            return
        
        try:
            # Get or create product
            product = self.db.get_product(part_number)
            
            if product:
                product_id = product['product_id']
                
                # Save revision if requested
                if import_info['save_revision']:
                    self.db.save_bom_as_revision(
                        product_id, 
                        product['revision'], 
                        import_info['notes']
                    )
                
                # Clear existing BOM
                self.db.clear_product_bom(product_id)
            else:
                # Create new product
                description = import_info.get('description', '')
                revision = import_info.get('revision', 'A')
                product_id = self.db.add_or_update_product(part_number, description, revision)
            
            # Read and import CSV
            imported_components = 0
            imported_assemblies = 0
            
            with open(filename, 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
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
                            
                            component_id = self.db.add_or_update_component(
                                item_pn, manufacturer, description, category, uom, notes
                            )
                            
                            if distributor:
                                self.db.add_or_update_component_source(
                                    component_id, distributor, dist_pn, unit_cost
                                )
                            
                            self.db.add_bom_entry(product_id, component_id, quantity, ref_des, notes)
                            imported_components += 1
                            
                        elif item_type == 'assembly':
                            # Add sub-assembly
                            child_product = self.db.get_product(item_pn)
                            if not child_product:
                                # Create placeholder assembly
                                child_product_id = self.db.add_or_update_product(
                                    item_pn, 
                                    row.get('description', '').strip()
                                )
                            else:
                                child_product_id = child_product['product_id']
                            
                            self.db.add_sub_assembly(product_id, child_product_id, quantity, ref_des, notes)
                            imported_assemblies += 1
                    
                    except Exception as e:
                        raise Exception(f"Error on row {row_num} ({item_pn if 'item_pn' in locals() else 'unknown'}): {str(e)}")
            
            # NEW: Save initial revision for newly created assemblies
            if import_info.get('is_new', False):
                product = self.db.get_product(part_number)
                self.db.save_bom_as_revision(
                    product_id,
                    product['revision'],
                    "Initial BOM import"
                )
            
            messagebox.showinfo("Import Complete", 
                f"Successfully imported BOM for {part_number}\n\n"
                f"Components: {imported_components}\n"
                f"Sub-assemblies: {imported_assemblies}")
            
            self.refresh_assembly_lists()
            self.refresh_assemblies()
            self.refresh_components(False)
            
            # Load the imported BOM using actual product data
            product = self.db.get_product(part_number)
            if product:
                self.bom_assembly_var.set(
                    f"{product['part_number']} - {product['description']} (Rev {product['revision']})"
                )
                self.load_bom_viewer()
            
        except Exception as e:
            messagebox.showerror("Import Error", f"Error importing BOM:\n{str(e)}")
    
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
        self.bom_item_metadata = {}
        
        # Clear tree
        for item in self.bom_tree.get_children():
            self.bom_tree.delete(item)
        
        # Load BOM
        components, sub_assemblies = self.db.get_product_bom(product['product_id'])
        
        # Add components
        for comp in components:
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
            
            self.bom_item_metadata[item_id] = ('component', comp['entry_id'])
        
        # Add sub-assemblies
        for sub in sub_assemblies:
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
            
            self.bom_item_metadata[item_id] = ('assembly', sub['sub_assembly_id'])
        
        # Configure tag
        self.bom_tree.tag_configure('assembly', background='#e8f4f8')
        
        # Calculate and display cost
        total_cost, _ = self.db.calculate_bom_cost(product['product_id'])
        self.bom_cost_label.config(text=f"Total Cost: ${total_cost:.2f}")
    
    def export_bom(self):
        """Export BOM to CSV (same format as import)"""
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
            
            with open(filename, 'w', newline='', encoding='utf-8') as f:
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
            
            messagebox.showinfo("Success", f"BOM exported to {filename}")
            
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
            
            messagebox.showinfo("Success", f"Flattened BOM exported to {filename}")
            
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
            
            messagebox.showinfo("Success", f"Exploded BOM exported to {filename}")
            
        except Exception as e:
            messagebox.showerror("Export Error", f"Error exporting exploded BOM:\n{str(e)}")
    
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
        
        item_type, db_id = self.bom_item_metadata[item_id]
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
                                   "This cannot be undone!",
                                   icon='warning'):
            return
        
        self.db.clear_product_bom(self.current_product_id)
        messagebox.showinfo("Success", "BOM cleared")
        self.load_bom_viewer()
    
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
        
        # Calculate cost
        total_cost, breakdown = self.db.calculate_bom_cost(product['product_id'], qty)
        
        # Update display
        self.total_cost_label.config(text=f"${total_cost:.2f}")
        
        # Clear tree
        for item in self.cost_tree.get_children():
            self.cost_tree.delete(item)
        
        # Add breakdown
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
    
    def refresh_components(self, unused_only):
        """Refresh component list"""
        if self.db is None:
            return  # Database not loaded yet
        
        for item in self.comp_tree.get_children():
            self.comp_tree.delete(item)
        
        if unused_only:
            components = self.db.get_unused_components()
        else:
            components = self.db.get_all_components()
        
        for comp in components:
            # Get usage count
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
    
    def edit_component(self):
        """Edit selected component"""
        selected = self.comp_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a component")
            return
        
        tags = self.comp_tree.item(selected[0], 'tags')
        component_id = int(tags[0])
        
        # Get component details
        self.db.cursor.execute("""
            SELECT c.*, cs.distributor, cs.distributor_part_number, cs.unit_cost
            FROM components c
            LEFT JOIN component_sources cs ON c.component_id = cs.component_id
            WHERE c.component_id = ?
        """, (component_id,))
        comp = self.db.cursor.fetchone()
        
        # Show edit dialog
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Edit Component: {comp['mfg_part_number']}")
        dialog.geometry("500x350")
        dialog.transient(self.root)
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
                self.db.update_component(
                    component_id,
                    desc_entry.get().strip(),
                    cat_entry.get().strip(),
                    uom_entry.get().strip() or 'EA',
                    notes_entry.get().strip()
                )
                
                cost_str = cost_entry.get().strip()
                if cost_str:
                    self.db.update_component_source(
                        component_id,
                        dist_entry.get().strip(),
                        dpn_entry.get().strip(),
                        float(cost_str)
                    )
                
                messagebox.showinfo("Success", "Component updated")
                dialog.destroy()
                self.refresh_components(False)
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to update component:\n{str(e)}")
        
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Save", command=save).pack(side=tk.LEFT, padx=5)
    
    def delete_component(self):
        """Delete selected component"""
        selected = self.comp_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a component")
            return
        
        tags = self.comp_tree.item(selected[0], 'tags')
        component_id = int(tags[0])
        
        # Check if used
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
        
        tags = self.comp_tree.item(selected[0], 'tags')
        component_id = int(tags[0])
        
        usage = self.db.get_component_usage(component_id)
        
        values = self.comp_tree.item(selected[0], 'values')
        comp_name = f"{values[0]} ({values[1]})"
        
        if not usage:
            messagebox.showinfo("Not Used", f"{comp_name} is not used in any assemblies")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Where Used: {comp_name}")
        dialog.geometry("500x400")
        dialog.transient(self.root)
        
        ttk.Label(dialog, text=f"Assemblies using {comp_name}:",
                 font=('TkDefaultFont', 11, 'bold')).pack(pady=10)
        
        listbox = tk.Listbox(dialog, width=60, height=20)
        listbox.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        
        for assy in usage:
            listbox.insert(tk.END, f"{assy['part_number']} - {assy['description']}")
        
        ttk.Button(dialog, text="Close", command=dialog.destroy).pack(pady=10)
    
    def refresh_assemblies(self):
        """Refresh assembly list"""
        if self.db is None:
            return  # Database not loaded yet
        
        for item in self.assy_tree.get_children():
            self.assy_tree.delete(item)
        
        products = self.db.get_all_products()
        
        for product in products:
            # Get item count
            components, sub_assemblies = self.db.get_product_bom(product['product_id'])
            item_count = len(components) + len(sub_assemblies)
            
            # Get cost
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
        
        tags = self.assy_tree.item(selected[0], 'tags')
        product_id = int(tags[0])
        
        product = self.db.get_product_by_id(product_id)
        
        # Switch to BOM viewer tab and load this assembly
        self.notebook.select(0)  # Select first tab (BOM Viewer)
        self.bom_assembly_var.set(f"{product['part_number']} - {product['description']} (Rev {product['revision']})")
        self.load_bom_viewer()
    
    def view_assembly_usage(self):
        """Show where assembly is used as sub-assembly"""
        selected = self.assy_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select an assembly")
            return
        
        tags = self.assy_tree.item(selected[0], 'tags')
        product_id = int(tags[0])
        
        usage = self.db.get_assembly_usage(product_id)
        
        values = self.assy_tree.item(selected[0], 'values')
        assy_name = values[0]
        
        if not usage:
            messagebox.showinfo("Not Used", f"{assy_name} is not used as a sub-assembly")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Where Used: {assy_name}")
        dialog.geometry("500x400")
        dialog.transient(self.root)
        
        ttk.Label(dialog, text=f"Assemblies containing {assy_name}:",
                 font=('TkDefaultFont', 11, 'bold')).pack(pady=10)
        
        listbox = tk.Listbox(dialog, width=60, height=20)
        listbox.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        
        for parent in usage:
            listbox.insert(tk.END, f"{parent['part_number']} - {parent['description']}")
        
        ttk.Button(dialog, text="Close", command=dialog.destroy).pack(pady=10)
    
    def view_assembly_revisions(self):
        """View revision history for selected assembly"""
        selected = self.assy_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select an assembly")
            return
        
        tags = self.assy_tree.item(selected[0], 'tags')
        product_id = int(tags[0])
        
        product = self.db.get_product_by_id(product_id)
        
        # Switch to revision tab and load this assembly
        self.notebook.select(4)  # Select revision history tab
        self.rev_assembly_var.set(f"{product['part_number']} - {product['description']} (Rev {product['revision']})")
        self.load_revisions()
    
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
        
        tags = self.rev_tree.item(selected[0], 'tags')
        revision_id = int(tags[0])
        
        # Get revision data
        self.db.cursor.execute("SELECT * FROM revision_history WHERE revision_id = ?", (revision_id,))
        revision = self.db.cursor.fetchone()
        
        snapshot = json.loads(revision['bom_snapshot'])
        
        # Show in dialog
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Revision {revision['revision']} BOM")
        dialog.geometry("1000x600")
        dialog.transient(self.root)
        
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
    
    def export_revision_bom(self):
        """Export revision BOM to CSV"""
        selected = self.rev_tree.selection()
        if not selected:
            messagebox.showwarning("No Selection", "Please select a revision")
            return
        
        tags = self.rev_tree.item(selected[0], 'tags')
        revision_id = int(tags[0])
        
        self.db.cursor.execute("SELECT * FROM revision_history WHERE revision_id = ?", (revision_id,))
        revision = self.db.cursor.fetchone()
        
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
            
            messagebox.showinfo("Success", f"Revision BOM exported to {filename}")
            
        except Exception as e:
            messagebox.showerror("Export Error", f"Error exporting revision BOM:\n{str(e)}")
    
    def view_flattened_bom(self):
        """View flattened BOM in a dialog"""
        if not self.current_product_id:
            messagebox.showwarning("No BOM", "Please select an assembly first")
            return
        
        product = self.db.get_product_by_id(self.current_product_id)
        flattened = self.db.get_flattened_bom(self.current_product_id)
        
        # Create dialog
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Flattened BOM: {product['part_number']}")
        dialog.geometry("1200x600")
        dialog.transient(self.root)
        
        ttk.Label(dialog, text=f"Flattened BOM for {product['part_number']} - {product['description']}",
                 font=('TkDefaultFont', 12, 'bold')).pack(pady=10)
        
        ttk.Label(dialog, text="(All components from all sub-assembly levels, quantities summed)",
                 font=('TkDefaultFont', 9, 'italic')).pack(pady=5)
        
        # Bottom frame with total and buttons - pack BEFORE tree so it anchors to bottom
        bottom_frame = ttk.Frame(dialog)
        bottom_frame.pack(fill=tk.X, padx=10, pady=10, side=tk.BOTTOM)
        
        self._flat_total_label = ttk.Label(bottom_frame, text="Total Cost: $0.00",
                 font=('TkDefaultFont', 12, 'bold'))
        self._flat_total_label.pack(side=tk.LEFT)
        
        ttk.Button(bottom_frame, text="Close", 
                  command=dialog.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="Export to CSV", 
                  command=lambda: (dialog.destroy(), self.export_flattened_bom())).pack(side=tk.RIGHT, padx=5)
        
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
        self._flat_total_label.config(text=f"Total Cost: ${total_cost:.2f}")
    
    def view_exploded_bom(self):
        """View exploded BOM in a dialog"""
        if not self.current_product_id:
            messagebox.showwarning("No BOM", "Please select an assembly first")
            return
        
        product = self.db.get_product_by_id(self.current_product_id)
        exploded = self.db.get_exploded_bom(self.current_product_id)
        
        # Create dialog
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Exploded BOM: {product['part_number']}")
        dialog.geometry("1400x600")
        dialog.transient(self.root)
        
        ttk.Label(dialog, text=f"Exploded BOM for {product['part_number']} - {product['description']}",
                 font=('TkDefaultFont', 12, 'bold')).pack(pady=10)
        
        ttk.Label(dialog, text="(Hierarchical view with item numbers - indented by level)",
                 font=('TkDefaultFont', 9, 'italic')).pack(pady=5)
        
        # Bottom frame with buttons - pack BEFORE tree so it anchors to bottom
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill=tk.X, padx=10, pady=10, side=tk.BOTTOM)
        
        ttk.Button(btn_frame, text="Close", 
                  command=dialog.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Export to CSV", 
                  command=lambda: (dialog.destroy(), self.export_exploded_bom())).pack(side=tk.RIGHT, padx=5)
        
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
    
    def cleanup_duplicates(self):
        """Clean up duplicate component sources"""
        if not messagebox.askyesno("Clean Up Duplicates",
                                   "This will remove duplicate component sources.\n\n"
                                   "Continue?"):
            return
        
        # Find and remove duplicates
        self.db.cursor.execute("""
            SELECT component_id, distributor, COUNT(*) as count
            FROM component_sources
            GROUP BY component_id, distributor
            HAVING count > 1
        """)
        duplicates = self.db.cursor.fetchall()
        
        removed_count = 0
        for dup in duplicates:
            self.db.cursor.execute("""
                SELECT source_id FROM component_sources
                WHERE component_id = ? AND distributor = ?
                ORDER BY last_updated DESC
            """, (dup['component_id'], dup['distributor']))
            
            all_sources = self.db.cursor.fetchall()
            # Keep first (most recent), delete others
            for source in all_sources[1:]:
                self.db.cursor.execute("DELETE FROM component_sources WHERE source_id = ?",
                                      (source['source_id'],))
                removed_count += 1
        
        self.db.conn.commit()
        
        if removed_count > 0:
            messagebox.showinfo("Cleanup Complete", f"Removed {removed_count} duplicate sources")
            self.refresh_components(False)
        else:
            messagebox.showinfo("No Duplicates", "No duplicate sources found")


def main():
    root = tk.Tk()
    app = BOMSystemGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
