"""
Paso 1 del día: descarga los datos y guarda la "foto" de hoy.

Uso:   python descargar.py
Ejecútalo una vez al día (por ejemplo, por la mañana, después de que
se actualicen los valores de mercado).
"""
import json
from datetime import date
from pathlib import Path

from fantasy.api import FantasyAPI, como_lista
from fantasy.db import (conectar, guardar_actividad, guardar_jugadores,
                        guardar_mi_saldo, guardar_plantilla)

CARPETA_CRUDOS = Path(__file__).resolve().parent / "datos_crudos"
MAX_PAGINAS_ACTIVIDAD = 50  # tope de seguridad; normalmente para mucho antes


def guardar_crudo(nombre: str, datos) -> None:
    """Guarda la respuesta tal cual: imprescindible para explorar la API."""
    CARPETA_CRUDOS.mkdir(exist_ok=True)
    (CARPETA_CRUDOS / f"{nombre}.json").write_text(
        json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def main():
    hoy = date.today().isoformat()
    api = FantasyAPI()
    con = conectar()

    # 1) Tus ligas
    ligas = como_lista(api.mis_ligas())
    guardar_crudo("ligas", ligas)
    if not ligas:
        raise SystemExit("No he encontrado ligas en tu cuenta.")
    print("Tus ligas:")
    for l in ligas:
        print(f"  · {l.get('name')}  (id {l.get('id')})")
    liga = ligas[0]
    liga_id = liga.get("id")
    print(f"\nUsando: {liga.get('name')}\n")

    # 2) Valores de mercado de todos los jugadores (la "foto" de hoy)
    jugadores = como_lista(api.jugadores())
    guardar_crudo("jugadores", jugadores[:5])  # una muestra basta para ver la estructura
    n = guardar_jugadores(con, jugadores, hoy)
    print(f"✅ {n} jugadores guardados con su valor de {hoy}")

    # 3) Mercado y clasificación de tu liga
    guardar_crudo("mercado", api.mercado(liga_id))
    clasificacion = como_lista(api.clasificacion(liga_id))
    guardar_crudo("clasificacion", clasificacion)
    print("✅ Mercado y clasificación guardados en datos_crudos/")

    # 3b) Tu saldo real y la cláusula de cada jugador de cada equipo
    guardar_mi_saldo(con, hoy, (liga.get("team") or {}).get("money"))
    total_clausulas = 0
    for c in clasificacion:
        equipo = c.get("team") or {}
        manager_id = (equipo.get("manager") or {}).get("id") or equipo.get("managerId")
        if not equipo.get("id") or not manager_id:
            continue
        plantilla = api.equipo(liga_id, equipo["id"])
        guardar_crudo(f"equipo_{equipo['id']}", plantilla)
        jugadores_equipo = plantilla.get("players", []) if isinstance(plantilla, dict) else []
        total_clausulas += guardar_plantilla(con, hoy, manager_id, jugadores_equipo)
    print(f"✅ Cláusulas de {total_clausulas} jugadores de la liga guardadas")

    # 4) Actividad (fichajes, ventas, premios): base del saldo de los rivales
    total_nuevos = 0
    muestra = []
    for pagina in range(MAX_PAGINAS_ACTIVIDAD):
        movs = como_lista(api.actividad(liga_id, pagina))
        if not movs:
            break
        muestra.extend(movs)
        nuevos = guardar_actividad(con, liga_id, movs)
        total_nuevos += nuevos
        if nuevos == 0:
            break  # esta página ya la teníamos: lo anterior también
    guardar_crudo("actividad", muestra)
    print(f"✅ Actividad: {total_nuevos} movimientos nuevos guardados")

    print("\nListo. Ahora puedes ejecutar:  python resumen.py  ·  python clausulas.py")


if __name__ == "__main__":
    main()
