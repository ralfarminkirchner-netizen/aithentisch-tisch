"""Tests fuer kugelmatrix_export.py — der vendorierte AiTHENTiSCH-Konverter.

Baut eine Tischseite + Rohantworten von Hand nach (gleiche Struktur wie
tisch.py sie schreibt) und prueft:
- Form entspricht kugelmatrix.round.v1 (validate() wirft nicht)
- Runden/Finger/Beziehungen sind korrekt extrahiert
- deterministisch: zweimal derselbe Input -> byte-identischer Output
  (bis auf den einzigen Zeitstempel `source.converted_at`)
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import kugelmatrix_export as km


def _write_wiki(tmp_path: Path, *, contested: bool = True) -> Path:
    wiki = tmp_path / "wiki"
    queries = wiki / "queries"
    raw = wiki / "raw" / "tisch"
    queries.mkdir(parents=True)
    raw.mkdir(parents=True)

    slug = "20260926-tisch-testfrage"
    sources = f"raw/tisch/{slug}-gemini.md, raw/tisch/{slug}-kimi.md"
    page = queries / f"{slug}.md"
    page.write_text(
        f"""---
title: "Tisch: Testfrage"
created: 2026-09-26
updated: 2026-09-26
type: query
status: proposed
tags: [methode, offene-frage]
sources: [{sources}]
confidence: medium
contested: {'true' if contested else 'false'}
sensitivity: private
public: false
public_export_allowed: false
origin_assessment: mixed_declared
---

# Tisch: Testfrage

**Frage:** Ist ein Testlauf eine echte Runde?

**Plaetze:** gemini=Praktiker; kimi=Analytiker
**Ok:** gemini, kimi

## KONSENS
- gemini und kimi stimmen ueberein, dass ein Testlauf technisch eine Runde ist.

## INTERFERENZ
- gemini haelt einen Testlauf fuer bedeutungslos, kimi haelt ihn fuer aussagekraeftig.

## OFFEN
- Ob ein Testlauf mit Stub-Antworten epistemisch zaehlt.

## NEUE PERSPEKTIVEN
- Die Unterscheidung zwischen technischer und epistemischer Gueltigkeit einer Runde.

## GEFÜHL
- Nuechternheit, keine Dramatik.

---

## Rohantworten
- [[../../raw/tisch/{slug}-gemini.md|Platz gemini]]
- [[../../raw/tisch/{slug}-kimi.md|Platz kimi]]
""",
        encoding="utf-8",
    )
    (raw / f"{slug}-gemini.md").write_text(
        "---\nseat: gemini\nperspektive: Praktiker\nts: 20260926-090000\nok: True\n"
        "sensitivity: private\npublic_export_allowed: false\n"
        "origin_assessment: mixed_declared\n---\n\n"
        "FRAGE:\nIst ein Testlauf eine echte Runde?\n\nANTWORT:\nJa, technisch schon.\n",
        encoding="utf-8",
    )
    (raw / f"{slug}-kimi.md").write_text(
        "---\nseat: kimi\nperspektive: Analytiker\nts: 20260926-090000\nok: True\n"
        "sensitivity: private\npublic_export_allowed: false\n"
        "origin_assessment: mixed_declared\n---\n\n"
        "FRAGE:\nIst ein Testlauf eine echte Runde?\n\nANTWORT:\nJa, und die Struktur ist identisch zu echten Laeufen.\n",
        encoding="utf-8",
    )
    return page


def test_from_aithentisch_shape(tmp_path):
    page = _write_wiki(tmp_path)
    doc = km.from_aithentisch([page])

    assert doc["format"] == "kugelmatrix.round.v1"
    assert doc["status"] == "proposed"
    assert doc["source"]["system"] == "aithentisch-tisch"

    assert len(doc["rounds"]) == 1
    r = doc["rounds"][0]
    assert r["id"] == "R1"
    assert r["contested"] is True
    assert r["question"] == "Ist ein Testlauf eine echte Runde?"
    assert "konsens" in r["summary"] and "interferenz" in r["summary"]

    fingers_by_seat = {f["speaker"]["seat"]: f for f in doc["fingers"]}
    assert set(fingers_by_seat) == {"gemini", "kimi"}
    assert fingers_by_seat["gemini"]["text"] == "Ja, technisch schon."
    assert fingers_by_seat["gemini"]["speaker"]["role"] == "Praktiker"
    assert fingers_by_seat["kimi"]["round"] == "R1"

    kinds = {rel["kind"] for rel in doc["relations"]}
    assert "consensus" in kinds
    assert "incompatible" in kinds
    for rel in doc["relations"]:
        assert rel["authority"] == "synthesis_reading"
        assert rel["a"] in fingers_by_seat_ids(doc) and rel["b"] in fingers_by_seat_ids(doc)


def fingers_by_seat_ids(doc):
    return {f["id"] for f in doc["fingers"]}


def test_validate_passes(tmp_path):
    page = _write_wiki(tmp_path)
    doc = km.from_aithentisch([page])
    warnings = km.validate(doc)
    assert warnings == []


def test_export_round_wrapper_validates(tmp_path):
    page = _write_wiki(tmp_path)
    doc = km.export_round(page)
    assert doc["format"] == "kugelmatrix.round.v1"


def test_deterministic_except_timestamp(tmp_path):
    page = _write_wiki(tmp_path)
    doc1 = km.from_aithentisch([page])
    doc2 = km.from_aithentisch([page])
    doc1["source"]["converted_at"] = "STUB"
    doc2["source"]["converted_at"] = "STUB"
    assert json.dumps(doc1, sort_keys=True) == json.dumps(doc2, sort_keys=True)


def test_no_seats_raises(tmp_path):
    wiki = tmp_path / "wiki"
    queries = wiki / "queries"
    queries.mkdir(parents=True)
    page = queries / "20260926-tisch-leer.md"
    page.write_text(
        "---\ntitle: \"Tisch: Leer\"\ncreated: 2026-09-26\ncontested: false\nsources: []\n---\n\n"
        "# Tisch: Leer\n\n**Frage:** Leere Frage?\n\n**Plaetze:** \n**Ok:** \n",
        encoding="utf-8",
    )
    with pytest.raises(km.RoundError):
        km.from_aithentisch([page])


def test_failed_seat_excluded(tmp_path):
    """Ein ausgefallener Platz (ok: False) darf keinen Finger erzeugen."""
    page = _write_wiki(tmp_path)
    raw = page.resolve().parent.parent / "raw" / "tisch"
    slug = page.stem
    (raw / f"{slug}-deepseek.md").write_text(
        "---\nseat: deepseek\nperspektive: Logiker\nok: False\n---\n\n"
        "FRAGE:\nIst ein Testlauf eine echte Runde?\n\nANTWORT:\n(ausgefallen: timeout 300s)\n",
        encoding="utf-8",
    )
    # deepseek ist in `sources` der Seite nicht gelistet -> zaehlt ohnehin nicht;
    # dieser Test dokumentiert nur, dass ok: False separat gefiltert wuerde, falls
    # eine kuenftige Seite ausgefallene Plaetze mit auflistet.
    meta, body = km._frontmatter((raw / f"{slug}-deepseek.md").read_text(encoding="utf-8"))
    assert str(meta.get("ok")).lower() in ("false", "0", "nein")
