# Vendored from checkctfb

`parser.py`, `rules.py`, `report.py`, `__init__.py` are copied verbatim from
`/Users/walterapboeger/Desktop/APPS/checkctfb` (src/checkctfb/), commit-free
local project. `cli.py` and `download.py` are intentionally **not** vendored:
the Porcentômetro app never downloads its own DwC-A archive — it feeds the
Taxon rules the `PLANILHA_DF` dataset already loaded in memory (see the
`/anomalies` route in `app.py`, via `parser.rows_from_records`).

Vendored (not a git submodule / pip dependency) because this app deploys as
a single directory upload (Railway/Render, see Procfile) — a relative path
outside the deploy root would not survive deployment. checkctfb has zero
external dependencies, so vendoring is a plain file copy.

To re-sync after a checkctfb change:

```bash
cp /Users/walterapboeger/Desktop/APPS/checkctfb/src/checkctfb/{__init__,parser,rules,report}.py \
   /Users/walterapboeger/Desktop/CTFB/taxon_analysis_app/checkctfb/
```
