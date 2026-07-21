#!/usr/bin/env python3
"""
site.py — baut die statische Tisch-Site (GitHub Pages) aus ~/wiki/queries + ~/wiki/raw/tisch.

Rendert:
  docs/index.html            — Tisch-Übersicht (letzte Runden, contested-Quote)
  docs/runden/<slug>.html    — eine Seite pro Tischrunde (Konsens/Interferenz/Offen + Rohantworten)
  docs/plaetze.html          — Platz-Tafel (Perspektiven, Kostenstufen, Status)

Kein Framework, keine Dependencies — Python-Stdlib, dunkles Theme, deutsch.
Status: proposed. Kanon setzt nur Ralf.
"""
import datetime as dt, html, re, sys, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import tisch  # SEATS, PERSPEKTIVEN, load_env_keys, seat_status

WIKI = Path(os.environ.get("WIKI_PATH", str(Path.home() / "wiki")))
DOCS = Path(__file__).parent / "docs"

# Giscus (Kommentare via GitHub Discussions): aktiv, sobald die Giscus-App im Repo
# installiert ist, Discussions an sind und hier die Kategorie-ID eingetragen wird.
GISCUS_REPO_ID = "1308038765"
GISCUS_CATEGORY_ID = ""  # TODO nach App-Installation eintragen

STYLE = """
:root { --bg:#0d1117; --fg:#e6edf3; --mut:#8b949e; --acc:#58a6ff; --ok:#3fb950; --warn:#d29922; --bad:#f85149; --card:#161b22; --line:#30363d; }
* { box-sizing:border-box; }
body { background:var(--bg); color:var(--fg); font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; margin:0; }
.wrap { max-width:900px; margin:0 auto; padding:2rem 1.2rem 4rem; }
h1 { font-size:1.9rem; margin:.2em 0 .1em; } h2 { color:var(--acc); border-bottom:1px solid var(--line); padding-bottom:.3em; margin-top:2em; }
h3 { color:var(--fg); margin-top:1.4em; }
a { color:var(--acc); text-decoration:none; } a:hover { text-decoration:underline; }
.mut { color:var(--mut); } .small { font-size:.85rem; }
.card { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:1rem 1.2rem; margin:1rem 0; }
table { border-collapse:collapse; width:100%; } th,td { border:1px solid var(--line); padding:.45rem .6rem; text-align:left; vertical-align:top; }
th { background:var(--card); }
.tag { display:inline-block; border:1px solid var(--line); border-radius:20px; padding:.05rem .6rem; font-size:.78rem; margin:.1rem .15rem .1rem 0; color:var(--mut); }
.ok { color:var(--ok); } .warn { color:var(--warn); } .bad { color:var(--bad); }
.contested { border-left:4px solid var(--warn); } .clean { border-left:4px solid var(--ok); }
pre { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:1rem; overflow-x:auto; white-space:pre-wrap; }
blockquote { border-left:3px solid var(--acc); margin-left:0; padding-left:1rem; color:var(--mut); }
details { margin:.5rem 0; } summary { cursor:pointer; color:var(--acc); }
"""


def md_lite(text: str) -> str:
    """Minimaler Markdown→HTML-Renderer (Absätze, Listen, Überschriften, **fett**, `code`, > zitat)."""
    out, in_list = [], False
    for line in text.splitlines():
        esc = html.escape(line)
        esc = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", esc)
        esc = re.sub(r"`(.+?)`", r"<code>\1</code>", esc)
        if line.startswith("## "):
            if in_list: out.append("</ul>"); in_list = False
            out.append(f"<h3>{html.escape(line[3:])}</h3>")
        elif line.startswith("- "):
            if not in_list: out.append("<ul>"); in_list = True
            out.append(f"<li>{esc[2:] if esc.startswith('- ') else esc}</li>")
        elif line.startswith("> "):
            if in_list: out.append("</ul>"); in_list = False
            out.append(f"<blockquote>{html.escape(line[2:])}</blockquote>")
        elif line.strip() == "---":
            if in_list: out.append("</ul>"); in_list = False
            out.append("<hr>")
        elif line.strip() == "":
            if in_list: out.append("</ul>"); in_list = False
        else:
            if in_list: out.append("</ul>"); in_list = False
            out.append(f"<p>{esc}</p>")
    if in_list: out.append("</ul>")
    return "\n".join(out)


def page(title: str, body: str, subtitle: str = "") -> str:
    sub = f'<p class="mut">{html.escape(subtitle)}</p>' if subtitle else ""
    return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title) if title.startswith("AiTHENTiSCH") else html.escape(title) + " · AiTHENTiSCH-Tisch"}</title>
<link rel="alternate" type="application/atom+xml" title="AiTHENTiSCH-Tisch" href="{'' if title.startswith('AiTHENTiSCH') else '../'}atom.xml">
<style>{STYLE}</style></head>
<body><div class="wrap">
<p class="small mut"><a href="../index.html">← Übersicht</a> · <a href="../plaetze.html">Plätze</a> · <a href="../matrix.html">Interferenz-Matrix</a></p>
<h1>{html.escape(title)}</h1>{sub}
{body}
<hr><p class="small mut">Erzeugt {dt.date.today()} · AiTHENTiSCH-Tisch · Interferenz ist Erkenntnis, kein Lärm.</p>
</div></body></html>"""


def top_page(title: str, body: str, subtitle: str = "") -> str:
    # Variante für Seiten direkt in docs/ (eine Ebene höher verlinkt)
    return page(title, body, subtitle).replace('href="../', 'href="')


def parse_query(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    fm = {}
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip()
        text = text[m.end():]
    frage = ""
    qm = re.search(r"\*\*Frage:\*\*\s*(.+)", text)
    if qm: frage = qm.group(1).strip()
    tags = []
    tm = re.match(r"\[(.*)\]", fm.get("tags", ""))
    if tm:
        tags = [t.strip() for t in tm.group(1).split(",") if t.strip()]
    return {"slug": path.stem, "fm": fm, "frage": frage, "body": text, "tags": tags,
            "contested": fm.get("contested", "false") == "true",
            "created": fm.get("created", "")}


def build_matrix(entries):
    """Interferenz-Matrix: Co-Konsens-Paare + Divergenz-Quote pro Platz.
    Ehrliche Proxy-Metrik aus den Synthese-Strukturen (kein Embeddings-Voodoo)."""
    from collections import Counter
    co = Counter()          # (a,b) -> wie oft gemeinsam in einer KONSENS-Zeile
    part = Counter()        # platz -> Runden mit Antwort
    div = Counter()         # platz -> Runden, in denen er in INTERFERENZ auftaucht
    seats = list(tisch.SEATS.keys())
    for e in entries:
        body = e["body"]
        konsens_m = re.search(r"## KONSENS\n(.*?)## INTERFERENZ", body, re.S)
        interf_m = re.search(r"## INTERFERENZ\n(.*?)(## OFFEN|contested:)", body, re.S)
        present = set()
        for s in seats:
            if re.search(rf"\|Platz {re.escape(s)}\]\]", body) or f"-{s}.md" in body:
                present.add(s)
        for s in present:
            part[s] += 1
        if konsens_m:
            for line in konsens_m.group(1).splitlines():
                found = [s for s in seats if re.search(rf"\b{re.escape(s)}\b", line)]
                for i in range(len(found)):
                    for j in range(i + 1, len(found)):
                        co[tuple(sorted((found[i], found[j])))] += 1
        if interf_m:
            for s in seats:
                if re.search(rf"\b{re.escape(s)}\b", interf_m.group(1)):
                    div[s] += 1
    used = [s for s in seats if part[s] > 0]
    if not used:
        return "", ""
    # Matrix-Tabelle (obere Dreiecksform)
    header = "".join(f"<th class='small'>{s}</th>" for s in used)
    mrows = ""
    for a in used:
        cells = f"<td><strong>{a}</strong><br><span class='small mut'>{part[a]} Runden</span></td>"
        for b in used:
            if a == b:
                cells += "<td style='background:var(--card)' class='mut'>—</td>"
            else:
                n = co.get(tuple(sorted((a, b))), 0)
                cells += f"<td>{n if n else ''}</td>"
        mrows += f"<tr>{cells}</tr>"
    divrows = "".join(
        f"<tr><td><strong>{s}</strong></td><td>{part[s]}</td><td>{div.get(s,0)}</td>"
        f"<td>{round(100*div.get(s,0)/part[s]) if part[s] else 0}%</td>"
        f"<td class='small mut'>{html.escape(tisch.PERSPEKTIVEN[tisch.SEATS[s]['perspektive']][0])}</td></tr>"
        for s in sorted(used, key=lambda x: -div.get(x, 0)))
    matrix_html = f"""
<h2>Co-Konsens-Matrix</h2>
<p class="mut">Wie oft zwei Plätze in derselben KONSENS-Zeile genannt wurden (über {len(entries)} öffentliche Runden).
Hohe Werte = die beiden landen oft gemeinsam im Konsens. Niedrige = sie befruchten sich eher durch Differenz.</p>
<table><tr><th></th>{header}</tr>{mrows}</table>
<h2>Divergenz-Profil</h2>
<p class="mut">Wie oft ein Platz im INTERFERENZ-Abschnitt auftaucht — der Tisch braucht Plätze, die widersprechen.</p>
<table><tr><th>Platz</th><th>Runden</th><th>divergiert</th><th>Quote</th><th>Perspektive</th></tr>{divrows}</table>
"""
    return matrix_html, used


def build_atom(entries):
    items = ""
    for e in entries[:20]:
        link = f"https://ralfarminkirchner-netizen.github.io/aithentisch-tisch/runden/{e['slug']}.html"
        konsens = re.search(r"## KONSENS\n(.*?)\n## ", e["body"], re.S)
        summary = html.escape((konsens.group(1).strip()[:400] + "…") if konsens else e["frage"])
        items += f"""  <entry>
    <title>{html.escape(e['frage'][:120] or e['slug'])}</title>
    <link href="{link}"/>
    <id>{link}</id>
    <updated>{e['created']}T08:00:00+02:00</updated>
    <summary>{summary}</summary>
  </entry>\n"""
    return f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>AiTHENTiSCH-Tisch</title>
  <subtitle>Konsens · Interferenz · Offen</subtitle>
  <link href="https://ralfarminkirchner-netizen.github.io/aithentisch-tisch/atom.xml" rel="self"/>
  <link href="https://ralfarminkirchner-netizen.github.io/aithentisch-tisch/"/>
  <id>https://ralfarminkirchner-netizen.github.io/aithentisch-tisch/</id>
  <updated>{dt.date.today()}T08:00:00+02:00</updated>
{items}</feed>"""


def claims_link(d: dict) -> str:
    """Link zum AssignmentClaim-Export, falls die Runde contested ist und Claims existieren."""
    p = Path(__file__).parent / "kanon-export" / f"{d['slug']}-claims.json"
    if p.exists():
        return (f'<p class="small"><a href="../kanon-export/{p.name}">⚖ AssignmentClaim-Entwürfe '
                f'dieser Runde (JSON, unvalidiert)</a></p>')
    return ""


def giscus_block(d: dict) -> str:
    if not GISCUS_CATEGORY_ID:
        return "<!-- Giscus: aktiviert sich, sobald App installiert + GISCUS_CATEGORY_ID gesetzt ist. -->"
    return f"""
<h2>Diskussion</h2>
<script src="https://giscus.app/client.js"
        data-repo="ralfarminkirchner-netizen/aithentisch-tisch"
        data-repo-id="{GISCUS_REPO_ID}"
        data-category="General"
        data-category-id="{GISCUS_CATEGORY_ID}"
        data-mapping="specific" data-term="{d['slug']}"
        data-reactions-enabled="1" data-emit-metadata="0"
        data-input-position="top" data-theme="dark"
        data-lang="de" crossorigin="anonymous" async></script>"""


def uptime_table() -> str:
    """7-Tage-Uptime + Ø-Latenz pro Platz aus history.jsonl (Probe-Events)."""
    import json
    hist = Path(__file__).parent / "history.jsonl"
    if not hist.exists():
        return ""
    from collections import defaultdict
    ok_c, tot_c, lat = defaultdict(int), defaultdict(int), defaultdict(list)
    cutoff = dt.date.today() - dt.timedelta(days=7)
    for line in hist.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("event") != "probe":
            continue
        try:
            day = dt.date.fromisoformat(r["ts"][:10])
        except Exception:
            continue
        if day < cutoff:
            continue
        s = r["seat"]
        tot_c[s] += 1
        ok_c[s] += 1 if r.get("ok") else 0
        lat[s].append(r.get("latency_s", 0))
    if not tot_c:
        return ""
    rounds = [json.loads(l) for l in hist.read_text(encoding="utf-8").splitlines()
              if l.strip() and '"event": "round"' in l]
    dur = [r["duration_s"] for r in rounds if "duration_s" in r]
    rows = "".join(
        f"<tr><td><strong>{s}</strong></td><td>{tot_c[s]}</td>"
        f"<td class='{'ok' if ok_c[s]==tot_c[s] else 'bad'}'>{round(100*ok_c[s]/tot_c[s])}%</td>"
        f"<td>{round(sum(lat[s])/len(lat[s]),1)}s</td></tr>"
        for s in sorted(tot_c))
    extra = (f"<p class='small mut'>{len(dur)} Runden im Protokoll · Ø Dauer "
             f"{round(sum(dur)/len(dur))}s</p>") if dur else ""
    return f"""
<h2>Verlauf (7 Tage)</h2>
<p class="mut">Aus <code>history.jsonl</code>: Watchdog-Proben, Erfolgsquote, Ø Antwortzeit.</p>
<table><tr><th>Platz</th><th>Proben</th><th>Uptime</th><th>Ø Latenz</th></tr>{rows}</table>
{extra}"""


def build():
    runden_dir = DOCS / "runden"
    runden_dir.mkdir(parents=True, exist_ok=True)

    queries = sorted((WIKI / "queries").glob("*tisch*.md"), reverse=True) if (WIKI / "queries").exists() else []
    entries, skipped = [], []
    for q in queries:
        d = parse_query(q)
        # OPT-IN: Nur Runden mit `public: true` im Frontmatter werden veroeffentlicht.
        # Der Tisch behandelt auch interne Manuskripte — die Site ist oeffentlich.
        if d["fm"].get("public") != "true":
            skipped.append(d["slug"])
            continue
        entries.append(d)
        raw_links = re.findall(r"\[\[\.\./\.\./(raw/tisch/[^|\]]+)\|([^\]]+)\]\]", d["body"])
        raw_html = ""
        for rel, label in raw_links:
            rp = WIKI / rel
            if rp.exists():
                rtext = rp.read_text(encoding="utf-8")
                rtext = re.sub(r"^---\n.*?\n---\n", "", rtext, flags=re.S)
                raw_html += f"<details><summary>{html.escape(label)}</summary><pre>{html.escape(rtext.strip())}</pre></details>"
        main = re.sub(r"## Rohantworten.*", "", d["body"], flags=re.S)
        main = re.sub(r"^# .*\n", "", main)
        cls = "contested" if d["contested"] else "clean"
        body = f"""
<div class="card {cls}">
  <span class="tag">{'⚡ contested' if d['contested'] else '○ kein Widerspruch'}</span>
  <span class="tag">{html.escape(d['created'])}</span>
  <h3>Frage</h3><p><strong>{html.escape(d['frage'])}</strong></p>
</div>
{md_lite(main)}
<h2>Rohantworten der Plätze</h2>
{raw_html or '<p class="mut">Keine Rohantworten gefunden.</p>'}
{claims_link(d)}
{giscus_block(d)}
"""
        (runden_dir / f"{d['slug']}.html").write_text(
            page(d["frage"][:80] or d["slug"], body, f"Tischrunde · {d['created']}"), encoding="utf-8")

    # --- Platz-Tafel ---
    keys = tisch.load_env_keys()
    status = tisch.seat_status(keys)
    state = {}
    state_file = Path(__file__).parent / ".seat-state.json"
    if state_file.exists():
        import json
        try: state = json.loads(state_file.read_text())
        except Exception: pass
    rows = ""
    order = {"free": 0, "cheap": 1, "premium": 2}
    for name in sorted(tisch.SEATS, key=lambda n: (order[tisch.SEATS[n]["tier"]], n)):
        cfg = tisch.SEATS[name]
        role_name, role_desc = tisch.PERSPEKTIVEN[cfg["perspektive"]]
        aktiv, grund = status[name]
        if not aktiv:
            st = f'<span class="mut">✗ {html.escape(cfg["env_key"])} fehlt</span>'
        elif name in state:
            st = '<span class="ok">✓ antwortet</span>' if state[name] else '<span class="bad">✗ ausgefallen</span>'
        else:
            st = '<span class="mut">… ungetestet</span>'
        rows += (f"<tr><td><strong>{name}</strong></td><td>{cfg['tier']}</td>"
                 f"<td><strong>{html.escape(role_name)}</strong><br><span class='small mut'>{html.escape(role_desc[:110])}…</span></td>"
                 f"<td class='small'>{cfg['provider']}/{cfg['model'] or 'default'}</td><td>{st}</td></tr>")
    plaetze_body = f"""
<p class="mut">Jeder Platz = ein Modell + eine Perspektive. Perspektiven sind dem Modell-Charakter zugeordnet.
Premium-Plätze (Claude, GPT) laufen nur bei ausdrücklicher Anfrage — Kosten-Disziplin ist Teil der Verfassung.</p>
<table><tr><th>Platz</th><th>Stufe</th><th>Perspektive</th><th>Provider/Modell</th><th>Status</th></tr>{rows}</table>
{uptime_table()}
<div class="card"><h3>Regeln am Tisch</h3>
<ul><li>Kein Platz benutzt Werkzeuge oder Websuche — Antwort aus eigenem Wissen.</li>
<li>Unsicherheit wird als Unsicherheit markiert.</li>
<li>Zustimmung um der Zustimmung willen gilt als Fehler (Geltungsenteignung durch Rechtgeben).</li>
<li>Interferenz wird gespeichert, nicht geglättet. <code>contested</code> ist ein zulässiger Endzustand.</li></ul></div>
"""
    (DOCS / "plaetze.html").write_text(
        top_page("Die Plätze", plaetze_body, "Wer am Tisch sitzt — und in welcher Perspektive"), encoding="utf-8")

    # --- Index ---
    n_contested = sum(1 for e in entries if e["contested"])
    runden_wort = "Runde" if len(entries) == 1 else "Runden"
    cards = ""
    for e in entries:
        cls = "contested" if e["contested"] else "clean"
        chips = "".join(f'<span class="tag">{html.escape(t)}</span>' for t in e["tags"])
        cards += (f'<div class="card {cls} runde-card" data-tags="{html.escape(" ".join(e["tags"]))}">'
                  f'<a href="runden/{e["slug"]}.html"><strong>{html.escape(e["frage"][:120] or e["slug"])}</strong></a>'
                  f'<br><span class="small mut">{e["created"]} · {"⚡ contested" if e["contested"] else "○ ohne Widerspruch"}</span> {chips}</div>')
    # Themen-Filter (alle vorkommenden Tags)
    all_tags = sorted({t for e in entries for t in e["tags"]})
    filter_bar = ""
    if all_tags and len(entries) > 1:
        btns = "".join(f'<button class="tag" onclick="tagFilter(\'{t}\',this)">{html.escape(t)}</button>' for t in all_tags)
        filter_bar = f"""<p class="small mut">Themen: <button class="tag" onclick="tagFilter('',this)">alle</button>{btns}</p>
<script>
function tagFilter(t, btn) {{
  document.querySelectorAll('.runde-card').forEach(c => {{
    c.style.display = (!t || (c.dataset.tags||'').split(' ').includes(t)) ? '' : 'none';
  }});
  document.querySelectorAll('button.tag').forEach(b => b.style.borderColor = 'var(--line)');
  if (btn) btn.style.borderColor = 'var(--acc)';
}}
</script>"""
    aktiv_n = sum(1 for n, (a, _) in status.items() if a)
    index_body = f"""
<p class="mut">Mehrere LLMs sitzen an einem Tisch. Jeder antwortet aus einer eigenen, ihm zugeordneten Perspektive.
Die Synthese trennt streng: <strong>Konsens</strong> (was mindestens zwei unabhängig sagen) ·
<strong>Interferenz</strong> (alle Widersprüche stehen bleiben, mit Namen) · <strong>Offen</strong> (was keiner beantworten konnte).</p>
<div class="card"><strong>{len(entries)}</strong> {runden_wort} · <strong class="warn">{n_contested}</strong> contested ·
<strong>{aktiv_n}</strong> Plätze besetzt · <a href="plaetze.html">Platz-Tafel →</a> · <a href="matrix.html">Interferenz-Matrix →</a> · <a href="atom.xml">Feed</a></div>
<h2>Runden</h2>
{filter_bar}
{cards or '<p class="mut">Noch keine Runden.</p>'}
"""
    (DOCS / "index.html").write_text(
        top_page("AiTHENTiSCH-Tisch", index_body, "Konsens · Interferenz · Offen"), encoding="utf-8")

    # --- Interferenz-Matrix + Atom-Feed ---
    matrix_html, _ = build_matrix(entries)
    if matrix_html:
        (DOCS / "matrix.html").write_text(
            top_page("Interferenz-Matrix", matrix_html,
                     "Wer stimmt wem zu — und wer widerspricht? (über alle öffentlichen Runden)"),
            encoding="utf-8")
    (DOCS / "atom.xml").write_text(build_atom(entries), encoding="utf-8")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    print(f"[site] {len(entries)} oeffentliche Runden gerendert, {len(skipped)} privat zurueckgehalten → {DOCS}")


if __name__ == "__main__":
    build()
