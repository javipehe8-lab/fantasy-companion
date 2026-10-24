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

from fantasy.db import conectar
from saldos import SALDO_INICIAL, calcular_movimientos, euros, leer

FACTOR_SUBIDA = 2
CLAUSULA_MINIMA = 1_000_000


def adquisiciones(movimientos):
    """(manager, jugador) -> lista de (fecha 'AAAA-MM-DD', precio)."""
    res = defaultdict(list)
    for m in movimientos:
        if m.get("activityTypeId") in (1, 31) and m.get("playerMasterId"):
            res[(m["user1Id"], int(m["playerMasterId"]))].append(
                (m.get("createdAt", "")[:10], m.get("amount") or 0))
    return res


def estimacion_historica(con, fecha, compras):
    """Subidas anteriores al primer día con datos (aproximado)."""
    gasto, detalle = defaultdict(float), defaultdict(list)
    for r in con.execute("SELECT * FROM clausulas WHERE fecha = ?", (fecha,)):
        precios = [p for f, p in compras.get((r["manager_id"], r["jugador_id"]), []) if f <= fecha]
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
            if any(ayer < f <= hoy for f, _ in compras.get((r["manager_id"], r["jugador_id"]), [])):
                continue
            # ¿Se le abrió la cláusula entre medias? Podría ser un ajuste automático.
            se_abrio = r["bloqueo_hasta"] and r["bloqueo_hasta"][:10] <= hoy
            if se_abrio and r["ahora"] <= max(CLAUSULA_MINIMA, r["valor"] or 0) * 1.001:
                dudosas.append((hoy, r["manager_id"], r["jugador_id"], r["antes"], r["ahora"]))
                continue
            coste = (r["ahora"] - r["antes"]) / FACTOR_SUBIDA
            gasto[r["manager_id"]] += coste
            detalle[r["manager_id"]].append((hoy, r["jugador_id"], r["antes"], r["ahora"], coste))
    return gasto, detalle, dudosas


def main():
    liga = leer("ligas")[0]
    clasificacion = leer("clasificacion")
    con = conectar()

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

    gasto_hist, detalle_hist = estimacion_historica(con, fechas[0], compras)
    gasto_exacto, detalle_exacto, dudosas = subidas_exactas(con, fechas, compras)

    mi_equipo = str(liga["team"]["id"])
    mi_manager = next((int(c["team"]["manager"]["id"]) for c in clasificacion
                       if str(c["team"]["id"]) == mi_equipo), None)

    dias = f"{len(fechas)} día{'s' if len(fechas) > 1 else ''} de datos, desde {fechas[0]}"
    print(f"🔒 Cláusulas y saldo ajustado · {liga['name']} ({dias})\n")
    print(f"{'Manager':<18} {'Saldo bruto':>14} {'Cláus. antes*':>14} {'Cláus. exactas':>15} {'Saldo ajustado':>15}")
    print("-" * 80)
    filas = []
    for mid, nombre in nombre_manager.items():
        bruto = SALDO_INICIAL + flujo.get(mid, 0)
        ajustado = bruto - gasto_hist[mid] - gasto_exacto[mid]
        filas.append((nombre, bruto, gasto_hist[mid], gasto_exacto[mid], ajustado, mid == mi_manager))
    for nombre, bruto, hist, exacto, ajustado, soy_yo in sorted(filas, key=lambda f: -f[4]):
        marca = "  ← tú" if soy_yo else ""
        print(f"{nombre[:18]:<18} {euros(bruto):>14} {euros(hist):>14} {euros(exacto):>15} {euros(ajustado):>15}{marca}")
    print(f"\n* Estimación de subidas anteriores al {fechas[0]}: tiende a quedarse corta.")

    # Validación con tu saldo real
    real = con.execute("SELECT dinero FROM mi_saldo ORDER BY fecha DESC LIMIT 1").fetchone()
    real = real[0] if real else liga["team"].get("money")
    for nombre, bruto, hist, exacto, ajustado, soy_yo in filas:
        if soy_yo and real is not None:
            print(f"\n🎯 Tu equipo: saldo real {euros(real)} · ajustado {euros(ajustado)} "
                  f"· error {euros(ajustado - real)}")
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
        print("\n❓ Cambios al abrirse la cláusula (posible ajuste automático, no cuentan):")
        for fecha, mid, jid, antes, ahora in dudosas:
            print(f"  {fecha} · {nombre_manager.get(mid, mid)} · {nombre_jugador.get(jid, jid)}: "
                  f"{euros(antes)} → {euros(ahora)}")


if __name__ == "__main__":
    main()
