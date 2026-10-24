"""
Saldo estimado de cada manager de tu liga.

La API oculta el dinero de los rivales, pero publica todos sus movimientos.
Reconstruimos el saldo como en una cuenta bancaria:

    saldo = saldo inicial
          + ventas al mercado de LaLiga        (tipo 33)
          + ventas a otros managers            (tipo 1, como vendedor)
          + premios por jornada                (tipo 6)
          - fichajes del mercado de LaLiga     (tipo 31)
          - compras a otros managers           (tipo 1, como comprador)

Lo que NO aparece en la actividad (subir cláusulas, blindajes...) no se puede
contar, así que la estimación tiende a ser algo OPTIMISTA. Para medir cuánto
nos equivocamos, comparamos con tu saldo real, que la API sí nos da.

Uso:   python descargar.py   (para tener los datos al día)
       python saldos.py
"""
import json
from collections import defaultdict
from pathlib import Path

from fantasy.db import conectar

SALDO_INICIAL = 100_000_000  # cámbialo si tu liga empezó con otro presupuesto
CRUDOS = Path(__file__).resolve().parent / "datos_crudos"

# Tipos de actividad (activityTypeId) y quién gana o pierde dinero
FICHAJE_MERCADO = 31   # user1 compra a LaLiga        -> user1 paga
VENTA_MERCADO = 33     # user1 vende a LaLiga         -> user1 cobra
COMPRA_ENTRE = 1       # user1 compra a user2         -> user1 paga, user2 cobra
PREMIO_JORNADA = 6     # user1 cobra por su jornada


def euros(x: float) -> str:
    return f"{x:,.0f} €".replace(",", ".")


def leer(nombre):
    ruta = CRUDOS / f"{nombre}.json"
    if not ruta.exists():
        raise SystemExit(f"Falta {ruta.name}. Ejecuta antes:  python descargar.py")
    return json.loads(ruta.read_text(encoding="utf-8"))


def calcular_movimientos(movimientos):
    flujo = defaultdict(int)
    for m in movimientos:
        tipo, importe = m.get("activityTypeId"), m.get("amount") or 0
        u1, u2 = m.get("user1Id"), m.get("user2Id")
        if tipo == FICHAJE_MERCADO:
            flujo[u1] -= importe
        elif tipo in (VENTA_MERCADO, PREMIO_JORNADA):
            flujo[u1] += importe
        elif tipo == COMPRA_ENTRE:
            flujo[u1] -= importe
            if u2 is not None:
                flujo[u2] += importe
    return flujo


def main():
    liga = leer("ligas")[0]
    clasificacion = leer("clasificacion")

    con = conectar()
    movimientos = [
        json.loads(fila["json"])
        for fila in con.execute(
            "SELECT json FROM actividad WHERE liga_id = ?", (str(liga["id"]),)
        )
    ]
    if not movimientos:
        raise SystemExit("No hay actividad guardada. Ejecuta antes:  python descargar.py")
    flujo = calcular_movimientos(movimientos)

    mi_equipo = str(liga["team"]["id"])
    mi_saldo_real = liga["team"].get("money")

    filas, error = [], None
    for c in clasificacion:
        equipo = c["team"]
        manager_id = int(equipo["manager"]["id"])
        estimado = SALDO_INICIAL + flujo.get(manager_id, 0)
        soy_yo = str(equipo["id"]) == mi_equipo
        if soy_yo and mi_saldo_real is not None:
            error = estimado - mi_saldo_real
        filas.append((equipo["manager"]["managerName"], estimado, equipo.get("teamValue") or 0, soy_yo))

    print(f"💰 Saldo estimado · {liga['name']} ({len(movimientos)} movimientos analizados)\n")
    print(f"{'Manager':<20} {'Saldo estimado':>16} {'Valor plantilla':>17}")
    print("-" * 56)
    for nombre, saldo, valor, soy_yo in sorted(filas, key=lambda f: f[1], reverse=True):
        marca = "  ← tú" if soy_yo else ""
        print(f"{nombre[:20]:<20} {euros(saldo):>16} {euros(valor):>17}{marca}")

    if error is not None:
        print(f"\n🎯 Comprobación con tu equipo: saldo real {euros(mi_saldo_real)}, "
              f"estimado {euros(mi_saldo_real + error)}.")
        if abs(error) < 1_000_000:
            print("   La fórmula cuadra casi al euro 👌")
        else:
            sentido = "de más" if error > 0 else "de menos"
            print(f"   Me desvío {euros(abs(error))} {sentido}. Probablemente sean gastos que")
            print("   no salen en la actividad (subir cláusulas, blindajes). Usa ese margen")
            print("   como referencia para los rivales.")


if __name__ == "__main__":
    main()
