"""
Send schedule reminder via Signal API.

This script reads a markdown schedule file, formats upcoming events,
and sends a message via the CallMeBot Signal API.
Only shows today's events and events within the next 7 days.
"""

import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date

# Configuration
CHAR_LIMIT = 1000
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
    Parse markdown schedule file. Only returns events within the next 7 days.

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

                    # Only include today and next 7 days
                    if 0 <= days_until <= 7:
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


def build_message(termine: list[Termin]) -> str:
    """Build the complete message from pre-parsed data."""
    today_obj = date.today()
    weekday = WEEKDAYS_DE[today_obj.weekday()]

    today_termine = [t for t in termine if t.days_until == 0]
    week_termine  = [t for t in termine if t.days_until > 0]

    lines = [f"Guten Morgen {GREETING_NAME} - {today_obj.strftime('%d.%m.%Y')} ({weekday})"]

    # Today
    lines.append(f"\nHeute:")
    if today_termine:
        for t in today_termine:
            entry = f"  - {t.task}"
            if t.note:
                entry += f" ({t.note})"
            lines.append(entry)
    else:
        lines.append("  Keine Termine")

    # This week
    if week_termine:
        lines.append(f"\nDiese Woche:")
        for t in week_termine:
            entry = f"  - {t.weekday} {t.event_date.strftime('%d.%m.')} - {t.task}"
            if t.note:
                entry += f" ({t.note})"
            lines.append(entry)

    return "\n".join(lines)


def send_via_signal(message: str, phone: str, api_key: str) -> bool:
    """
    Send message via Signal API (GET request as required by CallMeBot).

    Works with both phone numbers (+49123...) and UUIDs (d8b500f9-ec82-...).
    Credentials are not logged to avoid exposure in CI logs.

    Args:
        message: Message content to send
        phone:   Signal phone number or UUID
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

    logger.info(f"Sending {len(message)} chars to CallMeBot")

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
    phone   = os.environ.get('SIGNAL_PHONE', '').strip()
    api_key = os.environ.get('SIGNAL_APIKEY', '').strip()

    if not phone or not api_key:
        logger.error("Missing required environment variables: SIGNAL_PHONE or SIGNAL_APIKEY")
        raise SystemExit(1)

    # Parse schedule file (only today + next 7 days)
    termine, discarded = parse_schedule_file(SCHEDULE_FILE)
    logger.info(f"Loaded {len(termine)} events (today + next 7 days)")

    if discarded:
        logger.warning(f"{len(discarded)} lines could not be parsed")

    # Build and send message
    message = build_message(termine)

    if len(message) > CHAR_LIMIT:
        message = message[:CHAR_LIMIT - 1] + "…"
        logger.warning("Message truncated to fit character limit")

    logger.info(f"Message length: {len(message)} characters")
    print(message)

    if not send_via_signal(message, phone, api_key):
        raise SystemExit(1)


if __name__ == "__main__":
    main()