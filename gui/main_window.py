# gui/main_window.py
import datetime
from pathlib import Path
import json


from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QFileDialog, QMessageBox, QSpinBox, QToolTip, QSplitter, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QFont

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
        self.resize(1200, 800)

        # Use the resource_path helper so it works in dev and in PyInstaller EXE
        from main import resource_path
        self.setWindowIcon(QIcon(resource_path("icon.ico")))

        # Default start date
        self.year = 2026
        self.month = 3

        # Data files
        self.plans_path = Path("data/homeoffice_plans.json")
        self.plans_path.parent.mkdir(parents=True, exist_ok=True)
        self.allowance_path = Path("data/holiday_allowance.json")

        # Plans cache (for HO lookup across months in calendar grey cells)
        self._plans_cache = None

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
        # 1) TOP TOOLBAR – Save / Load / Reset / Export / Instructions / What's New
        # =====================================================
        topbar = QHBoxLayout()
        self.save_as_btn = QPushButton("💾 Save ALL (Choose location)")
        self.load_btn = QPushButton("📂 Load Saved File")
        self.reset_btn = QPushButton("🗑 Reset ALL Data")
        self.export_excel_btn = QPushButton("📊 Export to Excel")
        self.export_pdf_btn = QPushButton("📄 Export to PDF")
        self.instructions_btn = QPushButton("📘 Instructions")
        self.whats_new_btn = QPushButton("📢 What’s New?")

        # Compact button styling
        for b in (
            self.save_as_btn, self.load_btn, self.reset_btn,
            self.export_excel_btn, self.export_pdf_btn, self.instructions_btn,
            self.whats_new_btn
        ):
            b.setMinimumHeight(28)
            b.setStyleSheet("padding: 4px 10px;")

        # Tooltips
        self.save_as_btn.setToolTip("Save ALL months and years to a single JSON file at a location you choose.")
        self.load_btn.setToolTip("Load a previously saved JSON file (all months/years).")
        self.reset_btn.setToolTip("Delete all saved data: HO days, personal holidays, and yearly allowance. This cannot be undone.")
        self.export_excel_btn.setToolTip("Export this month’s selected Home‑Office (HO) days to Excel (.xlsx).")
        self.export_pdf_btn.setToolTip("Export this month’s selected Home‑Office (HO) days to PDF.")
        self.instructions_btn.setToolTip("Open step‑by‑step instructions and rules.")
        self.whats_new_btn.setToolTip("See what’s new and improved in v2.0.0.")

        # Assemble topbar
        topbar.addWidget(self.save_as_btn)
        topbar.addWidget(self.load_btn)
        topbar.addWidget(self.reset_btn)
        topbar.addSpacing(12)
        topbar.addWidget(self.export_excel_btn)
        topbar.addWidget(self.export_pdf_btn)
        topbar.addWidget(self.instructions_btn)
        topbar.addWidget(self.whats_new_btn)   # NEW
        topbar.addStretch(1)
        main_layout.addLayout(topbar)

        # =====================================================
        # 2) SECOND ROW – Navigation + Today  (Year/Allowance live in right panel)
        # =====================================================
        nav = QHBoxLayout()
        self.prev_btn = QPushButton("◀ Previous Month")
        self.today_btn = QPushButton("Today")
        self.next_btn = QPushButton("Next Month ▶")

        nav.addWidget(self.prev_btn)
        nav.addWidget(self.today_btn)
        nav.addWidget(self.next_btn)
        nav.addStretch(1)
        main_layout.addLayout(nav)

        # Tooltips for nav
        self.prev_btn.setToolTip("Go to the previous month.")
        self.today_btn.setToolTip("Jump to the current day.")
        self.next_btn.setToolTip("Go to the next month.")

        # =====================================================
        # 3) MAIN CONTENT – QSplitter: Left (header + calendar) | Right (controls + summary)
        # =====================================================

        # --- Left: a container with a small "Calendar week" header + the calendar widget
        left_container = QWidget()
        left_vbox = QVBoxLayout(left_container)
        left_vbox.setContentsMargins(0, 0, 0, 0)
        left_vbox.setSpacing(4)

        cw_label = QLabel("")
        cw_label.setStyleSheet("color:#666; font-size:12px; padding-left:6px;")
        cw_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        # Calendar widget (the CalendarWidget should call ISO week numbers in its __init__)
        self.calendar = CalendarWidget(self.calendar_engine, self.rule_engine)

        left_vbox.addWidget(cw_label, 0)
        left_vbox.addWidget(self.calendar, 1)

        # --- Right: a QWidget container with a vertical layout (controls bar + summary)
        right_container = QWidget()
        right_panel = QVBoxLayout(right_container)
        right_panel.setContentsMargins(0, 0, 0, 0)
        right_panel.setSpacing(6)

        # ---- Controls bar (Year + Total holidays + Available) ----
        controls_bar = QHBoxLayout()
        controls_bar.setContentsMargins(0, 0, 0, 0)
        controls_bar.setSpacing(8)

        year_label = QLabel("Year:")
        self.year_select = QComboBox()
        for y in range(2020, 2040):
            self.year_select.addItem(str(y))
        self.year_select.setCurrentText(str(self.year))
        controls_bar.addWidget(year_label)
        controls_bar.addWidget(self.year_select)

        controls_bar.addSpacing(10)
        controls_bar.addWidget(QLabel("Total holidays:"))
        self.allowance_spin = QSpinBox()
        self.allowance_spin.setRange(0, 100)
        self.allowance_spin.setSingleStep(1)
        self.allowance_spin.setButtonSymbols(self.allowance_spin.ButtonSymbols.PlusMinus)
        controls_bar.addWidget(self.allowance_spin)

        controls_bar.addSpacing(10)
        self.available_label = QLabel("Available: 0")
        self.available_label.setStyleSheet("font-weight: 700;")
        controls_bar.addWidget(self.available_label)

        controls_bar.addStretch(1)

        # Tooltips for controls in right panel
        self.year_select.setToolTip("Pick the working year. Allowance and ‘Available’ are tracked per year.")
        self.allowance_spin.setToolTip(
            "Set your total annual holiday allowance. "
            "Only planned holidays on workdays (Mon–Fri, not legal holidays) are counted as ‘used’."
        )
        self.available_label.setToolTip(
            "Available = Total annual allowance − planned holidays (workdays only) for the selected year. "
            "Turns green if ≥ 0 and red if negative."
        )
        QToolTip.setFont(QFont("Segoe UI", 10))

        right_panel.addLayout(controls_bar)

        # ---- Summary (body) under controls bar ----
        self.summary = QLabel()
        self.summary.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.summary.setStyleSheet("font-size: 14px; padding: 10px;")
        self.summary.setWordWrap(True)
        right_panel.addWidget(self.summary, 1)

        # --- Splitter setup
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_container)     # left side now: header + calendar
        splitter.addWidget(right_container)    # right side: controls + summary

        # Cap right panel so it never wastes too much space; tweak as you like
        right_container.setMaximumWidth(420)   # e.g., 360–480 is a good range

        # Initial sizes: calendar ~70%, right panel ~30%
        total_w = self.width() if self.width() > 0 else 1200
        splitter.setSizes([int(total_w * 0.7), int(total_w * 0.3)])

        # Add the splitter to the main layout (it will expand with window)
        main_layout.addWidget(splitter, 1)

        # Legend under content
        legend = QLabel(
            "Legend: "
            "<span style='background:#ffd6d6;color:red;padding:2px 6px;'> Legal holiday </span> "
            " "
            "<span style='background:#ffe5b4;color:red;padding:2px 6px;'> My planned holiday </span> "
            " "
            "<span style='background:#b5ffb5;padding:2px 6px;'> Selected HO </span> "
            " "
            "<span style='background:#a7d8ff;padding:2px 6px;'> HO linked to weekend </span> "
            " "
            "<span style='background:#faf0f0;padding:2px 6px;'> Weekend </span>"
        )
        legend.setStyleSheet("font-size: 12px;")
        main_layout.addWidget(legend)

        # --- Status bar (bottom) ---
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(
            "color:#333; background:#f7f7f7; border-top:1px solid #ddd; padding:6px 10px; font-size:12px;"
        )
        main_layout.addWidget(self.status_label)

        self.setLayout(main_layout)

        # =========================
        # SIGNALS
        # =========================
        # Calendar interactions
        self.calendar.selection_changed.connect(self.on_selection_changed)
        if hasattr(self.calendar, "holidays_changed"):
            self.calendar.holidays_changed.connect(self.on_holidays_changed)

        # Navigation
        self.prev_btn.clicked.connect(self.load_previous_month)
        self.today_btn.clicked.connect(self.go_to_today)
        self.next_btn.clicked.connect(self.load_next_month)

        # Year and Calendar page sync
        self.year_select.currentTextChanged.connect(self.change_year)
        self.calendar.currentPageChanged.connect(self.on_calendar_page_changed)

        # Topbar actions
        self.export_excel_btn.clicked.connect(self.export_excel)
        self.export_pdf_btn.clicked.connect(self.export_pdf)
        self.save_as_btn.clicked.connect(self.save_all_work_as)
        self.load_btn.clicked.connect(self.load_all_work)
        self.reset_btn.clicked.connect(self.reset_all_data)
        self.instructions_btn.clicked.connect(self.show_instructions_popup)
        self.whats_new_btn.clicked.connect(self.show_whats_new_popup)  # NEW

        # Allowance spin events
        self.allowance_spin.valueChanged.connect(self.on_allowance_changed)

        # ---- Initial data ----
        self._refresh_plans_cache()
        # Provide HO lookup to calendar so grey cells can render HO from adjacent months
        self.calendar.set_ho_lookup(self._is_ho_planned)

        self._apply_saved_plan()
        self._load_allowance_into_ui(self.year)
        self._update_available_for_year(self.year)
        self.update_summary()
    # =========================
    # Convenience: status
    # =========================
    def _set_status(self, text: str):
        self.status_label.setText(text)


    # =========================
    # Plans cache helpers (for HO lookup in calendar)
    # =========================
    def _refresh_plans_cache(self):
        """(Re)read data/homeoffice_plans.json into memory."""
        self._plans_cache = self._read_plans_file()

    def _get_plans_cache(self) -> dict:
        """Return the cached plans dict; lazy-load if needed."""
        if self._plans_cache is None:
            self._refresh_plans_cache()
        return self._plans_cache

    def _is_ho_planned(self, d: datetime.date) -> bool:
        """
        Return True if date d appears in homeoffice_plans.json for its year/month.
        Used by CalendarWidget to paint HO on adjacent-month grey cells.
        """
        data = self._get_plans_cache()
        y = data.get(str(d.year), {})
        m = y.get(f"{d.month:02d}", [])
        iso = d.strftime("%Y-%m-%d")
        return iso in m


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
                "• Right‑click a workday in current month to add or remove a planned holiday.\n"
                "• Autosave is active when changing the month or closing the application.\n"
                "• Rules enforced automatically:\n"
                "  – Weekend‑linked count only Friday & Monday\n"
                "  – Weekend enclosed only if Fri HO + next Mon HO (and both are workdays)\n"
                "• Legal holidays show their names; personal holidays show “Holiday”.\n"
                "• Annual allowance is per year; Available updates as you add/remove planned holidays.\n"
            )
        )
    def show_whats_new_popup(self):
        """Show a friendly popup with the most important improvements in v2."""
        text = (
            "<div style='font-size: 13px; line-height:1.45;'>"
            "<h3 style='margin:0 0 8px 0;'>🎉 What’s New in Home Office Planner v2.0.0</h3>"
            "<ul style='margin:0 0 0 18px; padding:0;'>"
            "<li><b>Week-number column removed</b> (the narrow column before Sunday is no longer shown).</li>"
            "<li><b>Right‑click on hovered workday</b> to add/remove planned holiday (no left‑click needed).</li>"
            "<li><b>Only workdays</b> can be planned; removal always allowed.</li>"
            "<li><b>Grey days</b> no longer change month when clicked; they still display HO / legal / personal info.</li>"
            "<li><b>Today</b> button jumps to the <b>exact current day</b>; subtle hover highlight + blue ring for today.</li>"
            "<li><b>Yearly allowance</b> next to the summary with a live <b>Available</b> counter (green/red).</li>"
            "<li><b>Bigger calendar</b> with a <b>resizable splitter</b> — drag the divider to give the calendar more space.</li>"
            "<li><b>Summary</b> redesigned (icons, spacing, compact cards) + mini‑stats.</li>"
            "<li><b>Status bar</b> messages with timestamps for saves and updates.</li>"
            "</ul>"
            "</div>"
        )
        QMessageBox.information(self, "What’s New in v2.0.0", text)

            # =========================
    # Navigation / page change
    # =========================
    def on_calendar_page_changed(self, year: int, month: int):
        self.year = year
        self.month = month
        if self.year_select.currentText() != str(self.year):
            self.year_select.setCurrentText(str(self.year))
        self.reload_calendar()
        self._load_allowance_into_ui(self.year)
        self._update_available_for_year(self.year)
        self._set_status(f"Navigated to {self.calendar_engine.month_name()} {self.year}")

    def load_previous_month(self):
        self.month -= 1
        if self.month == 0:
            self.month = 12
            self.year -= 1
        if self.year_select.currentText() != str(self.year):
            self.year_select.setCurrentText(str(self.year))
        self.reload_calendar()
        self._load_allowance_into_ui(self.year)
        self._update_available_for_year(self.year)
        self._set_status(f"Navigated to {self.calendar_engine.month_name()} {self.year}")

    def load_next_month(self):
        self.month += 1
        if self.month == 13:
            self.month = 1
            self.year += 1
        if self.year_select.currentText() != str(self.year):
            self.year_select.setCurrentText(str(self.year))
        self.reload_calendar()
        self._load_allowance_into_ui(self.year)
        self._update_available_for_year(self.year)
        self._set_status(f"Navigated to {self.calendar_engine.month_name()} {self.year}")

    def go_to_today(self):
        """Jump to the current day (and its month/year) and refresh UI + availability."""
        from datetime import date
        from PyQt6.QtCore import QDate

        today = date.today()
        self.year = today.year
        self.month = today.month

        if self.year_select.currentText() != str(self.year):
            self.year_select.setCurrentText(str(self.year))

        self.calendar.setCurrentPage(self.year, self.month)
        self.reload_calendar()

        self.calendar.setSelectedDate(QDate(self.year, self.month, today.day))
        self._load_allowance_into_ui(self.year)
        self._update_available_for_year(self.year)

        self._set_status(f"Jumped to today: {today.isoformat()}")
        self.calendar.setFocus()

    def change_year(self, year_str: str):
        if not year_str or not year_str.isdigit():
            return
        new_year = int(year_str)
        if new_year == self.year:
            return
        self.year = new_year
        self.reload_calendar()
        self._load_allowance_into_ui(self.year)
        self._update_available_for_year(self.year)
        self._set_status(f"Year changed to {self.year}")

    # =========================
    # Reload engines + calendar sync
    # =========================
    def reload_calendar(self):
        self.calendar_engine = CalendarEngine(self.year, self.month)
        self.rule_engine = RuleEngine(self.calendar_engine)
        self.calendar.reload_engines(self.calendar_engine, self.rule_engine)
        self.calendar.setCurrentPage(self.year, self.month)
        # Keep HO lookup wired after reload
        self.calendar.set_ho_lookup(self._is_ho_planned)
        self._refresh_plans_cache()
        self._apply_saved_plan()
        self.update_summary()

    # =========================
    # Selection / Holidays change handlers
    # =========================
    def on_selection_changed(self):
        self.update_summary()
        self.save_current_plan(autosave=True)

    def on_holidays_changed(self):
        self.update_summary()
        self._update_available_for_year(self.year)
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self._set_status(f"Planned holidays updated at {now}")

    # =========================
    # Summary (with improved body layout & mini‑stats)
    # =========================
    def update_summary(self):
        # Core numbers
        workdays = len(self.calendar_engine.workdays_of_month())
        max_allowed = self.rule_engine.max_allowed_ho()
        total_ho = len(self.rule_engine.selected_days)
        linked = len(self.rule_engine.weekend_link_days())
        sandwich = self.rule_engine.violates_sandwich_rule()

        # Mini‑stats
        month_dates = list(self.calendar_engine.dates_of_month())
        weekends = sum(1 for d in month_dates if self.calendar_engine.is_weekend(d))
        legal_in_month = sum(1 for d in month_dates if self.calendar_engine.is_legal_holiday(d))
        personal_in_month = len(self.calendar_engine.personal_holidays)

        # Colors
        RED = "#d32f2f"; GREEN = "#2e7d32"
        status_invalid = (total_ho > max_allowed) or (linked > 4) or sandwich
        status_text = "INVALID" if status_invalid else "VALID"
        status_color = RED if status_invalid else GREEN

        sandwich_text = "YES" if sandwich else "NO"
        sandwich_color = RED if sandwich else GREEN

        # Header
        month_name = self.calendar_engine.month_name()
        header = f"<h2>{month_name} {self.year}</h2>"

        # --- Improved BODY with better column spacing ---
        body = f"""
<div style='font-size: 14px; line-height: 1.45;'>

  <!-- MONTHLY OVERVIEW -->
  <div style='padding: 6px 10px; border: 1px solid #ddd; border-radius: 6px; margin-bottom: 10px;'>
    <div style='font-size: 16px; font-weight: 600; margin-bottom: 6px;'>Monthly Overview</div>

    <table style='width: 100%; font-size: 14px; border-collapse: collapse;'>
      <tr>
        <td style='padding: 3px 20px 3px 0;'><b>📅 Working days:</b></td>
        <td style='padding: 3px 0;'>{workdays}</td>
      </tr>
      <tr>
        <td style='padding: 3px 20px 3px 0;'><b>💼 Max allowed HO (50/50):</b></td>
        <td style='padding: 3px 0;'>{max_allowed}</td>
      </tr>
      <tr>
        <td style='padding: 3px 20px 3px 0;'><b>🏠 Selected HO days:</b></td>
        <td style='padding: 3px 0;'>{total_ho}</td>
      </tr>
    </table>
  </div>

  <!-- RULES CHECK -->
  <div style='padding: 6px 10px; border: 1px solid #ddd; border-radius: 6px; margin-bottom: 10px;'>
    <div style='font-size: 16px; font-weight: 600; margin-bottom: 6px;'>Rules Check</div>

    <table style='width: 100%; font-size: 14px; border-collapse: collapse;'>
      <tr>
        <td style='padding: 3px 20px 3px 0;'><b>🔗 Weekend links (Fri/Mon only):</b></td>
        <td style='padding: 3px 0;'>{linked} / 4</td>
      </tr>
      <tr>
        <td style='padding: 3px 20px 3px 0;'><b>🥪 Weekend enclosed (Fri→Mon):</b></td>
        <td style='padding: 3px 0; color:{sandwich_color}; font-weight:600;'>{sandwich_text}</td>
      </tr>
      <tr>
        <td style='padding: 3px 20px 3px 0;'><b>Status:</b></td>
        <td style='padding: 3px 0; color:{status_color}; font-weight:700;'>{status_text}</td>
      </tr>
    </table>
  </div>

  <!-- MINI-STATS -->
  <div style='padding: 6px 10px; border: 1px solid #ddd; border-radius: 6px;'>
    <div style='font-size: 16px; font-weight: 600; margin-bottom: 6px;'>Mini‑stats (this month)</div>

    <ul style='margin: 0 0 0 14px; padding: 0;'>
      <li>📆 <b>Weekends:</b> {weekends}</li>
      <li>🏛 <b>Legal holidays:</b> {legal_in_month}</li>
      <li>🎉 <b>Planned holidays (personal):</b> {personal_in_month}</li>
    </ul>
  </div>

</div>
"""

        self.summary.setText(header + body)

    # =========================
    # Save / Load plans (current month)
    # =========================
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
        return f"{month:02d}"

    def _apply_saved_plan(self):
        data = self._get_plans_cache()  # use cache
        y = str(self.year)
        m = self._month_key(self.month)
        saved_list = data.get(y, {}).get(m, [])
        saved_days = set()
        for s in saved_list:
            try:
                d = datetime.date.fromisoformat(s)
                if d.year == self.year and d.month == self.month:
                    saved_days.add(d)
            except Exception:
                pass

        self.calendar.selected_days = saved_days
        self.rule_engine.set_selected_days(saved_days)
        if hasattr(self.rule_engine, "invalidate_cache"):
            self.rule_engine.invalidate_cache()
        self.calendar.recolor()

    def save_current_plan(self, autosave: bool = False):
        data = self._read_plans_file()
        y = str(self.year)
        m = self._month_key(self.month)

        days = sorted(list(self.rule_engine.selected_days))
        iso_days = [d.strftime("%Y-%m-%d") for d in days]

        if y not in data:
            data[y] = {}
        data[y][m] = iso_days

        self._write_plans_file(data)
        self._refresh_plans_cache()  # keep cache fresh for adjacent-month draw

        now = datetime.datetime.now().strftime("%H:%M:%S")
        if autosave:
            self._set_status(f"Autosaved current month at {now}")
        else:
            self.summary.setText(self.summary.text() + f"<br><b>Saved:</b> {self.plans_path.as_posix()}")
            self._set_status(f"Saved file at {now}")

    # =========================
    # Exports
    # =========================
    def export_excel(self):
        default_name = f"HomeOffice_{self.year}_{self.month:02d}.xlsx"
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export to Excel", default_name, "Excel Workbook (*.xlsx)"
        )
        if not filename:
            return
        if not filename.lower().endswith(".xlsx"):
            filename = f"{filename}.xlsx"

        days = sorted(list(self.rule_engine.selected_days))
        df = pd.DataFrame({"Home Office Days": [d.strftime('%Y-%m-%d') for d in days]})
        df.to_excel(filename, index=False, engine="openpyxl")

        self.summary.setText(self.summary.text() + f"<br><b>Saved Excel to:</b> {filename}")
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self._set_status(f"Exported Excel at {now}")

    def export_pdf(self):
        default_name = f"HomeOffice_{self.year}_{self.month:02d}.pdf"
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export to PDF", default_name, "PDF Files (*.pdf)"
        )
        if not filename:
            return
        if not filename.lower().endswith(".pdf"):
            filename = f"{filename}.pdf"

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
        c.setFont("Helvetica-Oblique", 10)
        c.setFillColorRGB(0.4, 0.4, 0.4)
        c.drawString(50, 40, "© 2026 Florin Săulescu – All rights reserved")
        c.save()

        self.summary.setText(self.summary.text() + f"<br><b>Saved PDF to:</b> {filename}")
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self._set_status(f"Exported PDF at {now}")

    # =========================
    # Save / Load ALL data
    # =========================
    def save_all_work_as(self):
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Work As", "homeoffice_all_plans.json", "JSON Files (*.json)"
        )
        if not filename:
            return
        data = self._read_plans_file()
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self.summary.setText(self.summary.text() + f"<br><b>Saved all work to:</b> {filename}")
            now = datetime.datetime.now().strftime("%H:%M:%S")
            self._set_status(f"Saved ALL at {now}")
        except Exception as e:
            self.summary.setText(self.summary.text() + f"<br><b style='color:red;'>Save error:</b> {e}")
            self._set_status(f"Save error: {e}")

    def load_all_work(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Load Work", "", "JSON Files (*.json)"
        )
        if not filename:
            return
        try:
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._write_plans_file(data)
            self._refresh_plans_cache()
            self._apply_saved_plan()
            self.update_summary()
            self._update_available_for_year(self.year)
            self.summary.setText(self.summary.text() + f"<br><b>Loaded saved work from:</b> {filename}")
            now = datetime.datetime.now().strftime("%H:%M:%S")
            self._set_status(f"Loaded ALL at {now}")
        except Exception as e:
            self.summary.setText(self.summary.text() + f"<br><b style='color:red;'>Load error:</b> {e}")
            self._set_status(f"Load error: {e}")

    def reset_all_data(self):
        if self.plans_path.exists():
            self.plans_path.unlink()
        personal_file = Path("data/personal_holidays.json")
        if personal_file.exists():
            personal_file.unlink()
        if self.allowance_path.exists():
            self.allowance_path.unlink()

        self.calendar_engine = CalendarEngine(self.year, self.month)
        self.rule_engine = RuleEngine(self.calendar_engine)
        self.calendar.reload_engines(self.calendar_engine, self.rule_engine)
        self.calendar.selected_days = set()
        self.rule_engine.set_selected_days(set())
        self.calendar.recolor()

        # Reset caches and UI
        self._plans_cache = {}
        self.calendar.set_ho_lookup(self._is_ho_planned)
        self.allowance_spin.blockSignals(True)
        self.allowance_spin.setValue(0)
        self.allowance_spin.blockSignals(False)
        self._update_available_for_year(self.year)

        self.summary.setText("<b>All data has been reset.</b><br>Calendar is now empty.")
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self._set_status(f"All data reset at {now}")

    # =========================
    # Allowance helpers
    # =========================
    def _read_allowance_file(self) -> dict:
        if self.allowance_path.exists():
            try:
                return json.loads(self.allowance_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
        return {}

    def _write_allowance_file(self, data: dict):
        self.allowance_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _get_year_allowance(self, year: int) -> int:
        data = self._read_allowance_file()
        return int(data.get(str(year), 0))

    def _set_year_allowance(self, year: int, value: int):
        data = self._read_allowance_file()
        data[str(year)] = int(value)
        self._write_allowance_file(data)

    def _load_allowance_into_ui(self, year: int):
        value = self._get_year_allowance(year)
        self.allowance_spin.blockSignals(True)
        self.allowance_spin.setValue(value)
        self.allowance_spin.blockSignals(False)

    def on_allowance_changed(self, value: int):
        self._set_year_allowance(self.year, int(value))
        self._update_available_for_year(self.year)
        now = datetime.datetime.now().strftime("%H:%M:%S")
        self._set_status(f"Allowance for {self.year} set to {int(value)} at {now}")

    def _update_available_for_year(self, year: int):
        """
        Available = Total allowance (year) - Personal holidays on WORKDAYS (Mon–Fri, NOT legal holidays).
        """
        total = self._get_year_allowance(year)
        used = self._count_personal_workday_holidays_in_year(year)
        available = total - used
        color = "#2e7d32" if available >= 0 else "#d32f2f"
        self.available_label.setText(f"Available: <span style='color:{color};'>{available}</span>")

    def _count_personal_workday_holidays_in_year(self, year: int) -> int:
        """
        Count personal holidays in the given year that fall on WORKDAYS:
        - Monday..Friday (weekday < 5) AND NOT a legal holiday.
        NOTE: We do NOT use ce.is_workday(d) because personal holidays are marked as holidays in that set.
        """
        personal_file = Path("data/personal_holidays.json")
        if not personal_file.exists():
            return 0
        try:
            data = json.loads(personal_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return 0

        year_list = data.get(str(year), [])
        if not year_list:
            return 0

        engines_by_month = {}
        count = 0
        for s in year_list:
            try:
                d = datetime.date.fromisoformat(s)
            except Exception:
                continue
            if d.year != year:
                continue
            key = (year, d.month)
            if key not in engines_by_month:
                engines_by_month[key] = CalendarEngine(year, d.month)
            ce = engines_by_month[key]
            if d.weekday() < 5 and not ce.is_legal_holiday(d):
                count += 1
        return count
    