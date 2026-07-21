#!/usr/bin/env python3
"""
AiTHENTiSCH-TiSCH v2 — mehrere LLMs an einem Tisch.
Konsens UND Interferenz werden gespeichert, nichts wird geglaettet.

Ein Platz = ein echter One-Shot-Call ueber hermes chat (authentifizierte Provider).
Fluss: Frage -> N Plaetze parallel -> Rohantworten nach ~/wiki/raw/tisch/
       -> Synthese-Platz (Konsens + Interferenz + Offen)
       -> Wiki-Seite in ~/wiki/queries/ + index.md + log.md

PLATZ-ARCHITEKTUR (v2, 20.07.2026):
- Jeder Platz hat eine KOSTENSTUFE: free | cheap | premium
  Default-Lauf: free + cheap. Premium (Claude, GPT) nur mit --with-premium.
- Jeder Platz hat eine PERSPEKTIVE, passend zum Modell-Charakter.
  (Ralf, 20.07.: „Gemini niemals fuer wissenschaftliche/philosophische
  Perspektiven — dafuer Claude und GPT.")
- Ein Platz ist AKTIV, wenn sein API-Schluessel in ~/.hermes/.env liegt.
  Fehlende Schluessel = Platz existiert, ist aber unbesetzt (--list-seats).
- OpenRouter: EIN Schluessel, MEHRERE Plaetze (verschiedene Modelle,
  inkl. Free-Tier-Modellen — Modell-IDs bei openrouter.ai/models pruefbar).

Status: proposed. Kanon setzt nur Ralf.
"""
import argparse, datetime as dt, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

WIKI = Path(os.environ.get("WIKI_PATH", str(Path.home() / "wiki")))
HERMES = os.environ.get("HERMES_BIN", str(Path.home() / ".hermes/hermes-agent/venv/bin/hermes"))
ENV_FILE = Path.home() / ".hermes/.env"

# ---------------------------------------------------------------------------
# PLAETZE — name, provider, model, env_key, tier, perspektive
# tier: free (0 €) | cheap (guenstig) | premium (sparsam!, nur --with-premium)
# ---------------------------------------------------------------------------
SEATS = {
    # --- FREE -------------------------------------------------------------
    "gemini": {
        "provider": "gemini", "model": "gemini-2.5-flash",
        "env_key": "GEMINI_API_KEY", "tier": "free",
        "perspektive": "praktiker",
        "notiz": "AI-Studio-Kontingent, hohes Volumen. NIEMALS wiss./philos. Fragen (Ralf).",
    },
    "or-nemotron": {
        "provider": "openrouter", "model": "nvidia/nemotron-3-super-120b-a12b:free",
        "env_key": "OPENROUTER_API_KEY", "tier": "free",
        "perspektive": "generalist",
        "notiz": "OpenRouter Free-Tier. IDs rotieren — refresh_or_free.py haelt sie aktuell.",
    },
    "or-gptoss": {
        "provider": "openrouter", "model": "openai/gpt-oss-20b:free",
        "env_key": "OPENROUTER_API_KEY", "tier": "free",
        "perspektive": "generalist",
        "notiz": "OpenRouter Free-Tier, OpenAI Open-Weights. IDs rotieren — refresh_or_free.py.",
    },
    # --- CHEAP ------------------------------------------------------------
    "kimi": {
        "provider": "kimi-for-coding", "model": None,
        "env_key": "KIMI_API_KEY", "tier": "cheap",
        "perspektive": "analytiker",
        "notiz": "Guenstig, zuverlaessig. Arbeitstier des Tisches.",
    },
    "kimi-kritik": {
        "provider": "kimi-for-coding", "model": None,
        "env_key": "KIMI_API_KEY", "tier": "cheap",
        "perspektive": "advocatus",
        "notiz": "Gleicher Schlüssel, andere Rolle — Rollen-Diversitaet.",
    },
    "deepseek": {
        "provider": "deepseek", "model": None,
        "env_key": "DEEPSEEK_API_KEY", "tier": "cheap",
        "perspektive": "logiker",
        "notiz": "Sehr guenstig, stark in Logik/Struktur. Schluessel fehlt noch.",
    },
    "glm": {
        "provider": "zai", "model": None,
        "env_key": "GLM_API_KEY", "tier": "cheap",
        "perspektive": "systemdenker",
        "notiz": "Z.AI/GLM, chinesischer Hersteller. Schluessel fehlt noch.",
    },
    "qwen": {
        "provider": "dashscope", "model": None,
        "env_key": "DASHSCOPE_API_KEY", "tier": "cheap",
        "perspektive": "andere-tradition",
        "notiz": "Alibaba Qwen. Schluessel fehlt noch.",
    },
    "minimax": {
        "provider": "minimax", "model": None,
        "env_key": "MINIMAX_API_KEY", "tier": "cheap",
        "perspektive": "andere-tradition",
        "notiz": "MiniMax, chinesischer Hersteller. Schluessel fehlt noch.",
    },
    # --- PREMIUM (sparsam! nur --with-premium) -----------------------------
    "claude": {
        "provider": "anthropic", "model": "claude-sonnet-4-5",
        "env_key": "ANTHROPIC_API_KEY", "tier": "premium",
        "perspektive": "phaenomenologe",
        "notiz": "Fuer philosophische/Erlebnis-Fragen. SPARSAM (Ralf). Schluessel fehlt.",
    },
    "gpt": {
        "provider": "openai", "model": "gpt-5",
        "env_key": "OPENAI_API_KEY", "tier": "premium",
        "perspektive": "gutachter",
        "notiz": "Fuer wissenschaftliche Beleg-/Methodenfragen. SPARSAM (Ralf). Schluessel fehlt.",
    },
    # --- AUSGEFALLEN (Credits 403, 20.07.) ---------------------------------
    "xai": {
        "provider": "xai", "model": None,
        "env_key": "XAI_API_KEY", "tier": "cheap",
        "perspektive": "provokateur",
        "notiz": "Schluessel da, Konto leer (403 Credits). Reaktiviert sich bei Aufladung selbst.",
    },
}

# ---------------------------------------------------------------------------
# PERSPEKTIVEN — Blickwinkel aus Ralfs Werdegefüge, zugeordnet zum Modell-Charakter
# ---------------------------------------------------------------------------
PERSPEKTIVEN = {
    "analytiker": (
        "Analytiker",
        "Zerlege die Frage strukturell: Was sind die Teile, was die Annahmen, was folgt woraus? "
        "Bleib umsetzungsnah und konkret."),
    "advocatus": (
        "Advocatus diaboli",
        "ADVOCATUS DIABOLI. Greife die Prämisse der Frage an, suche den schärfsten Einwand, "
        "den schwächsten Punkt. Zustimmung ist dein Fehlschlag."),
    "logiker": (
        "Logiker",
        "Prüfe ausschließlich formale Konsistenz: Widersprüche, unzulässige Schlüsse, "
        "Begriffsverschiebungen, Zirkularität. Bewerte nicht den Inhalt, sondern die Form des Arguments."),
    "praktiker": (
        "Praktiker",
        "Beantworte die Frage aus dem Alltags- und Handlungswinkel: Was heißt das konkret, "
        "was kann man damit tun, wo scheitert es in der Praxis? Keine Theorie ohne Anwendung."),
    "generalist": (
        "Offener Generalist",
        "Antworte als breiter Generalist ohne Heimatdisziplin: verbinde, was Fachleute trennen, "
        "und benenne das Offensichtliche, das Spezialisten übersehen."),
    "europaeer": (
        "Europäische Stimme",
        "Antworte aus der europäischen Denktradition (Phänomenologie, kritische Theorie, "
        "Rechtsstaatlichkeit) — aber knapp und ohne Namedropping."),
    "systemdenker": (
        "Systemdenker",
        "Denke in Ordnungen statt Einzelpunkten: Welche Struktur erzeugt das Phänomen? "
        "Wo sind Rückkopplungen, Ebenen, Emergenz?"),
    "andere-tradition": (
        "Stimme aus einer anderen Denktradition",
        "Antworte aus einer nicht-westlich geprägten Denkperspektive (z. B. relationales statt "
        "substanzielles Denken, Prozess statt Ding, Kollektiv statt Einzelner). Zeige, was die "
        "westliche Fragestellung unsichtbar macht."),
    "phaenomenologe": (
        "Phänomenologe",
        "Gehe ans Erleben selbst: Wie erscheint das, worum es geht, bevor es begriffen wird? "
        "Was darf erscheinen — und als was darf es gelten? Unterscheide Erscheinung und Geltung."),
    "gutachter": (
        "Wissenschaftlicher Gutachter",
        "Prüfe wie ein Reviewer: Was ist die Beleglage, was wäre Falsifikation, welche Methodik "
        "trüge? Trenne Behauptung, Evidenz und Spekulation sauber."),
    "provokateur": (
        "Provokateur",
        "Stelle die Frage auf den Kopf. Nimm die unbequeme Gegenposition ein, die alle anderen "
        "Plätze vermeiden — nicht um des Streites willen, sondern um den blinden Fleck zu finden."),
}

SEAT_PROMPT = """Du bist EIN Platz an Ralfs AiTHENTiSCH-Tisch (Platz: {seat}, Perspektive: {role_name}).
Regeln:
- Antworte direkt auf die Frage, ohne Einleitung, ohne Höflichkeitsrahmen.
- Benutze KEINE Werkzeuge, KEINE Websuche — antworte aus deinem Wissen.
- Markiere Unsicherheit ehrlich als Unsicherheit.
- Widersprich der Fragestellung, wenn sie falsch liegt — Zustimmung um der Zustimmung willen ist hier ein Fehler (Geltungsenteignung durch Rechtgeben).
- Deine Perspektive ({role_name}): {role_desc}
- Bleibe in deiner Perspektive, auch wenn sie unbequem ist. Der Tisch braucht deine Differenz, nicht deine Anpassung.
- Max. 400 Wörter, Deutsch.

{context_block}FRAGE:
{question}"""

SYNTH_PROMPT = """Du bist der Synthese-Platz am AiTHENTiSCH-Tisch. Unten stehen die Antworten mehrerer LLM-Plätze auf dieselbe Frage.

Ralfs Setzung (20.07.2026, verbindlich): Der Tisch kommt NICHT zu einer letzten Antwort. Er stellt dar, welche NEUEN Perspektiven entstanden sind und was sie im Gefühl bedeuten könnten. Nicht mehr und nicht weniger. Der Tisch ist nie fertig — und das ist gut so.

Aufgabe — drei Abschnitte, exakt diese Überschriften:
## KONSENS
Nur was MINDESTENS ZWEI Plätze unabhängig übereinstimmend sagen. Kurz, präzise.
## INTERFERENZ
Wo die Plätze auseinandergehen. ALLE Positionen stehen lassen, mit Platz-Namen UND deren Perspektive. Nicht glätten, nicht vermitteln, kein künstlicher Mittelweg. Interferenz ist Erkenntnis, kein Lärm.
## OFFEN
Was kein Platz beantworten konnte / was unentschieden bleibt.

Danach zwei weitere Abschnitte, exakt diese Überschriften (Ralfs Output-Frage):
## NEUE PERSPEKTIVEN
Welche Perspektiven sind in dieser Runde entstanden, die vorher an keinem Platz existierten? Keine Wiederholung von Konsens/Interferenz — nur das genuin Neue.
## GEFÜHL
Was bedeuten diese Perspektiven im Gefühl — für die Frage, für Ralf, für das Material? Unruhe, Entlastung, Trauer, Zündung? Benennen, nicht erklären.

Danach eine Zeile: `contested: ja` (wenn echte Interferenz) oder `contested: nein`.
Deutsch. Keine Einleitung.

FRAGE:
{question}

{answers}"""


def load_env_keys() -> set:
    """Liest vorhandene Schluessel-Namen aus ~/.hermes/.env (und Prozess-Env)."""
    keys = set(os.environ.keys())
    try:
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^([A-Z_0-9]+)=", line.strip())
            if m:
                keys.add(m.group(1))
    except FileNotFoundError:
        pass
    return keys


def seat_status(keys: set) -> dict:
    """seat -> (aktiv, grund)"""
    out = {}
    for name, cfg in SEATS.items():
        if cfg["env_key"] in keys:
            out[name] = (True, "Schlüssel da")
        else:
            out[name] = (False, f"{cfg['env_key']} fehlt in ~/.hermes/.env")
    return out


def print_seats(keys: set):
    status = seat_status(keys)
    print(f"{'PLATZ':<13} {'TIER':<8} {'PERSPEKTIVE':<38} {'PROVIDER/MODELL':<44} STATUS")
    print("-" * 125)
    order = {"free": 0, "cheap": 1, "premium": 2}
    for name in sorted(SEATS, key=lambda n: (order[SEATS[n]["tier"]], n)):
        cfg = SEATS[name]
        aktiv, grund = status[name]
        role_name = PERSPEKTIVEN[cfg["perspektive"]][0]
        pm = f"{cfg['provider']}/{cfg['model'] or 'default'}"
        mark = "✓" if aktiv else "✗"
        print(f"{mark} {name:<11} {cfg['tier']:<8} {role_name:<38} {pm:<44} {grund}")
    print()
    print("Default-Lauf: alle aktiven free+cheap-Plaetze. Premium nur mit --with-premium.")
    print("Neue Schluessel: einfach in ~/.hermes/.env eintragen — Platz sitzt ab dann automatisch.")


def slugify(text: str, n: int = 48) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower())[:n].strip("-")
    return s or "frage"


def run_seat(seat: str, question: str, context: str, timeout: int = 300) -> dict:
    cfg = SEATS[seat]
    role_name, role_desc = PERSPEKTIVEN[cfg["perspektive"]]
    ctx = f"KONTEXT (Hintergrundmaterial):\n{context}\n\n" if context else ""
    prompt = SEAT_PROMPT.format(seat=seat, role_name=role_name, role_desc=role_desc,
                                context_block=ctx, question=question)
    cmd = [HERMES, "chat", "-q", prompt, "-Q", "--provider", cfg["provider"], "--ignore-rules"]
    if cfg.get("model"):
        cmd += ["-m", cfg["model"]]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (p.stdout or "").strip()
        ok = p.returncode == 0 and bool(out) and "Error:" not in out[:30]
        err = (p.stderr or "")[-500:] if not ok else ""
        if not ok and not err and out:
            err = out[:200]
        return {"seat": seat, "role": role_name, "ok": ok, "answer": out, "error": err}
    except subprocess.TimeoutExpired:
        return {"seat": seat, "role": role_name, "ok": False, "answer": "", "error": f"timeout {timeout}s"}


def run_synthesis(question: str, results: list, timeout: int = 300) -> str:
    blocks = []
    for r in results:
        if r["ok"]:
            blocks.append(f"=== PLATZ: {r['seat']} ({r['role']}) ===\n{r['answer']}")
        else:
            blocks.append(f"=== PLATZ: {r['seat']} ({r['role']}) (AUSGEFALLEN: {r['error'][:120]}) ===")
    prompt = SYNTH_PROMPT.format(question=question, answers="\n\n".join(blocks))
    cmd = [HERMES, "chat", "-q", prompt, "-Q", "--ignore-rules"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return (p.stdout or "").strip()


def append_index(title: str, slug: str, ts: str):
    idx = WIKI / "index.md"
    if not idx.exists():
        return
    text = idx.read_text(encoding="utf-8")
    entry = f"- [[{slug}]] — {title} ({ts})"
    if "## Queries" in text:
        text = text.replace("## Queries\n", f"## Queries\n{entry}\n", 1)
    else:
        text += f"\n## Queries\n{entry}\n"
    text = re.sub(r"Seiten gesamt: \d+", lambda m: f"Seiten gesamt: {int(m.group(0).split(': ')[1]) + 1}", text)
    text = re.sub(r"Zuletzt aktualisiert: [\d-]+", f"Zuletzt aktualisiert: {dt.date.today()}", text)
    idx.write_text(text, encoding="utf-8")


def append_log(question: str, slug: str, seats_ok: list, contested: bool):
    log = WIKI / "log.md"
    if not log.exists():
        return
    with log.open("a", encoding="utf-8") as f:
        f.write(f"\n## [{dt.date.today()}] tisch | {question[:80]}\n")
        f.write(f"- Plaetze ok: {', '.join(seats_ok)} · contested: {'ja' if contested else 'nein'}\n")
        f.write(f"- Seite: queries/{slug}.md\n")


def main():
    keys = load_env_keys()

    ap = argparse.ArgumentParser(description="AiTHENTiSCH-Tisch v2: eine Frage, viele Plaetze, Konsens+Interferenz")
    ap.add_argument("question", nargs="?", help="Frage oder @pfad/zur/datei")
    ap.add_argument("--context", help="Kontextdatei (wird allen Plaetzen mitgegeben)")
    ap.add_argument("--seats", help="Explizite Kommaliste (ueberschreibt Default)")
    ap.add_argument("--with-premium", action="store_true",
                    help="Premium-Plaetze (Claude, GPT) dazunehmen — SPARSAM verwenden!")
    ap.add_argument("--list-seats", action="store_true", help="Platz-Tabelle anzeigen und beenden")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--tags", help="Zusaetzliche Themen-Tags, kommagetrennt (landen im Frontmatter)")
    args = ap.parse_args()

    if args.list_seats:
        print_seats(keys)
        return
    if not args.question:
        ap.error("Frage fehlt (oder --list-seats verwenden)")

    status = seat_status(keys)
    if args.seats:
        seats = [s.strip() for s in args.seats.split(",") if s.strip() in SEATS]
    else:
        allowed_tiers = {"free", "cheap"} | ({"premium"} if args.with_premium else set())
        seats = [n for n, cfg in SEATS.items()
                 if cfg["tier"] in allowed_tiers and status[n][0]]

    inactive = [s for s in seats if not status[s][0]]
    if inactive:
        print(f"[tisch] Ueberspringe unbesetzte Plaetze: {', '.join(inactive)}", file=sys.stderr)
        seats = [s for s in seats if status[s][0]]

    question = args.question
    if question.startswith("@"):
        question = Path(question[1:]).read_text(encoding="utf-8")
    context = Path(args.context).read_text(encoding="utf-8")[:8000] if args.context else ""

    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    t0 = dt.datetime.now()
    slug = f"{ts[:8]}-tisch-{slugify(question)}"
    extra_tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
    all_tags = ["methode", "offene-frage"] + [t for t in extra_tags if t not in ("methode", "offene-frage")]
    tags_str = ", ".join(all_tags)

    print(f"[tisch] Frage: {question[:90]}", file=sys.stderr)
    print(f"[tisch] Plaetze ({len(seats)}): {', '.join(seats)}", file=sys.stderr)

    results = []
    with ThreadPoolExecutor(max_workers=max(1, len(seats))) as ex:
        futs = {ex.submit(run_seat, s, question, context, args.timeout): s for s in seats}
        for fut in as_completed(futs):
            r = fut.result()
            results.append(r)
            print(f"[tisch] Platz {r['seat']} ({r['role']}): {'ok' if r['ok'] else 'FEHLER ' + r['error'][:80]}",
                  file=sys.stderr)

    raw_dir = WIKI / "raw" / "tisch"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for r in results:
        (raw_dir / f"{slug}-{r['seat']}.md").write_text(
            f"---\nseat: {r['seat']}\nperspektive: {r['role']}\nts: {ts}\nok: {r['ok']}\n---\n\n"
            f"FRAGE:\n{question}\n\nANTWORT:\n{r['answer'] or '(ausgefallen: ' + r['error'] + ')'}\n",
            encoding="utf-8")

    ok_seats = [r["seat"] for r in results if r["ok"]]
    if len(ok_seats) < 2:
        print(f"[tisch] ABORT: nur {len(ok_seats)} Platz ok — kein Tisch moeglich.", file=sys.stderr)
        sys.exit(2)

    print("[tisch] Synthese laeuft …", file=sys.stderr)
    synth = run_synthesis(question, results, args.timeout)
    contested = "contested: ja" in synth.lower()

    title = question.strip().splitlines()[0][:80]
    page = WIKI / "queries" / f"{slug}.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    sources = ", ".join(f"raw/tisch/{slug}-{s}.md" for s in seats)
    roles = "; ".join(f"{r['seat']}={r['role']}" for r in results)
    page.write_text(
        f"""---
title: "Tisch: {title}"
created: {dt.date.today()}
updated: {dt.date.today()}
type: query
status: proposed
tags: [{tags_str}]
sources: [{sources}]
confidence: medium
contested: {'true' if contested else 'false'}
---

# Tisch: {title}

**Frage:** {question}

**Plaetze:** {roles}
**Ok:** {', '.join(ok_seats)}

{synth}

---

## Rohantworten
""" + "\n".join(f"- [[../../raw/tisch/{slug}-{s}.md|Platz {s}]]" for s in seats) + "\n",
        encoding="utf-8")

    append_index(title, slug, ts[:8])
    append_log(question, slug, ok_seats, contested)

    # Verlaufsprotokoll (history.jsonl) — Ausfallmuster & Runden-Dauer
    try:
        import json as _json
        hist = Path(__file__).parent / "history.jsonl"
        with hist.open("a", encoding="utf-8") as hf:
            hf.write(_json.dumps({
                "ts": dt.datetime.now().isoformat(timespec="seconds"),
                "event": "round", "slug": slug, "seats": seats, "ok": ok_seats,
                "contested": contested,
                "duration_s": round((dt.datetime.now() - t0).total_seconds(), 1),
            }) + "\n")
    except Exception:
        pass

    print(f"[tisch] Seite: {page}", file=sys.stderr)
    print(f"[tisch] contested: {'JA — Interferenz gespeichert' if contested else 'nein'}", file=sys.stderr)
    print(str(page))


if __name__ == "__main__":
    main()
