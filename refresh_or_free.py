#!/usr/bin/env python3
"""
OpenRouter-Free-Modelle aktuell halten — kostenlos.
Der Models-Endpunkt ist oeffentlich, es werden KEINE Tokens verbraucht.

Prueft, ob die in tisch.py hinterlegten :free-Modell-IDs (or-llama, or-mistral)
noch existieren. Wenn eine ID verfallen ist, wird sie durch die aktuellste
passende Free-ID ersetzt. Silent, wenn nichts zu tun ist.
"""
import json, re, sys, urllib.request
from pathlib import Path

TISCH = Path(__file__).parent / "tisch.py"
WISH = {"or-nemotron": "nemotron", "or-gptoss": "gpt-oss"}


def version_key(model_id: str):
    """Extrahiert Zahlenbloecke fuer 'neueste zuerst'-Sortierung (7b < 24b < 70b < 235b)."""
    nums = re.findall(r"\d+", model_id)
    return tuple(int(x) for x in nums) if nums else (0,)


def main():
    try:
        req = urllib.request.Request("https://openrouter.ai/api/v1/models",
                                     headers={"User-Agent": "aithentisch-tisch/2.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
    except Exception as e:
        print(f"OR-Refresh FEHLER (Netz/API): {e}")
        sys.exit(1)

    free = [m["id"] for m in data.get("data", []) if m.get("id", "").endswith(":free")]
    if not free:
        print("OR-Refresh FEHLER: keine :free-Modelle gefunden — API-Antwort unerwartet.")
        sys.exit(1)

    src = TISCH.read_text(encoding="utf-8")
    changed = []
    for seat, needle in WISH.items():
        m = re.search(rf'"{seat}": \{{\s*"provider": "openrouter",\s*"model": "([^"]+)"', src)
        if not m:
            continue
        current = m.group(1)
        if current in free:
            continue  # aktuelle ID lebt noch — kein Eingriff, kein Churn
        cands = [i for i in free if needle in i.lower()]
        if not cands:
            print(f"OR-Refresh WARNUNG: {seat}-ID '{current}' verfallen, kein Ersatz mit '{needle}' gefunden.")
            continue
        best = sorted(cands, key=version_key)[-1]
        src = src.replace(f'"model": "{current}"', f'"model": "{best}"', 1)
        changed.append(f"{seat}: {current} -> {best}")

    if changed:
        TISCH.write_text(src, encoding="utf-8")
        print("OR-Free-Modelle aktualisiert: " + "; ".join(changed))


if __name__ == "__main__":
    main()
