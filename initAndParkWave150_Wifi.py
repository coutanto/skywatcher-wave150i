#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Sep  8 21:49:18 2025

@author: Olivier Coutant & ChatGpt

Contrôler une monture SkyWatcher Wave150i via UDP,
faire initialisation, puis lancer 2 threads configurant axe1 et axe2.

Traitement des erreurs incomplet
TODO: error management
"""

import socket
import threading
import time
from typing import Optional, Tuple, List, Callable
import parkAxis

# ----------------------------
# Configuration réseau / temps
# ----------------------------
MOUNT_IP = "192.168.4.1"   # adapter
MOUNT_PORT = 11880         # adapter
LOCAL_BIND_PORT = 0        # 0 = auto
RECV_BUF = 4096
DEFAULT_TIMEOUT = 1.0      # s
DEFAULT_RETRIES = 2
INTER_CMD_DELAY = 0.05     # s entre envois


# ----------------------------
# Utilitaires
# ----------------------------
def safe_encode(cmd: str) -> bytes:
    """Encoder en ascii; remplacer les littéraux <cr> si nécessaires."""
    # si tu veux accepter l'écriture :f1<cr> dans les listes, décommenter
    # cmd = cmd.replace("<cr>", "\r")
    tmp = cmd.strip().replace(" ","")+"\r"
    return tmp.encode("ascii", errors="ignore")


# ----------------------------
# UDP client thread-safe
# ----------------------------
class ThreadSafeUDPClient:
    def __init__(self, host: str, port: int, bind_port: int = 0,
                 timeout: float = DEFAULT_TIMEOUT, retries: int = DEFAULT_RETRIES):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.retries = retries
        self.lock = threading.Lock()           # protège send+recv
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(self.timeout)
        self.inter_cmd_delay = INTER_CMD_DELAY
        try:
            self.sock.bind(("", bind_port))
        except OSError as e:
            raise RuntimeError(f"Impossible de binder le port local: {e}")

    def close(self):
        with self.lock:
            try:
                self.sock.close()
            except Exception:
                pass

    def send_and_recv(self, cmd: str, expect_response: bool = True
                     ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Envoie payload (bytes) et attend une réponse si expect_response True.
        Protège send+recv par un lock pour éviter les croisements de trames.
        Retourne: (ok, response_bytes_or_None, error_message_or_empty)
        """
        payload = safe_encode(cmd)
        last_err = ""
        for attempt in range(1, self.retries + 1):
            with self.lock:
                try:
                    # Envoi
                    self.sock.sendto(payload, (self.host, self.port))
                    # Lecture seulement si on attend une réponse
                    if expect_response:
                        data, _addr = self.sock.recvfrom(RECV_BUF)
                        txt = data.decode("ascii", errors="ignore").strip("\r\n")
                        if txt[0]=='=':
                            print(txt)
                            return True, txt[1:], ""
                        else:
                            return False, None, ""
                    else:
                        return True, None, ""
                except socket.timeout:
                    last_err = f"timeout (attempt {attempt}/{self.retries})"
                except OSError as e:
                    last_err = f"OSError: {e}"
                    break
            # si on arrive ici c'est qu'on a eu timeout ou erreur
            time.sleep(0.02)  # petite pause avant retry
        return False, None, last_err


# ----------------------------
# Worker thread pour un axe
# ----------------------------
class AxisWorker(threading.Thread):
    def __init__(self, name: str, client: ThreadSafeUDPClient, 
                 stop_event: threading.Event, 
                 delay_between_cmd: float = INTER_CMD_DELAY, 
                 process: Optional[Callable[[str, bytes], None]] = None):
        super().__init__(daemon=True)
        self.name = name
        self.client = client
        self.stop_event = stop_event
        self.delay_between_cmd = delay_between_cmd
        self.process = process
        
        self.thread = threading.Thread(target=process, args=(name, self))


# ----------------------------
# Routine d'initialisation séquentielle
# ----------------------------
def run_initialization(client: ThreadSafeUDPClient) -> bool:
    print("[INIT] Démarrage initialisation séquentielle...")
    # Sequence d'initialisation
    ok=parkAxis.init_mount(client)
    if (ok):
        print("[INIT] Initialisation terminée avec succès.")
        return True
    else:
        print("[INIT] Initialisation échoué.")
        return False

# ----------------------------
# programme principal
# ----------------------------
def main():
    stop_event = threading.Event()
    client = None
    try:
        client = ThreadSafeUDPClient(MOUNT_IP, MOUNT_PORT, bind_port=LOCAL_BIND_PORT,
                                     timeout=DEFAULT_TIMEOUT, retries=DEFAULT_RETRIES)

        # 1) initialisation séquentielle
        ok = run_initialization(client)
        if not ok:
            print("[MAIN] Initialisation échouée -> arrêt.")
            return

        # 2) lancer les workers et les threads pour chaque axe
        axis1 = AxisWorker("Axe1", client,  stop_event, process=parkAxis.axis1)
        axis2 = AxisWorker("Axe2", client,  stop_event, process=parkAxis.axis2)


    # Démarre les threads
        axis1.thread.start()
        axis2.thread.start()


        # 3) attendre fin ou Ctrl-C
        try:
            while axis1.thread.is_alive() or axis2.thread.is_alive():
                time.sleep(0.2)
        except KeyboardInterrupt:
            print("[MAIN] Ctrl-C reçu -> arrêt des threads...")
            stop_event.set()

        axis1.thread.join(timeout=2.0)
        axis2.thread.join(timeout=2.0)
        print("[MAIN] Workers terminés, fermeture cliente.")
    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    main()