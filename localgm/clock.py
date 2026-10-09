"""World time. Minutes are added by the program from the time costs the AI states."""
from __future__ import annotations
import datetime as _dt, re

_ISO = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})\s*$")


def daypart(minutes: int) -> str:
    for limit, name in ((300, "night"), (480, "dawn"), (720, "morning"), (1020, "afternoon"), (1260, "evening")):
        if minutes < limit:
            return name
    return "night"


def hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


class Gregorian:
    """The default: dates are written YYYY-MM-DD."""
    name = "iso"
    pattern = r"(?P<y>\d{4})-(?P<mo>\d{2})-(?P<d>\d{2})"

    def ordinal_of(self, y, mo, d) -> int:
        return _dt.date(int(y), int(mo), int(d)).toordinal()

    def fmt(self, n: int) -> str:
        return _dt.date.fromordinal(n).isoformat()

    def weekday(self, n: int):
        return None


class Custom:
    """A world's own calendar, written as a table in the BACKGROUND:
        calendar:
          era: Year                      # printed before the year (optional)
          months: [{name: Thawmonth, days: 30}, ...]
          leap: {every: 4, month: Thawmonth, extra: 1}      # optional: every Nth year this month has extra days
          weekdays: [Moonday, ...]       # optional, with start_weekday: the weekday name of day 1 of the first month of year 1
          start_weekday: Moonday
    A date is written '<era> <year>, <Month> <day>' ("Year 318, Floodmonth 6"). The program converts it; the AI never does."""
    name = "custom"

    def __init__(self, c: dict):
        ms = c.get("months")
        if not (isinstance(ms, list) and ms and all(isinstance(m, dict) and str(m.get("name", "")).strip()
                                                      and isinstance(m.get("days"), int) and 1 <= m["days"] <= 100 for m in ms)):
            raise ValueError("calendar.months must be a list of {name, days} with whole-number days (1 to 100)")
        self.months = [(str(m["name"]).strip(), m["days"]) for m in ms]
        names = [n.lower() for n, _ in self.months]
        if len(set(names)) != len(names):
            raise ValueError("calendar.months: month names must be different")
        self.era = str(c.get("era") or "").strip()
        self.leap = c.get("leap")
        if self.leap is not None and not (isinstance(self.leap, dict) and isinstance(self.leap.get("every"), int) and self.leap["every"] >= 2
                                          and str(self.leap.get("month", "")).lower() in names and isinstance(self.leap.get("extra"), int)):
            raise ValueError("calendar.leap must be {every: N (2 or more), month: <a month name>, extra: <days>}")
        self.weekdays = [str(w) for w in c.get("weekdays") or []]
        self.start_weekday = (self.weekdays.index(str(c["start_weekday"])) if self.weekdays and c.get("start_weekday") in self.weekdays
                              else 0)
        if self.weekdays and "start_weekday" in c and c["start_weekday"] not in self.weekdays:
            raise ValueError("calendar.start_weekday must be one of calendar.weekdays")
        alt = "|".join(re.escape(n) for n, _ in sorted(self.months, key=lambda m: -len(m[0])))
        era = (re.escape(self.era) + r"\s+") if self.era else ""
        self.pattern = rf"(?:{era})?(?P<y>\d+)\s*,?\s*(?P<mo>{alt})\s+(?P<d>\d{{1,3}})"

    def _len(self, y: int, i: int) -> int:
        n, days = self.months[i]
        if self.leap and n.lower() == str(self.leap["month"]).lower() and y % self.leap["every"] == 0:
            days += self.leap["extra"]
        return days

    def _year_days(self, y: int) -> int:
        return sum(self._len(y, i) for i in range(len(self.months)))

    def ordinal_of(self, y, mo, d) -> int:
        y, d = int(y), int(d)
        idx = [n.lower() for n, _ in self.months].index(str(mo).lower())
        if not 1 <= d <= self._len(y, idx):
            raise ValueError(f"{mo} has {self._len(y, idx)} days in year {y}, not {d}")
        n = sum(self._year_days(k) for k in range(1, y)) + sum(self._len(y, i) for i in range(idx)) + d
        return n

    def fmt(self, n: int) -> str:
        y = 1
        while n > self._year_days(y):
            n -= self._year_days(y)
            y += 1
        for i, (name, _) in enumerate(self.months):
            if n <= self._len(y, i):
                return f"{self.era + ' ' if self.era else ''}{y}, {name} {n}"
            n -= self._len(y, i)
        raise ValueError("date out of range")

    def weekday(self, n: int):
        return self.weekdays[(n - 1 + self.start_weekday) % len(self.weekdays)] if self.weekdays else None


def calendar_from(tree: dict):
    c = (tree or {}).get("calendar")
    return Custom(c) if c else Gregorian()


def date_ordinal(cal, text) -> int | None:
    """The ordinal day of a date written whole in the calendar's form (nothing else in the text), else None."""
    m = re.fullmatch(r"\s*" + cal.pattern + r"\s*", str(text or ""), re.I)
    if not m:
        return None
    try:
        return cal.ordinal_of(m["y"], m["mo"], m["d"])
    except ValueError:
        return None


def advance(t: dict, minutes: int, cal=None) -> tuple[dict, int]:
    """New time dict and the number of midnights crossed. The date moves by the world's calendar table."""
    if minutes < 0:
        raise ValueError("time only moves forward")
    cal = cal or Gregorian()
    total = int(t["clock_minutes"]) + minutes
    days = total // 1440
    new = dict(t, day_index=int(t["day_index"]) + days, clock_minutes=total % 1440)
    new["daypart"] = daypart(new["clock_minutes"])
    n = date_ordinal(cal, t.get("date"))
    if days and n is not None:
        new["date"] = cal.fmt(n + days)
    elif days:
        new["date"] = f"day {new['day_index']}"
    return new, days
