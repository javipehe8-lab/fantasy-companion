"""
Cliente de SOLO LECTURA para la API (no oficial) de LaLiga Fantasy.

A propósito solo hay métodos GET: este proyecto consulta datos, nunca
puja, vende ni toca tu equipo. Si algún día quieres acciones, añádelas
tú sabiendo lo que haces.
"""
import time

import requests

from .auth import obtener_bearer

BASE_URL = "https://fantasy-api.llt-services.com/api"
CMP = "/v1/competition/1"  # 1 = LaLiga EA Sports
PAUSA_ENTRE_PETICIONES = 0.7  # segundos: sé amable con su servidor


class FantasyAPI:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update(
            {
                "Authorization": f"Bearer {obtener_bearer()}",
                "x-app": "2",
                "x-lang": "es",
                "User-Agent": "Mozilla/5.0 (fantasy-companion; uso personal)",
            }
        )

    def _get(self, ruta: str):
        time.sleep(PAUSA_ENTRE_PETICIONES)
        sep = "&" if "?" in ruta else "?"
        r = self.s.get(f"{BASE_URL}{ruta}{sep}x-lang=es", timeout=20)
        if r.status_code == 401:
            raise SystemExit("La API dice 401 (no autorizado): vuelve a copiar token.json.")
        r.raise_for_status()
        return r.json()

    # --- Tú ---
    def yo(self):
        return self._get("/v4/user/me")

    def mis_ligas(self):
        return self._get(f"{CMP}/leagues")

    # --- Jugadores y mercado ---
    def jugadores(self):
        """Todos los jugadores de LaLiga con su valor de mercado actual."""
        return self._get(f"{CMP}/players")

    def mercado(self, liga_id):
        return self._get(f"{CMP}/league/{liga_id}/market")

    # --- Tu liga ---
    def clasificacion(self, liga_id):
        return self._get(f"{CMP}/leagues/{liga_id}/standing")

    def actividad(self, liga_id, pagina: int = 0):
        """Fichajes, ventas, cláusulas y premios de la liga (paginado)."""
        return self._get(f"{CMP}/leagues/{liga_id}/activity/{pagina}")

    def equipo(self, liga_id, equipo_id):
        """Plantilla de un equipo de tu liga, con la cláusula de cada jugador."""
        return self._get(f"{CMP}/leagues/{liga_id}/teams/{equipo_id}")

    def dinero_equipo(self, equipo_id):
        """Probablemente solo funcione con TU equipo (lo comprobaremos)."""
        return self._get(f"{CMP}/teams/{equipo_id}/money")


def como_lista(respuesta):
    """La API a veces devuelve una lista y a veces {'data': [...]}. Normalizamos."""
    if isinstance(respuesta, list):
        return respuesta
    if isinstance(respuesta, dict):
        for clave in ("data", "elements", "items", "results"):
            if isinstance(respuesta.get(clave), list):
                return respuesta[clave]
    return []
