#!/usr/bin/env bash
# Roda o pipeline completo, do Excel bruto até tabelas e figuras.
set -euo pipefail
cd "$(dirname "$0")"
export LANG=C.UTF-8 LC_ALL=C.UTF-8
# (opcional) python3 src/00_recortar_gtfs.py caminho/gtfs_bh.zip  -> já executado; recorte em data/gtfs_4110
python3 src/01_preprocessar_gps.py
python3 src/02_passagens_paradas.py
python3 src/03_montar_bases_modelo.py
Rscript src/04_replica_pasquim.R
Rscript src/05_modelo_atraso.R
python3 src/06_sensibilidade.py
python3 src/07_figuras_tabelas.py
echo "Pronto: veja outputs/tabelas e outputs/figuras"
