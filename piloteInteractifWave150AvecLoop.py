import socket
import ctypes
import time
from typing import Optional, Tuple


# ------------------------
# Paramètres de connexion
# ------------------------
MOUNT_IP = "192.168.4.1"   # IP de la monture (à adapter)
MOUNT_PORT = 11880         # Port UDP de la monture (à adapter)
TIMEOUT = 2.
RETRIES = 20

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
            resp=data.decode(errors='ignore').strip()
            resp = resp.strip().lstrip("=")
            #print(f"{resp}")
            rtt = time.perf_counter() - t0
            return True, resp, rtt, ""
        except socket.timeout:
            last_err = f"timeout (attempt {attempt}/{retries}, timeout={timeout}s)"
        except OSError as e:
            last_err = f"OSError: {e}"
            break
    return False, None, 0.0, last_err

def processLoop(cmd, sock, ip, port, timeout, retries):
    
    parts = cmd.split(maxsplit=2)
    print (f'LOOP on {parts[1]} waiting  {parts[2]}')
    if len(parts) != 3:
        raise ValueError('syntaxe fausse pour LOOP: {cmd}')
    sw_cmd = parts[1]+'\r'
    ok, resp, rtt, err = send_and_recv(
        sock, ip, port, sw_cmd.encode("ascii"), 
        timeout, retries
    )
    print(f'> {parts[1]} => Response {resp}, condition {parts[2]}',eval(parts[2]))
    while (eval(parts[2])):
        time.sleep(0.1)
        ok, resp, rtt, err = send_and_recv(
            sock, ip, port, sw_cmd.encode("ascii"), 
            timeout, retries)
        print(f'> {parts[1]} => Response {resp}, condition {parts[2]}',eval(parts[2]))

        
def decode_status(s: str) -> str:
    """
    Décode une chaîne hexa de 3 caractères (ex: '0FA')
    et renvoie une description compacte des statuts.
    """

    # Convertir en entier
    value = int(s, 16)

    # Extraire les 3 digits hex
    c1 = (value >> 8) & 0xF   # premier caractère
    c2 = (value >> 4) & 0xF   # deuxième
    c3 = value & 0xF          # troisième

    # Décodage
    parts = [
        "Tracking" if (c1 & 0b001) else "Goto",
        "CCW" if (c1 & 0b010) else "CW",
        "Fast" if (c1 & 0b100) else "Slow",
        "Running" if (c2 & 0b001) else "Stopped",
        "Blocked" if (c2 & 0b010) else "Normal",
        "Init done" if (c3 & 0b001) else "Not Init",
        "Level on" if (c3 & 0b010) else "Level off",
    ]

    return " | ".join(parts)

def decode_position(hexstr: str) -> int:
    """
    Décode une chaîne de 6 caractères hexadécimaux (24 bits)
    envoyée dans l'ordre 56 34 12 et renvoie l'entier correspondant.

    Exemple :
        "563412" -> 0x123456 -> 1193046
    """
    if len(hexstr) != 6:
        raise ValueError("La chaîne doit contenir exactement 6 caractères hexadécimaux")

    # Extraire les octets envoyés
    b1 = hexstr[0:2]  # "56"
    b2 = hexstr[2:4]  # "34"
    b3 = hexstr[4:6]  # "12"

    # Remettre dans l'ordre correct = 12 34 56
    reordered = b3 + b2 + b1

    # Convertir en entier
    return int(reordered, 16)

def interactive_session(ip, port, timeout, retries):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    print("=== Session interactive SkyWatcher (UDP) ===")
    print("Tapez une commande (ex: :f1 ou :GVP). Tapez 'quit' pour sortir.\n")

    while True:
        raw = input("Commande > ")
        cmd = raw.strip().replace(" ","")
        if not cmd or cmd.startswith("#") or cmd.startswith(";"):
            continue

# process WAIT        
        if cmd.upper().startswith("WAIT"):
            parts = cmd.split()
            if len(parts) != 2:
                raise ValueError(f"Input: syntaxe WAIT invalide -> {cmd}")
            try:
                wait_s = float(parts[1])
            except ValueError:
                raise ValueError(f"Input: durée WAIT invalide -> {cmd}")
            time.sleep(wait_s)

#process LOOP      
        if cmd.upper().startswith("LOOP"):
            processLoop(raw, sock, ip, port, timeout, retries)
            continue

    
# process skywatcher command  
        kind=cmd[1]
        
#        for kind in ('f','e','q'):
        if cmd.lower() in ("quit", "exit"):
            break

        # Ajout <CR> si non fourni
        if not cmd.endswith("\r"):
            cmd += "\r"

        ok, resp, rtt, err = send_and_recv(
            sock, ip, port, cmd.encode("ascii"), 
            timeout, retries
        )
        if (ok != True):
            raise ValueError('ca merdouille')
            
        if (kind=='f'):
            try:
                print(f"Réponse: {decode_status(resp)}")
            except:
                pass
            
        elif (kind=='X' and cmd[3:5]=='0F'):
            try:
                pos1 = ctypes.c_int32(int(resp[1:9], 16)).value
                pos2 = ctypes.c_int32(int(resp[9:17], 16)).value
                unknown = ctypes.c_int32(int(resp[25:32], 16)).value/1000000
                print(f'Réponse: Ox{resp}; {pos1}; {pos2}; {unknown}')
            except:
                pass
            
        elif (kind=='j'):
            try:
                pos = decode_position(resp)
                print(f"Réponse (j): 0x{pos}, {ctypes.c_uint32(int(resp, 16)).value} {pos - ctypes.c_uint32(int('0x800000', 16)).value}")
            except:
                pass
        else:
            try:
                 print(f"Réponse: {resp}, {ctypes.c_int32(int(resp, 16)).value}")
            except:
                 print(f"Réponse: {resp}")        

        # try:
        #     sock.sendto(cmd.encode("ascii"), (ip, port))
        #     data, _ = sock.recvfrom(1024)
        #     resp=data.decode(errors='ignore').strip()
        #     s = resp.strip().lstrip("=")
        #     try:
        #          print(f"Réponse: {s}, {ctypes.c_int32(int(s, 16)).value}")
        #     except:
        #          print(f"Réponse: {s}")
        # except socket.timeout:
        #     print("⚠️ Pas de réponse (timeout)")

    sock.close()
    print("Session terminée.")

if __name__ == "__main__":
    interactive_session(MOUNT_IP, MOUNT_PORT, TIMEOUT, RETRIES)
