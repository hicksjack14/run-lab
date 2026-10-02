"""Export a training plan as an iCalendar (.ics) file Google Calendar can import.

Times are "floating" (no timezone), so a 5:00 PM run shows at 5:00 PM wherever the calendar is read.
UIDs are stable per plan + date + workout kind, so re-importing the same plan updates events.
"""
from datetime import date, datetime, timedelta, timezone


def _escape(text):
    return (str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\n").replace("\n", "\\n"))


def _fold(line):
    """Fold to at most 75 octets per physical line (continuation lines start with one space)."""
    out, cur, cur_bytes, limit = [], "", 0, 75
    for ch in line:
        n = len(ch.encode("utf-8"))
        if cur_bytes + n > limit:
            out.append(cur)
            cur, cur_bytes, limit = " ", 1, 75
        cur += ch
        cur_bytes += n
    out.append(cur)
    return "\r\n".join(out)


def to_ics(workouts, calendar_name, plan_id="plan", start_time="17:00", now=None):
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    hh, mm = (int(x) for x in start_time.split(":"))
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Run Lab//Training Plan//EN", "CALSCALE:GREGORIAN",
             f"X-WR-CALNAME:{_escape(calendar_name)}"]
    seen = {}
    for w in workouts:
        day = date.fromisoformat(w["date"])
        start = datetime(day.year, day.month, day.day, hh, mm)
        end = start + timedelta(minutes=int(w.get("duration_min") or 45))
        base_uid = f"{plan_id}-{w['date']}-{w.get('kind', 'run')}"
        seen[base_uid] = seen.get(base_uid, 0) + 1
        uid = base_uid if seen[base_uid] == 1 else f"{base_uid}-{seen[base_uid]}"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}@runlab.local",
            f"DTSTAMP:{now.strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{_escape(w['title'])}",
            f"DESCRIPTION:{_escape(w.get('description', ''))}",
            "BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:Run time", "TRIGGER:-PT60M", "END:VALARM",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"
