# BOM Management System v2

A comprehensive desktop application for managing hierarchical bills of materials (BOMs) with cost analysis, revision tracking, and multi-level assembly support.

![Version](https://img.shields.io/badge/version-2.1-blue)
![Python](https://img.shields.io/badge/python-3.10+-green)
![License](https://img.shields.io/badge/license-MIT-orange)

## Overview

BOM Management System v2 is a powerful tool for engineers, product managers, and manufacturing teams to create, manage, and analyze complex product structures. It supports unlimited nesting of sub-assemblies, automatic cost rollup, and comprehensive revision control.

## Key Features

### 📋 BOM Management
- **Hierarchical Structure** - Unlimited sub-assembly nesting
- **Component Library** - Centralized component database with distributor information
- **Import/Export** - CSV-based data exchange
- **Visual BOM Viewer** - Tree-based display with component and assembly differentiation

### 💰 Cost Analysis
- **Automatic Cost Rollup** - Recursive calculation through all assembly levels
- **Multi-Quantity Costing** - Calculate costs for production runs of any size
- **Distributor Pricing** - Track multiple sources and automatically use lowest cost
- **Cost Breakdown** - Detailed view of where costs come from

### 📊 BOM Views
- **Standard BOM** - Direct components and sub-assemblies for a product
- **Flattened BOM** - All components summed across all levels (no assemblies)
- **Exploded BOM** - Hierarchical view with item numbers and indentation

### 🔄 Revision Control
- **Automatic Revision Tracking** - Initial BOM saved on import
- **Snapshot History** - Complete BOM state saved for each revision
- **Revision Comparison** - View and export any historical revision
- **Change Notes** - Document why changes were made

### 🗂️ Data Management
- **Database Configuration** - Choose database location and filename
- **Schema Validation** - Automatic verification of database structure
- **Sortable Columns** - Click column headers to sort data
- **Search Functions** - Find assemblies and components quickly
- **Where-Used Analysis** - See which assemblies use specific components

### 🎯 User Interface
- **Tab-Based Interface** - Organized workflow with 5 main tabs
- **Intuitive Design** - Clean, professional layout
- **Real-Time Updates** - Costs and totals update automatically
- **Error Handling** - Clear messages guide you through issues

## Installation

### Requirements

- Python 3.10 or higher
- tkinter (usually included with Python)
- SQLite3 (included with Python)

### Quick Start

1. **Download the application:**
   ```bash
   git clone https://github.com/bobamosfet/bomDbV2.git
   cd bomDbV2
   ```

2. **Run the application:**
   ```bash
   python3 bom_system_v2.py
   ```

3. **First-time setup:**
   - The Database Configuration dialog will appear
   - Choose to create a new database or select an existing one
   - Click "Confirm" to proceed

### Dependencies

All required libraries are part of Python's standard library:
- `tkinter` - GUI framework
- `sqlite3` - Database engine
- `csv` - CSV file handling
- `json` - Configuration and data serialization
- `datetime` - Timestamp management

## User Guide

### Getting Started

#### 1. Database Configuration

On first launch, you'll see the Database Configuration dialog:

- **Create New Database:**
  1. Click "Create New..."
  2. Choose a location and filename
  3. Click "Confirm"

- **Use Existing Database:**
  1. Click "Browse Existing..."
  2. Select your `.db` file
  3. Click "Confirm"

The system saves your choice in `bom_config.json` so you won't need to select it again.

#### 2. Importing Your First BOM

1. Go to the **BOM Viewer** tab
2. Click **Import BOM**
3. Select your CSV file
4. Choose **Create new assembly**
5. Enter:
   - Part Number (required)
   - Description
   - Revision (default: A)
6. Click **Import**

**CSV Format Required:**
```csv
item_part_number,item_type,manufacturer,description,category,unit_of_measure,quantity,ref_des,distributor,distributor_pn,unit_cost,notes
R1234,component,Yageo,10k Resistor,Resistors,EA,10,R1-R10,Digi-Key,311-10.0KHRCT-ND,0.10,1% tolerance
C5678,component,Samsung,10uF Cap,Capacitors,EA,5,C1-C5,Mouser,187-CL21A106KAYNNNE,0.25,X7R ceramic
```

**Column Definitions:**
- `item_part_number` - Manufacturer part number or assembly part number
- `item_type` - Either "component" or "assembly"
- `manufacturer` - Component manufacturer (blank for assemblies)
- `description` - Part description
- `category` - Component category (Resistors, Capacitors, ICs, etc.)
- `unit_of_measure` - EA, FT, M, etc. (default: EA)
- `quantity` - Quantity required
- `ref_des` - Reference designators (R1-R10, C1, etc.)
- `distributor` - Where to buy it
- `distributor_pn` - Distributor's part number
- `unit_cost` - Price per unit
- `notes` - Any additional information

### Main Tabs

#### BOM Viewer Tab

**Purpose:** View and manage the BOM for a specific assembly

**Features:**
- Select assembly from dropdown
- View all components and sub-assemblies
- See total cost at bottom
- Delete individual items
- Clear entire BOM
- Export to various formats

**Actions:**
- **Import BOM** - Load BOM from CSV file
- **Export BOM** - Save in import-compatible format
- **Export Flattened BOM** - All components summed (no assemblies)
- **Export Exploded BOM** - Hierarchical with item numbers
- **View Flattened BOM** - Preview flattened view
- **View Exploded BOM** - Preview exploded view
- **Delete Selected Item** - Remove one component/assembly
- **Clear Entire BOM** - Delete all items (saves revision first)

#### Cost Analysis Tab

**Purpose:** Calculate production costs for different quantities

**How to Use:**
1. Select an assembly
2. Enter quantity (e.g., 100 for production run)
3. Click **Calculate Cost**

**Results Show:**
- Total cost for the quantity
- Per-item breakdown:
  - Component costs (quantity × unit price)
  - Sub-assembly costs (calculated recursively)

**Color Coding:**
- White background = Component
- Light blue background = Sub-assembly

#### Component Management Tab

**Purpose:** Manage your component library

**Features:**
- View all components or only unused ones
- Sort by any column (click header)
- Edit component details
- Delete unused components
- See where components are used

**Buttons:**
- **Show All Components** - Display entire library
- **Show Unused Only** - Components not in any BOM
- **Edit Selected** - Modify component details and pricing
- **Delete Selected** - Remove component (only if unused)
- **View Where Used** - List assemblies using this component

**Sortable Columns:**
Click any column header to sort:
- Part Number (alphanumeric)
- Manufacturer (alphabetic)
- Description (alphabetic)
- UOM (alphabetic)
- Cost (numeric)
- Distributor (alphabetic)
- Used In (alphanumeric)

Click again to reverse sort order. Arrow indicators (▲▼) show current sort.

#### Assembly Management Tab

**Purpose:** Browse all assemblies in the database

**Features:**
- Search assemblies by part number or description
- Sort by any column
- View BOM for any assembly
- Check where assemblies are used as sub-assemblies
- View revision history

**Buttons:**
- **Search** - Find assemblies matching search term
- **Show All** - Display all assemblies
- **View BOM** - Jump to BOM Viewer for selected assembly
- **View Where Used** - See parent assemblies
- **View Revision History** - Jump to Revision History tab

**Columns:**
- Part Number - Assembly identifier
- Description - What it is
- Revision - Current revision letter
- Modified - Last modification date
- # Items - Count of components + sub-assemblies
- Cost - Total calculated cost

**Sortable:** Click any column to sort, click again to reverse.

#### Revision History Tab

**Purpose:** Track BOM changes over time

**Features:**
- View all saved revisions for an assembly
- See revision notes and dates
- View historical BOM snapshots
- Export any revision to CSV

**Automatic Revision Saves:**
- Initial import creates first revision ("Initial BOM import")
- Replacing existing BOM (optional save before replacement)
- Manual revision saves (future feature)

**Buttons:**
- **View Revision BOM** - See complete BOM for selected revision
- **Export Revision BOM** - Save revision to CSV file

**Columns:**
- Revision - Revision identifier (A, B, C, etc.)
- Date - When revision was created
- Notes - Why the change was made

### Advanced Features

#### Multi-Level Assemblies

You can nest assemblies to any depth:

```
Main Product (Assembly)
├── Power Supply (Sub-assembly)
│   ├── Transformer
│   ├── Rectifier Circuit (Sub-sub-assembly)
│   │   ├── Diodes (4x)
│   │   └── Capacitors (2x)
│   └── Regulator IC
├── Control Board (Sub-assembly)
│   └── Components...
└── Enclosure (Sub-assembly)
```

**Cost Rollup:**
- Costs automatically calculate through all levels
- Each assembly knows its total cost
- Top-level shows complete product cost

#### Flattened vs Exploded BOMs

**Flattened BOM:**
- Shows ONLY components (no assemblies)
- Quantities are summed across all levels
- Best for: Purchasing, inventory
- Example:
  ```
  Resistor 10k: 25 EA  (from 3 different boards)
  Capacitor 1uF: 15 EA (from 2 different boards)
  ```

**Exploded BOM:**
- Shows complete hierarchy
- Item numbers reflect structure (1, 1.1, 1.1.1, etc.)
- Quantities at each level
- Best for: Manufacturing, assembly instructions
- Example:
  ```
  1     Main Assembly
  1.1     Power Board
  1.1.1     Resistor 10k (qty: 10)
  1.1.2     Capacitor 1uF (qty: 5)
  1.2     Control Board
  1.2.1     Resistor 10k (qty: 15)
  ```

#### Where-Used Analysis

Find where components or assemblies are used:

**Component Where-Used:**
1. Go to Component Management tab
2. Select a component
3. Click **View Where Used**
4. See all assemblies containing this component

**Assembly Where-Used:**
1. Go to Assembly Management tab
2. Select an assembly
3. Click **View Where Used**
4. See all assemblies using this as a sub-assembly

This helps with:
- Impact analysis for component changes
- Finding all affected assemblies
- Understanding product relationships

#### Database Management

**Change Database:**
1. File → Change Database...
2. Select different database file
3. All tabs refresh with new data

**Database Location:**
- Stored in `bom_config.json`
- Can be anywhere on your system
- Share database files with team members
- Keep backups of important databases

**Schema Validation:**
- Automatic on database load
- Checks for all required tables
- Verifies column structure
- Clear error messages if invalid

## File Menu

### Change Database...
Switch to a different database file without restarting the application.

### Exit
Close the application.

## Tools Menu

### Clean Up Duplicates
Removes duplicate distributor entries for components (keeps most recent).

## Keyboard Shortcuts

- **Ctrl+Q** - Quit application (on some systems)
- **Tab** - Navigate between tabs
- **Enter** - Confirm dialogs
- **Esc** - Cancel dialogs

## Tips & Best Practices

### Component Naming
- Use manufacturer part numbers for accuracy
- Include key specs in description
- Use consistent category names

### Assembly Organization
- Use logical part numbering system
- Keep descriptions clear and concise
- Update revisions when making changes

### Cost Management
- Keep distributor pricing up to date
- Enter costs for all components
- Review cost rollups regularly

### Revision Control
- Always add notes when creating revisions
- Save revisions before major changes
- Export revisions for documentation

### Database Backups
- Regularly backup your `.db` file
- Keep copies before major imports
- Test imports with small files first

## Troubleshooting

### "Database schema is invalid"
**Problem:** Database file is corrupted or from incompatible version

**Solutions:**
1. Create a new database
2. Restore from backup
3. Export data from old database and import to new one

### Import fails with "Error on row X"
**Problem:** CSV file has formatting issues

**Solutions:**
1. Check that row X has all required columns
2. Verify quantity is a number
3. Ensure item_type is "component" or "assembly"
4. Check for special characters in data

### "Component is used in X assemblies"
**Problem:** Trying to delete a component that's in use

**Solution:**
1. Go to BOM Viewer for each assembly listed
2. Remove the component from each BOM
3. Then delete the component

### Columns won't sort
**Problem:** Click not registering on header

**Solution:**
1. Click directly on the column header text
2. Make sure you're in Component or Assembly Management tab
3. Try clicking a different column first

### Cost shows $0.00
**Problem:** No pricing information entered

**Solution:**
1. Go to Component Management tab
2. Edit each component
3. Add distributor and unit cost
4. Cost will automatically recalculate

## Data Export Formats

### Standard BOM Export
- Format: CSV
- Contents: Same format as import
- Use: Share BOM, backup data, import elsewhere

### Flattened BOM Export
- Format: CSV
- Contents: All components with summed quantities
- Use: Send to purchasing, create buy lists

### Exploded BOM Export
- Format: CSV
- Contents: Hierarchical structure with item numbers
- Use: Manufacturing documentation, assembly instructions

## Architecture

### Database Schema

**Components Table:**
- Stores component master data
- Unique constraint on (part_number, manufacturer)

**Component Sources Table:**
- Multiple distributors per component
- Tracks pricing and part numbers
- System uses lowest cost automatically

**Products Table:**
- Assembly definitions
- Revision tracking
- Created/modified timestamps

**BOM Entries Table:**
- Links components to assemblies
- Quantities and reference designators

**Sub-Assemblies Table:**
- Links assemblies to parent assemblies
- Enables multi-level nesting

**Revision History Table:**
- JSON snapshots of complete BOMs
- Change notes and timestamps

### Technology Stack

- **Language:** Python 3.10+
- **GUI:** tkinter (Tk/Tcl)
- **Database:** SQLite3
- **Data Format:** CSV for import/export

## File Structure

```
bom-system-v2/
├── bom_system_v2_updated2.py    # Main application
├── bom_config.json              # Database configuration (auto-created)
├── bom_system_v2.db             # Default database (auto-created)
├── README.md                    # This file
└── sample_bom.csv               # Example import file
```

## Version History

### Version 2.1 (Current)
- ✅ Database configuration with path selection
- ✅ Automatic schema validation
- ✅ Sortable columns in Assembly and Component tabs
- ✅ Initial revision auto-saved on import
- ✅ Fixed startup freeze issues
- ✅ Improved error handling

### Version 2.0
- Initial release
- Core BOM management
- Cost analysis
- Import/export functionality
- Basic revision tracking

## Support & Contributing

### Getting Help
- Check this README for common issues
- Review error messages carefully
- Export and backup data before major changes

### Reporting Bugs
Please include:
- Python version
- Operating system
- Steps to reproduce
- Error messages
- Sample CSV file (if import issue)

### Feature Requests
We welcome suggestions for:
- Additional export formats
- New analysis features
- UI improvements
- Integration capabilities

## License

MIT License - Feel free to use, modify, and distribute.

## Acknowledgments

Built with Python's excellent standard library and tkinter framework.

---

**Need help?** Check the troubleshooting section or review the user guide above.

**Want to contribute?** Fork the repository and submit a pull request!

**Found this useful?** Star the repository and share with your team!