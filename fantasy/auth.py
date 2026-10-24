"""
Gestión del token de LaLiga Fantasy.

token.json es la respuesta completa de login.laliga.es que copias desde
las herramientas de desarrollador (ver README). Contiene:
  - id_token:      el "pase" que mandamos en cada petición (caduca en ~24 h)
  - refresh_token: sirve para pedir un id_token nuevo sin volver a iniciar sesión

¡token.json equivale a tu contraseña! Nunca lo subas a GitHub ni lo compartas.
"""
import base64
import json
import time
from pathlib import Path

import requests

TOKEN_FILE = Path(__file__).resolve().parent.parent / "token.json"

# Endpoint y client_id que usa la web de LaLiga para refrescar la sesión
REFRESH_URL = (
    "https://login.laliga.es/laligadspprob2c.onmicrosoft.com/oauth2/v2.0/token"
    "?p=B2C_1A_5ULAIP_PARAMETRIZED_SIGNIN"
)
CLIENT_ID_POR_DEFECTO = "6457fa17-1224-416a-b21a-ee6ce76e9bc0"


def _leer_payload_jwt(jwt: str) -> dict:
    """Un JWT son 3 trozos en base64 separados por puntos; el del medio es un JSON."""
    payload = jwt.split(".")[1]
    payload += "=" * (-len(payload) % 4)  # base64 necesita relleno
    return json.loads(base64.urlsafe_b64decode(payload))


def _cargar() -> dict:
    if not TOKEN_FILE.exists():
        raise SystemExit(
            "No encuentro token.json. Sigue el paso 3 del README para obtenerlo."
        )
    return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))


def _caducado(jwt: str, margen_seg: int = 300) -> bool:
    try:
        return _leer_payload_jwt(jwt)["exp"] - margen_seg < time.time()
    except Exception:
        return True


def _refrescar(tokens: dict) -> dict:
    refresh = tokens.get("refresh_token")
    if not refresh:
        raise SystemExit("token.json no tiene refresh_token. Vuelve a copiarlo entero.")

    # El client_id con el que se emitió el token va dentro del propio JWT ("aud")
    try:
        client_id = _leer_payload_jwt(tokens["id_token"]).get("aud", CLIENT_ID_POR_DEFECTO)
    except Exception:
        client_id = CLIENT_ID_POR_DEFECTO

    r = requests.post(
        REFRESH_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh,
            "client_id": client_id,
            "scope": "openid offline_access",
        },
        timeout=15,
    )
    if r.status_code != 200:
        raise SystemExit(
            f"No he podido refrescar la sesión (HTTP {r.status_code}). "
            "Vuelve a copiar token.json desde el navegador."
        )
    nuevos = {**tokens, **r.json()}
    TOKEN_FILE.write_text(json.dumps(nuevos, indent=2), encoding="utf-8")
    print("🔄 Sesión renovada y guardada en token.json")
    return nuevos


def obtener_bearer() -> str:
    """Devuelve un id_token válido, refrescándolo si hace falta."""
    tokens = _cargar()
    jwt = tokens.get("id_token") or tokens.get("access_token")
    if not jwt or _caducado(jwt):
        tokens = _refrescar(tokens)
        jwt = tokens.get("id_token") or tokens.get("access_token")
    return jwt
