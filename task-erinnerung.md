# Tägliche Schuljahres-Erinnerung

Dieser Task wird täglich um 07:00 Uhr von Cowork ausgeführt.

## Was der Task tut

1. Liest `schuljahr-terme.md` aus diesem Repo (raw GitHub URL)
2. Berechnet Termine in 4 Wochen, 2 Wochen, 3 Tagen sowie Wochenvorschau und 6-Wochen-Übersicht
3. Sendet die Zusammenfassung per Signal (CallMeBot API)

## Terminformat

```
YYYY-MM-DD | Aufgabe | (optional) Hinweis
```

Zeilen mit `#` oder leerem Inhalt werden ignoriert.

## Signal-Credentials

Werden aus `signal-credentials.txt` im lokalen Cowork-Ordner gelesen:
```
phone=+49...
apikey=...
```
