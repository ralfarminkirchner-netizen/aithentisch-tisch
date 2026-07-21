# AiTHENTiSCH-Tisch

Mehrere LLMs sitzen an einem Tisch. Jeder Platz antwortet aus einer eigenen, dem
Modell-Charakter zugeordneten **Perspektive**. Die Synthese trennt streng:

- **KONSENS** — was mindestens zwei Plätze unabhängig übereinstimmend sagen
- **INTERFERENZ** — alle Widersprüche bleiben stehen, mit Platz-Namen; nichts wird geglättet
- **OFFEN** — was kein Platz beantworten konnte

`contested` ist ein zulässiger Endzustand, kein Fehler.

## Warum

Ein System erkennt seine blinden Flecken nicht allein aus sich — es braucht
organisierte Alterität. Der Tisch operationalisiert das: echte Modelle, echte
Perspektiven, echte Kosten. Zustimmung um der Zustimmung willen gilt hier als
Fehler (*Geltungsenteignung durch Rechtgeben*).

## Plätze (Auszug)

| Stufe | Plätze | Prinzip |
|-------|--------|---------|
| free | Gemini (Praktiker), OpenRouter-Free-Modelle | hohes Volumen, 0 € |
| cheap | Kimi (Analytiker + Advocatus diaboli), DeepSeek (Logiker), GLM, Qwen, MiniMax, xAI | günstig, Default |
| premium | Claude (Phänomenologe), GPT (wiss. Gutachter) | nur auf ausdrückliche Anfrage |

Die Perspektive folgt dem Modell-Charakter: Gemini wird nie für
wissenschaftlich-philosophische Fragen eingesetzt — dafür sitzen Claude und GPT
am Tisch (sparsam). Qwen und MiniMax antworten als *Stimmen aus einer anderen
Denktradition* (relational statt substanziell).

## Benutzung

```bash
python3 tisch.py "Deine Frage"                  # Default: free+cheap
python3 tisch.py "Deine Frage" --with-premium   # inkl. Claude/GPT (sparsam!)
python3 tisch.py --list-seats                   # Platz-Tafel
python3 site.py                                 # Site neu bauen (docs/)
```

Fragen für die tägliche automatische Runde: eine Zeile in `warteschlange.txt`.

## Automatisierung (Cron)

| Job | Zeitplan | Funktion |
|-----|----------|----------|
| Sitz-Watchdog | täglich 07:00 | testet aktive Plätze, meldet nur Zustandswechsel |
| Warteschlange | täglich 08:00 | arbeitet `warteschlange.txt` ab (nie Premium) |
| OR-Free-Refresh | So 06:00 | hält OpenRouter-Free-Modell-IDs aktuell (0 Tokens) |

## Veröffentlichung

Die Site (docs/, GitHub Pages) rendert **nur** Tischrunden, deren Wiki-Frontmatter
`public: true` trägt. Alles andere bleibt privat — der Tisch behandelt auch
interne Manuskripte. Opt-in, nicht Opt-out.

Zur Site gehören außerdem:

- **Interferenz-Matrix** (`matrix.html`) — Co-Konsens-Paare und Divergenz-Quote
  pro Platz: der empirische Nachweis, ob die Perspektiven echte Diversität liefern.
- **Atom-Feed** (`atom.xml`) — neue öffentliche Runden per Feedreader abonnierbar.
- **Auto-Publikation** — der Warteschlangen-Cron baut die Site nach jeder Runde
  neu und pusht sie selbständig.

## Öffentlicher Eingangskanal

Fragen können als **GitHub-Issue mit Label `tischfrage`** gestellt werden.
Der morgendliche Lauf übernimmt sie in die Warteschlange (Label `eingeplant`)
und der Tisch antwortet — Ergebnis erscheint auf der Site, sofern die Runde
`public: true` erhält (menschliche Freigabe, kein Automatismus).

## Verfassung

- Kein Platz benutzt Werkzeuge oder Websuche.
- Unsicherheit wird als Unsicherheit markiert.
- Rohantworten werden vollständig archiviert (`~/wiki/raw/tisch/`).
- Die Synthese darf nicht vermitteln, was die Plätze nicht vermittelt haben.

Status: proposed. Kanon setzt nur Ralf.
