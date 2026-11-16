"""Plantilla de configuración local para el ejecutor de respaldos.

Cópiala como configuracion_entorno.py y reemplaza los valores de ejemplo. El
archivo real está excluido de Git. El ejecutor importa esta configuración en
cada ejecución; no pongas credenciales reales en esta plantilla.
"""

import os

VARIABLES = {
    "DJANGO_SECRET_KEY": "CAMBIAR_POR_UNA_CLAVE_DJANGO",
    "DB_NAME": "gestion_rgbeauty2",
    "DB_USER": "USUARIO_MYSQL",
    "DB_PASSWORD": "CAMBIAR_POR_LA_CLAVE_MYSQL",
    "DB_HOST": "localhost",
    "DB_PORT": "3306",
    "B2_ACCESS_KEY_ID": "CAMBIAR_POR_KEY_ID",
    "B2_SECRET_ACCESS_KEY": "CAMBIAR_POR_APPLICATION_KEY",
    "B2_BUCKET_NAME": "respaldos-bdd-beautygo",
    "B2_REGION_NAME": "eu-central-003",
    "DBBACKUP_GPG_RECIPIENT": "HUELLA_DE_LA_CLAVE_PUBLICA_GPG",
    "GNUPGHOME": r"C:\Users\USUARIO\AppData\Roaming\gnupg",
}


def aplicar_variables():
    """Expone las variables a Django y a los procesos hijos de esta ejecución."""
    os.environ.update(VARIABLES)
