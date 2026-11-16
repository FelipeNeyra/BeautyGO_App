"""Lee la configuración del entorno y ejecuta el respaldo comprimido y cifrado."""

import os
from pathlib import Path
import importlib.util
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
MANAGE_PY = ROOT / "manage.py"
REQUIRED_VARIABLES = (
    "B2_ACCESS_KEY_ID",
    "B2_SECRET_ACCESS_KEY",
    "DB_PASSWORD",
    "DBBACKUP_GPG_RECIPIENT",
    "GNUPGHOME",
)
PLACEHOLDER_MARKERS = ("CAMBIAR_", "HUELLA_", "USUARIO_")


def main():
    try:
        import configuracion_entorno
    except ImportError:
        print(
            "No se encontró configuracion_entorno.py. Copia configuracion_entorno.example.py "
            "con ese nombre y completa la configuración local.",
            file=sys.stderr,
        )
        return 2

    configuracion_entorno.aplicar_variables()

    missing = [name for name in REQUIRED_VARIABLES if not os.environ.get(name, "").strip()]
    if missing:
        print("Faltan variables de entorno requeridas: " + ", ".join(missing), file=sys.stderr)
        return 2
    placeholders = [
        name
        for name in REQUIRED_VARIABLES
        if any(marker in os.environ[name] for marker in PLACEHOLDER_MARKERS)
    ]
    if placeholders:
        print("Completa los valores de ejemplo para: " + ", ".join(placeholders), file=sys.stderr)
        return 2

    if shutil.which("mysqldump") is None:
        print("No se encuentra mysqldump en PATH.", file=sys.stderr)
        return 2
    if shutil.which("gpg") is None:
        print("No se encuentra gpg.exe en PATH. Instala GnuPG e importa la clave pública destinataria.", file=sys.stderr)
        return 2
    if importlib.util.find_spec("gnupg") is None:
        print("Falta el módulo Python python-gnupg. Instala requirements.txt en este intérprete.", file=sys.stderr)
        return 2

    recipient = os.environ["DBBACKUP_GPG_RECIPIENT"]
    key_listing = subprocess.run(
        ["gpg", "--batch", "--with-colons", "--list-keys", recipient],
        capture_output=True,
        text=True,
        check=False,
    )
    key_records = [
        line.split(":")
        for line in key_listing.stdout.splitlines()
        if line.startswith(("pub:", "sub:"))
    ]
    if not any(len(record) > 11 and "e" in record[11].lower() for record in key_records):
        print(
            "GPG no encuentra una clave pública destinataria con capacidad de cifrado "
            "en el llavero de esta cuenta de Windows.",
            file=sys.stderr,
        )
        return 2

    if not MANAGE_PY.is_file():
        print(f"No se encuentra {MANAGE_PY}", file=sys.stderr)
        return 2

    command = [sys.executable, str(MANAGE_PY), "dbbackup", "--compress", "--encrypt"]
    return subprocess.run(command, cwd=ROOT, env=os.environ.copy(), check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
