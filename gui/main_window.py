# gui/main_window.py
import datetime
from pathlib import Path
import json

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon

from gui.calendar_widget import CalendarWidget
from logic.rules import RuleEngine
from logic.calendar_engine import CalendarEngine

import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        # --- Window title / size / icon ---
        self.setWindowTitle("Home Office Planner v2.0.0 – by Florin Săulescu © 2026")
        self.resize(1200, 750)

        # Use the resource_path helper so it works in dev and in PyInstaller EXE
        from main import resource_path  # or: from utils import resource_path
        self.setWindowIcon(QIcon(resource_path("icon.ico")))

        # Default start date
        self.year = 2026
        self.month = 3

        # Data file for plans (all years & months)
        self.plans_path = Path("data/homeoffice_plans.json")
        self.plans_path.parent.mkdir(parents=True, exist_ok=True)

        # Engines
        self.calendar_engine = CalendarEngine(self.year, self.month)
        self.rule_engine = RuleEngine(self.calendar_engine)

        # =========================
        # LAYOUT
        # =========================
        main_layout = QVBoxLayout()

        # --- Application Title (visible banner) ---
        title = QLabel("Home Office Planner v2.0.0")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: bold; padding: 10px;")
        main_layout.addWidget(title)

        # =====================================================
        # 1) TOP TOOLBAR – Save / Load / Reset / Export / Instructions
        #    (Instructions placed right after Export to PDF)
        # =====================================================
        topbar = QHBoxLayout()

        self.save_as_btn = QPushButton("💾 Save ALL (Choose location)")
        self.load_btn = QPushButton("📂 Load Saved File")
        self.reset_btn = QPushButton("🗑 Reset ALL Data")
        self.export_excel_btn = QPushButton("📊 Export to Excel")
        self.export_pdf_btn = QPushButton("📄 Export to PDF")
        self.instructions_btn = QPushButton("📘 Instructions")

        # Compact button styling
        for b in (
            self.save_as_btn, self.load_btn, self.reset_btn,
            self.export_excel_btn, self.export_pdf_btn, self.instructions_btn
        ):
            b.setMinimumHeight(28)
            b.setStyleSheet("padding: 4px 10px;")

        # Assemble topbar
        topbar.addWidget(self.save_as_btn)
        topbar.addWidget(self.load_btn)
        topbar.addWidget(self.reset_btn)

        topbar.addSpacing(12)
        topbar.addWidget(self.export_excel_btn)
        topbar.addWidget(self.export_pdf_btn)
        topbar.addWidget(self.instructions_btn)

        # Keep slight stretch to push a little to the left if window is wide
        topbar.addStretch(1)
        main_layout.addLayout(topbar)

        # =====================================================
        # 2) SECOND ROW – Navigation + Year (Year next to Next Month)
        # =====================================================
        nav = QHBoxLayout()
        self.prev_btn = QPushButton("◀ Previous Month")
        self.next_btn = QPushButton("Next Month ▶")

        self.year_select = QComboBox()
        for y in range(2020, 2040):
            self.year_select.addItem(str(y))
        self.year_select.setCurrentText(str(self.year))

        nav.addWidget(self.prev_btn)
        nav.addWidget(self.next_btn)

        # Year immediately next to Next Month
        nav.addSpacing(12)
        nav.addWidget(QLabel("Year:"))
        nav.addWidget(self.year_select)

        nav.addStretch(1)
        main_layout.addLayout(nav)

        # --- Main content: Calendar + Summary ---
        content = QHBoxLayout()

        self.calendar = CalendarWidget(self.calendar_engine, self.rule_engine)
        content.addWidget(self.calendar, 3)

        self.summary = QLabel()
        self.summary.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.summary.setStyleSheet("font-size: 14px; padding: 10px;")
        content.addWidget(self.summary, 1)

        main_layout.addLayout(content)

        # (Optional) Legend under content
        legend = QLabel(
            "Legend: "
            "<span style='background:#ffd6d6;color:red;padding:2px 6px;'> Legal holiday </span> "
            "&nbsp; "
            "<span style='background:#ffe5b4;color:red;padding:2px 6px;'> My planned holiday </span> "
            "&nbsp; "
            "<span style='background:#b5ffb5;padding:2px 6px;'> Selected HO </span> "
            "&nbsp; "
            "<span style='background:#a7d8ff;padding:2px 6px;'> HO linked to weekend </span> "
            "&nbsp; "
            "<span style='background:#faf0f0;padding:2px 6px;'> Weekend </span>"
        )
        legend.setStyleSheet("font-size: 12px;")
        main_layout.addWidget(legend)

        self.setLayout(main_layout)

        # =========================
        # SIGNALS
        # =========================
        # Calendar interactions
        self.calendar.selection_changed.connect(self.on_selection_changed)
        if hasattr(self.calendar, "holidays_changed"):
            self.calendar.holidays_changed.connect(self.on_holidays_changed)

        # Custom navigation
        self.prev_btn.clicked.connect(self.load_previous_month)
        self.next_btn.clicked.connect(self.load_next_month)
        self.year_select.currentTextChanged.connect(self.change_year)

        # Built-in QCalendarWidget header arrows (◀ ▶)
        self.calendar.currentPageChanged.connect(self.on_calendar_page_changed)

        # Topbar actions
        self.export_excel_btn.clicked.connect(self.export_excel)
        self.export_pdf_btn.clicked.connect(self.export_pdf)
        self.save_as_btn.clicked.connect(self.save_all_work_as)
        self.load_btn.clicked.connect(self.load_all_work)
        self.reset_btn.clicked.connect(self.reset_all_data)
        self.instructions_btn.clicked.connect(self.show_instructions_popup)

        # Load any previously saved plan for the initial month
        self._apply_saved_plan()

        # Initial summary
        self.update_summary()

    # =========================
    # Instructions popup
    # =========================
    def show_instructions_popup(self):
        QMessageBox.information(
            self,
            "Home Office Planner – Instructions",
            (
                "📘 Home Office Planner – Instructions\n\n"
                "• Click a calendar day to add or remove Home Office (HO).\n"
                "• Right‑click a calendar day to add or remove a planned holiday.\n"
                "• Autosave is active when changing the month or closing the application.\n"
                "• Rules enforced automatically:\n"
                "    – Weekend‑linked count only Friday & Monday\n"
                "    – Weekend enclosed only if Fri HO + next Mon HO (and both are workdays)\n"
                "• Legal holidays show their names; personal holidays show “Holiday”.\n"
            )
        )

    # ================================================================
    # Built-in QCalendarWidget header arrows
    # ================================================================
    def on_calendar_page_changed(self, year: int, month: int):
        self.year = year
        self.month = month

        # Keep combobox synced
        if self.year_select.currentText() != str(self.year):
            self.year_select.setCurrentText(str(self.year))

        self.reload_calendar()

    # ================================================================
    # Custom navigation
    # ================================================================
    def load_previous_month(self):
        self.month -= 1
        if self.month == 0:
            self.month = 12
            self.year -= 1
            if self.year_select.currentText() != str(self.year):
                self.year_select.setCurrentText(str(self.year))
        self.reload_calendar()

    def load_next_month(self):
        self.month += 1
        if self.month == 13:
            self.month = 1
            self.year += 1
            if self.year_select.currentText() != str(self.year):
                self.year_select.setCurrentText(str(self.year))
        self.reload_calendar()

    def change_year(self, year_str: str):
        if not year_str.isdigit():
            return
        new_year = int(year_str)
        if new_year != self.year:
            self.year = new_year
            self.reload_calendar()

    # ================================================================
    # Reload engines + calendar sync
    # ================================================================
    def reload_calendar(self):
        self.calendar_engine = CalendarEngine(self.year, self.month)
        self.rule_engine = RuleEngine(self.calendar_engine)

        self.calendar.reload_engines(self.calendar_engine, self.rule_engine)
        self.calendar.setCurrentPage(self.year, self.month)

        # Apply saved plan for the newly loaded month
        self._apply_saved_plan()

        self.update_summary()

    # ================================================================
    # Selection / Holidays change handlers (auto-save)
    # ================================================================
    def on_selection_changed(self):
        self.update_summary()
        # Autosave current month’s plan
        self.save_current_plan(autosave=True)

    def on_holidays_changed(self):
        self.update_summary()
        self.save_current_plan(autosave=True)

    # ================================================================
    # Summary update
    # ================================================================
    def update_summary(self):
        # Recompute current values directly from the RuleEngine
        workdays = len(self.calendar_engine.workdays_of_month())
        max_allowed = self.rule_engine.max_allowed_ho()
        total_ho = len(self.rule_engine.selected_days)
        linked = len(self.rule_engine.weekend_link_days())
        sandwich = self.rule_engine.violates_sandwich_rule()

        # Colors
        RED = "#d32f2f"    # strong red
        GREEN = "#2e7d32"  # strong green

        # Status coloring
        status_invalid = (total_ho > max_allowed) or (linked > 4) or sandwich
        status_text = "INVALID" if status_invalid else "VALID"
        status_color = RED if status_invalid else GREEN

        # Sandwich coloring
        sandwich_text = "YES" if sandwich else "NO"
        sandwich_color = RED if sandwich else GREEN

        # Header
        month_name = self.calendar_engine.month_name()
        header = f"<h2>{month_name} {self.year}</h2>"

        # Body with HTML formatting
        body = (
            f"Working days: {workdays}<br>"
            f"Max allowed HO days (50/50): {max_allowed}<br>"
            f"Selected HO days: {total_ho}<br><br>"
            f"HO days linked to weekend (Fri/Mon only): {linked} / 4 allowed<br>"
            f"Weekend enclosed (Fri→Mon): "
            f"<span style='color:{sandwich_color}; font-weight:600;'>{sandwich_text}</span><br><br>"
            f"Status: "
            f"<span style='color:{status_color}; font-weight:700;'>{status_text}</span>"
        )

        # Update the summary
        self.summary.setText(header + body)

    # ================================================================
    # Save / Load Home-Office plans (all months)
    # ================================================================
    def _read_plans_file(self) -> dict:
        if self.plans_path.exists():
            try:
                return json.loads(self.plans_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def _write_plans_file(self, data: dict):
        self.plans_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _month_key(self, month: int) -> str:
        # Store months as "01", "02", ..., "12"
        return f"{month:02d}"

    def _apply_saved_plan(self):
        """Load saved HO days for current (year, month) and paint the calendar."""
        data = self._read_plans_file()
        y = str(self.year)
        m = self._month_key(self.month)

        saved_list = data.get(y, {}).get(m, [])
        saved_days = set()
        for s in saved_list:
            try:
                d = datetime.date.fromisoformat(s)
                # Apply only dates that are in this month (defensive)
                if d.year == self.year and d.month == self.month:
                    saved_days.add(d)
            except Exception:
                pass

        # Push into the calendar widget and rule engine
        self.calendar.selected_days = saved_days
        self.rule_engine.set_selected_days(saved_days)
        if hasattr(self.rule_engine, "invalidate_cache"):
            self.rule_engine.invalidate_cache()
        self.calendar.recolor()

    def save_current_plan(self, autosave: bool = False):
        """
        Save current month’s selected HO days to data/homeoffice_plans.json.
        This file keeps plans for ALL months and years, so your entire work stays together.
        """
        data = self._read_plans_file()
        y = str(self.year)
        m = self._month_key(self.month)

        # Collect the selected dates as ISO strings
        days = sorted(list(self.rule_engine.selected_days))
        iso_days = [d.strftime("%Y-%m-%d") for d in days]

        # Upsert into the dict
        if y not in data:
            data[y] = {}
        data[y][m] = iso_days

        # Write back
        self._write_plans_file(data)

        if not autosave:
            self.summary.setText(self.summary.text() + f"<br><b>Saved:</b> {self.plans_path.as_posix()}")

    # ================================================================
    # Export to Excel
    # ================================================================
    def export_excel(self):
        # Build default name like HomeOffice_2026_03.xlsx
        default_name = f"HomeOffice_{self.year}_{self.month:02d}.xlsx"

        # Ask user where to save
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export to Excel",
            default_name,
            "Excel Workbook (*.xlsx)"
        )
        if not filename:
            return  # user cancelled

        # Ensure .xlsx extension
        if not filename.lower().endswith(".xlsx"):
            filename = f"{filename}.xlsx"

        # Prepare data
        days = sorted(list(self.rule_engine.selected_days))
        df = pd.DataFrame({"Home Office Days": [d.strftime('%Y-%m-%d') for d in days]})

        # Save
        df.to_excel(filename, index=False, engine="openpyxl")

        # Show location in the summary
        self.summary.setText(
            self.summary.text() + f"<br><b>Saved Excel to:</b> {filename}"
        )

    # ================================================================
    # Export to PDF
    # ================================================================
    def export_pdf(self):
        # Build default name like HomeOffice_2026_03.pdf
        default_name = f"HomeOffice_{self.year}_{self.month:02d}.pdf"

        # Ask user where to save
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export to PDF",
            default_name,
            "PDF Files (*.pdf)"
        )
        if not filename:
            return  # user cancelled

        # Ensure .pdf extension
        if not filename.lower().endswith(".pdf"):
            filename = f"{filename}.pdf"

        # Create PDF
        c = canvas.Canvas(filename, pagesize=A4)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, 800, f"Home Office Plan – {self.month:02d}/{self.year}")

        c.setFont("Helvetica", 12)
        y = 760
        for d in sorted(self.rule_engine.selected_days):
            c.drawString(50, y, f"- {d.strftime('%Y-%m-%d')}")
            y -= 20
            if y < 50:
                c.showPage()
                c.setFont("Helvetica", 12)
                y = 800

        # Footer copyright (optional)
        c.setFont("Helvetica-Oblique", 10)
        c.setFillColorRGB(0.4, 0.4, 0.4)
        c.drawString(50, 40, "© 2026 Florin Săulescu – All rights reserved")

        c.save()

        # Show location in the summary
        self.summary.setText(
            self.summary.text() + f"<br><b>Saved PDF to:</b> {filename}"
        )

    # ================================================================
    # Save / Load ALL data
    # ================================================================
    def save_all_work_as(self):
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Work As",
            "homeoffice_all_plans.json",
            "JSON Files (*.json)"
        )

        if not filename:
            return  # user cancelled

        data = self._read_plans_file()

        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            self.summary.setText(
                self.summary.text()
                + f"<br><b>Saved all work to:</b> {filename}"
            )

        except Exception as e:
            self.summary.setText(
                self.summary.text()
                + f"<br><b style='color:red;'>Save error:</b> {e}"
            )

    def load_all_work(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Load Work",
            "",
            "JSON Files (*.json)"
        )

        if not filename:
            return

        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Save loaded data into app storage
            self._write_plans_file(data)

            # Reload HO for the current month
            self._apply_saved_plan()
            self.update_summary()

            self.summary.setText(
                self.summary.text()
                + f"<br><b>Loaded saved work from:</b> {filename}"
            )

        except Exception as e:
            self.summary.setText(
                self.summary.text()
                + f"<br><b style='color:red;'>Load error:</b> {e}"
            )

    def reset_all_data(self):
        """
        Delete ALL saved data: HO plans + personal holidays.
        Reset calendar display to empty.
        """
        # Delete HO plans file
        if self.plans_path.exists():
            self.plans_path.unlink()

        # Delete personal holidays file
        personal_file = Path("data/personal_holidays.json")
        if personal_file.exists():
            personal_file.unlink()

        # Reset engines
        self.calendar_engine = CalendarEngine(self.year, self.month)
        self.rule_engine = RuleEngine(self.calendar_engine)
        self.calendar.reload_engines(self.calendar_engine, self.rule_engine)

        # Clear selections
        self.calendar.selected_days = set()
        self.rule_engine.set_selected_days(set())
        self.calendar.recolor()

        self.summary.setText(
            "<b>All data has been reset.</b><br>Calendar is now empty."
        )