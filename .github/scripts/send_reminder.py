import os
import urllib.request
import urllib.parse
from datetime import date

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
header = f"Guten Morgen Jens — {today.strftime('%d.%m.%Y')} ({wt_heute})"

# A) Punkt-Erinnerungen: genau 28, 14 oder 3 Tage vorher
erinnerungen = []
for tage, label in [(28, '4 Wochen'), (14, '2 Wochen'), (3, '3 Tagen')]:
    treffer = [(d, a, h) for diff, d, wt, a, h in termine if diff == tage]
    if treffer:
        erinnerungen.append(f"\U0001f5d3 In {label} ({treffer[0][0].strftime('%d.%m.')}):")
        for d, a, h in treffer:
            erinnerungen.append(f"  • {a}" + (f" — {h}" if h else ""))

# B) Wochenvorschau: 0-7 Tage
def wochenzeilen(mit_hinweis=True):
    zeilen = []
    woche = [(diff, d, wt, a, h) for diff, d, wt, a, h in termine if 0 <= diff <= 7]
    if woche:
        zeilen.append("\n\U0001f4c5 Diese Woche (n\xe4chste 7 Tage)")
        for diff, d, wt, a, h in woche:
            tage_str = "heute" if diff == 0 else f"in {diff} Tag{'en' if diff != 1 else ''}"
            zeile = f"  • {wt} {d.strftime('%d.%m.')} ({tage_str}) — {a}"
            if mit_hinweis and h:
                zeile += f" — {h}"
            zeilen.append(zeile)
    return zeilen

# C) 6-Wochen-Übersicht: 8-42 Tage
def sechswochen(limit=10, mit_hinweis=True):
    zeilen = []
    sechs = [(diff, d, wt, a, h) for diff, d, wt, a, h in termine if 8 <= diff <= 42]
    if sechs:
        zeilen.append("\n\U0001f52d N\xe4chste 6 Wochen")
        for diff, d, wt, a, h in sechs[:limit]:
            zeile = f"  • {wt} {d.strftime('%d.%m.')} (in {diff} Tagen) — {a}"
            if mit_hinweis and h:
                zeile += f" — {h}"
            zeilen.append(zeile)
        if len(sechs) > limit:
            zeilen.append("  … (weitere ausgelassen)")
    return zeilen

def warn_zeilen():
    zeilen = []
    if verworfen:
        zeilen.append("\n⚠️ Folgende Zeilen konnten nicht gelesen werden:")
        for z in verworfen:
            zeilen.append(f"  • {z}")
    return zeilen

def baue_nachricht(mit_sechs=True, sechs_limit=10, mit_hinweisen=True):
    teile = [header]
    if erinnerungen:
        teile.append("\n\U0001f514 Heute f\xe4llige Erinnerungen")
        teile.extend(erinnerungen)
    teile.extend(wochenzeilen(mit_hinweis=mit_hinweisen))
    if mit_sechs:
        teile.extend(sechswochen(limit=sechs_limit, mit_hinweis=mit_hinweisen))
    if not erinnerungen and not wochenzeilen() and not sechswochen():
        teile.append("Heute keine anstehenden Termine in der Liste.")
    teile.extend(warn_zeilen())
    return "\n".join(teile)

# Kürzungstufen: volle Version → ohne 6W-Hinweise → 6W auf 5 → ohne 6W → ohne Hinweise überall
stufen = [
    lambda: baue_nachricht(mit_sechs=True,  sechs_limit=10, mit_hinweisen=True),
    lambda: baue_nachricht(mit_sechs=True,  sechs_limit=5,  mit_hinweisen=True),
    lambda: baue_nachricht(mit_sechs=True,  sechs_limit=10, mit_hinweisen=False),
    lambda: baue_nachricht(mit_sechs=False,                 mit_hinweisen=True),
    lambda: baue_nachricht(mit_sechs=False,                 mit_hinweisen=False),
]

message = None
for i, stufe in enumerate(stufen):
    kandidat = stufe()
    if len(kandidat) <= LIMIT:
        if i > 0:
            print(f"ℹ️ Nachricht gek\xfcrzt (Stufe {i})")
        message = kandidat
        break

if message is None:
    # Notfallkürzung: nur Header + Erinnerungen, hart abschneiden
    message = baue_nachricht(mit_sechs=False, mit_hinweisen=False)
    if len(message) > LIMIT:
        message = message[:LIMIT - 1] + "…"

print("--- Nachricht ---")
print(message)
print(f"--- {len(message)} Zeichen ---")

# Signal-Versand
phone = os.environ.get('SIGNAL_PHONE', '').strip()
apikey = os.environ.get('SIGNAL_APIKEY', '').strip()

if not phone or not apikey:
    print("FEHLER: SIGNAL_PHONE oder SIGNAL_APIKEY nicht als GitHub Secret gesetzt.")
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
