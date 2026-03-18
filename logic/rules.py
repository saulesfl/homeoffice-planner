import datetime as dt

class RuleEngine:
    """
    Evaluates all business rules for the Home Office Planner.
    Works with CalendarEngine (which supplies working days, holiday sets, and weekend blocks).
    """

    def __init__(self, calendar_engine):
        self.calendar_engine = calendar_engine
        self.ce = calendar_engine
        self.selected_days = set()

        # caches
        self._ext_cache = None
        self._blocks_cache = None

    # ------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------
    def invalidate_cache(self):
        self._ext_cache = None
        self._blocks_cache = None

    def _ext(self):
        if self._ext_cache is None:
            self._ext_cache = self.ce.extended_weekends()
        return self._ext_cache

    def _blocks(self):
        if self._blocks_cache is None:
            self._blocks_cache = self.ce.weekend_blocks()
        return self._blocks_cache

    # ------------------------------------------------------------
    # Selection API
    # ------------------------------------------------------------
    def set_selected_days(self, days):
        """Store selected HO days and clear caches if needed."""
        self.selected_days = set(days)
        self.invalidate_cache()

    # ------------------------------------------------------------
    # Rules
    # ------------------------------------------------------------
    def max_allowed_ho(self):
        """Max 50% HOMEOFFICE = half of working days."""
        return len(self.ce.workdays_of_month()) // 2

    
    def is_weekend_link(self, day: dt.date) -> bool:
        """
        Weekend-linked HO days are ONLY:
        - Monday (weekday 0)
        - Friday (weekday 4)
        """
        return day.weekday() in (0, 4)


    def weekend_link_days(self):
        return [d for d in self.selected_days if self.is_weekend_link(d)]

    # ------------------------------------------------------------
    # Sandwich rule (simplified per new requirement)
    # ------------------------------------------------------------
    def _prev_workday(self, d):
        x = d - dt.timedelta(days=1)
        while not self.ce.is_workday(x):
            x -= dt.timedelta(days=1)
        return x

    def _next_workday(self, d):
        x = d + dt.timedelta(days=1)
        while not self.ce.is_workday(x):
            x += dt.timedelta(days=1)
        return x

    def violates_sandwich_rule(self) -> bool:
        """
        Weekend sandwich rule (same-month + cross-month HO-link extension)

        SAME-MONTH RULE:
            Friday HO link + Monday HO link inside same month → violation

        CROSS-MONTH RULE (Option C):
            If the previous month has a Friday HO LINK
            AND the current month has a Monday HO LINK
            (first Monday that is HO)
            → violation
        """

        import datetime as dt
        from datetime import date, timedelta
        import json

        # -------------------------------------------------
        # SAME-MONTH VIOLATION (your original logic)
        # -------------------------------------------------
        for friday in self.selected_days:
            if friday.weekday() != 4:  # Friday
                continue

            monday = friday + dt.timedelta(days=3)
            if (monday.year, monday.month) != (friday.year, friday.month):
                continue

            if monday in self.selected_days:
                return True  # SAME-MONTH HO link violation

        # -------------------------------------------------
        # CROSS-MONTH HO-LINK LOGIC (Option C)
        # -------------------------------------------------

        cy, cm = self.ce.year, self.ce.month

        # Determine previous month (py, pm)
        if cm == 1:
            py = cy - 1
            pm = 12
        else:
            py = cy
            pm = cm - 1

        # LOAD previous month HO from file
        try:
            with open("data/homeoffice_plans.json", "r", encoding="utf-8") as f:
                all_plans = json.load(f)
        except:
            all_plans = {}

        prev_list = all_plans.get(str(py), {}).get(f"{pm:02d}", [])
        prev_ho = {date.fromisoformat(s) for s in prev_list}

        # 1️⃣ Find last Friday HO-LINK of previous month
        last_fri_link = None
        for d in sorted(prev_ho):
            if d.weekday() == 4:  # Friday
                last_fri_link = d

        # If no HO Friday last month → NO violation
        if not last_fri_link:
            return False

        # 2️⃣ Find FIRST Monday HO-LINK of current month
        first_mon_link = None
        for d in sorted(self.selected_days):
            if d.month == cm and d.weekday() == 0:   # Monday
                first_mon_link = d
                break

        # If no Monday HO this month → NO violation
        if not first_mon_link:
            return False

        # If both exist → WEEKEND ENCLOSED
        return True
   

    # Summary generator for GUI
    # ------------------------------------------------------------
    def generate_report(self):
        workdays = len(self.ce.workdays_of_month())
        max_allowed = self.max_allowed_ho()
        total_ho = len(self.selected_days)
        linked = len(self.weekend_link_days())
        sandwich = self.violates_sandwich_rule()

        status = "VALID"
        if total_ho > max_allowed or linked > 4 or sandwich:
            status = "INVALID"

        text = (
            f"Working days: {workdays}\n"
            f"Max allowed HO days (50/50): {max_allowed}\n"
            f"Selected HO days: {total_ho}\n\n"
            f"HO days linked to weekend: {linked} / 4 allowed\n"
            f"Weekend sandwich violation: {'YES' if sandwich else 'NO'}\n\n"
            f"Status: {status}"
        )
        return text