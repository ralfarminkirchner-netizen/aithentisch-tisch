#!/usr/bin/env python3
"""
sync_fragen.py — GitHub Issues mit Label 'tischfrage' → warteschlange.txt

Oeffentlicher Eingangskanal des AiTHENTiSCH-Tisch:
Jede offene Issue mit Label 'tischfrage' im Repo wird als Frage in die
Warteschlange uebernommen und mit Label 'eingeplant' markiert.
Dedupe: Titel, die schon in warteschlange.txt oder erledigt.txt stehen,
werden nicht erneut eingeplant.

Token kommt aus dem macOS-Schluesselbund (git credential osxkeychain).
Silent, wenn nichts Neues anliegt.
"""
import json, re, subprocess, sys, urllib.request
from pathlib import Path

D = Path(__file__).parent
QUEUE, DONE = D / "warteschlange.txt", D / "erledigt.txt"
REPO = "ralfarminkirchner-netizen/aithentisch-tisch"


def get_token() -> str:
    p = subprocess.run(["git", "credential-osxkeychain", "get"],
                       input="protocol=https\nhost=github.com\n\n",
                       capture_output=True, text=True, timeout=30)
    for line in p.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1].strip()
    return ""


def api(path: str, token: str, method: str = "GET", payload=None):
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        method=method,
        headers={"Authorization": f"token {token}",
                 "Accept": "application/vnd.github+json",
                 "User-Agent": "aithentisch-tisch/2.0"},
        data=json.dumps(payload).encode() if payload is not None else None)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def main():
    token = get_token()
    if not token:
        print("sync_fragen FEHLER: kein GitHub-Token im Schluesselbund.")
        sys.exit(1)

    try:
        issues = api(f"/repos/{REPO}/issues?labels=tischfrage&state=open&per_page=50", token)
    except Exception as e:
        print(f"sync_fragen FEHLER (API): {e}")
        sys.exit(1)

    known = ""
    for f in (QUEUE, DONE):
        if f.exists():
            known += f.read_text(encoding="utf-8")

    new = []
    for issue in issues:
        if "pull_request" in issue:
            continue
        num, title = issue["number"], issue["title"].strip()
        if f"#{num}" in known or title in known:
            continue
        new.append((num, title))

    if not new:
        return  # silent

    lines = QUEUE.read_text(encoding="utf-8").splitlines() if QUEUE.exists() else []
    with QUEUE.open("a", encoding="utf-8") as f:
        if lines and lines[-1].strip():
            pass  # haengt direkt an
        for num, title in new:
            f.write(f"{title}  [GitHub-Issue #{num}]\n")

    for num, title in new:
        try:
            api(f"/repos/{REPO}/issues/{num}/labels", token, "POST", {"labels": ["eingeplant"]})
        except Exception:
            pass
        print(f"eingeplant: #{num} {title[:70]}")


if __name__ == "__main__":
    main()
