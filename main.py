#!/usr/bin/env python3
"""
BOM Management System v2 - Entry Point
"""

import tkinter as tk
from bom_gui import BOMSystemGUI


def main():
    root = tk.Tk()
    app = BOMSystemGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
