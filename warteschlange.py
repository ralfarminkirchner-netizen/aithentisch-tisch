#!/usr/bin/env python3
"""
Fragen-Warteschlange fuer den AiTHENTiSCH-Tisch.

Du legst Fragen in ~/adhsos/tisch/warteschlange.txt — eine pro Zeile,
Zeilen mit # sind Kommentare. Der Cron-Lauf nimmt pro Durchgang max. N
Fragen (default: 1), laesst den Tisch darueber laufen (Default-Plaetze:
free+cheap, NIEMALS premium) und verschiebt sie nach erledigt.txt.

Silent, wenn die Warteschlange leer ist (kein leerer Cron-Report).
"""
import datetime as dt, subprocess, sys
from pathlib import Path

D = Path(__file__).parent
QUEUE, DONE = D / "warteschlange.txt", D / "erledigt.txt"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 1


def main():
    if not QUEUE.exists():
        sys.exit(0)
    lines = QUEUE.read_text(encoding="utf-8").splitlines()
    comments = [l for l in lines if l.strip().startswith("#")]
    open_q = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
    if not open_q:
        sys.exit(0)  # silent

    todo, rest = open_q[:N], open_q[N:]
    for raw_q in todo:
        # Format: "Frage | tags: thema1, thema2"  (Tags optional)
        q, _, tagpart = raw_q.partition("| tags:")
        q = q.strip()
        tags = tagpart.strip() if tagpart else ""
        print(f"=== TISCHFRAGE: {q}")
        cmd = [sys.executable, str(D / "tisch.py"), q]
        if tags:
            cmd += ["--tags", tags]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=1500)
            sys.stderr.write(p.stderr)
            out = p.stdout.strip()
            print(out if out else "(kein Output — siehe Wiki)")
        except subprocess.TimeoutExpired:
            print("(TIMEOUT nach 1500s — Frage bleibt erhalten)")
            rest = [q] + rest
            continue
        with DONE.open("a", encoding="utf-8") as f:
            f.write(f"[{dt.datetime.now().isoformat(timespec='seconds')}] {q}\n")

    QUEUE.write_text("\n".join(comments + rest) + "\n", encoding="utf-8")

    # --- Auto-Publikation: Site neu bauen, bei Aenderungen committen+pushen ---
    if todo:
        try:
            subprocess.run([sys.executable, str(D / "site.py")], cwd=str(D),
                           capture_output=True, text=True, timeout=120)
            subprocess.run([sys.executable, str(D / "export_claims.py")], cwd=str(D),
                           capture_output=True, text=True, timeout=120)
            p = subprocess.run(["git", "add", "-A"], cwd=str(D), capture_output=True, text=True)
            st = subprocess.run(["git", "status", "--porcelain"], cwd=str(D),
                                capture_output=True, text=True).stdout.strip()
            if st:
                subprocess.run(["git", "-c", "user.name=AiTHENTiSCH-Tisch", "-c",
                                "user.email=tisch@localhost", "commit", "-m",
                                f"Site: {len(todo)} neue Runde(n) aus Warteschlange"],
                               cwd=str(D), capture_output=True, text=True)
                push = subprocess.run(["git", "push"], cwd=str(D),
                                      capture_output=True, text=True, timeout=120)
                print("[auto-publish] Site neu gebaut und gepusht." if push.returncode == 0
                      else f"[auto-publish] push FEHLER: {push.stderr[-200:]}")
            else:
                print("[auto-publish] Site aktuell, nichts zu pushen.")
        except Exception as e:
            print(f"[auto-publish] FEHLER: {e}")


if __name__ == "__main__":
    main()
