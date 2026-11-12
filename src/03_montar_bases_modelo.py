"""
Etapa 3 - Bases para os modelos.

Entrada : data/processed/passagens_4110.csv
Saídas  : data/processed/trechos_4110.csv   (tempo entre paradas consecutivas - réplica Pasquim)
          data/processed/atrasos_4110.csv   (atraso por parada - extensão)

Variáveis de calendário/horário usadas na extensão:
- tipo_dia : util / sabado / domingo
- semana   : S0 (30-31/03), S1 (06-12/04), S2 (13-19/04)
- pico     : partida programada entre 16h e 19h59 em dia útil (pico da tarde)
- faixa    : faixa horária da partida programada (manhã, entrepico, pico tarde, noite)
"""
from pathlib import Path
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
PROC = RAIZ / "data/processed"


def faixa_horaria(h):
    if h < 9:
        return "1_manha_ate_9h"
    if h < 16:
        return "2_entrepico_9_16h"
    if h < 20:
        return "3_pico_tarde_16_20h"
    return "4_noite_20h_mais"


def main():
    p = pd.read_csv(PROC / "passagens_4110.csv")
    p = p.sort_values(["viagem", "stop_sequence"])

    dt = pd.to_datetime(p.data)
    p["dia_semana"] = dt.dt.dayofweek  # 0 = segunda
    p["tipo_dia"] = np.select([p.dia_semana == 5, p.dia_semana == 6], ["sabado", "domingo"], "util")
    p["semana"] = np.select([dt < "2026-04-06", dt < "2026-04-13"], ["S0", "S1"], "S2")
    partida_prog = p.groupby("viagem").prog_seg.transform("min")
    p["hora_partida"] = (partida_prog // 3600).astype(int)
    p["faixa"] = p.hora_partida.map(faixa_horaria)
    p["pico"] = ((p.tipo_dia == "util") & p.hora_partida.between(16, 19)).astype(int)
    p["partida_obs_seg"] = p.groupby("viagem").obs_seg.transform("min")

    cols_ctx = ["viagem", "data", "trip_id", "veiculo", "dia_semana", "tipo_dia", "semana",
                "hora_partida", "faixa", "pico"]

    # --- atrasos por parada (extensão) ---
    at = p.dropna(subset=["obs_seg"])[cols_ctx + ["stop_sequence", "stop_id", "stop_name", "dist_m",
                                                   "prog_seg", "obs_seg", "atraso_min"]]
    at.to_csv(PROC / "atrasos_4110.csv", index=False)

    # --- tempos de trecho (réplica Pasquim) ---
    p["obs_prox"] = p.groupby("viagem").obs_seg.shift(-1)
    p["prog_prox"] = p.groupby("viagem").prog_seg.shift(-1)
    tr = p[p.stop_sequence < p.stop_sequence.max()].copy()
    tr["trecho"] = tr.stop_sequence  # trecho j = parada j -> j+1
    tr["tempo_s"] = tr.obs_prox - tr.obs_seg
    tr["tempo_prog_s"] = tr.prog_prox - tr.prog_seg
    tr = tr[cols_ctx + ["trecho", "dist_m", "tempo_s", "tempo_prog_s", "partida_obs_seg"]]
    # ordem cronológica: viagens pela partida, trechos pela sequência
    tr["ordem_viagem"] = tr.groupby("viagem").partida_obs_seg.transform("min")
    tr = tr.sort_values(["data", "ordem_viagem", "trecho"]).drop(columns="ordem_viagem")
    tr.to_csv(PROC / "trechos_4110.csv", index=False)

    ok = tr.tempo_s.notna()
    print(f"trechos possíveis: {len(tr)}  observados: {ok.sum()}")
    print(tr.loc[ok, "tempo_s"].describe())
    print(f"atrasos observados: {len(at)}")


if __name__ == "__main__":
    main()
