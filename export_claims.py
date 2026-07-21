#!/usr/bin/env python3
"""
export_claims.py — Kanon-Bruecke: contested oeffentliche Tischrunden
als AssignmentClaim-ENTWUERFE (JSON) exportieren.

Jede divergente Position im INTERFERENZ-Abschnitt wird ein eigener
Claim-Entwurf: perspektivgebunden, scope-limitiert, mit Claim Ceiling
und Widerspruchsweg. Interferenz wird so formaler Pruefgegenstand
der mindlaxy-canon-engine statt nur Protokoll.

EHRLICHKEIT: Diese Entwuerfe sind NICHT gegen die v0.4-Schemas der
canon-engine validiert (das Repo liegt nicht auf diesem Mac). Sie sind
Uebergabematerial, keine geltenden Claims. Status: proposed.

Ausgabe: kanon-export/<slug>-claims.json + kanon-export/index.json
"""
import datetime as dt, json, re, sys
from pathlib import Path

D = Path(__file__).parent
sys.path.insert(0, str(D))
import tisch

# site.py heisst wie das stdlib-Modul 'site' — daher per importlib laden
import importlib.util
_spec = importlib.util.spec_from_file_location("tisch_site", D / "site.py")
site_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(site_mod)

OUT = D / "kanon-export"

CEILING = [
    "Keine Ratifikation durch den Tisch — der Tisch behauptet nichts, er bezeugt Positionen.",
    "Die Position ist perspektiv- und modellgebunden, nicht wahrheitsbehauptend.",
    "Widersprechende Positionen derselben Runde bleiben gleichberechtigt bestehen.",
    "Gueltig nur im Kontext der ausgewiesenen Frage und Runde.",
]


def claims_for(entry: dict) -> list:
    body = entry["body"]
    interf = re.search(r"## INTERFERENZ\n(.*?)(?:## OFFEN|contested:)", body, re.S)
    if not interf:
        return []
    claims, n = [], 0
    mentioned = [s for s in tisch.SEATS if re.search(rf"\b{re.escape(s)}\b", interf.group(1))]
    for m in re.finditer(r"- \*\*([a-z0-9-]+) \(([^)]+)\):\*\*\s*(.+?)(?=\n- \*\*|\Z)", interf.group(1), re.S):
        seat, role, text = m.group(1), m.group(2), " ".join(m.group(3).split())
        if seat not in tisch.SEATS:
            continue
        n += 1
        cfg = tisch.SEATS[seat]
        claims.append({
            "$schema_note": "AssignmentClaim-Entwurf v0.1 (Tisch-Export; NICHT gegen mindlaxy-canon-engine v0.4 validiert)",
            "id": f"ac-tisch-{entry['slug']}-{n:02d}",
            "type": "AssignmentClaim",
            "status": "proposed",
            "assignment_kind": "position_attribution",
            "source": {"kind": "question", "ref": entry["frage"]},
            "claim": text,
            "claimed_by": {
                "seat": seat,
                "perspektive": role,
                "provider": cfg["provider"],
                "model": cfg.get("model") or "default",
                "cost_tier": cfg["tier"],
            },
            "validity_dimensions": ["epistemic"],
            "scope": {"round": entry["slug"], "created": entry["created"]},
            "claim_ceiling": CEILING,
            "contested_by": [s for s in mentioned if s != seat],
            "provenance": {
                "pipeline": "aithentisch-tisch v2",
                "round_file": f"queries/{entry['slug']}.md",
                "round_url": f"https://ralfarminkirchner-netizen.github.io/aithentisch-tisch/runden/{entry['slug']}.html",
                "exported": str(dt.date.today()),
            },
            "revision_path": "Neue Tischrunde zur selben Frage oder menschliches Review. Kanon setzt nur Ralf.",
        })
    return claims


def main():
    OUT.mkdir(exist_ok=True)
    queries = sorted((site_mod.WIKI / "queries").glob("*tisch*.md"), reverse=True)
    index, n_claims = [], 0
    for q in queries:
        e = site_mod.parse_query(q)
        if e["fm"].get("public") != "true" or not e["contested"]:
            continue
        claims = claims_for(e)
        if not claims:
            continue
        path = OUT / f"{e['slug']}-claims.json"
        path.write_text(json.dumps(claims, ensure_ascii=False, indent=2), encoding="utf-8")
        index.append({"round": e["slug"], "created": e["created"],
                      "frage": e["frage"], "claims": len(claims),
                      "file": path.name})
        n_claims += len(claims)
    (OUT / "index.json").write_text(json.dumps({
        "generated": str(dt.date.today()),
        "note": "AssignmentClaim-Entwuerfe aus contested Tischrunden. Unvalidiert, status=proposed. Kanon setzt nur Ralf.",
        "rounds": index,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[claims] {n_claims} Claim-Entwuerfe aus {len(index)} contested Runden → {OUT}")


if __name__ == "__main__":
    main()
