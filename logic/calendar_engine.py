# logic/calendar_engine.py

import datetime as dt
import calendar
import json
from pathlib import Path
from logic.holidays_ro import HOLIDAYS_RO_2026


class CalendarEngine:
    def __init__(self, year=2026, month=3):
        self.year = year
        self.month = month

        self.data_dir = Path("data")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.personal_file = self.data_dir / "personal_holidays.json"

        # ---------------- Legal holidays with NAMES ----------------
        if self.year == 2026:
            self._legal_all_year = HOLIDAYS_RO_2026.copy()   # dict: date -> name
        else:
            self._legal_all_year = {}

        # ---------------- Load personal holidays ----------------
        self._personal_all_year = self._load_personal_for_year(self.year)

        # Combined holiday set (legal + personal)
        self._all_holidays_year = set(self._legal_all_year.keys()) | set(self._personal_all_year)

        # Month boundaries
        self._first_day = dt.date(self.year, self.month, 1)
        ndays = calendar.monthrange(self.year, self.month)[1]
        self._last_day = dt.date(self.year, self.month, ndays)

        # Month-specific sets
        self.holidays = {d for d in self._all_holidays_year if d.month == self.month}
        self.personal_holidays = {d for d in self._personal_all_year if d.month == self.month}

    # ---------------- Personal holiday load/save ----------------
    def _load_personal_for_year(self, year: int) -> set[dt.date]:
        if not self.personal_file.exists():
            return set()

        try:
            data = json.loads(self.personal_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}

        year_str = str(year)
        dates = data.get(year_str, [])

        rv = set()
        for s in dates:
            try:
                d = dt.date.fromisoformat(s)
                if d.year == year:
                    rv.add(d)
            except:
                pass
        return rv

    def _save_personal_for_year(self):
        if self.personal_file.exists():
            try:
                data = json.loads(self.personal_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
        else:
            data = {}

        year_str = str(self.year)
        data[year_str] = sorted([d.isoformat() for d in self._personal_all_year])
        self.personal_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add_personal_holiday(self, d: dt.date):
        if d.year != self.year:
            return
        self._personal_all_year.add(d)
        self._all_holidays_year.add(d)

        if d.month == self.month:
            self.personal_holidays.add(d)
            self.holidays.add(d)

        self._save_personal_for_year()

    def remove_personal_holiday(self, d: dt.date):
        if d.year != self.year:
            return
        if d in self._personal_all_year:
            self._personal_all_year.remove(d)

        if d not in self._legal_all_year:
            self._all_holidays_year.discard(d)

        self.personal_holidays.discard(d)
        if d.month == self.month and d not in self._legal_all_year:
            self.holidays.discard(d)

        self._save_personal_for_year()

    def is_personal_holiday(self, d: dt.date) -> bool:
        return d in self._personal_all_year

    # ---------------- Basics ----------------
    def month_name(self) -> str:
        return calendar.month_name[self.month]

    def dates_of_month(self):
        d = self._first_day
        while d <= self._last_day:
            yield d
            d += dt.timedelta(days=1)

    def is_weekend(self, d: dt.date) -> bool:
        return d.weekday() >= 5  # Sat/Sun

    def is_legal_holiday(self, d: dt.date) -> bool:
        return d in self._legal_all_year

    def is_workday(self, d: dt.date) -> bool:
        return (d.weekday() < 5) and (d not in self._all_holidays_year)

    def workdays_of_month(self):
        return [d for d in self.dates_of_month() if self.is_workday(d)]