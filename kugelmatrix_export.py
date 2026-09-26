#!/usr/bin/env python3
"""
kugelmatrix_export.py — AiTHENTiSCH-Tisch → kugelmatrix.round.v1.

Vendorierter Ausschnitt aus dem Referenz-Konverter des Kugelmatrix-Repos
(`tools/round_import.py`, Subkommando `aithentisch`, Branch
`claude/inspiring-babbage-g8767k`). Nur Python-Standardbibliothek, keine neue
Abhängigkeit. Die Logik ist bewusst 1:1 übernommen (gleiche Regex, gleiche
Feldnamen, gleiche Reihenfolge), damit eine hier erzeugte Datei bit-äquivalent
zu `python3 tools/round_import.py aithentisch <seite>.md` aus dem
Kugelmatrix-Repo ist. Bei einer Formatänderung dort: hier nachziehen.

Format-Doku: kugelmatrix-Repo, docs/ROUND-FORMAT.md.
Status der Ausgabe: immer `proposed` — eine Abschrift zur Darstellung, keine
zweite Wahrheit. Diese Datei liest nur (die Tischseite + ihre Rohantworten),
schreibt nie in die Quelle zurück.
"""
from __future__ import annotations

import itertools
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

FORMAT = "kugelmatrix.round.v1"
RELATION_KINDS = ("incompatible", "compatible", "complementary", "incommensurable", "consensus", "reply")
BOARD_B = ("feel", "depth", "prec", "emo", "horizon", "urgency", "ambig", "novel", "cohere", "link")
HAND = ("emo", "tiefe", "praez", "klar", "weit", "stimme")
MAX_TEXT = 20000
MAX_PAIRS_PER_ITEM = 12

FM_RX = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.S)
SECTIONS = ("KONSENS", "INTERFERENZ", "OFFEN", "NEUE PERSPEKTIVEN", "GEFÜHL")


class RoundError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _doc(system: str, title: str, session_id: Optional[str] = None, ref: Optional[str] = None) -> dict:
    return {"format": FORMAT, "status": "proposed",
            "source": {"system": system, "title": title, "session_id": session_id, "ref": ref, "converted_at": _now()},
            "rounds": [], "fingers": [], "relations": []}


def _pairs(ids: Iterable[str]) -> list[tuple[str, str]]:
    uniq = sorted(set(i for i in ids if i))
    return list(itertools.combinations(uniq, 2))[:MAX_PAIRS_PER_ITEM]


def _frontmatter(text: str) -> tuple[dict, str]:
    m = FM_RX.match(text)
    if not m:
        return {}, text
    meta: dict[str, Any] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                v = [x.strip().strip('"') for x in v[1:-1].split(",") if x.strip()]
            else:
                v = v.strip('"')
            meta[k.strip()] = v
    return meta, m.group(2)


def _sections(body: str) -> dict[str, str]:
    out: dict[str, str] = {}
    parts = re.split(r"^##\s+(.+?)\s*$", body, flags=re.M)
    for head, content in zip(parts[1::2], parts[2::2]):
        key = head.strip().upper()
        if key in SECTIONS:
            out[key] = content.strip()
    return out


def _bullets(section: str) -> list[str]:
    items = [re.sub(r"^\s*(?:[-*•]|\d+[.)])\s+", "", b).strip() for b in re.split(r"\n(?=\s*(?:[-*•]|\d+[.)])\s)", section)]
    return [b for b in items if b]


def from_aithentisch(pages: list[Path], raw_dir: Optional[Path] = None) -> dict:
    """Baut kugelmatrix.round.v1 aus einer oder mehreren AiTHENTiSCH-Tischseiten.

    Identisch zu `round_import.py aithentisch` im Kugelmatrix-Repo: jede Seite
    ist eine Runde, Platz-Antworten kommen aus `raw/tisch/<slug>-<platz>.md`,
    INTERFERENZ-/KONSENS-Punkte mit ≥2 genannten Plätzen werden zu Bögen
    (`authority: synthesis_reading`).
    """
    if not pages:
        raise RoundError("keine Tischseite angegeben")
    doc = _doc("aithentisch-tisch", "AiTHENTiSCH-Tisch", ref=str(pages[0]))
    for rn, page in enumerate(pages, 1):
        meta, body = _frontmatter(page.read_text(encoding="utf-8"))
        wiki = page.resolve().parent.parent
        rdir = raw_dir or wiki / "raw" / "tisch"
        q = re.search(r"\*\*Frage:\*\*\s*(.+)", body)
        roles = {}
        pm = re.search(r"\*\*Pl(?:ae|ä)tze:\*\*\s*(.+)", body)
        if pm:
            for part in pm.group(1).split(";"):
                if "=" in part:
                    s, r = part.split("=", 1)
                    roles[s.strip()] = r.strip()
        secs = _sections(body)
        rid = f"R{rn}"
        contested = str(meta.get("contested", "")).lower() in ("true", "ja", "yes")
        doc["rounds"].append({"id": rid, "label": f"Runde {rn}", "title": str(meta.get("title", "")).removeprefix("Tisch: "),
                              "question": q.group(1).strip() if q else None, "created": meta.get("created"),
                              "contested": contested, "ref": str(page),
                              "summary": {k.lower().replace(" ", "_").replace("ü", "ue"): v for k, v in secs.items()}})
        sources = meta.get("sources") or []
        if isinstance(sources, str):
            sources = [sources]
        seat_ids: dict[str, str] = {}
        for src in sources:
            path = (wiki / src) if not Path(src).is_absolute() else Path(src)
            if not path.exists():
                path = rdir / Path(src).name
            if not path.exists():
                continue
            smeta, sbody = _frontmatter(path.read_text(encoding="utf-8"))
            if str(smeta.get("ok", "True")).lower() in ("false", "0", "nein"):
                continue
            answer = sbody.split("ANTWORT:", 1)[1].strip() if "ANTWORT:" in sbody else sbody.strip()
            seat = smeta.get("seat") or path.stem.rsplit("-", 1)[-1]
            role = smeta.get("perspektive") or roles.get(seat, "")
            fid = f"{rid}:{seat}"
            seat_ids[seat.lower()] = fid
            if role:
                seat_ids[role.lower()] = fid
            doc["fingers"].append({"id": fid, "round": rid, "label": f"{seat} · {role}" if role else seat,
                                   "speaker": {"seat": seat, "role": role}, "text": answer[:MAX_TEXT],
                                   "ref": str(path)})
        # Synthese-Lesart: Aufzählungspunkte, die ≥2 Plätze nennen → Beziehung.
        for sec, kind in (("INTERFERENZ", "incompatible"), ("KONSENS", "consensus")):
            for b in _bullets(secs.get(sec, "")):
                low = b.lower()
                hit = [fid for name, fid in seat_ids.items() if re.search(r"(?<![\wäöüß])" + re.escape(name) + r"(?![\wäöüß])", low)]
                for a, c in _pairs(hit):
                    doc["relations"].append({"a": a, "b": c, "kind": kind, "text": b[:400], "authority": "synthesis_reading"})
    if not doc["fingers"]:
        raise RoundError("keine Platz-Antworten gefunden (raw/tisch/…) — --raw-dir angeben?")
    return doc


def validate(doc: dict) -> list[str]:
    """Wirft RoundError bei Formfehlern; gibt Warnungen zurück. 1:1 aus round_import.py."""
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise RoundError(f"format muss {FORMAT!r} sein")
    for key in ("rounds", "fingers", "relations"):
        if not isinstance(doc.get(key), list):
            raise RoundError(f"{key} fehlt oder ist keine Liste")
    warn = []
    rids = {r.get("id") for r in doc["rounds"]}
    fids = set()
    for f in doc["fingers"]:
        if not isinstance(f, dict) or not f.get("id") or not isinstance(f.get("text"), str):
            raise RoundError(f"Finger ohne id/text: {str(f)[:80]}")
        if f["id"] in fids:
            raise RoundError(f"doppelte Finger-id {f['id']!r}")
        fids.add(f["id"])
        if f.get("round") not in rids:
            warn.append(f"Finger {f['id']}: unbekannte Runde {f.get('round')!r}")
        for block, keys, hi in (("scores", BOARD_B, 100), ("hand", HAND, 10)):
            s = f.get(block)
            if s is not None:
                if not isinstance(s, dict) or any(k not in keys or not isinstance(v, (int, float)) or not 0 <= v <= hi for k, v in s.items()):
                    raise RoundError(f"Finger {f['id']}: {block} ungültig (Schlüssel {keys}, 0–{hi})")
    for r in doc["relations"]:
        if r.get("kind") not in RELATION_KINDS:
            raise RoundError(f"Beziehung mit unbekannter Art {r.get('kind')!r}")
        if r.get("a") not in fids or r.get("b") not in fids:
            warn.append(f"Beziehung {r.get('a')}→{r.get('b')}: Finger fehlt")
    return warn


def export_round(page: Path, raw_dir: Optional[Path] = None) -> dict:
    """Komfort-Wrapper für einen einzelnen Tisch-Aufruf (eine Seite = eine Runde)."""
    doc = from_aithentisch([page], raw_dir=raw_dir)
    validate(doc)
    return doc
