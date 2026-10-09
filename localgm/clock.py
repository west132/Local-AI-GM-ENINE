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


def advance(t: dict, minutes: int) -> tuple[dict, int]:
    """New time dict and the number of midnights crossed. ISO dates move on their own;
    any other calendar is left for the setting's own date text (the caller sets t['date'])."""
    if minutes < 0:
        raise ValueError("time only moves forward")
    total = int(t["clock_minutes"]) + minutes
    days = total // 1440
    new = dict(t, day_index=int(t["day_index"]) + days, clock_minutes=total % 1440)
    new["daypart"] = daypart(new["clock_minutes"])
    m = _ISO.match(str(t.get("date") or ""))
    if days and m:
        new["date"] = (_dt.date(*map(int, m.groups())) + _dt.timedelta(days=days)).isoformat()
    elif days:
        new["date"] = f"day {new['day_index']}"
    return new, days
