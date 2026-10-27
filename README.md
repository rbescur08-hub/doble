# Doble

Básquet argentino y del mundo: resultados, fixtures, tablas y dónde ver cada partido, en hora argentina.

- `index.html`: la página (estática, lee `data/*.json`).
- `data/`: los datos.
  - `ligas.json`, `noticias.json`, `escudos.json`, `logos.json`, `extra.json`: los sube la tarea diaria de Claude (`scripts/exportar_db.py`).
  - `nba.json`, `bp.json`, `fotos.json`, `estado.json`: los actualiza GitHub Actions cada 30 minutos (`scripts/actualizar.py`).
- `.github/workflows/actualizar.yml`: la tarea automática. Si algo falla, mirá `data/estado.json` o la pestaña Actions.
