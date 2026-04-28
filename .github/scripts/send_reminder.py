import os
import urllib.request
import urllib.parse
from datetime import date, timedelta

LIMIT = 1500
today = date.today()
WOCHENTAG = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']

# schuljahr-termine.md parsen
termine = []
verworfen = []

with open('schuljahr-termine.md', 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('<!--') or line.startswith('-'):
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) < 2:
            continue
        try:
            d = date.fromisoformat(parts[0])
            aufgabe = parts[1]
            hinweis = parts[2] if len(parts) > 2 else ''
            diff = (d - today).days
            if diff < 0:
                continue
            termine.append((diff, d, WOCHENTAG[d.weekday()], aufgabe, hinweis))
        except ValueError:
            if parts[0].strip():
                verworfen.append(line)

wt_heute = WOCHENTAG[today.weekday()]

# Termine nach Sektionen aufteilen
heute_termine  = [(d, wt, a, h) for diff, d, wt, a, h in termine if diff == 0]
woche_termine  = [(diff, d, wt, a, h) for diff, d, wt, a, h in termine if 1 <= diff <= 7]
spaeter_termine = [(diff, d, wt, a, h) for diff, d, wt, a, h in termine if diff > 7]

def fmt_heute(mit_hinweis=True):
    zeilen = [f"\n\U0001f4cc Heute — {today.strftime('%d.%m.%Y')} ({wt_heute})"]
    if heute_termine:
        for d, wt, a, h in heute_termine:
            zeile = f"  • {a}"
            if mit_hinweis and h:
                zeile += f" — {h}"
            zeilen.append(zeile)
    else:
        zeilen.append("  Heute keine Termine")
    return zeilen

def fmt_woche(mit_hinweis=True):
    if not woche_termine:
        return []
    zeilen = [f"\n\U0001f4c5 Diese Woche"]
    for diff, d, wt, a, h in woche_termine:
        zeile = f"  • {wt} {d.strftime('%d.%m.')} — {a}"
        if mit_hinweis and h:
            zeile += f" — {h}"
        zeilen.append(zeile)
    return zeilen

def fmt_spaeter(limit=10, mit_hinweis=True):
    if not spaeter_termine:
        return []
    zeilen = [f"\n\U0001f52d Sp\xe4tere Termine"]
    for diff, d, wt, a, h in spaeter_termine[:limit]:
        zeile = f"  • {wt} {d.strftime('%d.%m.')} (in {diff}T) — {a}"
        if mit_hinweis and h:
            zeile += f" — {h}"
        zeilen.append(zeile)
    if len(spaeter_termine) > limit:
        zeilen.append(f"  … ({len(spaeter_termine) - limit} weitere)")
    return zeilen

def warn():
    if not verworfen:
        return []
    z = ["\n⚠️ Nicht lesbare Zeilen:"]
    for v in verworfen:
        z.append(f"  • {v}")
    return z

def baue(heute_hint=True, woche_hint=True, spaeter_limit=10, spaeter_hint=True):
    teile = [f"Guten Morgen Jens — {today.strftime('%d.%m.%Y')} ({wt_heute})"]
    teile.extend(fmt_heute(mit_hinweis=heute_hint))
    teile.extend(fmt_woche(mit_hinweis=woche_hint))
    teile.extend(fmt_spaeter(limit=spaeter_limit, mit_hinweis=spaeter_hint))
    teile.extend(warn())
    return "\n".join(teile)

# Kürzungsstufen
stufen = [
    (lambda: baue(heute_hint=True,  woche_hint=True,  spaeter_limit=10, spaeter_hint=True),  "1"),
    (lambda: baue(heute_hint=True,  woche_hint=True,  spaeter_limit=5,  spaeter_hint=True),  "2"),
    (lambda: baue(heute_hint=True,  woche_hint=True,  spaeter_limit=10, spaeter_hint=False), "3"),
    (lambda: baue(heute_hint=True,  woche_hint=True,  spaeter_limit=5,  spaeter_hint=False), "4"),
    (lambda: baue(heute_hint=True,  woche_hint=False, spaeter_limit=0,  spaeter_hint=False), "5"),
]

message = None
stufe_nr = "1"
for fn, nr in stufen:
    kandidat = fn()
    if len(kandidat) <= LIMIT:
        message = kandidat
        stufe_nr = nr
        break

if message is None:
    message = baue(heute_hint=False, woche_hint=False, spaeter_limit=0, spaeter_hint=False)
    if len(message) > LIMIT:
        message = message[:LIMIT - 1] + "…"
    stufe_nr = "6"

if stufe_nr != "1":
    message += f"\nℹ️ Nachricht gek\xfcrzt (Stufe {stufe_nr})"

print("--- Nachricht ---")
print(message)
print(f"--- {len(message)} Zeichen ---")

# Signal-Versand
phone = os.environ.get('SIGNAL_PHONE', '').strip()
apikey = os.environ.get('SIGNAL_APIKEY', '').strip()

if not phone or not apikey:
    print("FEHLER: SIGNAL_PHONE oder SIGNAL_APIKEY nicht gesetzt.")
    raise SystemExit(1)

params = urllib.parse.urlencode({'phone': phone, 'apikey': apikey, 'text': message})
url = f"https://signal.callmebot.com/signal/send.php?{params}"

try:
    with urllib.request.urlopen(url, timeout=30) as resp:
        antwort = resp.read().decode()
    print(f"Signal-Antwort: {antwort}")
    if 'error' not in antwort.lower():
        print("✅ Signal-Versand erfolgreich")
    else:
        print(f"❌ Signal-Versand fehlgeschlagen: {antwort}")
        raise SystemExit(1)
except urllib.error.URLError as e:
    print(f"❌ Netzwerkfehler: {e}")
    raise SystemExit(1)
