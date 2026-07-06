"""Calendar ICS: parsing (incl. RRULE), reminder windows, settings, fetch."""

import io
import urllib.error
from datetime import datetime, timedelta, timezone

from mycat.calendar_ics import (
    CalendarController,
    CalendarSettings,
    ReminderTracker,
    fetch_ics,
    load_calendar_settings,
    normalize_ics_url,
    parse_upcoming,
    save_calendar_settings,
)

TZ = timezone.utc


def ics(body: str) -> bytes:
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//test//EN\r\n"
        + body
        + "END:VCALENDAR\r\n"
    ).encode()


SIMPLE_EVENT = ics(
    "BEGIN:VEVENT\r\nUID:one@test\r\nSUMMARY:Dentist\r\n"
    "DTSTART:20260702T140000Z\r\nDTEND:20260702T150000Z\r\nEND:VEVENT\r\n"
)

DAILY_STANDUP = ics(
    "BEGIN:VEVENT\r\nUID:standup@test\r\nSUMMARY:Standup\r\n"
    "DTSTART:20260601T090000Z\r\nDTEND:20260601T091500Z\r\n"
    "RRULE:FREQ=DAILY\r\nEND:VEVENT\r\n"
)

ALL_DAY = ics(
    "BEGIN:VEVENT\r\nUID:allday@test\r\nSUMMARY:Holiday\r\n"
    "DTSTART;VALUE=DATE:20260702\r\nEND:VEVENT\r\n"
)


def test_parse_simple_event():
    start = datetime(2026, 7, 2, 0, 0, tzinfo=TZ)
    events = parse_upcoming(SIMPLE_EVENT, start, start + timedelta(days=1))
    assert len(events) == 1
    assert events[0]["summary"] == "Dentist"
    assert events[0]["start"].astimezone(TZ).hour == 14


def test_parse_expands_rrule_daily():
    start = datetime(2026, 7, 2, 0, 0, tzinfo=TZ)
    events = parse_upcoming(DAILY_STANDUP, start, start + timedelta(days=3))
    assert len(events) == 3  # one standup per day, expanded from the RRULE
    assert all(event["summary"] == "Standup" for event in events)
    keys = {event["key"] for event in events}
    assert len(keys) == 3  # each occurrence dedupes independently


def test_parse_skips_all_day_events():
    start = datetime(2026, 7, 1, 0, 0, tzinfo=TZ)
    events = parse_upcoming(ALL_DAY, start, start + timedelta(days=3))
    assert events == []


def test_reminder_tracker_fires_inside_window_once():
    tracker = ReminderTracker(remind_minutes=10)
    event_start = datetime(2026, 7, 2, 14, 0, tzinfo=TZ)
    events = [{"key": "k|2026-07-02T14:00:00+00:00", "start": event_start, "summary": "Dentist"}]

    too_early = event_start - timedelta(minutes=30)
    assert tracker.due(events, too_early) == []
    in_window = event_start - timedelta(minutes=7)
    assert [e["summary"] for e in tracker.due(events, in_window)] == ["Dentist"]
    assert tracker.due(events, in_window) == []  # fires once
    after_start = event_start + timedelta(minutes=1)
    assert tracker.due(events, after_start) == []


def test_reminder_tracker_ignores_already_started_events():
    tracker = ReminderTracker(remind_minutes=10)
    event_start = datetime(2026, 7, 2, 14, 0, tzinfo=TZ)
    events = [{"key": "k", "start": event_start, "summary": "Missed"}]
    assert tracker.due(events, event_start + timedelta(minutes=5)) == []


def test_normalize_webcal_url():
    assert normalize_ics_url("webcal://example.com/cal.ics") == "https://example.com/cal.ics"
    assert normalize_ics_url(" https://x/y.ics ") == "https://x/y.ics"


def test_settings_round_trip(tmp_path):
    cfg = tmp_path / "config.ini"
    save_calendar_settings(CalendarSettings(enabled=True, url="https://x/y.ics", remind_minutes=15), cfg_file=cfg)
    loaded = load_calendar_settings(cfg_file=cfg)
    assert loaded.enabled is True
    assert loaded.url == "https://x/y.ics"
    assert loaded.remind_minutes == 15


class FakeResponse:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_fetch_ics_success_and_304():
    def opener(request, timeout):
        return FakeResponse(200, {"ETag": "E1"}, SIMPLE_EVENT)

    result = fetch_ics("https://x/y.ics", opener=opener)
    assert result["status"] == 200
    assert result["etag"] == "E1"
    assert result["ics_bytes"] == SIMPLE_EVENT

    def opener_304(request, timeout):
        assert request.get_header("If-none-match") == "E1"
        raise urllib.error.HTTPError("url", 304, "Not Modified", {}, io.BytesIO(b""))

    result = fetch_ics("https://x/y.ics", etag="E1", opener=opener_304)
    assert result["status"] == 304
    assert result["error"] == ""


class AnnouncerStub:
    def __init__(self):
        self.announced = []

    def announce(self, text, url="", **kwargs):
        self.announced.append(text)


def test_controller_announces_before_event(qapp):
    now_holder = {"now": datetime(2026, 7, 2, 13, 55, tzinfo=TZ)}
    ann = AnnouncerStub()
    controller = CalendarController(
        None,
        announcer=ann,
        settings=CalendarSettings(enabled=True, url="https://x/y.ics", remind_minutes=10),
        now_fn=lambda: now_holder["now"],
        start_timers=False,
    )
    event_start = datetime(2026, 7, 2, 14, 0, tzinfo=TZ)
    controller.events = [{"key": "k", "start": event_start, "summary": "Dentist"}]
    controller.tick()
    assert len(ann.announced) == 1
    text = ann.announced[0]
    assert "Dentist" in text
    assert "5 min" in text
    controller.tick()  # no double fire
    assert len(ann.announced) == 1


def test_controller_disabled_never_fetches(qapp):
    controller = CalendarController(
        None,
        announcer=AnnouncerStub(),
        settings=CalendarSettings(enabled=False, url="https://x/y.ics"),
        start_timers=False,
    )
    controller.poll()
    assert controller.fetching is False
