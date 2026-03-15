import datetime as dt

class RuleEngine:
    """
    Evaluates all business rules for the Home Office Planner.
    Works with CalendarEngine (which supplies working days, holiday sets, and weekend blocks).
    """

    def __init__(self, calendar_engine):
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
        Weekend sandwich rule (same-month only)

        A violation occurs only when BOTH of these are true:
        • A Friday is selected AND the next Monday is selected
        • Both days are workdays
        • Both days are in the SAME month (and same year)

        Cross-month cases (e.g., Friday in previous month + Monday in current month)
        are explicitly ignored and DO NOT count as a violation for the current month.

        Returns
        -------
        bool
            True if a same-month weekend-sandwich violation is detected, else False.
        """
        # We only need to check Fridays that are selected in the current selection.
        for friday in self.selected_days:
            if friday.weekday() != 4:  # 0=Mon, 4=Fri
                continue

            monday = friday + dt.timedelta(days=3)

            # Same-month/same-year is a strict requirement.
            if (monday.month, monday.year) != (friday.month, friday.year):
                # This skips cross-month sandwiches by design.
                continue

            # Monday must be selected too.
            if monday not in self.selected_days:
                continue

            # Both sides must be workdays (respect holidays).
            if not self.ce.is_workday(friday) or not self.ce.is_workday(monday):
                continue

            # Same-month Friday+Monday selected and both workdays -> violation.
            return True

        # No same-month sandwich found.
        return False
    
    # ------------------------------------------------------------
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