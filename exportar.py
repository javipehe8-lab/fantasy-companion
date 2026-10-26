"""
Prepara los datos de la web: genera web/datos.json a partir de fantasy.db.

Para cada jugador visible (las 6 plantillas + el mercado) calcula:
  - valor actual
  - dif_hoy:  cuánto ha cambiado de ayer a hoy
  - dif_ayer: cuánto cambió de anteayer a ayer
  - historial completo de su valor (para la gráfica)
Y para cada manager, la suma de las diferencias de su plantilla.

Uso:   python exportar.py
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from fantasy.db import conectar
from clausulas import calcular_saldos

CARPETA = Path(__file__).resolve().parent
CRUDOS = CARPETA / "datos_crudos"
SALIDA = CARPETA / "web" / "datos.json"


# ---------------------------------------------------------------------------
# Valores y diferencias
# ---------------------------------------------------------------------------

def valor_en(con, jugador_id: int, fecha: str):
    """Valor de mercado de un jugador en una fecha, o None si no hay dato."""
    fila = con.execute(
        "SELECT valor FROM valores WHERE jugador_id = ? AND fecha = ?",
        (jugador_id, fecha),
    ).fetchone()
    return fila["valor"] if fila else None


def subida_bajada(con, jugador_id: int, fecha_antes, fecha_despues):
    """Cuánto ha subido (+) o bajado (-) entre dos fechas, o None si falta algún dato."""
    if fecha_antes is None or fecha_despues is None:
        return None
    antes = valor_en(con, jugador_id, fecha_antes)
    despues = valor_en(con, jugador_id, fecha_despues)
    if antes is None or despues is None:
        return None
    return despues - antes


def ultimas_fechas(con, n: int) -> list:
    """Las n fechas más recientes con datos, de la más nueva a la más vieja."""
    filas = con.execute(
        "SELECT DISTINCT fecha FROM valores ORDER BY fecha DESC LIMIT ?",
        (n,),
    ).fetchall()
    return [fila["fecha"] for fila in filas]


def historial(con, jugador_id: int) -> list:
    """[[fecha, valor], ...] de un jugador, de la más vieja a la más nueva."""
    filas = con.execute(
        "SELECT fecha, valor FROM valores WHERE jugador_id = ? ORDER BY fecha",
        (jugador_id,),
    ).fetchall()
    return [[f["fecha"], f["valor"]] for f in filas]


# ---------------------------------------------------------------------------
# Quién tiene a quién
# ---------------------------------------------------------------------------

def plantillas(con) -> dict:
    """{manager_id: [jugador_id, ...]} según la foto de cláusulas más reciente
    DE CADA MANAGER (si un día falta la de alguno, se usa la anterior)."""
    resultado = {}
    for fila in con.execute("""
        SELECT c.manager_id, c.jugador_id
        FROM clausulas c
        JOIN (SELECT manager_id, MAX(fecha) AS ultima
              FROM clausulas GROUP BY manager_id) u
          ON u.manager_id = c.manager_id AND u.ultima = c.fecha
    """):
        # setdefault: si el manager aún no está en el diccionario, crea su lista vacía
        resultado.setdefault(fila["manager_id"], []).append(fila["jugador_id"])
    return resultado


def leer_crudo(nombre: str):
    ruta = CRUDOS / f"{nombre}.json"
    if not ruta.exists():
        return None
    return json.loads(ruta.read_text(encoding="utf-8"))


def managers_info() -> tuple:
    """({manager_id: nombre}, mi_manager_id) a partir de la clasificación."""
    clasificacion = leer_crudo("clasificacion") or []
    ligas = leer_crudo("ligas") or [{}]
    mi_equipo = str((ligas[0].get("team") or {}).get("id"))

    nombres, yo = {}, None
    for c in clasificacion:
        equipo = c.get("team") or {}
        manager = equipo.get("manager") or {}
        if not manager.get("id"):
            continue
        mid = int(manager["id"])
        nombres[mid] = manager.get("managerName")
        if str(equipo.get("id")) == mi_equipo:
            yo = mid
    return nombres, yo


def foto_de(jugador: dict):
    """URL de la foto de un jugador (viene dentro de playerMaster)."""
    return ((jugador.get("images") or {}).get("transparent") or {}).get("256x256")


def fotos() -> dict:
    """{jugador_id: url_foto} sacado de las plantillas y del mercado."""
    resultado = {}
    for ruta in CRUDOS.glob("equipo_*.json"):
        equipo = json.loads(ruta.read_text(encoding="utf-8"))
        for p in equipo.get("players", []):
            jugador = p.get("playerMaster") or {}
            if jugador.get("id") and foto_de(jugador):
                resultado[int(jugador["id"])] = foto_de(jugador)
    for item in leer_crudo("mercado") or []:
        jugador = item.get("playerMaster") or {}
        if jugador.get("id") and foto_de(jugador):
            resultado[int(jugador["id"])] = foto_de(jugador)
    return resultado


def mercado() -> list:
    """Jugadores en venta: id, precio, quién lo vende, nº de pujas y cierre."""
    resultado = []
    for item in leer_crudo("mercado") or []:
        jugador = item.get("playerMaster") or {}
        if not jugador.get("id"):
            continue
        vendedor = ((item.get("sellerTeam") or {}).get("manager") or {}).get("managerName")
        resultado.append({
            "id": int(jugador["id"]),
            "precio": item.get("salePrice"),
            "vendedor": vendedor or "LaLiga",
            # marketPlayerLeague = lo pone LaLiga y se renueva cada día
            # marketPlayerTeam   = lo ha puesto a la venta un manager
            "de_laliga": item.get("discr") == "marketPlayerLeague",
            "pujas": item.get("numberOfBids", item.get("numberOfOffers", 0)),
            "cierra": item.get("expirationDate"),
        })
    return resultado


# ---------------------------------------------------------------------------
# Juntarlo todo
# ---------------------------------------------------------------------------

def sumar(valores: list):
    """Suma ignorando los None; None si no hay ningún dato."""
    validos = [v for v in valores if v is not None]
    return sum(validos) if validos else None


def main():
    con = conectar()

    fechas = ultimas_fechas(con, 3) + [None, None, None]   # rellenamos por si faltan días
    hoy, ayer, anteayer = fechas[:3]
    if hoy is None:
        raise SystemExit("No hay datos todavía. Ejecuta antes descargar.py")

    nombres, yo = managers_info()
    # Solo managers que siguen en la liga (por si alguno se va)
    equipos = {m: js for m, js in plantillas(con).items() if not nombres or m in nombres}
    en_venta = mercado()

    # Todos los jugadores que la web va a mostrar, sin repetir
    visibles = {j for lista in equipos.values() for j in lista} | {m["id"] for m in en_venta}

    info = {f["id"]: f for f in con.execute("SELECT id, nombre, equipo, posicion FROM jugadores")}
    urls = fotos()

    jugadores = {}
    for jid in visibles:
        datos = info.get(jid)
        jugadores[jid] = {
            "nombre": datos["nombre"] if datos else f"#{jid}",
            "equipo": datos["equipo"] if datos else None,
            "posicion": datos["posicion"] if datos else None,
            "foto": urls.get(jid),
            "valor": valor_en(con, jid, hoy),
            "dif_hoy": subida_bajada(con, jid, ayer, hoy),
            "dif_ayer": subida_bajada(con, jid, anteayer, ayer),
            "historial": historial(con, jid),
        }

    managers = []
    for mid, lista in equipos.items():
        managers.append({
            "id": mid,
            "nombre": nombres.get(mid, f"#{mid}"),
            "soy_yo": mid == yo,
            "jugadores": lista,
            "valor_total": sumar([jugadores[j]["valor"] for j in lista]),
            "total_hoy": sumar([jugadores[j]["dif_hoy"] for j in lista]),
            "total_ayer": sumar([jugadores[j]["dif_ayer"] for j in lista]),
        })
    # Tú primero, luego el resto por lo que han ganado hoy
    managers.sort(key=lambda m: (not m["soy_yo"], -(m["total_hoy"] or 0)))

    # Saldos: mismo cálculo que clausulas.py (si falla, la web sigue funcionando)
    try:
        r = calcular_saldos(con)
        saldos = {
            "filas": r["filas"],
            "real": r["real"],
            "desde": r["fechas"][0],
            "subidas_exactas": [
                {"fecha": fecha, "manager": r["nombre_manager"].get(mid, mid),
                 "jugador": r["nombre_jugador"].get(jid, jid), "coste": round(coste)}
                for mid, lista in r["detalle_exacto"].items()
                for fecha, jid, _antes, _ahora, coste in lista
            ],
        }
    except (SystemExit, Exception) as error:
        print(f"⚠️  No se pudieron calcular los saldos: {error}")
        saldos = None

    salida = {
        "generado": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "saldos": saldos,
        "fechas": {"hoy": hoy, "ayer": ayer, "anteayer": anteayer},
        "jugadores": jugadores,
        "managers": managers,
        "mercado": en_venta,
    }
    SALIDA.parent.mkdir(exist_ok=True)
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False), encoding="utf-8")
    print(f"✅ {SALIDA.relative_to(CARPETA)}: {len(jugadores)} jugadores, "
          f"{len(managers)} managers, {len(en_venta)} en el mercado")


if __name__ == "__main__":
    main()
