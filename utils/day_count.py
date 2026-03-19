"""
Day count convention utilities for interest rate calculations.
"""
from datetime import date
from dateutil.relativedelta import relativedelta


def add_tenor(base_date: date, tenor: str) -> date:
    """
    Add tenor string to a date.
    Supported tenors: 1D, 1W, 1M, 3M, 6M, 9M, 1Y, 2Y, ...
    """
    tenor = tenor.upper().strip()
    if tenor.endswith("D"):
        from datetime import timedelta
        return base_date + timedelta(days=int(tenor[:-1]))
    elif tenor.endswith("W"):
        from datetime import timedelta
        return base_date + timedelta(weeks=int(tenor[:-1]))
    elif tenor.endswith("M"):
        return base_date + relativedelta(months=int(tenor[:-1]))
    elif tenor.endswith("Y"):
        return base_date + relativedelta(years=int(tenor[:-1]))
    else:
        raise ValueError(f"Unsupported tenor format: {tenor}")


def act360(start: date, end: date) -> float:
    """Actual/360 day count fraction."""
    return (end - start).days / 360.0


def act365(start: date, end: date) -> float:
    """Actual/365 Fixed day count fraction."""
    return (end - start).days / 365.0


def dcf(start: date, end: date, convention: str) -> float:
    """
    Day count fraction dispatcher.
    convention: 'ACT/360', 'ACT/365', '30/360'
    """
    conv = convention.upper().replace(" ", "")
    if conv in ("ACT/360", "ACTUAL/360"):
        return act360(start, end)
    elif conv in ("ACT/365", "ACTUAL/365", "ACT/365F"):
        return act365(start, end)
    else:
        raise ValueError(f"Unsupported day count convention: {convention}")
