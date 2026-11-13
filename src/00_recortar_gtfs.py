"""
Etapa 0 - Recorte do GTFS estático da BHTRANS para a linha 4110.

Uso: python3 src/00_recortar_gtfs.py caminho/para/gtfs_bh.zip

O GTFS usado no trabalho é a versão 202604181953 (baixada pelo crawler em
19/04/2026, último dia da coleta), que é o quadro de horários em vigor durante a
coleta. Versões posteriores do GTFS mantêm os mesmos trip_ids, mas com horários
programados diferentes em ~1/3 das paradas - por isso a versão importa.

Saída: data/gtfs_4110/{trips,stop_times,stops,shapes}_4110.csv + calendar/feed_info/routes
"""
import sys
import zipfile
from pathlib import Path
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "data/gtfs_4110"
LINHA = "4110"


def main(zip_path):
    SAIDA.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        ler = lambda nome, **kw: pd.read_csv(z.open(nome), dtype=str, **kw)
        routes = ler("routes.txt")
        rid = set(routes.loc[routes.route_short_name == LINHA, "route_id"])
        trips = ler("trips.txt")
        trips = trips[trips.route_id.isin(rid)]
        ids = set(trips.trip_id)
        st = pd.concat(c[c.trip_id.isin(ids)] for c in ler("stop_times.txt", chunksize=2_000_000))
        stops = ler("stops.txt")
        shapes = ler("shapes.txt")
        trips.to_csv(SAIDA / "trips_4110.csv", index=False)
        st.to_csv(SAIDA / "stop_times_4110.csv", index=False)
        stops[stops.stop_id.isin(st.stop_id)].to_csv(SAIDA / "stops_4110.csv", index=False)
        shapes[shapes.shape_id.isin(trips.shape_id)].to_csv(SAIDA / "shapes_4110.csv", index=False)
        for nome in ("calendar.txt", "feed_info.txt", "routes.txt"):
            (SAIDA / nome).write_bytes(z.read(nome))
    print(f"{len(trips)} viagens, {len(st)} horários de parada da linha {LINHA}")


if __name__ == "__main__":
    main(sys.argv[1])
