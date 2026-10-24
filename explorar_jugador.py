"""
Exploración: ¿qué endpoint nos da el HISTORIAL de valor de mercado?

Prueba dos rutas con un par de jugadores y guarda lo que respondan en
datos_crudos/explorar_*.json. No imprime ni guarda tu token.

Uso:   python explorar_jugador.py
"""
import json
from pathlib import Path

from fantasy.api import CMP, FantasyAPI

CRUDOS = Path(__file__).resolve().parent / "datos_crudos"
JUGADORES = ["2435", "2303"]  # Marrero (tu equipo) e Iván Romero (mercado)


def main():
    liga_id = json.loads((CRUDOS / "ligas.json").read_text(encoding="utf-8"))[0]["id"]
    api = FantasyAPI()

    for jugador in JUGADORES:
        rutas = {
            "detalle": f"{CMP}/player/{jugador}/league/{liga_id}",
            "historial_v3": f"/v3/player/{jugador}/market-value",
            "historial_v4": f"/v4/player/{jugador}/market-value",
        }
        for nombre, ruta in rutas.items():
            archivo = CRUDOS / f"explorar_{jugador}_{nombre}.json"
            try:
                datos = api._get(ruta)
                archivo.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"✅ {jugador} {nombre}: guardado")
            except Exception as e:
                print(f"❌ {jugador} {nombre}: {e}")


if __name__ == "__main__":
    main()
