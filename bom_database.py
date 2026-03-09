#!/usr/bin/env python3
"""
BOM Database Layer
Handles all SQLite database operations for the BOM Management System.
No GUI code — raises exceptions on errors for callers to handle.
"""

import sqlite3
from datetime import datetime
import json


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
        # Enforce foreign key constraints (off by default in SQLite)
        self.cursor.execute("PRAGMA foreign_keys = ON")

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

    # ----------------------------------------------------------------
    # Component CRUD
    # ----------------------------------------------------------------

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

    def get_all_components(self):
        """Get all components with their cheapest source"""
        self.cursor.execute("""
            SELECT 
                c.component_id,
                c.mfg_part_number,
                c.manufacturer,
                c.description,
                c.category,
                c.unit_of_measure,
                c.notes,
                (SELECT distributor FROM component_sources 
                 WHERE component_id = c.component_id 
                 ORDER BY unit_cost ASC LIMIT 1) as distributor,
                (SELECT distributor_part_number FROM component_sources 
                 WHERE component_id = c.component_id 
                 ORDER BY unit_cost ASC LIMIT 1) as distributor_part_number,
                (SELECT unit_cost FROM component_sources 
                 WHERE component_id = c.component_id 
                 ORDER BY unit_cost ASC LIMIT 1) as unit_cost
            FROM components c
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
                (SELECT distributor FROM component_sources 
                 WHERE component_id = c.component_id 
                 ORDER BY unit_cost ASC LIMIT 1) as distributor,
                (SELECT unit_cost FROM component_sources 
                 WHERE component_id = c.component_id 
                 ORDER BY unit_cost ASC LIMIT 1) as unit_cost
            FROM components c
            WHERE c.component_id NOT IN (SELECT DISTINCT component_id FROM bom_entries)
            ORDER BY c.mfg_part_number
        """)
        return self.cursor.fetchall()

    def get_component_details(self, component_id):
        """Get full component details including source info"""
        self.cursor.execute("""
            SELECT c.*, cs.distributor, cs.distributor_part_number, cs.unit_cost
            FROM components c
            LEFT JOIN component_sources cs ON c.component_id = cs.component_id
            WHERE c.component_id = ?
        """, (component_id,))
        return self.cursor.fetchone()

    def delete_component(self, component_id):
        """Delete a component and its sources"""
        self.cursor.execute("DELETE FROM component_sources WHERE component_id = ?", (component_id,))
        self.cursor.execute("DELETE FROM components WHERE component_id = ?", (component_id,))
        self.conn.commit()
        return self.cursor.rowcount > 0

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

    def search_components(self, search_term):
        """Search components by part number, manufacturer, or description.

        Returns up to 50 matching components with their primary source info.
        """
        like_term = f"%{search_term}%"
        self.cursor.execute("""
            SELECT 
                c.component_id, c.mfg_part_number, c.manufacturer,
                c.description, c.category, c.unit_of_measure,
                cs.unit_cost, cs.distributor
            FROM components c
            LEFT JOIN component_sources cs ON c.component_id = cs.component_id
            WHERE c.mfg_part_number LIKE ?
               OR c.manufacturer LIKE ?
               OR c.description LIKE ?
            ORDER BY c.mfg_part_number
            LIMIT 50
        """, (like_term, like_term, like_term))
        return self.cursor.fetchall()

    def get_primary_source(self, component_id):
        """Get the primary (cheapest) source for a component, or None."""
        self.cursor.execute("""
            SELECT * FROM component_sources
            WHERE component_id = ?
            ORDER BY unit_cost ASC
            LIMIT 1
        """, (component_id,))
        return self.cursor.fetchone()

    # ----------------------------------------------------------------
    # Product / Assembly CRUD
    # ----------------------------------------------------------------

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

    # ----------------------------------------------------------------
    # BOM entries
    # ----------------------------------------------------------------

    def add_bom_entry(self, product_id, component_id, quantity, ref_des="", notes=""):
        """Add a component to a product's BOM"""
        self.cursor.execute("""
            INSERT INTO bom_entries (product_id, component_id, quantity, reference_designators, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (product_id, component_id, quantity, ref_des, notes))
        self.conn.commit()
        return self.cursor.lastrowid

    def add_sub_assembly(self, parent_product_id, child_product_id, quantity, ref_des="", notes=""):
        """Add a sub-assembly to a product's BOM.

        Raises Exception if adding this relationship would create a circular
        dependency (e.g. A contains B contains A).
        """
        # Guard against circular references
        if self._would_create_cycle(parent_product_id, child_product_id):
            parent = self.get_product_by_id(parent_product_id)
            child = self.get_product_by_id(child_product_id)
            parent_pn = parent['part_number'] if parent else str(parent_product_id)
            child_pn = child['part_number'] if child else str(child_product_id)
            raise Exception(
                f"Circular dependency detected: adding {child_pn} as a sub-assembly "
                f"of {parent_pn} would create a cycle.\n\n"
                f"A sub-assembly cannot directly or indirectly contain its own parent."
            )

        self.cursor.execute("""
            INSERT INTO sub_assemblies (parent_product_id, child_product_id, quantity,
                                        reference_designators, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (parent_product_id, child_product_id, quantity, ref_des, notes))
        self.conn.commit()
        return self.cursor.lastrowid

    def _would_create_cycle(self, parent_product_id, child_product_id):
        """Check if adding child as a sub-assembly of parent would create a cycle.

        A cycle exists if child_product_id already contains parent_product_id
        somewhere in its descendant tree (i.e. parent is reachable from child),
        or if parent == child.
        """
        if parent_product_id == child_product_id:
            return True

        # Walk the descendant tree of child_product_id using BFS.
        # If we ever find parent_product_id, adding this link would create a cycle.
        visited = set()
        queue = [child_product_id]

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            self.cursor.execute("""
                SELECT child_product_id FROM sub_assemblies
                WHERE parent_product_id = ?
            """, (current,))
            for row in self.cursor.fetchall():
                child_id = row['child_product_id']
                if child_id == parent_product_id:
                    return True
                queue.append(child_id)

        return False

    def get_product_bom(self, product_id):
        """Get the BOM for a product.

        Returns (components, sub_assemblies) where each is a list of Row objects.
        """
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

    def clear_product_bom(self, product_id):
        """Delete all BOM entries for a product"""
        self.cursor.execute("DELETE FROM bom_entries WHERE product_id = ?", (product_id,))
        self.cursor.execute("DELETE FROM sub_assemblies WHERE parent_product_id = ?", (product_id,))
        self.conn.commit()

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

    def update_bom_entry(self, entry_id, quantity, ref_des, notes):
        """Update quantity, reference designators, and notes on a BOM entry."""
        self.cursor.execute("""
            UPDATE bom_entries
            SET quantity = ?, reference_designators = ?, notes = ?
            WHERE entry_id = ?
        """, (quantity, ref_des, notes, entry_id))
        self.conn.commit()

    def update_sub_assembly_entry(self, sub_assembly_id, quantity, ref_des, notes):
        """Update quantity, reference designators, and notes on a sub-assembly entry."""
        self.cursor.execute("""
            UPDATE sub_assemblies
            SET quantity = ?, reference_designators = ?, notes = ?
            WHERE sub_assembly_id = ?
        """, (quantity, ref_des, notes, sub_assembly_id))
        self.conn.commit()

    def get_bom_entry(self, entry_id):
        """Get a single BOM entry with component info."""
        self.cursor.execute("""
            SELECT be.*, c.mfg_part_number, c.manufacturer
            FROM bom_entries be
            JOIN components c ON be.component_id = c.component_id
            WHERE be.entry_id = ?
        """, (entry_id,))
        return self.cursor.fetchone()

    def get_sub_assembly_entry(self, sub_assembly_id):
        """Get a single sub-assembly entry with product info."""
        self.cursor.execute("""
            SELECT sa.*, p.part_number, p.description
            FROM sub_assemblies sa
            JOIN products p ON sa.child_product_id = p.product_id
            WHERE sa.sub_assembly_id = ?
        """, (sub_assembly_id,))
        return self.cursor.fetchone()

    # ----------------------------------------------------------------
    # Cost calculation
    # ----------------------------------------------------------------

    def calculate_bom_cost(self, product_id, quantity=1):
        """Calculate total cost of a BOM recursively"""
        components, sub_assemblies = self.get_product_bom(product_id)

        total_cost = 0.0
        breakdown = []

        # Add component costs
        for comp in components:
            unit_cost = float(comp['unit_cost']) if comp['unit_cost'] is not None else 0.0
            comp_total = unit_cost * float(comp['quantity']) * quantity
            total_cost += comp_total
            breakdown.append({
                'type': 'component',
                'item': f"{comp['mfg_part_number']} ({comp['manufacturer']})",
                'quantity': float(comp['quantity']) * quantity,
                'uom': comp['unit_of_measure'],
                'unit_cost': unit_cost,
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

    # ----------------------------------------------------------------
    # Flattened / Exploded BOM
    # ----------------------------------------------------------------

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

    # ----------------------------------------------------------------
    # Revision history
    # ----------------------------------------------------------------

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

    def get_revision_history(self, product_id):
        """Get revision history for a product"""
        self.cursor.execute("""
            SELECT * FROM revision_history
            WHERE product_id = ?
            ORDER BY change_date DESC
        """, (product_id,))
        return self.cursor.fetchall()

    def get_revision(self, revision_id):
        """Get a single revision by ID"""
        self.cursor.execute("SELECT * FROM revision_history WHERE revision_id = ?", (revision_id,))
        return self.cursor.fetchone()

    # ----------------------------------------------------------------
    # Maintenance
    # ----------------------------------------------------------------

    def find_duplicate_sources(self):
        """Find duplicate component sources. Returns list of (component_id, distributor, count)."""
        self.cursor.execute("""
            SELECT component_id, distributor, COUNT(*) as count
            FROM component_sources
            GROUP BY component_id, distributor
            HAVING count > 1
        """)
        return self.cursor.fetchall()

    def get_sources_for_component_distributor(self, component_id, distributor):
        """Get all source records for a component+distributor pair, newest first."""
        self.cursor.execute("""
            SELECT source_id FROM component_sources
            WHERE component_id = ? AND distributor = ?
            ORDER BY last_updated DESC
        """, (component_id, distributor))
        return self.cursor.fetchall()

    def delete_source(self, source_id):
        """Delete a single component source record."""
        self.cursor.execute("DELETE FROM component_sources WHERE source_id = ?", (source_id,))
        self.conn.commit()

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
