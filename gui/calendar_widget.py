# gui/calendar_widget.py

from PyQt6.QtWidgets import QCalendarWidget, QMenu
from PyQt6.QtCore import pyqtSignal, QDate, Qt
from PyQt6.QtGui import QTextCharFormat, QColor, QFont, QPainter, QPen


class CalendarWidget(QCalendarWidget):
    selection_changed = pyqtSignal()
    holidays_changed = pyqtSignal()

    def __init__(self, calendar_engine, rule_engine):
        super().__init__()

        self.calendar_engine = calendar_engine
        self.rule_engine = rule_engine

        self.selected_days = set()
        self.setGridVisible(True)
        self.setStyleSheet("font-size: 15px;")

        self.clicked.connect(self.toggle_day)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._open_context_menu)

        self.setCurrentPage(self.calendar_engine.year, self.calendar_engine.month)

        self.recolor()

    # ---------- font safety helpers ----------
    def _safe_point_size(self, pt: int) -> int:
        """Clamp font size to a readable positive value to avoid (-1) or 0."""
        return max(6, int(pt or 0))

    def _apply_font(self, painter: QPainter, point_size: int, bold: bool = False):
        f = QFont()
        f.setBold(bold)
        f.setPointSize(self._safe_point_size(point_size))
        painter.setFont(f)

    def reload_engines(self, calendar_engine, rule_engine):
        self.calendar_engine = calendar_engine
        self.rule_engine = rule_engine
        self.selected_days.clear()
        self.setCurrentPage(self.calendar_engine.year, self.calendar_engine.month)
        self.setSelectedDate(QDate(self.calendar_engine.year, self.calendar_engine.month, 1))
        self.recolor()

    def toggle_day(self, qdate: QDate):
        d = qdate.toPyDate()

        # Do not allow selecting HO on a holiday (legal or personal)
        if d in self.calendar_engine.holidays:
            return

        if d in self.selected_days:
            self.selected_days.remove(d)
        else:
            self.selected_days.add(d)

        self.rule_engine.set_selected_days(self.selected_days)
        self.rule_engine.invalidate_cache()
        self.recolor()
        self.selection_changed.emit()

    # ---------------- Context Menu -------------------
    def _open_context_menu(self, pos):
        qd = self.selectedDate()
        d = qd.toPyDate()

        menu = QMenu(self)

        if self.calendar_engine.is_personal_holiday(d):
            act_remove = menu.addAction("Remove planned holiday")
            chosen = menu.exec(self.mapToGlobal(pos))
            if chosen == act_remove:
                self.calendar_engine.remove_personal_holiday(d)
                if d in self.selected_days:
                    self.selected_days.remove(d)
                self.rule_engine.invalidate_cache()
                self.recolor()
                self.holidays_changed.emit()
        else:
            act_add = menu.addAction("Add planned holiday")
            chosen = menu.exec(self.mapToGlobal(pos))
            if chosen == act_add:
                self.calendar_engine.add_personal_holiday(d)
                if d in self.selected_days:
                    self.selected_days.remove(d)
                self.rule_engine.invalidate_cache()
                self.recolor()
                self.holidays_changed.emit()

    # ---------------- Recolor trigger -------------------
    def recolor(self):
        # We custom-paint in paintCell; here we only trigger a repaint.
        self.setDateTextFormat(QDate(), QTextCharFormat())
        self.updateCells()

    # ---------------- Painting -------------------
    def paintCell(self, painter: QPainter, rect, qdate: QDate):

        # Out‑of‑month → default paint (prevents invalid font warnings from inherited styles)
        if qdate.year() != self.calendar_engine.year or qdate.month() != self.calendar_engine.month:
            super().paintCell(painter, rect, qdate)
            return

        day = qdate.toPyDate()

        # Flags
        is_personal = day in self.calendar_engine.personal_holidays
        is_legal = self.calendar_engine.is_legal_holiday(day)
        is_weekend = self.calendar_engine.is_weekend(day)
        is_ho = day in self.selected_days
        is_link = is_ho and day.weekday() in (0, 4)  # Mon / Fri

        # --- Background color ---
        bg = None
        fg = QColor("black")

        if is_personal:
            bg = QColor("#ffe5b4")
            fg = QColor("red")
        elif is_legal:
            bg = QColor("#ffd6d6")
            fg = QColor("red")
        elif is_link:
            bg = QColor("#a7d8ff")
        elif is_ho:
            bg = QColor("#b5ffb5")
        elif is_weekend:
            bg = QColor("#faf0f0")

        # Paint BG
        if bg:
            painter.fillRect(rect, bg)

        # A tiny defensive guard: if the cell is extremely small (during resizes),
        # skip center/bottom labels to avoid overdraw and font glitches.
        min_h_for_labels = 20

        # --- Day number (top-right) ---
        painter.save()
        self._apply_font(painter, 12, bold=True)  # safe positive size
        painter.setPen(fg)
        painter.drawText(
            rect.adjusted(2, 2, -2, -2),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
            str(qdate.day())
        )
        painter.restore()

        # --- HO / HO link (center) ---
        if rect.height() >= min_h_for_labels and is_ho and not (is_legal or is_personal):
            painter.save()
            self._apply_font(painter, 12, bold=True)
            painter.setPen(QPen(QColor("black")))
            text = "HO link" if is_link else "HO"
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
            painter.restore()

        # --- Legal holiday name (bottom-left) ---
        if rect.height() >= min_h_for_labels and is_legal:
            painter.save()
            self._apply_font(painter, 10, bold=True)
            painter.setPen(QPen(QColor("red")))
            name = self.calendar_engine._legal_all_year.get(day, "")
            painter.drawText(
                rect.adjusted(3, 0, -3, -3),
                Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
                name
            )
            painter.restore()

        # --- Personal holiday "Holiday" ---
        if rect.height() >= min_h_for_labels and is_personal:
            painter.save()
            self._apply_font(painter, 10, bold=True)
            painter.setPen(QPen(QColor("red")))
            painter.drawText(
                rect.adjusted(3, 0, -3, -3),
                Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
                "Holiday"
            )
            painter.restore()

        # --- Selection outline ---
        if qdate == self.selectedDate():
            painter.save()
            sel_pen = QPen(QColor("#4a90e2"))
            sel_pen.setWidth(2)
            painter.setPen(sel_pen)
            painter.drawRect(rect.adjusted(1, 1, -1, -1))
            painter.restore()