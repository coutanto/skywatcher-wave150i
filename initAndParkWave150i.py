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
import serial
import threading
import time
from typing import Optional, Tuple, Callable
import parkAxis
import sys
import getopt


# =================================================================
#
#                 Connection parameter
#
# =================================================================
class Connection:
    def __init__(self, iface):
    # ----------------------------
    # Configuration UDP / temps
    # ----------------------------
        if iface == "UDP":           
            self.MOUNT_IP = "192.168.4.1"   # adapter
            self.MOUNT_PORT = 11880         # adapter
            self.LOCAL_BIND_PORT = 0        # 0 = auto
            self.RECV_BUF = 4096
            self.DEFAULT_TIMEOUT = 1.0      # s
            self.DEFAULT_RETRIES = 2
            self.INTER_CMD_DELAY = 0.05     # s entre envois

    # ----------------------------
    # Configuration USB / temps
    # ----------------------------
        elif iface == "USB":
            self.MOUNT_PORT = "/dev/tty.usbserial-A10NDBX9"         # adapter
            self.MOUNT_BAUDRATE = 9600
            self.DEFAULT_TIMEOUT = 1.0      # s
            self.DEFAULT_RETRIES = 2
            self.INTER_CMD_DELAY = 0.05     # s entre envois
            
        else:
            raise ValueError('interface must be one of (USB, UDP)')



# =================================================================
#
#                 Utilities
#
# =================================================================
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
    def __init__(self, conn):
        self.host = conn.MOUNT_IP
        self.port = conn.MOUNT_PORT
        self.timeout = conn.DEFAULT_TIMEOUT
        self.retries = conn.DEFAULT_RETRIES
        self.RECV_BUF = conn.RECV_BUF
        self.lock = threading.Lock()           # protège send+recv
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(self.timeout)
        self.inter_cmd_delay = conn.INTER_CMD_DELAY
        try:
            self.sock.bind(("", conn.LOCAL_BIND_PORT))
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
                        data, _addr = self.sock.recvfrom(self.RECV_BUF)
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
# USB-Serial client thread-safe
# ----------------------------
class ThreadSafeSerialClient:
    def __init__(self, conn): 
    
        self.lock = threading.Lock()
        self.retries = conn.DEFAULT_RETRIES

        # ouverture du port série
        self.ser = serial.Serial(
            port=conn.MOUNT_PORT,
            baudrate=conn.MOUNT_BAUDRATE,
            timeout=conn.DEFAULT_TIMEOUT
        )
        self.inter_cmd_delay = conn.INTER_CMD_DELAY

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
    def __init__(self, name: str, 
                 driver: str,
                 client: ThreadSafeUDPClient, 
                 stop_event: threading.Event, 
                 process: Optional[Callable[[str, bytes], None]] = None):
        super().__init__(daemon=True)
        self.name = name
        self.client = client
        self.driver = driver
        self.stop_event = stop_event
        self.delay_between_cmd = client.inter_cmd_delay
        self.process = process
        
        self.thread = threading.Thread(target=process, args=(name, self))


# ----------------------------
# Routine d'initialisation séquentielle
# ----------------------------
def run_initialization(driver, client: ThreadSafeUDPClient) -> bool:
    print("[INIT] Démarrage initialisation séquentielle...")
    # Sequence d'initialisation
    ok=parkAxis.init_mount(driver, client)
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
    
    # parse command line args
    driver = "SynScan"
    iface = "UDP"
    try:
        opts, args = getopt.getopt(sys.argv[1:], "d:i:", ["driver=", "iface="])
    except:
        raise ValueError("usage: {sys.argv[0]} [--driver [INDI, SynScan]][--iface [UDP, USB]]")
    
    for opt, arg in opts:
        if opt in ("-d", "--driver"):
            driver = arg
        if opt in ("-i", "--iface"):
            iface = arg
        
        
    stop_event = threading.Event()
    conn = Connection(iface)
    client = None
    try:
        if iface == "UDP":
            client = ThreadSafeUDPClient(conn)
        elif iface == "USB":
            client = ThreadSafeSerialClient(conn)

        # 1) initialisation séquentielle
        ok = run_initialization(driver, client)
        if not ok:
            print("[MAIN] Initialisation échouée -> arrêt.")
            return

        # 2) lancer les workers et les threads pour chaque axe
        axis1 = AxisWorker("Axis1", driver, client,  stop_event, process=parkAxis.axis1)
        axis2 = AxisWorker("Axis2", driver, client,  stop_event, process=parkAxis.axis2)


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