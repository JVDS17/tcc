"""
Crawler de posições de veículos (GTFS-Realtime / VehiclePositions) - BH.

IMPORTANTE: este script foi REIMPLEMENTADO após a coleta. O código original,
usado entre 30/03/2026 e 19/04/2026, não foi preservado. Esta versão reproduz o
mesmo formato de saída da planilha de coleta (data/raw/Monitoramento_Transporte_BH.xlsx):

    timestamp_captura, linha, veiculo, trip_id, hora_partida_prog, lat, lon, flag

Uso:
    pip install requests gtfs-realtime-bindings
    python crawler_gtfs_rt.py --url <URL_DO_FEED_VEHICLE_POSITIONS> --linhas 4110 \
        --intervalo 20 --saida coleta.csv

O endereço do feed GTFS-RT da PBH/BHTRANS deve ser conferido no Portal de Dados
Abertos (dados.pbh.gov.br) antes de rodar - ele não é fixado no código de
propósito. Se o feed exigir chave de acesso, passe-a com --header.
"""
import argparse
import csv
import datetime as dt
import sys
import time

import requests
from google.transit import gtfs_realtime_pb2


def hora_partida(trip_id: str) -> str:
    """Os trip_ids da BHTRANS terminam em HHMM (horário de partida programado)."""
    hhmm = trip_id.strip()[-4:]
    return f"{hhmm[:2]}:{hhmm[2:]}:00" if hhmm.isdigit() else ""


def coletar(url, linhas, headers):
    feed = gtfs_realtime_pb2.FeedMessage()
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    feed.ParseFromString(r.content)
    agora = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for ent in feed.entity:
        if not ent.HasField("vehicle"):
            continue
        v = ent.vehicle
        trip_id = v.trip.trip_id
        linha = trip_id.split()[0] if trip_id else v.trip.route_id
        if linhas and linha not in linhas:
            continue
        yield [agora, linha, v.vehicle.id or v.vehicle.label, trip_id, hora_partida(trip_id),
               f"{v.position.latitude:.6f}", f"{v.position.longitude:.6f}", 0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="URL do feed GTFS-RT VehiclePositions")
    ap.add_argument("--linhas", nargs="*", default=["4110"], help="linhas a manter (vazio = todas)")
    ap.add_argument("--intervalo", type=int, default=20, help="segundos entre consultas")
    ap.add_argument("--saida", default="coleta.csv")
    ap.add_argument("--header", action="append", default=[], help='ex.: "Authorization: Bearer XYZ"')
    a = ap.parse_args()
    headers = dict(h.split(":", 1) for h in a.header)
    headers = {k.strip(): v.strip() for k, v in headers.items()}

    with open(a.saida, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        while True:
            t0 = time.time()
            try:
                linhas = list(coletar(a.url, set(a.linhas), headers))
                w.writerows(linhas)
                f.flush()
                print(f"{dt.datetime.now():%H:%M:%S} {len(linhas)} registros", flush=True)
            except Exception as e:  # lacunas da API são registradas e a coleta continua
                print(f"{dt.datetime.now():%H:%M:%S} falha: {e}", file=sys.stderr, flush=True)
            time.sleep(max(0, a.intervalo - (time.time() - t0)))


if __name__ == "__main__":
    main()
