# La Naranja

Básquet argentino y del mundo: resultados, fixtures, tablas y dónde ver cada partido, en hora argentina.

- `app.html`: la página (lee `/data/*.json`). **No edites `index.html` ni las carpetas de cada competencia**: las genera `scripts/paginas.py` a partir de `app.html`, con el contenido escrito para Google.
- `scripts/sitio.json`: nombre de la marca y dominio (cambiar `base` cuando esté el dominio propio).
- `data/`: los datos.
  - `ligas.json`, `noticias.json`, `escudos.json`, `logos.json`, `extra.json`: los sube la tarea diaria de Claude (`scripts/exportar_db.py`).
  - `nba.json`, `bp.json`, `fotos.json`, `estado.json`: los actualiza GitHub Actions cada 30 minutos (`scripts/actualizar.py`).
- `.github/workflows/actualizar.yml`: la tarea automática. Si algo falla, mirá `data/estado.json` o la pestaña Actions.
