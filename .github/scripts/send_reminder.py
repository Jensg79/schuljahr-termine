"""
Send schedule reminder via Signal API.

This script reads a markdown schedule file, formats upcoming events,
and sends a message via the CallMeBot Signal API.
"""

import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from typing import Optional

# Configuration
CHAR_LIMIT = 1500
WEEKDAYS_DE = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
SCHEDULE_FILE = os.environ.get('SCHEDULE_FILE', 'schuljahr-termine.md')
GREETING_NAME = os.environ.get('GREETING_NAME', 'Jens')
SIGNAL_API_URL = "https://signal.callmebot.com/signal/send.php"
REQUEST_TIMEOUT = 30

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class Termin:
    """Represents a scheduled event."""
    days_until: int
    event_date: date
    weekday: str
    task: str
    note: str


def parse_schedule_file(filepath: str) -> tuple[list[Termin], list[str]]:
    """
    Parse markdown schedule file.

    Args:
        filepath: Path to the schedule markdown file

    Returns:
        Tuple of (valid_termine, discarded_lines)
    """
    termine = []
    discarded = []
    today = date.today()

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()

                # Skip empty lines and special lines
                if not line or line.startswith(('#', '<!--', '-')):
                    continue

                parts = [p.strip() for p in line.split('|')]
                if len(parts) < 2:
                    continue

                try:
                    event_date = date.fromisoformat(parts[0])
                    task = parts[1]
                    note = parts[2] if len(parts) > 2 else ''
                    days_until = (event_date - today).days

                    # Only include future events (including today)
                    if days_until >= 0:
                        weekday = WEEKDAYS_DE[event_date.weekday()]
                        termine.append(Termin(days_until, event_date, weekday, task, note))

                except ValueError:
                    if parts[0].strip():
                        discarded.append(line)

    except FileNotFoundError:
        logger.error(f"Schedule file not found: {filepath}")
        raise SystemExit(1)
    except OSError as e:
        logger.error(f"Error reading schedule file: {e}")
        raise SystemExit(1)

    return sorted(termine, key=lambda t: t.event_date), discarded


def categorize_termine(termine: list[Termin]) -> tuple[list[Termin], list[Termin], list[Termin]]:
    """Categorize events into today, this week, and later."""
    today_list = [t for t in termine if t.days_until == 0]
    this_week  = [t for t in termine if 1 <= t.days_until <= 7]
    later      = [t for t in termine if t.days_until > 7]
    return today_list, this_week, later


def format_today_section(termine: list[Termin], include_notes: bool = True) -> str:
    """Format today's events section."""
    today = date.today()
    weekday = WEEKDAYS_DE[today.weekday()]

    lines = [f"\n📌 Heute — {today.strftime('%d.%m.%Y')} ({weekday})"]

    if termine:
        for termin in termine:
            line = f"  • {termin.task}"
            if include_notes and termin.note:
                line += f" — {termin.note}"
            lines.append(line)
    else:
        lines.append("  Heute keine Termine")

    return "\n".join(lines)


def format_week_section(termine: list[Termin], include_notes: bool = False) -> str:
    """Format this week's events section."""
    if not termine:
        return ""

    lines = ["\n📅 Diese Woche"]
    for termin in termine:
        line = f"  • {termin.weekday} {termin.event_date.strftime('%d.%m.')} — {termin.task}"
        if include_notes and termin.note:
            line += f" — {termin.note}"
        lines.append(line)

    return "\n".join(lines)


def format_later_section(
    termine: list[Termin],
    limit: int = 10,
    include_notes: bool = False
) -> str:
    """Format later events section."""
    if not termine:
        return ""

    lines = ["\n📅 Spätere Termine"]
    for termin in termine[:limit]:
        line = f"  • {termin.weekday} {termin.event_date.strftime('%d.%m.%Y')} (in {termin.days_until}T) — {termin.task}"
        if include_notes and termin.note:
            line += f" — {termin.note}"
        lines.append(line)

    if len(termine) > limit:
        lines.append(f"  … ({len(termine) - limit} weitere)")

    return "\n".join(lines)


def format_warnings_section(discarded: list[str]) -> str:
    """Format warnings for unparseable lines."""
    if not discarded:
        return ""

    lines = ["\n⚠️ Nicht lesbare Zeilen:"]
    for line in discarded:
        lines.append(f"  • {line}")

    return "\n".join(lines)


def build_message(
    termine: list[Termin],
    discarded: list[str],
    heute_include_notes: bool = True,
    week_include_notes: bool = False,
    later_limit: int = 10,
    later_include_notes: bool = False,
    include_warnings: bool = True,
) -> str:
    """
    Build the complete message from pre-parsed data.

    Args:
        termine:              Pre-parsed list of Termin objects.
        discarded:            Lines that could not be parsed.
        heute_include_notes:  Show notes for today's events.
        week_include_notes:   Show notes for this-week events.
        later_limit:          Max number of later events to include (0 = omit section).
        later_include_notes:  Show notes for later events.
        include_warnings:     Append unparseable-line warnings.
    """
    today_obj = date.today()
    weekday = WEEKDAYS_DE[today_obj.weekday()]

    today_termine, week_termine, later_termine = categorize_termine(termine)

    parts = [f"Guten Morgen {GREETING_NAME} — {today_obj.strftime('%d.%m.%Y')} ({weekday})"]

    parts.append(format_today_section(today_termine, include_notes=heute_include_notes))

    week_section = format_week_section(week_termine, include_notes=week_include_notes)
    if week_section:
        parts.append(week_section)

    if later_limit > 0:
        later_section = format_later_section(later_termine, limit=later_limit, include_notes=later_include_notes)
        if later_section:
            parts.append(later_section)

    if include_warnings and discarded:
        warning_section = format_warnings_section(discarded)
        if warning_section:
            parts.append(warning_section)

    return "\n".join(parts)


# Truncation stages: progressively reduce content to stay within CHAR_LIMIT.
# Each tuple: (heute_notes, week_notes, later_limit, later_notes, include_warnings)
_TRUNCATION_STAGES = [
    (True,  False, 10, False, True),   # Stage 1 – full
    (True,  False,  5, False, True),   # Stage 2 – fewer later events
    (True,  False,  0, False, False),  # Stage 3 – no later events, no warnings
    (False, False,  0, False, False),  # Stage 4 – today only, no notes
]


def truncate_with_fallback(
    termine: list[Termin],
    discarded: list[str],
    limit: int = CHAR_LIMIT,
) -> tuple[str, int]:
    """
    Progressively truncate message until it fits within the character limit.

    Returns:
        Tuple of (message, truncation_stage) where stage 1 = no truncation.
    """
    for stage_num, (h_notes, w_notes, later_lim, l_notes, warnings) in enumerate(_TRUNCATION_STAGES, start=1):
        message = build_message(
            termine=termine,
            discarded=discarded,
            heute_include_notes=h_notes,
            week_include_notes=w_notes,
            later_limit=later_lim,
            later_include_notes=l_notes,
            include_warnings=warnings,
        )
        if len(message) <= limit:
            return message, stage_num

    # Final hard truncation
    message = build_message(
        termine=termine,
        discarded=[],
        heute_include_notes=False,
        week_include_notes=False,
        later_limit=0,
        later_include_notes=False,
        include_warnings=False,
    )
    if len(message) > limit:
        message = message[:limit - 1] + "…"

    return message, len(_TRUNCATION_STAGES) + 1


def send_via_signal(message: str, phone: str, api_key: str) -> bool:
    """
    Send message via Signal API (GET request as required by CallMeBot).

    Credentials are not logged to avoid exposure in CI logs.

    Args:
        message: Message content to send
        phone:   Signal phone number
        api_key: CallMeBot API key

    Returns:
        True if successful, False otherwise.
    """
    params = urllib.parse.urlencode({
        'phone': phone,
        'apikey': api_key,
        'text': message,
    })
    url = f"{SIGNAL_API_URL}?{params}"

    # Safe URL for logging — credentials redacted
    safe_params = urllib.parse.urlencode({
        'phone': phone,
        'apikey': '***',
        'text': f"[{len(message)} chars]",
    })
    logger.info(f"Sending to CallMeBot: {SIGNAL_API_URL}?{safe_params}")

    try:
        with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT) as response:
            response_text = response.read().decode('utf-8')

        logger.info(f"Signal API response ({response.status}): {response_text[:200]}")

        if 'Message not sent' in response_text or 'error' in response_text.lower():
            logger.error(f"Signal send failed: {response_text}")
            return False

        logger.info("Message sent successfully via Signal")
        return True

    except urllib.error.HTTPError as e:
        logger.error(f"HTTP error {e.code}: {e.reason}")
        return False
    except urllib.error.URLError as e:
        logger.error(f"Network error: {e.reason}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return False


def main() -> None:
    """Main entry point."""
    # Load credentials
    phone   = os.environ.get('SIGNAL_PHONE', '').strip()
    api_key = os.environ.get('SIGNAL_APIKEY', '').strip()

    if not phone or not api_key:
        logger.error("Missing required environment variables: SIGNAL_PHONE or SIGNAL_APIKEY")
        raise SystemExit(1)

    # Parse schedule file once
    termine, discarded = parse_schedule_file(SCHEDULE_FILE)
    logger.info(f"Loaded {len(termine)} upcoming events, {len(discarded)} discarded lines")

    # Build message (with progressive truncation if needed)
    message, stage = truncate_with_fallback(termine, discarded)

    logger.info(f"Message length: {len(message)} characters (truncation stage {stage})")
    print(message)

    if stage != 1:
        logger.warning(f"Message was truncated at stage {stage}")

    # Send via Signal
    if not send_via_signal(message, phone, api_key):
        raise SystemExit(1)


if __name__ == "__main__":
    main()