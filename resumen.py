"""
Resumen de subidas y bajadas de valor entre las dos últimas fotos guardadas.

Uso:   python resumen.py            -> top 10
       python resumen.py 20         -> top 20
Necesitas haber ejecutado descargar.py al menos dos días distintos.
"""
import sys

from fantasy.db import POSICIONES, conectar

CONSULTA = """
SELECT j.nombre, j.equipo, j.posicion,
       hoy.valor                 AS valor,
       hoy.valor - ayer.valor    AS cambio,
       ROUND(100.0 * (hoy.valor - ayer.valor) / ayer.valor, 1) AS pct
FROM valores hoy
JOIN valores ayer ON ayer.jugador_id = hoy.jugador_id AND ayer.fecha = :ayer
JOIN jugadores j  ON j.id = hoy.jugador_id
WHERE hoy.fecha = :hoy AND ayer.valor > 0 AND (hoy.valor - ayer.valor) {filtro} 0
ORDER BY cambio {orden}
LIMIT :n
"""


def euros(x: int) -> str:
    return f"{x:,.0f} €".replace(",", ".")


def imprimir(titulo, filas):
    print(f"\n{titulo}")
    print("-" * 72)
    for f in filas:
        pos = POSICIONES.get(f["posicion"], "?")
        signo = "+" if f["cambio"] > 0 else ""
        print(
            f"{f['nombre'][:22]:<22} {pos:<4} {(f['equipo'] or '')[:14]:<14} "
            f"{euros(f['valor']):>14}  {signo + euros(f['cambio']):>13} ({signo}{f['pct']}%)"
        )


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    con = conectar()
    fechas = [r[0] for r in con.execute(
        "SELECT DISTINCT fecha FROM valores ORDER BY fecha DESC LIMIT 2"
    )]
    if len(fechas) < 2:
        print("Solo tengo datos de un día. Vuelve a ejecutar descargar.py mañana 🙂")
        return

    hoy, ayer = fechas
    print(f"Cambios de valor: {ayer} → {hoy}")
    params = {"hoy": hoy, "ayer": ayer, "n": n}
    imprimir("📈 MÁS SUBEN", con.execute(CONSULTA.format(orden="DESC", filtro=">"), params))
    imprimir("📉 MÁS BAJAN", con.execute(CONSULTA.format(orden="ASC", filtro="<"), params))


if __name__ == "__main__":
    main()
