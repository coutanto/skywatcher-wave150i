#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Envoi de commandes UDP à une monture (ex. Wave 150i) et lecture des réponses.
- Les commandes sont lues depuis un fichier texte (ASCII).
- Les lignes de commande peuvent contenir le littéral <cr> qui sera remplacé par '\r'.
- Les lignes vides sont ignorées; les lignes commençant par '#' ou ';' sont des commentaires.
- Directive spéciale: WAIT <secondes>  -> pause entre commandes (ex: WAIT 0.5)

Exemple de fichier:
    # Test basique
    :f1<cr>
    WAIT 0.2
    :f2<cr>
"""

import argparse
import csv
import socket
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

def parse_args():
    p = argparse.ArgumentParser(
        description="Envoi de commandes UDP à la monture et lecture des réponses."
    )
    p.add_argument("host", help="Adresse IP de la monture (ex: 192.168.4.1)")
    p.add_argument("port", type=int, help="Port UDP de la monture (ex: 11880)")
    p.add_argument("cmdfile", type=Path, help="Fichier ASCII des commandes")
    p.add_argument("--timeout", type=float, default=1.0,
                   help="Timeout lecture réponse (s) [def: 1.0]")
    p.add_argument("--retries", type=int, default=2,
                   help="Nombre de tentatives par commande [def: 2]")
    p.add_argument("--delay", type=float, default=0.0,
                   help="Délai fixe entre deux commandes (s) [def: 0.0]")
    p.add_argument("--bind", type=int, default=0,
                   help="Port UDP local à binder (0 = auto)")
    p.add_argument("--out", type=Path, default=Path("session_log.csv"),
                   help="Fichier CSV de log [def: session_log.csv]")
    return p.parse_args()

def load_commands(path: Path):
    cmds = []
    for ln, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        # Directive WAIT t
        if line.upper().startswith("WAIT"):
            parts = line.split()
            if len(parts) != 2:
                raise ValueError(f"Ligne {ln}: syntaxe WAIT invalide -> {raw}")
            try:
                wait_s = float(parts[1])
            except ValueError:
                raise ValueError(f"Ligne {ln}: durée WAIT invalide -> {raw}")
            cmds.append(("WAIT", wait_s, raw))
            continue

        # Remplacement du littéral <cr> par '\r'
        payload = line.replace("<cr>", "\r")
        cmds.append(("SEND", payload, raw))
    return cmds

def hexdump(b: bytes, maxlen: int = 64) -> str:
    s = b[:maxlen].hex(" ")
    return s + (" ..." if len(b) > maxlen else "")

def send_and_recv(sock: socket.socket, host: str, port: int, payload: bytes,
                  timeout: float, retries: int) -> Tuple[bool, Optional[bytes], float, str]:
    """
    Envoie payload et tente de lire une réponse. Réessaie si timeout.
    Retour: (ok, resp_bytes|None, rtt_seconds, err_msg)
    """
    sock.settimeout(timeout)
    last_err = ""
    for attempt in range(1, retries + 1):
        t0 = time.perf_counter()
        try:
            sock.sendto(payload, (host, port))
            data, _ = sock.recvfrom(2048)  # Réponse typiquement courte (=xxx<CR>)
            rtt = time.perf_counter() - t0
            return True, data, rtt, ""
        except socket.timeout:
            last_err = f"timeout (attempt {attempt}/{retries}, timeout={timeout}s)"
        except OSError as e:
            last_err = f"OSError: {e}"
            break
    return False, None, 0.0, last_err

def normalize_text_resp(b: bytes) -> str:
    # Décodage robuste ASCII; strip des CR/LF
    txt = b.decode("ascii", errors="replace").strip("\r\n")
    return txt

def main():
    args = parse_args()

    # Lecture des commandes
    try:
        commands = load_commands(args.cmdfile)
    except Exception as e:
        print(f"[ERREUR] Chargement commandes: {e}", file=sys.stderr)
        sys.exit(1)

    # Socket UDP
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("", args.bind))  # port local auto si 0
    except OSError as e:
        print(f"[ERREUR] Bind UDP local: {e}", file=sys.stderr)
        sys.exit(1)

    # CSV log
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as fcsv:
        w = csv.writer(fcsv)
        w.writerow([
            "timestamp_iso", "cmdline_raw", "directive", "payload_sent",
            "payload_hex", "ok", "response_text", "response_hex",
            "rtt_ms", "error"
        ])

        for kind, val, raw in commands:
            if kind == "WAIT":
                wait_s = float(val)
                print(f"[WAIT] {wait_s}s")
                time.sleep(wait_s)
                # Log la directive
                w.writerow([
                    time.strftime("%Y-%m-%dT%H:%M:%S"),
                    raw, "WAIT", "", "", True, "", "", 0.0, ""
                ])
                continue

            # kind == "SEND"
            payload_str: str = val
            payload_bytes = payload_str.encode("ascii", errors="strict")

            if args.delay > 0:
                time.sleep(args.delay)

            print(f"[SEND] {repr(payload_str)}")
            ok, resp, rtt, err = send_and_recv(
                sock, args.host, args.port, payload_bytes, args.timeout, args.retries
            )

            if ok and resp is not None:
                txt = normalize_text_resp(resp)
                # Optionnel: validation simple format "=...<cr>"
                looks_ok = txt.startswith("=")
                status = "OK" if looks_ok else "WARN"
                print(f"[RECV] ({status}) {repr(txt)}  ({int(rtt*1000)} ms)")
                w.writerow([
                    time.strftime("%Y-%m-%dT%H:%M:%S"),
                    raw, "SEND", payload_str.replace("\r", "<CR>"),
                    hexdump(payload_bytes),
                    looks_ok,
                    txt,
                    hexdump(resp),
                    round(rtt * 1000.0, 2),
                    "" if looks_ok else "Unexpected format"
                ])
            else:
                print(f"[TIMEOUT/ERR] {err}")
                w.writerow([
                    time.strftime("%Y-%m-%dT%H:%M:%S"),
                    raw, "SEND", payload_str.replace("\r", "<CR>"),
                    hexdump(payload_bytes),
                    False, "", "", 0.0, err
                ])

    sock.close()
    print(f"\n[LOG] Écrit: {args.out.resolve()}")

if __name__ == "__main__":
    main()
