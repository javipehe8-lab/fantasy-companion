"""
Gasto en subir cláusulas y saldo ajustado de cada manager.

La actividad no registra las subidas de cláusula, así que las sacamos de las
fotos diarias de cláusulas que guarda descargar.py. Subir una cláusula usa
factor 2: pagas X y la cláusula sube 2X.

Dos partes:
  1) DESDE QUE EMPEZASTE A GUARDAR DATOS -> EXACTO
     Si la cláusula de un jugador sube de un día al siguiente sin cambiar
     de dueño, es una subida, y costó la mitad.
  2) ANTES DE ESO -> ESTIMACIÓN
     Comparamos la cláusula del primer día con su "base":
     el mayor entre 1 M€ (mínimo del juego), lo que se pagó y el valor de
     mercado de ese día. Como no hay historial de valores anterior, si el
     jugador se revalorizó desde la subida, esa subida queda oculta:
     esta parte tiende a quedarse CORTA.

Uso:   python descargar.py   (una vez al día)
       python clausulas.py
"""
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from fantasy.db import conectar
from saldos import SALDO_INICIAL, calcular_movimientos, euros, leer

FACTOR_SUBIDA = 2
CLAUSULA_MINIMA = 1_000_000
TOLERANCIA = 1_000  # € de margen por redondeos


def a_utc(texto):
    """'2026-10-24T21:15:00+02:00' -> datetime en UTC (None si no se puede)."""
    try:
        return datetime.fromisoformat(texto).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def adquisiciones(movimientos):
    """(manager, jugador) -> lista de (fecha 'AAAA-MM-DD', momento UTC, precio)."""
    res = defaultdict(list)
    for m in movimientos:
        if m.get("activityTypeId") in (1, 31) and m.get("playerMasterId"):
            creado = m.get("createdAt", "")
            res[(m["user1Id"], int(m["playerMasterId"]))].append(
                (creado[:10], a_utc(creado), m.get("amount") or 0))
    return res


def comprado_entre(compras_jugador, ayer, hoy, momentos):
    """¿Hubo una compra entre la foto de 'ayer' y la de 'hoy'?"""
    desde, hasta = momentos.get(ayer), momentos.get(hoy)
    for fecha, momento, _ in compras_jugador:
        if desde and hasta and momento:
            if desde < momento <= hasta:
                return True
        elif ayer <= fecha <= hoy:  # fotos antiguas sin hora: criterio prudente
            return True
    return False


def estimacion_historica(con, fecha, compras):
    """Subidas anteriores al primer día con datos (aproximado)."""
    gasto, detalle = defaultdict(float), defaultdict(list)
    for r in con.execute("SELECT * FROM clausulas WHERE fecha = ?", (fecha,)):
        precios = [p for f, _, p in compras.get((r["manager_id"], r["jugador_id"]), []) if f <= fecha]
        pagado = precios[-1] if precios else 0
        base = max(CLAUSULA_MINIMA, pagado, r["valor"] or 0)
        if r["clausula"] > base:
            coste = (r["clausula"] - base) / FACTOR_SUBIDA
            gasto[r["manager_id"]] += coste
            detalle[r["manager_id"]].append((r["jugador_id"], r["clausula"], base, coste))
    return gasto, detalle


def subidas_exactas(con, fechas, compras):
    """Compara cada par de días consecutivos."""
    gasto, detalle, dudosas = defaultdict(float), defaultdict(list), []
    momentos = {f: a_utc(m) for f, m in con.execute("SELECT fecha, momento FROM fotos")}
    for ayer, hoy in zip(fechas, fechas[1:]):
        filas = con.execute("""
            SELECT h.manager_id, h.jugador_id, a.clausula AS antes, h.clausula AS ahora,
                   h.valor, a.bloqueo_hasta
            FROM clausulas h
            JOIN clausulas a ON a.manager_id = h.manager_id AND a.jugador_id = h.jugador_id
                            AND a.fecha = ?
            WHERE h.fecha = ? AND h.clausula > a.clausula
        """, (ayer, hoy))
        for r in filas:
            # ¿Lo volvió a comprar entre medias? Entonces no es una subida.
            # (cuenta también si se lo quitaron por cláusula y lo recompró)
            if comprado_entre(compras.get((r["manager_id"], r["jugador_id"]), []), ayer, hoy, momentos):
                continue
            # Ajuste automático: la cláusula nunca está por debajo del valor de
            # mercado (ni de 1 M€), así que cuando el jugador se revaloriza la
            # cláusula sube sola hasta su nuevo valor. Eso no lo paga nadie.
            minimo_hoy = max(CLAUSULA_MINIMA, r["valor"] or 0)
            if r["ahora"] <= minimo_hoy + TOLERANCIA:
                dudosas.append((hoy, r["manager_id"], r["jugador_id"], r["antes"], r["ahora"]))
                continue
            # Si la cláusula ya iba arrastrada por el valor, la parte "pagada"
            # es solo lo que queda por encima del valor de hoy.
            base = max(r["antes"], minimo_hoy)
            coste = (r["ahora"] - base) / FACTOR_SUBIDA
            gasto[r["manager_id"]] += coste
            detalle[r["manager_id"]].append((hoy, r["jugador_id"], r["antes"], r["ahora"], coste))
    return gasto, detalle, dudosas


def cargar_calibracion():
    """
    calibracion.json (opcional): saldos que sabes de rivales, p. ej. porque
    te lo dijeron. Formato:
        {"Tony_789": {"fecha": "2026-10-22", "saldo": 65000000}}
    """
    ruta = Path(__file__).resolve().parent / "calibracion.json"
    if not ruta.exists():
        return {}
    return json.loads(ruta.read_text(encoding="utf-8"))


def bruto_hasta(movimientos, manager_id, fecha):
    """Saldo bruto de un manager al final del día 'fecha'."""
    hasta = [m for m in movimientos if m.get("createdAt", "")[:10] <= fecha]
    return SALDO_INICIAL + calcular_movimientos(hasta).get(manager_id, 0)


def calcular_saldos(con=None) -> dict:
    """Calcula el saldo estimado de cada manager. Lo usan main() y exportar.py."""
    liga = leer("ligas")[0]
    clasificacion = leer("clasificacion")
    con = con or conectar()

    fechas = [r[0] for r in con.execute("SELECT DISTINCT fecha FROM clausulas ORDER BY fecha")]
    if not fechas:
        raise SystemExit("Aún no hay cláusulas guardadas. Ejecuta antes:  python descargar.py")

    movimientos = [json.loads(f["json"]) for f in con.execute(
        "SELECT json FROM actividad WHERE liga_id = ?", (str(liga["id"]),))]
    flujo = calcular_movimientos(movimientos)
    compras = adquisiciones(movimientos)
    nombre_jugador = {r["id"]: r["nombre"] for r in con.execute("SELECT id, nombre FROM jugadores")}
    nombre_manager = {int(c["team"]["manager"]["id"]): c["team"]["manager"]["managerName"]
                      for c in clasificacion}

    gasto_hist, _ = estimacion_historica(con, fechas[0], compras)
    gasto_exacto, detalle_exacto, dudosas = subidas_exactas(con, fechas, compras)

    mi_equipo = str(liga["team"]["id"])
    mi_manager = next((int(c["team"]["manager"]["id"]) for c in clasificacion
                       if str(c["team"]["id"]) == mi_equipo), None)

    calibracion = cargar_calibracion()
    filas, notas = [], []
    for mid, nombre in nombre_manager.items():
        bruto = SALDO_INICIAL + flujo.get(mid, 0)
        hist = gasto_hist[mid]
        cal = calibracion.get(nombre)
        if cal:
            # Lo que no cuadraba ese día lo tratamos como gasto oculto anterior
            hist = bruto_hasta(movimientos, mid, cal["fecha"]) - cal["saldo"]
            notas.append(f"{nombre}: calibrado con {euros(cal['saldo'])} el {cal['fecha']} "
                         f"→ gasto oculto previo ≈ {euros(hist)}")
        filas.append({
            "id": mid, "nombre": nombre, "bruto": bruto,
            "gasto_antes": round(hist), "gasto_exacto": round(gasto_exacto[mid]),
            "saldo": round(bruto - hist - gasto_exacto[mid]),
            "soy_yo": mid == mi_manager, "calibrado": bool(cal),
        })
    filas.sort(key=lambda f: -f["saldo"])

    real = con.execute("SELECT dinero FROM mi_saldo ORDER BY fecha DESC LIMIT 1").fetchone()
    real = real[0] if real else liga["team"].get("money")

    return {
        "liga": liga, "fechas": fechas, "filas": filas, "notas": notas, "real": real,
        "detalle_exacto": detalle_exacto, "dudosas": dudosas,
        "nombre_jugador": nombre_jugador, "nombre_manager": nombre_manager,
    }


def main():
    r = calcular_saldos()
    fechas, nombre_jugador, nombre_manager = r["fechas"], r["nombre_jugador"], r["nombre_manager"]
    detalle_exacto, dudosas = r["detalle_exacto"], r["dudosas"]

    dias = f"{len(fechas)} día{'s' if len(fechas) > 1 else ''} de datos, desde {fechas[0]}"
    print(f"🔒 Cláusulas y saldo ajustado · {r['liga']['name']} ({dias})\n")
    print(f"{'Manager':<18} {'Saldo bruto':>14} {'Cláus. antes*':>14} {'Cláus. exactas':>15} {'Saldo ajustado':>15}")
    print("-" * 80)
    for f in r["filas"]:
        marca = "  ← tú" if f["soy_yo"] else ("  (calibrado)" if f["calibrado"] else "")
        print(f"{f['nombre'][:18]:<18} {euros(f['bruto']):>14} {euros(f['gasto_antes']):>14} "
              f"{euros(f['gasto_exacto']):>15} {euros(f['saldo']):>15}{marca}")
    print(f"\n* Gasto oculto anterior al {fechas[0]} (cláusulas): estimado, tiende a quedarse corto,")
    print("  salvo en los managers calibrados con calibracion.json.")
    for n in r["notas"]:
        print(f"  · {n}")

    # Validación con tu saldo real
    for f in r["filas"]:
        if f["soy_yo"] and r["real"] is not None:
            print(f"\n🎯 Tu equipo: saldo real {euros(r['real'])} · ajustado {euros(f['saldo'])} "
                  f"· error {euros(f['saldo'] - r['real'])}")
            if len(fechas) > 1:
                print("   Si el error se mantiene igual día a día, la parte exacta está funcionando:")
                print("   lo que queda es el desfase de las subidas antiguas.")

    if detalle_exacto:
        print("\n✅ Subidas detectadas con exactitud:")
        for mid, lista in detalle_exacto.items():
            for fecha, jid, antes, ahora, coste in lista:
                print(f"  {fecha} · {nombre_manager.get(mid, mid)} · {nombre_jugador.get(jid, jid)}: "
                      f"{euros(antes)} → {euros(ahora)}  (pagó {euros(coste)})")
    elif len(fechas) > 1:
        print("\n✅ Ninguna subida de cláusula desde que guardas datos.")
    else:
        print("\nℹ️  Mañana, tras volver a ejecutar descargar.py, empezaré a detectar subidas exactas.")

    if dudosas:
        print(f"\nℹ️  {len(dudosas)} cláusulas subieron solas al revalorizarse el jugador (no cuentan).")
        if len(dudosas) > 15:
            return
        print("   Detalle:")
        for fecha, mid, jid, antes, ahora in dudosas:
            print(f"  {fecha} · {nombre_manager.get(mid, mid)} · {nombre_jugador.get(jid, jid)}: "
                  f"{euros(antes)} → {euros(ahora)}")


if __name__ == "__main__":
    main()
