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
import serial
import threading
import time
from typing import Optional, Tuple, Callable
import parkAxis

# ----------------------------
# Configuration réseau / temps
# ----------------------------

MOUNT_PORT = "/dev/tty.usbserial-A10NDBX9"         # adapter
MOUNT_BAUDRATE = 9600
DEFAULT_TIMEOUT = 1.0      # s
DEFAULT_RETRIES = 1
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


class ThreadSafeSerialClient:
    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 2.0,
                 retries: int = 1):
        self.lock = threading.Lock()
        self.retries = retries

        # ouverture du port série
        self.ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=timeout
        )
        self.inter_cmd_delay = INTER_CMD_DELAY

    def send_and_recv(self, cmd: str, expect_response: bool = True
                      ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Envoie une commande et lit la réponse de manière thread-safe"""
        with self.lock:
            if not cmd.endswith("\r"):
                cmd = cmd + "\r"

            # envoi
            self.ser.write(cmd.encode("ascii"))

            # lecture (jusqu’au retour chariot ou timeout)
            try:
                data = self.ser.readline()
                txt = data.decode("ascii", errors="ignore").strip("\r\n")
                if txt[0]=='=':
                    print(txt)
                    return True, txt[1:], ""
                else:
                    return False, None, ""

            except Exception as e:
                err = f"<error: {e}>"
                return False, None, err

    def close(self):
        self.ser.close()


# ----------------------------
# Worker thread pour un axe
# ----------------------------
class AxisWorker(threading.Thread):
    def __init__(self, name: str, client: ThreadSafeSerialClient, 
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
def run_initialization(client: ThreadSafeSerialClient) -> bool:
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
        client = ThreadSafeSerialClient(MOUNT_PORT, 
                                        MOUNT_BAUDRATE, 
                                        DEFAULT_TIMEOUT, 
                                        DEFAULT_RETRIES)

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