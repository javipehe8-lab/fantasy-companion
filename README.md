# Fantasy Companion ⚽📊

Tu propio panel de LaLiga Fantasy: historial de valores, subidas y bajadas,
saldo estimado de los rivales y, más adelante, un asistente con IA.

> Proyecto personal y no oficial. Usa la API interna de LaLiga Fantasy con
> **tu** cuenta y **solo lee** datos. La API puede cambiar sin avisar.

## Hoja de ruta

| Fase | Qué | Estado |
|---|---|---|
| 1 | Descargar datos y guardar una foto diaria en SQLite | ✅ este código |
| 2 | Resúmenes de subidas/bajadas y gráficas | 🟡 `resumen.py` es el inicio |
| 3 | Saldo estimado de rivales a partir de la actividad | ✅ `saldos.py` |
| 4 | Ejecución diaria automática en la nube (GitHub Actions) | ✅ |
| 5 | Asistente con IA sobre tu liga | ⏳ |

---

## 1. Requisitos

- **Python 3.10 o superior** → https://www.python.org/downloads/
  (en Windows marca la casilla *"Add Python to PATH"* al instalar)
- Un editor: **VS Code** es la opción más cómoda.

## 2. Instalación (una sola vez)

Abre una terminal **dentro de la carpeta del proyecto**:

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Mac / Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

Sabrás que el entorno está activo porque la terminal empieza por `(.venv)`.

## 3. Conseguir tu token (la parte delicada)

LaLiga desactivó en octubre de 2026 el login directo con email y contraseña,
así que copiamos la sesión desde el navegador:

1. En Chrome, abre las herramientas de desarrollador con **F12** y ve a la
   pestaña **Network** (Red).
2. Con el panel abierto, inicia sesión en LaLiga Fantasy desde el navegador.
3. En la caja de filtro de Network escribe:
   `token?p=B2C_1A_5ULAIP_PARAMETRIZED_SIGNIN`
4. Haz clic en la petición de `login.laliga.es` → pestaña **Response**.
5. Copia **todo** el JSON (de `{` a `}`) y pégalo en un archivo nuevo llamado
   **`token.json`** en la carpeta del proyecto.

Debe contener `id_token` y `refresh_token`. El script renueva solo la sesión
con el `refresh_token`, así que normalmente no tendrás que repetir esto.

> ⚠️ **`token.json` es como tu contraseña.** Ya está en `.gitignore` para que
> nunca se suba a GitHub. No se lo pases a nadie.

## 4. Uso diario

```bash
python descargar.py   # descarga y guarda la foto de hoy
python resumen.py     # top 10 subidas y bajadas (desde el 2º día)
python saldos.py      # dinero estimado de cada rival
```

`descargar.py` también guarda respuestas originales en `datos_crudos/`.
**Ábrelas**: es la mejor forma de aprender qué devuelve cada endpoint y
de dónde sacaremos el saldo de los rivales.

## 5. Estructura

```
fantasy-companion/
├── fantasy/
│   ├── auth.py      # token: leerlo, ver si caducó, renovarlo
│   ├── api.py       # cliente HTTP de solo lectura
│   └── db.py        # SQLite: tablas y guardado
├── descargar.py     # script diario
├── resumen.py       # informe de subidas/bajadas
├── saldos.py        # saldo estimado de rivales
├── clausulas.py     # gasto en cláusulas y saldo ajustado
├── informe.py       # genera INFORME.md (lo usa la nube)
├── .github/workflows/diario.yml  # ejecución diaria en GitHub
├── token.json       # TU sesión (lo creas tú, no se sube a git)
└── fantasy.db       # se crea solo al ejecutar
```

## Buenas prácticas

- Ejecútalo **una o dos veces al día**, no en bucle: hay una pausa entre
  peticiones a propósito.
- Si algo falla con 401 → vuelve a copiar `token.json`.
- Si falla con 404 → probablemente LaLiga cambió la API. Buen momento para
  investigar con F12 qué rutas usa ahora la web.

## Glosario rápido

- **API REST**: URLs que devuelven datos (JSON) en lugar de páginas web.
- **JWT / Bearer token**: el "pase" firmado que demuestra quién eres.
- **Snapshot**: una foto de los datos en un momento. Varias fotos = historial.

## 6. Despliegue en la nube (GitHub Actions)

Con esto, GitHub ejecuta `descargar.py` cada mañana aunque tu PC esté apagado,
guarda el historial en `fantasy.db` y genera `INFORME.md` en el repositorio.

**Una sola vez:**

1. Sube el proyecto a un repositorio **privado** de GitHub (VS Code → icono de
   control de código → *Publicar en GitHub* → *private*). Comprueba en la web
   que `token.json` **no** aparece.
2. Crea un token personal: GitHub → *Settings* → *Developer settings* →
   *Personal access tokens* → *Fine-grained tokens* → *Generate new token*.
   - *Repository access*: solo este repositorio.
   - *Permissions* → *Secrets*: **Read and write**.
   - Caducidad: la máxima que te deje (apúntate cuándo caduca).
3. En el repositorio: *Settings* → *Secrets and variables* → *Actions* →
   *New repository secret*, y crea dos:
   - `TOKEN_JSON`: pega el contenido completo de tu `token.json`.
   - `GH_PAT`: pega el token del paso 2.
4. Pestaña *Actions* → *Fantasy diario* → *Run workflow* para probarlo.

**A partir de entonces:**

- La nube es la única que descarga datos. En tu PC **no ejecutes
  `descargar.py`**: tu sesión local quedaría desfasada respecto a la de la nube.
- Para ver el informe, abre `INFORME.md` en GitHub (también desde la app móvil).
- Para trabajar en local con los datos al día: `git pull`.
- Si un día falla con 401: vuelve a copiar la sesión del navegador y actualiza
  el secret `TOKEN_JSON`.
