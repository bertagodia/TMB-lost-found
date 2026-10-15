"""Convenience launcher: opens SSH tunnel to university server and runs FastAPI backend."""
import os
import subprocess
import sys
from pathlib import Path
from sshtunnel import SSHTunnelForwarder

env_file = Path(__file__).resolve().parent / '.env'
if env_file.exists():
    for line in env_file.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())

SERVER_HOST = os.environ.get('SERVER_HOST', '147.83.46.71')
SERVER_PORT = int(os.environ.get('SERVER_PORT', '60001'))
SSH_USER = os.environ.get('SSH_USER', 'user')
SSH_PASS = os.environ.get('SSH_PASS', '')

PG_HOST = '127.0.0.1'
PG_PORT = 5432
DB_NAME = os.environ.get('DB_NAME', 'tmb_lost_found')
DB_USER = os.environ.get('DB_USER', 'user')
DB_PASS = os.environ.get('DB_PASS', '')

LOCAL_FORWARD_PORT = int(os.environ.get('LOCAL_FORWARD_PORT', '5433'))

def main():
    print(f"[*] Conectando túnel SSH con {SERVER_HOST}:{SERVER_PORT}...")
    try:
        with SSHTunnelForwarder(
            (SERVER_HOST, SERVER_PORT),
            ssh_username=SSH_USER,
            ssh_password=SSH_PASS,
            remote_bind_address=(PG_HOST, PG_PORT),
            local_bind_address=('127.0.0.1', LOCAL_FORWARD_PORT)
        ) as tunnel:
            bound_port = tunnel.local_bind_port
            dsn = f"postgresql://{DB_USER}:{DB_PASS}@127.0.0.1:{bound_port}/{DB_NAME}"
            print(f"[+] Túnel SSH activo en puerto local {bound_port}")
            print(f"[+] Base de datos: {DB_NAME} en {SERVER_HOST}")
            
            env = os.environ.copy()
            env["DATABASE_URL"] = dsn
            
            print("[*] Iniciando servidor FastAPI en http://127.0.0.1:8001 ...")
            cmd = [sys.executable, "-m", "backend.server", "--port", "8001"]
            if len(sys.argv) > 1:
                cmd.extend(sys.argv[1:])
                
            subprocess.run(cmd, env=env)
    except KeyboardInterrupt:
        print("\n[*] Servidor y túnel detenidos correctamente.")

if __name__ == "__main__":
    main()
