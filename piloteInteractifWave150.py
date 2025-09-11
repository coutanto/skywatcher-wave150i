import socket
import ctypes

# ------------------------
# Paramètres de connexion
# ------------------------
MOUNT_IP = "192.168.4.1"   # IP de la monture (à adapter)
MOUNT_PORT = 11880         # Port UDP de la monture (à adapter)

def interactive_session(ip, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2.0)

    print("=== Session interactive SkyWatcher (UDP) ===")
    print("Tapez une commande (ex: :f1 ou :GVP). Tapez 'quit' pour sortir.\n")

    while True:
        cmd = input("Commande > ").strip().replace(" ","")
        if cmd.lower() in ("quit", "exit"):
            break

        # Ajout <CR> si non fourni
        if not cmd.endswith("\r"):
            cmd += "\r"

        try:
            sock.sendto(cmd.encode("ascii"), (ip, port))
            data, _ = sock.recvfrom(1024)
            resp=data.decode(errors='ignore').strip()
            s = resp.strip().lstrip("=")
            try:
                 print(f"Réponse: {s}, {ctypes.c_int32(int(s, 16)).value}")
            except:
                 print(f"Réponse: {s}")
        except socket.timeout:
            print("⚠️ Pas de réponse (timeout)")

    sock.close()
    print("Session terminée.")

if __name__ == "__main__":
    interactive_session(MOUNT_IP, MOUNT_PORT)
