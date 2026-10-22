"""
Export the "Routine Blocks" Notion database to routine.ics (a separate calendar
feed from portfolio_sprint.ics).

Each block becomes one recurring event (RRULE by the Days field), Pacific time,
from Mon Oct 26 2026 through Sun Dec 6 2026.

PRIVACY: this repo is public, so the feed contains ONLY block titles and times.
No Details, nothing from Sleep Log, Speech or Top 3. Alerts are added only to
blocks with the Alert checkbox ticked (Calm time and Lights out).

Required environment variables:
  NOTION_TOKEN         Same integration secret the existing sync uses.
  ROUTINE_DATABASE_ID  The Routine Blocks database ID (set in the workflow file).
"""

import os
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests
from icalendar import Alarm, Calendar, Event

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
DATABASE_ID = os.environ["ROUTINE_DATABASE_ID"]
NOTION_VERSION = "2022-06-28"
OUTPUT_FILE = "routine.ics"

TZ = ZoneInfo("America/Los_Angeles")
PROGRAM_START = date(2026, 10, 26)  # Monday
PROGRAM_END = date(2026, 12, 6)  # Sunday, last day
DEFAULT_MINUTES = 15  # for blocks with no End time

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]  # date.weekday() order
BYDAY = {"Mon": "MO", "Tue": "TU", "Wed": "WE", "Thu": "TH", "Fri": "FR", "Sat": "SA", "Sun": "SU"}

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json",
}
QUERY_URL = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"


def fetch_pages():
    pages, payload = [], {}
    while True:
        resp = requests.post(QUERY_URL, headers=HEADERS, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        pages.extend(data["results"])
        if not data.get("has_more"):
            return pages
        payload["start_cursor"] = data["next_cursor"]


def text_of(prop):
    """Plain text of a title or rich_text property."""
    items = (prop or {}).get("title") or (prop or {}).get("rich_text") or []
    return "".join(i.get("plain_text", "") for i in items).strip()


def parse_hhmm(value):
    m = re.fullmatch(r"(\d{1,2})[:.](\d{2})", value.strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return None
    return h * 60 + mi


def first_date_for(days):
    """Earliest program date whose weekday is in `days`."""
    for offset in range(7):
        d = PROGRAM_START + timedelta(days=offset)
        if DAYS[d.weekday()] in days:
            return d
    return None


def build_calendar(pages):
    cal = Calendar()
    cal.add("prodid", "-//Sleep and Routine//notion2routine//")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", "Sleep & Routine")
    cal.add("x-wr-timezone", "America/Los_Angeles")

    # Recurrence ends after Sunday Dec 6 (UNTIL is UTC: Dec 7 08:00Z is after 22:00 PST on Dec 6).
    until = datetime(PROGRAM_END.year, PROGRAM_END.month, PROGRAM_END.day, tzinfo=timezone.utc) + timedelta(days=1, hours=8)

    count = 0
    for page in pages:
        props = page.get("properties", {})
        title = text_of(props.get("Activity"))
        start_min = parse_hhmm(text_of(props.get("Start")))
        days = [o["name"] for o in (props.get("Days") or {}).get("multi_select", []) if o["name"] in DAYS]
        if not title or start_min is None or not days:
            continue

        end_min = parse_hhmm(text_of(props.get("End")))
        if end_min is None or end_min <= start_min:
            end_min = min(start_min + DEFAULT_MINUTES, 24 * 60 - 1)

        first = first_date_for(days)
        midnight = datetime(first.year, first.month, first.day, tzinfo=TZ)
        # Add minutes to local midnight on the wall clock (no DST shift on Oct 26 week).
        dtstart = midnight.replace(hour=start_min // 60, minute=start_min % 60)
        dtend = midnight.replace(hour=end_min // 60, minute=end_min % 60)

        event = Event()
        event.add("summary", title)  # title only: no Details, ever
        event.add("uid", f"{page['id']}@routine")
        event.add("dtstamp", datetime.now(timezone.utc))
        event.add("dtstart", dtstart)
        event.add("dtend", dtend)
        event.add("rrule", {"freq": "weekly", "byday": [BYDAY[d] for d in days], "until": until})

        if (props.get("Alert") or {}).get("checkbox"):
            alarm = Alarm()
            alarm.add("action", "DISPLAY")
            alarm.add("description", title)
            alarm.add("trigger", timedelta(0))  # at the start time
            event.add_component(alarm)

        cal.add_component(event)
        count += 1

    cal.add_missing_timezones()
    return cal, count


def main():
    pages = fetch_pages()
    cal, count = build_calendar(pages)
    with open(OUTPUT_FILE, "wb") as f:
        f.write(cal.to_ical())
    print(f"Wrote {count} routine block(s) to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
