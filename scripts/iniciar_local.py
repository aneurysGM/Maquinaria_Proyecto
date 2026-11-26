"""Ejecuta MaquiRent en desarrollo local con su entorno virtual y sus estilos."""

import argparse
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--noreload', action='store_true', help='Desactivar la recarga automatica')
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parent.parent
    python_path = project_root / '.venv' / 'Scripts' / 'python.exe'
    if not python_path.is_file():
        parser.error('Crea .venv e instala requirements.txt antes de iniciar el servidor.')

    command = [str(python_path), 'manage.py', 'runserver', '127.0.0.1:8000']
    if args.noreload:
        command.append('--noreload')
    # Limita DEBUG al proceso local: runserver necesita servir los archivos estaticos.
    local_env = {**os.environ, 'DEBUG': 'True'}
    try:
        return subprocess.run(command, cwd=project_root, env=local_env).returncode
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
