"""
Base de datos local (SQLite: un único archivo, sin instalar nada).

La idea clave: la API solo te da el valor de HOY. Si cada día guardamos una
"foto" (snapshot) de todos los valores, con el tiempo tenemos el historial
para calcular subidas, bajadas y tendencias.
"""
import hashlib
import json
import sqlite3
from pathlib import Path

DB_FILE = Path(__file__).resolve().parent.parent / "fantasy.db"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS jugadores (
    id        INTEGER PRIMARY KEY,
    nombre    TEXT,
    equipo    TEXT,
    posicion  INTEGER          -- 1 POR, 2 DEF, 3 MED, 4 DEL, 5 entrenador
);

CREATE TABLE IF NOT EXISTS valores (
    jugador_id INTEGER,
    fecha      TEXT,           -- 'AAAA-MM-DD'
    valor      INTEGER,
    puntos     INTEGER,
    estado     TEXT,           -- ok, injured, doubtful...
    PRIMARY KEY (jugador_id, fecha)
);

CREATE TABLE IF NOT EXISTS actividad (
    liga_id  TEXT,
    huella   TEXT PRIMARY KEY, -- evita guardar dos veces el mismo movimiento
    tipo     INTEGER,
    importe  INTEGER,
    fecha    TEXT,
    json     TEXT              -- guardamos el original para analizarlo después
);

-- Foto diaria de la cláusula de cada jugador de cada equipo de la liga.
-- Comparando dos días seguidos detectamos subidas de cláusula exactas.
CREATE TABLE IF NOT EXISTS clausulas (
    fecha         TEXT,
    manager_id    INTEGER,
    jugador_id    INTEGER,
    clausula      INTEGER,
    valor         INTEGER,     -- valor de mercado ese día
    bloqueo_hasta TEXT,        -- buyoutClauseLockedEndTime
    PRIMARY KEY (fecha, manager_id, jugador_id)
);

-- Tu saldo real cada día (la API solo nos da el tuyo): sirve para validar.
CREATE TABLE IF NOT EXISTS mi_saldo (
    fecha  TEXT PRIMARY KEY,
    dinero INTEGER
);
"""

POSICIONES = {1: "POR", 2: "DEF", 3: "MED", 4: "DEL", 5: "ENT"}


def conectar() -> sqlite3.Connection:
    con = sqlite3.connect(DB_FILE)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    return con


def guardar_jugadores(con, jugadores: list, fecha: str) -> int:
    n = 0
    for j in jugadores:
        if "id" not in j:
            continue
        con.execute(
            "INSERT OR REPLACE INTO jugadores VALUES (?,?,?,?)",
            (
                int(j["id"]),
                j.get("nickname") or j.get("name"),
                (j.get("team") or {}).get("name"),
                j.get("positionId"),
            ),
        )
        con.execute(
            "INSERT OR REPLACE INTO valores VALUES (?,?,?,?,?)",
            (
                int(j["id"]),
                fecha,
                j.get("marketValue"),
                j.get("points"),
                j.get("playerStatus"),
            ),
        )
        n += 1
    con.commit()
    return n


def guardar_plantilla(con, fecha: str, manager_id: int, jugadores: list) -> int:
    n = 0
    for p in jugadores:
        master = p.get("playerMaster") or {}
        if not master.get("id") or p.get("buyoutClause") is None:
            continue
        con.execute(
            "INSERT OR REPLACE INTO clausulas VALUES (?,?,?,?,?,?)",
            (fecha, int(manager_id), int(master["id"]), p["buyoutClause"],
             master.get("marketValue"), p.get("buyoutClauseLockedEndTime")),
        )
        n += 1
    con.commit()
    return n


def guardar_mi_saldo(con, fecha: str, dinero) -> None:
    if dinero is not None:
        con.execute("INSERT OR REPLACE INTO mi_saldo VALUES (?,?)", (fecha, dinero))
        con.commit()


def guardar_actividad(con, liga_id, movimientos: list) -> int:
    nuevos = 0
    for m in movimientos:
        texto = json.dumps(m, sort_keys=True, ensure_ascii=False)
        huella = str(m.get("id") or hashlib.sha1(texto.encode()).hexdigest())
        cur = con.execute(
            "INSERT OR IGNORE INTO actividad VALUES (?,?,?,?,?,?)",
            (
                str(liga_id),
                huella,
                m.get("activityTypeId"),
                m.get("amount"),
                m.get("publicationDate") or m.get("date"),
                texto,
            ),
        )
        nuevos += cur.rowcount
    con.commit()
    return nuevos
