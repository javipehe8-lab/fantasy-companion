"""
Genera INFORME.md juntando la salida de los demás scripts.
GitHub lo muestra formateado al abrir el repositorio (también en el móvil).

Uso:   python informe.py
"""
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CARPETA = Path(__file__).resolve().parent

SECCIONES = [
    ("💰 Saldos y cláusulas", "clausulas.py"),
    ("📊 Subidas y bajadas de valor", "resumen.py"),
]


def ejecutar(script: str) -> str:
    r = subprocess.run(
        [sys.executable, script], cwd=CARPETA, capture_output=True, text=True,
        encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    salida = (r.stdout or "").strip()
    if r.returncode != 0:
        salida += f"\n\n⚠️ {script} terminó con error:\n{(r.stderr or '').strip()[-1500:]}"
    return salida or "(sin datos todavía)"


def main():
    ahora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    partes = [f"# ⚽ Fantasy Companion\n\n_Actualizado: {ahora}_\n"]
    for titulo, script in SECCIONES:
        partes.append(f"## {titulo}\n\n```text\n{ejecutar(script)}\n```\n")
    (CARPETA / "INFORME.md").write_text("\n".join(partes), encoding="utf-8")
    print("✅ INFORME.md generado")


if __name__ == "__main__":
    main()
