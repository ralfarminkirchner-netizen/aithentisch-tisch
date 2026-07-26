#!/usr/bin/env python3
"""
Fragen-Warteschlange fuer den AiTHENTiSCH-Tisch.

Du legst Fragen in ~/adhsos/tisch/warteschlange.txt — eine pro Zeile,
Zeilen mit # sind Kommentare. Der Cron-Lauf nimmt pro Durchgang max. N
Fragen (default: 1), laesst den Tisch darueber laufen (Default-Plaetze:
free+cheap, NIEMALS premium) und verschiebt sie nach erledigt.txt.

Silent, wenn die Warteschlange leer ist (kein leerer Cron-Report).
"""
import datetime as dt, re, subprocess, sys
from pathlib import Path

D = Path(__file__).parent
sys.path.insert(0, str(D.parent / "ingest"))
from guard import ACCEPT_PRIVATE, assess_note

QUEUE, DONE = D / "warteschlange.txt", D / "erledigt.txt"
FAILED = D / "abgebrochen.txt"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 1


def run_checked(command, *, timeout=120):
    result = subprocess.run(
        command,
        cwd=str(D),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"{command[0]} fehlgeschlagen (rc={result.returncode})")
    return result


def validate_public_tree() -> None:
    """Allowlist and scan every byte that may enter the public commit."""
    docs = (D / "docs").resolve(strict=True)
    allowed = re.compile(
        r"^(?:\.nojekyll|index\.html|matrix\.html|plaetze\.html|atom\.xml"
        r"|runden/[a-z0-9-]+\.html"
        r"|kanon-export/(?:index|[a-z0-9-]+-claims)\.json)$"
    )
    for candidate in docs.rglob("*"):
        if candidate.is_symlink():
            raise RuntimeError("Public-Baum enthält einen Symlink.")
        if not candidate.is_file():
            continue
        resolved = candidate.resolve(strict=True)
        relative = resolved.relative_to(docs).as_posix()
        if not allowed.fullmatch(relative):
            raise RuntimeError("Public-Baum enthält einen nicht erlaubten Pfad.")
        if resolved.stat().st_size > 5 * 1024 * 1024:
            raise RuntimeError("Public-Datei überschreitet das harte Größenlimit.")
        inspection = assess_note(
            relative,
            resolved.read_text(encoding="utf-8", errors="strict"),
        )
        if inspection["decision"] != ACCEPT_PRIVATE:
            codes = ",".join(inspection["issue_codes"]) or "POLICY_REVIEW"
            raise RuntimeError(f"Public-Baum durch Guard blockiert ({codes}).")


def main():
    if not QUEUE.exists():
        sys.exit(0)
    lines = QUEUE.read_text(encoding="utf-8").splitlines()
    comments = [l for l in lines if l.strip().startswith("#")]
    open_q = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
    if not open_q:
        sys.exit(0)  # silent

    todo, rest = open_q[:N], open_q[N:]
    gelaufen = []   # nur Fragen, ueber die wirklich ein Tisch getagt hat
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
            rest = [raw_q] + rest      # raw_q, nicht q: sonst gehen die --tags verloren
            continue
        if p.returncode != 0:
            # Der Exit-Code wurde hier nie geprueft. Brach tisch.py ab (Exit 2:
            # "nur N Platz ok — kein Tisch moeglich"), wanderte die Frage trotzdem
            # nach erledigt.txt und verschwand aus der Warteschlange. Am 22./23./24.07.
            # sind so drei Fragen vernichtet worden, darunter die erste oeffentliche
            # (GitHub-Issue #1) — als geprueft verbucht, ohne dass ein Tisch tagte.
            # Eine nicht gestellte Frage darf nicht aussehen wie eine beantwortete.
            print(f"(ABBRUCH rc={p.returncode} — Frage bleibt erhalten, NICHT erledigt)")
            letzte = (p.stderr or "").strip().splitlines()
            with FAILED.open("a", encoding="utf-8") as f:
                f.write(f"[{dt.datetime.now().isoformat(timespec='seconds')}] rc={p.returncode} | {q}\n")
                for zeile in letzte[-6:]:
                    f.write(f"    {zeile}\n")
            rest = [raw_q] + rest
            continue
        gelaufen.append(q)
        with DONE.open("a", encoding="utf-8") as f:
            f.write(f"[{dt.datetime.now().isoformat(timespec='seconds')}] {q}\n")

    QUEUE.write_text("\n".join(comments + rest) + "\n", encoding="utf-8")

    # --- Auto-Publikation: Site neu bauen, bei Aenderungen committen+pushen ---
    # Nur wenn wirklich eine Runde stattfand. Frueher stand hier `if todo:` — dadurch
    # wurden am 22./23./24.07. drei Commits "Site: 1 neue Runde(n)" gepusht, obwohl
    # keine Runde zustande kam (die Site selbst blieb korrekt, die Nachricht nicht).
    if gelaufen:
        try:
            site_run = subprocess.run(
                [sys.executable, str(D / "site.py")], cwd=str(D),
                capture_output=True, text=True, timeout=120
            )
            claims_run = subprocess.run(
                [sys.executable, str(D / "export_claims.py")], cwd=str(D),
                capture_output=True, text=True, timeout=120
            )
            if site_run.returncode != 0 or claims_run.returncode != 0:
                print(
                    "[auto-publish] ABORT: Public-Guard/Build fehlgeschlagen; "
                    "kein Commit, kein Push."
                )
                return
            validate_public_tree()
            run_checked(["git", "fetch", "--quiet", "origin", "main"])
            head = run_checked(["git", "rev-parse", "HEAD"]).stdout.strip()
            remote = run_checked(["git", "rev-parse", "origin/main"]).stdout.strip()
            if head != remote:
                raise RuntimeError(
                    "Auto-Publish verweigert: lokaler Branch ist nicht exakt origin/main."
                )
            run_checked(["git", "add", "--", "docs"])
            staged = run_checked(
                ["git", "diff", "--cached", "--name-only", "-z"]
            ).stdout.split("\0")
            unexpected = [
                path for path in staged
                if path and not path.startswith("docs/")
            ]
            if unexpected:
                raise RuntimeError(
                    "Auto-Publish verweigert: unerwartete Dateien im Staging-Baum."
                )
            st = run_checked(
                ["git", "status", "--porcelain", "--", "docs"]
            ).stdout.strip()
            if st:
                run_checked([
                    "git", "-c", "user.name=AiTHENTiSCH-Tisch", "-c",
                    "user.email=tisch@localhost", "commit", "-m",
                    f"Site: {len(gelaufen)} neue Runde(n) aus Warteschlange",
                ])
                committed = run_checked([
                    "git", "diff-tree", "--no-commit-id", "--name-only",
                    "-r", "HEAD",
                ]).stdout.splitlines()
                if any(not path.startswith("docs/") for path in committed):
                    raise RuntimeError(
                        "Auto-Publish verweigert: Commit enthält Nicht-Public-Dateien."
                    )
                run_checked(["git", "push", "origin", "HEAD:main"])
                print("[auto-publish] Site neu gebaut und gepusht.")
            else:
                print("[auto-publish] Site aktuell, nichts zu pushen.")
        except Exception as e:
            print(f"[auto-publish] FEHLER: {e}")


if __name__ == "__main__":
    main()
