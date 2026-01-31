# BOM Management System v2 - Test Suite

This test suite will thoroughly exercise all features of the BOM system including hierarchical assemblies, cost calculation, revision tracking, and various export formats.

## Test Scenario: Building a Complete Electronic Control Unit

You'll build a realistic product hierarchy:
```
MAIN-CONTROLLER-001 (Top-level assembly)
├── PCB-POWER-001 (Power supply board)
├── PCB-DISPLAY-001 (Display board)
├── CABLE-PWR-001 (Power cables) - 2 instances
├── Enclosure and hardware
```

## Prerequisites

1. **Start fresh** - Delete `bom_system_v2.db` if it exists (for clean test)
2. **Run the application:**
   ```bash
   python3 bom_system_v2.py
   ```
3. **Have test CSV files ready:**
   - `test_pcb_power.csv`
   - `test_pcb_display.csv`
   - `test_cable_assy.csv`
   - `test_main_enclosure.csv`
   - `test_pcb_power_rev_b.csv`

---

## Test 1: Import First Sub-Assembly (Power PCB)

**Purpose:** Test basic CSV import and component creation

**Steps:**
1. Click **"Import BOM"** button
2. Select `test_pcb_power.csv`
3. Choose **"Create new assembly"** radio button
4. Enter:
   - Part Number: `PCB-POWER-001`
   - Description: `Power Supply PCB Assembly`
   - Revision: `A`
5. Click **"Import"**

**Expected Results:**
- Success message: "Successfully imported BOM for PCB-POWER-001"
- Shows: 18 components imported
- BOM Viewer shows all components with quantities and reference designators
- Total cost displayed at bottom (~$17.53)

**Verify:**
- Go to **Component Management** tab → Click "Show All Components"
- Should see 18 unique components
- Check costs are populated (resistors $0.10, ICs ~$0.95, etc.)
- Go to **Assembly Management** tab
- Should see PCB-POWER-001 with Rev A

---

## Test 2: Import Second Sub-Assembly (Display PCB)

**Purpose:** Test reusing existing components

**Steps:**
1. Click **"Import BOM"** button
2. Select `test_pcb_display.csv`
3. Choose **"Create new assembly"**
4. Enter:
   - Part Number: `PCB-DISPLAY-001`
   - Description: `Display PCB Assembly`
   - Revision: `A`
5. Click **"Import"**

**Expected Results:**
- Success message: 11 components imported
- Some components already exist (RES-10K-0805, CAP-0.1UF-0805, LED-RED-0805, LED-GREEN-0805)
- New components created (74HC595, LCD display, buttons)

**Verify:**
- BOM Viewer: Select PCB-DISPLAY-001
- Should show 11 component entries
- Total cost ~$13.81
- Component Management: Total unique components should be ~25 (not 29, because some are shared)

---

## Test 3: Import Third Sub-Assembly (Cable)

**Purpose:** Test different unit of measure (feet for wire)

**Steps:**
1. Import `test_cable_assy.csv`
2. Create new assembly: `CABLE-PWR-001`
3. Description: `Power Cable Assembly`

**Expected Results:**
- 9 components imported
- Wire components use "FT" (feet) as unit of measure
- Heat shrink uses "IN" (inches)
- Cost calculation works with mixed units

**Verify:**
- BOM shows wire quantities in feet (6, 6, 3)
- Heat shrink shows 8 inches
- Unit costs per foot/inch calculated correctly
- Total cost ~$6.67 per cable

---

## Test 4: Import Top-Level Assembly with Sub-Assemblies

**Purpose:** Test hierarchical BOM with assembly nesting

**Steps:**
1. Import `test_main_enclosure.csv`
2. Create new assembly: `MAIN-CONTROLLER-001`
3. Description: `Complete Controller Unit`

**Expected Results:**
- Success message showing components AND sub-assemblies imported
- BOM Viewer shows:
  - 3 sub-assemblies (PCB-POWER-001, PCB-DISPLAY-001, CABLE-PWR-001 x2)
  - Direct components (enclosure, fan, hardware, labels)
- Sub-assemblies highlighted in blue
- Some show "Calculated" for cost (because they reference other assemblies)

**Verify:**
- BOM Viewer: Count items
  - Should see 4 sub-assembly entries (CABLE-PWR-001 appears twice)
  - Should see ~11 direct component entries
- Total cost should be sum of all sub-assemblies + direct components

---

## Test 5: Cost Analysis

**Purpose:** Test recursive cost calculation through all levels

**Steps:**
1. Go to **Cost Analysis** tab
2. Select assembly: `MAIN-CONTROLLER-001`
3. Quantity: `1`
4. Click **"Calculate Cost"**

**Expected Results:**
- Total cost displayed (approximately $77-80)
- Breakdown shows:
  - [ASSEMBLY] PCB-POWER-001 with calculated cost
  - [ASSEMBLY] PCB-DISPLAY-001 with calculated cost
  - [ASSEMBLY] CABLE-PWR-001 (appears twice) with calculated costs
  - All direct components with individual costs
- Sub-assemblies highlighted in blue

**Test Different Quantities:**
1. Change quantity to `10`
2. Click **"Calculate Cost"**
3. Total should be exactly 10x the single unit cost
4. All line items should show 10x quantities

---

## Test 6: View Flattened BOM

**Purpose:** Test component consolidation across all levels

**Steps:**
1. Go to **BOM Viewer** tab
2. Select `MAIN-CONTROLLER-001`
3. Click **"View Flattened BOM"**

**Expected Results:**
- Dialog opens showing ONLY components (no assemblies)
- Components that appear in multiple sub-assemblies have quantities summed
- Example: RES-10K-0805 appears in PCB-POWER-001 (8) and PCB-DISPLAY-001 (4) = Total 12
- Shows extended costs (quantity × unit cost)
- Total cost at bottom matches Cost Analysis total

**Verify:**
- No sub-assemblies in list
- All unique components listed once
- Quantities are totals across all levels
- Can export to CSV from this dialog

---

## Test 7: View Exploded BOM

**Purpose:** Test hierarchical view with item numbers

**Steps:**
1. Still on `MAIN-CONTROLLER-001`
2. Click **"View Exploded BOM"**

**Expected Results:**
- Dialog shows hierarchical structure with item numbers:
  - 1 (MAIN-CONTROLLER-001 - top level)
  - 1.1 (PCB-POWER-001)
  - 1.1.1 (first component in PCB-POWER-001)
  - 1.1.2 (second component)
  - ...
  - 1.2 (PCB-DISPLAY-001)
  - 1.2.1 (first component in PCB-DISPLAY-001)
  - ...
  - 1.3 (CABLE-PWR-001 - first instance)
  - 1.4 (CABLE-PWR-001 - second instance)
  - 1.5 (ENCLOSURE-ALU)
  - ...

**Verify:**
- Item numbers follow pattern (1, 1.1, 1.2, 1.1.1, 1.1.2, etc.)
- Part numbers indented by level (spaces at start)
- Assemblies highlighted in blue
- Extended costs shown for all items
- Level numbers correct (0, 1, 2)

---

## Test 8: Component Management

**Purpose:** Test editing component details and pricing

**Steps:**
1. Go to **Component Management** tab
2. Find `RES-10K-0805` in list
3. Click to select it
4. Click **"Edit Selected"**
5. Change:
   - Unit Cost: `0.12` (was 0.10)
   - Notes: `Price increase from supplier`
6. Click **"Save"**

**Expected Results:**
- Component updated successfully
- Cost shown in list updates to $0.12
- Click "View Where Used" → should show PCB-POWER-001 and PCB-DISPLAY-001

**Verify:**
1. Go to Cost Analysis tab
2. Recalculate cost for MAIN-CONTROLLER-001
3. Total cost should increase (12 resistors × $0.02 increase = $0.24 higher)

---

## Test 9: BOM Revision and Re-Import

**Purpose:** Test revision history and price preservation

**Steps:**
1. Go to **BOM Viewer** tab
2. Select `PCB-POWER-001`
3. Note current total cost
4. Click **"Import BOM"**
5. Select `test_pcb_power_rev_b.csv`
6. Choose **"Import to existing assembly"**
7. Select `PCB-POWER-001 - Power Supply PCB Assembly (Rev A)`
8. Click **"Import"**

**Expected Results:**
- Dialog asks: "Replace BOM for PCB-POWER-001 Rev A?"
- Checkbox checked: "Save current BOM as revision before replacing"
- Enter revision notes: `Added R15, R16, and U4. Updated quantities.`
- Click **"Replace BOM"**

**After Import:**
- Success message
- BOM shows new quantities (10 resistors instead of 8, added components)
- Some prices updated (RES-10K-0805 now $0.09)
- RES-100-0805 price UNCHANGED (was blank in CSV - preserved old price)
- Total cost different due to quantity and price changes

---

## Test 10: View Revision History

**Purpose:** Test revision tracking

**Steps:**
1. Go to **Revision History** tab
2. Select `PCB-POWER-001` from dropdown
3. Click refresh or wait for load

**Expected Results:**
- Shows at least one revision (Rev A - saved before replacement)
- Shows date and notes: "Added R15, R16, and U4. Updated quantities."

**Actions:**
1. Select the revision
2. Click **"View Revision BOM"**
   - Should show OLD BOM (18 components, old quantities)
3. Click **"Export Revision BOM"**
   - Saves CSV of historical BOM

**Verify:**
- Exported CSV has 18 rows (old BOM)
- Current BOM has 19 rows (new BOM with U4 added)

---

## Test 11: Export Tests

**Purpose:** Test all three export formats

**Steps for Each Assembly (do for PCB-POWER-001):**

1. **Standard Export:**
   - BOM Viewer → Select PCB-POWER-001
   - Click "Export BOM"
   - Save as `exported_standard.csv`
   - Open in Excel/text editor
   - Verify: Same format as import CSV, can re-import

2. **Flattened Export:**
   - Click "Export Flattened BOM"
   - Save as `exported_flattened.csv`
   - Verify: Only components (no assemblies), totaled quantities

3. **Exploded Export:**
   - Click "Export Exploded BOM"
   - Save as `exported_exploded.csv`
   - Verify: Has item_number column (1, 1.1, etc.), indented part numbers

---

## Test 12: Where Used Tracking

**Purpose:** Test dependency tracking

**Steps:**
1. **Component Where Used:**
   - Component Management tab
   - Select `ENCLOSURE-ALU`
   - Click "View Where Used"
   - Should show: MAIN-CONTROLLER-001

2. **Assembly Where Used:**
   - Assembly Management tab
   - Select `PCB-POWER-001`
   - Click "View Where Used"
   - Should show: MAIN-CONTROLLER-001 (parent assembly)

3. **Multi-Use Component:**
   - Select `RES-10K-0805`
   - Click "View Where Used"
   - Should show: PCB-POWER-001 AND PCB-DISPLAY-001

---

## Test 13: Delete Operations

**Purpose:** Test deletion with safety checks

**Steps:**
1. **Try to delete used component:**
   - Component Management → Select `RES-10K-0805`
   - Click "Delete Selected"
   - Should ERROR: "Component is used in 2 assemblies"

2. **Delete unused component:**
   - Click "Show Unused Only"
   - If any shown, select one and delete
   - Should succeed

3. **Delete BOM item:**
   - BOM Viewer → Select MAIN-CONTROLLER-001
   - Select one hardware item (like WASHER-M3)
   - Click "Delete Selected Item"
   - Confirm
   - Item removed from BOM
   - Cost recalculates

4. **Clear entire BOM:**
   - Select a test assembly
   - Click "Clear Entire BOM"
   - Confirms with warning
   - All items removed

---

## Test 14: Assembly Search

**Purpose:** Test search functionality

**Steps:**
1. Go to **Assembly Management** tab
2. Enter in search box: `PCB`
3. Click "Search"
4. Should show only PCB-POWER-001 and PCB-DISPLAY-001
5. Click "Show All" → all assemblies return

---

## Test 15: Build Quantity Scenarios

**Purpose:** Test realistic production scenarios

**Steps:**
1. Cost Analysis tab
2. Assembly: `MAIN-CONTROLLER-001`

**Scenario A - Prototype (1 unit):**
- Quantity: 1
- Calculate cost
- Note total (for comparison)

**Scenario B - Small batch (10 units):**
- Quantity: 10
- Calculate cost
- Verify: Exactly 10x prototype cost
- Note wire quantities in flattened BOM (feet needed)

**Scenario C - Production run (100 units):**
- Quantity: 100
- Calculate cost
- Check flattened BOM
- Calculate how many wire spools needed (sold in 100ft)

---

## Expected Overall Results Summary

After completing all tests, you should have:

**Database contains:**
- 4 assemblies (3 sub-assemblies + 1 top-level)
- ~40 unique components
- Multiple BOM entries linking them
- At least 1 revision history entry

**Features verified:**
✅ CSV import (new and existing assemblies)
✅ Hierarchical BOMs (assemblies containing assemblies)
✅ Cost calculation (recursive through all levels)
✅ Component reuse (same part in multiple assemblies)
✅ Unit of measure handling (EA, FT, IN)
✅ Price preservation on re-import (blank values)
✅ Revision history (save and view old BOMs)
✅ Three export formats (Standard, Flattened, Exploded)
✅ Component editing (pricing updates)
✅ Where used tracking (components and assemblies)
✅ Delete operations (with safety checks)
✅ Search functionality
✅ Multiple quantities in cost analysis

---

## Common Issues to Check

**If import fails:**
- Check CSV has no extra commas in blank fields
- Verify column headers exactly match format
- Check for special characters in part numbers

**If costs don't calculate:**
- Verify components have unit_cost in component_sources table
- Check sub-assemblies have their BOMs imported

**If quantities seem wrong:**
- Flattened BOM sums across all levels (this is correct)
- Exploded BOM shows at each level (this is correct)

---

## Clean Up After Testing

To start fresh:
1. Close application
2. Delete `bom_system_v2.db`
3. Restart application
4. Database recreates with clean schema

---

## Success Criteria

✅ All 15 tests complete without errors
✅ Cost calculations accurate at all levels
✅ Exports produce correct formatted files
✅ Revision history captures changes
✅ Where-used tracking works both ways
✅ UI is responsive and intuitive

**Congratulations! Your BOM system is fully tested and ready for production use!** 🎉
