# gui/calendar_widget.py
from PyQt6.QtWidgets import QCalendarWidget, QMenu, QWidget, QToolTip
from PyQt6.QtCore import pyqtSignal, QDate, Qt, QEvent
from PyQt6.QtGui import QTextCharFormat, QColor, QFont, QPainter, QPen
from datetime import date as _today_date  # for 'today' highlight

class CalendarWidget(QCalendarWidget):
    selection_changed = pyqtSignal()
    holidays_changed = pyqtSignal()

    def __init__(self, calendar_engine, rule_engine):
        super().__init__()
        # Show ISO week numbers in the left header column
        self.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.calendar_engine = calendar_engine
        self.rule_engine = rule_engine
        self.selected_days = set()

        # Track hovered day for hover highlight
        self._hovered_qdate = None

        # Optional callback provided by MainWindow to check if a date has HO
        # Signature: callable(datetime.date) -> bool
        self._ho_lookup = None

        self.setGridVisible(True)
        self.setStyleSheet("font-size: 15px;")

        # Left-click toggles HO day (unchanged for current month)
        self.clicked.connect(self.toggle_day)

        # Right-click context menu on hovered cell (current month only)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._open_context_menu)

        # Tooltips on hover + hover highlight
        self.setMouseTracking(True)

        # IMPORTANT: the internal month table view receives the click.
        # Install an event filter on it so we can swallow clicks on grey cells.
        view = self.findChild(QWidget, "qt_calendar_calendarview")
        if view is not None:
            view.setMouseTracking(True)
            view.installEventFilter(self)  # guard month-change on grey cells

        # Initialize current page and colors
        self.setCurrentPage(self.calendar_engine.year, self.calendar_engine.month)
        self.recolor()

    # ---------- public hook from MainWindow ----------
    def set_ho_lookup(self, fn):
        """Set a callable that returns True if a given date has Home Office planned."""
        self._ho_lookup = fn

    # ---------- font safety helpers ----------
    def _safe_point_size(self, pt: int) -> int:
        """Clamp font size to a readable positive value to avoid (-1) or 0."""
        return max(6, int(pt or 0))

    def _apply_font(self, painter: QPainter, point_size: int, bold: bool = False):
        f = QFont()
        f.setBold(bold)
        f.setPointSize(self._safe_point_size(point_size))
        painter.setFont(f)

    # ---------- reload ----------
    def reload_engines(self, calendar_engine, rule_engine):
        self.calendar_engine = calendar_engine
        self.rule_engine = rule_engine
        self.selected_days.clear()
        self.setCurrentPage(self.calendar_engine.year, self.calendar_engine.month)
        self.setSelectedDate(QDate(self.calendar_engine.year, self.calendar_engine.month, 1))
        self.recolor()

    # ---------- HO toggle (current month only) ----------
    def toggle_day(self, qdate: QDate):
        d = qdate.toPyDate()
        # Do not allow selecting HO on any holiday (legal or personal)
        if d in self.calendar_engine.holidays:
            return
        # Only allow toggling for current month
        if not self._is_current_month_qdate(qdate):
            return
        if d in self.selected_days:
            self.selected_days.remove(d)
        else:
            self.selected_days.add(d)
        self.rule_engine.set_selected_days(self.selected_days)
        self.rule_engine.invalidate_cache()
        self.recolor()
        self.selection_changed.emit()

    # ---------------- Helpers -------------------
    def _date_at_pos(self, pos):
        """
        Return the QDate under the mouse cursor.
        Returns None if no valid date can be determined.
        """
        view: QWidget | None = self.findChild(QWidget, "qt_calendar_calendarview")
        if view is None:
            return None

        local_pos = view.mapFrom(self, pos)
        try:
            index = view.indexAt(local_pos)
        except Exception:
            return None

        if not index or not index.isValid():
            return None

        qd = index.data(Qt.ItemDataRole.UserRole)
        if isinstance(qd, QDate) and qd.isValid():
            return qd

        # Fallback: compose from DisplayRole and current page
        try:
            day_str = str(index.data(Qt.ItemDataRole.DisplayRole)).strip()
            day_int = int(day_str)
            return QDate(self.calendar_engine.year, self.calendar_engine.month, day_int)
        except Exception:
            return None

    def _is_current_month_qdate(self, qd):
        return (
            isinstance(qd, QDate)
            and qd.isValid()
            and qd.year() == self.calendar_engine.year
            and qd.month() == self.calendar_engine.month
        )

    # ---------------- Context Menu (Right‑Click) -------------------
    def _open_context_menu(self, pos):
        """
        Right‑click add/remove planned holiday exactly on the hovered day.
        Rules enforced:
        - Disallow grey (adjacent month) cells for any action.
        - Allow REMOVE on personal holidays even if the day is not a 'workday' anymore.
        - Allow ADD only on workdays (weekday and not a legal holiday).
        """
        qd = self._date_at_pos(pos)
        if not isinstance(qd, QDate) or not qd.isValid():
            return

        d = qd.toPyDate()

        # 1) Disallow grey (adjacent month) cells completely
        if not self._is_current_month_qdate(qd):
            return

        is_personal = self.calendar_engine.is_personal_holiday(d)

        # 2) If not already a personal holiday, enforce "add only on workdays"
        if not is_personal and not self.calendar_engine.is_workday(d):
            return

        menu = QMenu(self)

        if is_personal:
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

    # ---------------- Event filter: swallow clicks on grey cells ----------------
    def eventFilter(self, obj, event):
        """
        Intercept mouse clicks that hit grey (adjacent-month) cells and consume them
        so QCalendarWidget will NOT auto-navigate to previous/next month.
        """
        if obj is self.findChild(QWidget, "qt_calendar_calendarview"):
            if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
                try:
                    index = obj.indexAt(event.pos())
                except Exception:
                    index = None
                if index and index.isValid():
                    qd = index.data(Qt.ItemDataRole.UserRole)
                    if not isinstance(qd, QDate) or not qd.isValid():
                        try:
                            day_int = int(str(index.data(Qt.ItemDataRole.DisplayRole)).strip())
                            qd = QDate(self.calendar_engine.year, self.calendar_engine.month, day_int)
                        except Exception:
                            qd = None
                    if qd and not self._is_current_month_qdate(qd):
                        event.accept()
                        return True  # stop propagation
        return super().eventFilter(obj, event)

    # ---------------- Tooltip + Hover helpers -------------------
    def _day_tooltip_text(self, qd):
        """
        Build the tooltip text for a given QDate (qd) according to your rules.
        Returns None for 'no tooltip'.
        """
        if not qd or not isinstance(qd, QDate) or not qd.isValid():
            return None

        # Adjacent month (grey cells) -> still show a tooltip, but clarify it's from another month
        d = qd.toPyDate()
        is_current = self._is_current_month_qdate(qd)

        # Personal holiday
        if self.calendar_engine.is_personal_holiday(d):
            return ("Planned holiday — right‑click to remove" if is_current
                    else "Planned holiday (adjacent month)")

        # Legal holiday
        if self.calendar_engine.is_legal_holiday(d):
            name = self.calendar_engine._legal_all_year.get(d, "Legal holiday")
            return (f"{name} — planning not allowed" if is_current
                    else f"{name} (adjacent month)")

        # Weekend
        if self.calendar_engine.is_weekend(d):
            return ("Weekend — planning not allowed" if is_current
                    else "Weekend (adjacent month)")

        # Workday
        return ("Workday — right‑click to plan holiday" if is_current
                else "Workday (adjacent month)")

    def mouseMoveEvent(self, event):
        """
        Show a contextual tooltip while hovering over the calendar,
        and record hovered cell for hover highlight.
        """
        qd = self._date_at_pos(event.pos())

        # Record hovered date only if it's in current month; else clear
        if self._is_current_month_qdate(qd):
            self._hovered_qdate = qd
        else:
            self._hovered_qdate = None

        # Tooltip text
        text = self._day_tooltip_text(qd)

        # Compute global position for the tooltip
        try:
            gp = event.globalPosition().toPoint()
        except Exception:
            gp = event.globalPos() if hasattr(event, "globalPos") else None

        if text and gp is not None:
            QToolTip.showText(gp, text, self)
        else:
            QToolTip.hideText()

        # Trigger repaint for hover highlight
        self.updateCells()

        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        QToolTip.hideText()
        self._hovered_qdate = None
        self.updateCells()
        super().leaveEvent(event)

    # ---------------- Recolor trigger -------------------
    def recolor(self):
        self.setDateTextFormat(QDate(), QTextCharFormat())
        self.updateCells()

    def _cw_badge_rect(self, rect):
            """
            Return a QRect for the CW badge, anchored hard-left in the cell,
            vertically under the day number, with a fixed size for clarity.
            Tunables:
            x_pad  : distance from the cell's left edge
            y_top  : distance from the cell's top edge
            w, h   : badge width/height
            """
            x_pad = 4
            y_top = 18
            w, h = 52, 18
            # rect.adjusted(left, top, right, bottom):
            # right = -(rect.width() - (x_pad + w)) keeps only w width
            # bottom = -(rect.height() - (y_top + h)) keeps only h height
            return rect.adjusted(x_pad, y_top, -(rect.width() - (x_pad + w)), -(rect.height() - (y_top + h)))

    def _draw_cw_badge_left(self, painter, rect, qdate: QDate):
        """Draw 'CW##' at the far-left of the cell (only on the first day-of-week column)."""
        # Optional: skip if cell is too small to avoid overlaps
        if rect.width() < 60 or rect.height() < 28:
            return

        # Use the widget's actual leftmost day-of-week (so badge hugs the week-number column)
        try:
            first_col = int(self.firstDayOfWeek())  # Qt.DayOfWeek enum → int 1..7
        except Exception:
            first_col = 1  # fallback (Monday) if something unexpected happens

        if qdate.dayOfWeek() != first_col:
            return

        # ISO week number
        week_num, _ = qdate.weekNumber()

        # Compute badge rectangle tight to the left side
        badge = self._cw_badge_rect(rect)

        # Draw badge
        painter.save()
        fill = QColor("#E6F0FF")     # soft blue
        border = QColor("#3B6DB3")   # stronger blue
        painter.setPen(QPen(border))
        painter.fillRect(badge, fill)
        painter.drawRoundedRect(badge, 6, 6)

        # Text
        self._apply_font(painter, 10, bold=True)
        painter.setPen(QPen(border))
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, f"CW{week_num}")
        painter.restore()
    def paintCell(self, painter: QPainter, rect, qdate: QDate):
        """
        Custom painting for calendar cells:
        - Current month: weekend/legal/personal/HO/link, day number, labels, today ring, selection outline
        - Adjacent month: grey background but still show HO / legal / "Holiday"
        - Hover highlight
        - Calendar Week badge "CW##" on Mondays, drawn hard-left (near week-number column)
        """
        is_current = self._is_current_month_qdate(qdate)
        day = qdate.toPyDate()

        # Precompute flags usable in both branches
        is_legal_any = self.calendar_engine.is_legal_holiday(day)
        is_weekend = self.calendar_engine.is_weekend(day)

        # ---------------- Current-month drawing ----------------
        if is_current:
            # Hover highlight
            if self._hovered_qdate is not None and qdate == self._hovered_qdate:
                painter.fillRect(rect, QColor("#e8f2ff"))

            is_personal = day in self.calendar_engine.personal_holidays
            is_legal = is_legal_any
            is_ho = day in self.selected_days
            is_link = is_ho and day.weekday() in (0, 4)  # Mon/Fri

            # Background color by priority
            bg = None
            fg = QColor("black")
            if is_personal:
                bg = QColor("#ffe5b4"); fg = QColor("red")
            elif is_legal:
                bg = QColor("#ffd6d6"); fg = QColor("red")
            elif is_link:
                bg = QColor("#a7d8ff")
            elif is_ho:
                bg = QColor("#b5ffb5")
            elif is_weekend:
                bg = QColor("#faf0f0")
            if bg:
                painter.fillRect(rect, bg)

            min_h_for_labels = 20

            # Day number (top-right)
            painter.save()
            self._apply_font(painter, 12, bold=True)
            painter.setPen(fg)
            painter.drawText(
                rect.adjusted(2, 2, -2, -2),
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
                str(qdate.day())
            )
            painter.restore()

            # CW badge (left, close to week-number header)
            self._draw_cw_badge_left(painter, rect, qdate)

            # HO / HO link (center)
            if rect.height() >= min_h_for_labels and is_ho and not (is_legal or is_personal):
                painter.save()
                self._apply_font(painter, 12, bold=True)
                painter.setPen(QPen(QColor("black")))
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "HO link" if is_link else "HO")
                painter.restore()

            # Legal holiday name (bottom-left)
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

            # Personal holiday (bottom-left)
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

            # TODAY ring
            try:
                from datetime import date as _today_date
                if day == _today_date():
                    painter.save()
                    pen = QPen(QColor("#0066ff")); pen.setWidth(2)
                    painter.setPen(pen)
                    inset = max(4, min(rect.width(), rect.height()) // 8)
                    painter.drawEllipse(rect.adjusted(inset, inset, -inset, -inset))
                    painter.restore()
            except Exception:
                pass

            # Selection outline (QCalendarWidget selection)
            if qdate == self.selectedDate():
                painter.save()
                sel_pen = QPen(QColor("#4a90e2")); sel_pen.setWidth(2)
                painter.setPen(sel_pen)
                painter.drawRect(rect.adjusted(1, 1, -1, -1))
                painter.restore()
            return

        # ---------------- Adjacent-month drawing ----------------
        painter.fillRect(rect, QColor("#f0f0f0"))
        min_h_for_labels = 20

        # Day number (grey)
        painter.save()
        self._apply_font(painter, 12, bold=True)
        painter.setPen(QPen(QColor("#7a7a7a")))
        painter.drawText(
            rect.adjusted(2, 2, -2, -2),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
            str(qdate.day())
        )
        painter.restore()

        # CW badge (left)
        self._draw_cw_badge_left(painter, rect, qdate)

        # HO center for adjacent months (informative only)
        has_ho = False
        if callable(self._ho_lookup):
            try:
                has_ho = bool(self._ho_lookup(day))
            except Exception:
                has_ho = False
        is_personal_any = day in getattr(self.calendar_engine, "_personal_all_year", set())

        if rect.height() >= min_h_for_labels and has_ho and not is_legal_any and not is_personal_any:
            painter.save()
            self._apply_font(painter, 12, bold=True)
            painter.setPen(QPen(QColor("black")))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "HO")
            painter.restore()

        # Legal / Personal (bottom-left, adjacent)
        if rect.height() >= min_h_for_labels and (is_legal_any or is_personal_any):
            painter.save()
            self._apply_font(painter, 10, bold=True)
            painter.setPen(QPen(QColor("red")))
            text = (self.calendar_engine._legal_all_year.get(day, "Legal holiday")
                    if is_legal_any else "Holiday")
            painter.drawText(
                rect.adjusted(3, 0, -3, -3),
                Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
                text
            )
            painter.restore()

        # TODAY ring on adjacent rows too
        try:
            from datetime import date as _today_date
            if day == _today_date():
                painter.save()
                pen = QPen(QColor("#0066ff")); pen.setWidth(2)
                painter.setPen(pen)
                inset = max(4, min(rect.width(), rect.height()) // 8)
                painter.drawEllipse(rect.adjusted(inset, inset, -inset, -inset))
                painter.restore()
        except Exception:
            pass
