#!/usr/bin/env python3
"""
Sitz-Watchdog fuer den AiTHENTiSCH-Tisch.
Testet taeglich alle AKTIVEN free/cheap-Plaetze mit einer Mini-Probe an.
Premium-Plaetze (Claude, GPT) werden aus Kostengruenden NICHT angetestet.

Watchdog-Pattern: SILENT, solange sich nichts aendert.
Meldet nur: Platz neu ausgefallen / Platz zurueck / neuer Platz direkt kaputt.
"""
import json, subprocess, sys
import datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import tisch  # SEATS, seat_status, load_env_keys, HERMES — eine Quelle der Wahrheit

STATE = Path(__file__).parent / ".seat-state.json"


def probe(name: str, cfg: dict):
    import time
    t0 = time.monotonic()
    cmd = [tisch.HERMES, "chat", "-q", "Antworte nur mit: OK", "-Q",
           "--provider", cfg["provider"], "--ignore-rules"]
    if cfg.get("model"):
        cmd += ["-m", cfg["model"]]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        out = (p.stdout or "").strip()
        ok = p.returncode == 0 and bool(out) and "Error" not in out[:40]
        return ok, ((p.stderr or out) or "")[-200:], round(time.monotonic() - t0, 1)
    except Exception as e:
        return False, str(e)[:200], round(time.monotonic() - t0, 1)


def main():
    keys = tisch.load_env_keys()
    status = tisch.seat_status(keys)
    active = [n for n, c in tisch.SEATS.items()
              if status[n][0] and c["tier"] in ("free", "cheap")]
    if not active:
        return  # nichts zu testen, nichts zu melden

    old = {}
    if STATE.exists():
        try:
            old = json.loads(STATE.read_text())
        except Exception:
            old = {}

    new, changes, hist_rows = {}, [], []
    with ThreadPoolExecutor(max_workers=len(active)) as ex:
        futs = {ex.submit(probe, n, tisch.SEATS[n]): n for n in active}
        for f in as_completed(futs):
            n = futs[f]
            ok, err, latency = f.result()
            new[n] = ok
            hist_rows.append({"ts": dt.datetime.now().isoformat(timespec="seconds"),
                              "event": "probe", "seat": n, "ok": ok,
                              "latency_s": latency,
                              "error": "" if ok else err.strip()[:100]})
            was = old.get(n)
            if was is None and not ok:
                changes.append((n, ok, err))      # neuer Platz, direkt kaputt
            elif was is not None and was != ok:
                changes.append((n, ok, err))      # Zustandswechsel

    STATE.write_text(json.dumps(new))
    try:
        with (Path(__file__).parent / "history.jsonl").open("a", encoding="utf-8") as hf:
            for row in hist_rows:
                hf.write(json.dumps(row) + "\n")
    except Exception:
        pass

    for n, ok, err in changes:
        if ok:
            print(f"SITZ ZURUECK: {n} antwortet wieder und steht dem Tisch zur Verfuegung.")
        else:
            print(f"SITZ AUSGEFALLEN: {n} — {err.strip()[:140]}")


if __name__ == "__main__":
    main()
