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
from pathlib import Path
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
                if not line or line.startswith('#') or line.startswith('<!--') or line.startswith('-'):
                    continue
                
                parts = [p.strip() for p in line.split('|')]
                if len(parts) < 2:
                    continue
                
                try:
                    event_date = date.fromisoformat(parts[0])
                    task = parts[1]
                    note = parts[2] if len(parts) > 2 else ''
                    days_until = (event_date - today).days
                    
                    # Only include future events
                    if days_until >= 0:
                        weekday = WEEKDAYS_DE[event_date.weekday()]
                        termine.append(Termin(days_until, event_date, weekday, task, note))
                        
                except ValueError:
                    if parts[0].strip():
                        discarded.append(line)
                        
    except FileNotFoundError:
        logger.error(f"Schedule file not found: {filepath}")
        raise SystemExit(1)
    except IOError as e:
        logger.error(f"Error reading schedule file: {e}")
        raise SystemExit(1)
    
    return sorted(termine, key=lambda t: t.event_date), discarded

def categorize_termine(termine: list[Termin]) -> tuple[list[Termin], list[Termin], list[Termin]]:
    """Categorize events into today, this week, and later."""
    today = [t for t in termine if t.days_until == 0]
    this_week = [t for t in termine if 1 <= t.days_until <= 7]
    later = [t for t in termine if t.days_until > 7]
    return today, this_week, later

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
    heute_include_notes: bool = True,
    week_include_notes: bool = False,
    later_limit: int = 10,
    later_include_notes: bool = False,
    discarded: Optional[list[str]] = None
) -> str:
    """Build the complete message from all sections."""
    today_obj = date.today()
    weekday = WEEKDAYS_DE[today_obj.weekday()]
    
    lines = [f"Guten Morgen {GREETING_NAME} — {today_obj.strftime('%d.%m.%Y')} ({weekday})"]
    
    # Add sections
    today_termine, week_termine, later_termine = categorize_termine(
        parse_schedule_file(SCHEDULE_FILE)[0]
    )
    
    lines.append(format_today_section(today_termine, include_notes=heute_include_notes))
    week_section = format_week_section(week_termine, include_notes=week_include_notes)
    if week_section:
        lines.append(week_section)
    later_section = format_later_section(later_termine, limit=later_limit, include_notes=later_include_notes)
    if later_section:
        lines.append(later_section)
    
    if discarded:
        warning_section = format_warnings_section(discarded)
        if warning_section:
            lines.append(warning_section)
    
    return "\n".join(lines)

def truncate_with_fallback(limit: int = CHAR_LIMIT) -> tuple[str, int]:
    """
    Progressively truncate message until it fits within character limit.
    
    Returns:
        Tuple of (message, truncation_stage)
    """
    truncation_stages = [
        {"heute": True, "week": False, "later_limit": 10, "later": False, "stage": 1},
        {"heute": True, "week": False, "later_limit": 5, "later": False, "stage": 2},
        {"heute": True, "week": False, "later_limit": 0, "later": False, "stage": 3},
        {"heute": False, "week": False, "later_limit": 0, "later": False, "stage": 4},
    ]
    
    termine, discarded = parse_schedule_file(SCHEDULE_FILE)
    
    for stage_config in truncation_stages:
        message = build_message(
            heute_include_notes=stage_config["heute"],
            week_include_notes=stage_config["week"],
            later_limit=stage_config["later_limit"],
            later_include_notes=stage_config["later"],
            discarded=discarded
        )
        
        if len(message) <= limit:
            return message, stage_config["stage"]
    
    # Final fallback: truncate and add ellipsis
    message = build_message(
        heute_include_notes=False,
        week_include_notes=False,
        later_limit=0,
        later_include_notes=False,
        discarded=None
    )
    
    if len(message) > limit:
        message = message[:limit - 1] + "…"
    
    return message, 5

def send_via_signal(message: str, phone: str, api_key: str) -> bool:
    """Send message via Signal API.
    
    Args:
        message: Message content to send
        phone: Signal phone number
        api_key: CallMeBot API key
        
    Returns:
        True if successful, False otherwise
    """
    params = urllib.parse.urlencode({
        'phone': phone,
        'apikey': api_key,
        'text': message
    })
    
    url = f"{SIGNAL_API_URL}?{params}"
    
    try:
        with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT) as response:
            response_text = response.read().decode('utf-8')
        
        logger.info(f"Signal API response: {response_text}")
        
        if 'error' in response_text.lower():
            logger.error(f"Signal send failed: {response_text}")
            return False
        
        logger.info("Message sent successfully via Signal")
        return True
        
    except urllib.error.URLError as e:
        logger.error(f"Network error: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return False

def main():
    """Main entry point."""
    # Load credentials
    phone = os.environ.get('SIGNAL_PHONE', '').strip()
    api_key = os.environ.get('SIGNAL_APIKEY', '').strip()
    
    if not phone or not api_key:
        logger.error("Missing required environment variables: SIGNAL_PHONE or SIGNAL_APIKEY")
        raise SystemExit(1)
    
    # Build message with truncation
    message, stage = truncate_with_fallback()
    
    logger.info(f"--- Message ({len(message)} characters) ---")
    print(message)
    
    if stage != 1:
        info_msg = f"ℹ️ Nachricht gekürzt (Stufe {stage})"
        print(f"\n{info_msg}")
    
    # Send via Signal
    if not send_via_signal(message, phone, api_key):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
