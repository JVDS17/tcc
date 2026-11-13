"""
Etapa 2 - Horário de passagem em cada parada (referenciamento linear + interpolação).

Entrada : data/processed/gps_4110_limpo.csv, data/gtfs_4110/*
Saída   : data/processed/passagens_4110.csv  (uma linha por viagem real x parada)
          outputs/tabelas/resumo_passagens.csv

Método:
1. O traçado (shape) do GTFS é densificado a cada ~5 m e cada ponto de GPS é
   projetado sobre ele, obtendo a distância percorrida ao longo da rota (m).
   A busca é feita numa janela à frente da última posição válida, o que evita
   projetar o ônibus num trecho errado quando a rota passa perto de si mesma.
   Pontos a mais de 80 m do traçado são descartados.
2. A distância de cada parada ao longo da rota vem de shape_dist_traveled do GTFS.
3. O horário de passagem na parada s é interpolado linearmente entre os dois
   pontos de GPS consecutivos (P_i, P_{i+1}) que a envolvem:
       T_s = T_i + (T_{i+1} - T_i) * (d_s - d_i) / (d_{i+1} - d_i)
   Interpolações em que T_{i+1} - T_i > 180 s são descartadas (lacuna de sinal;
   180 s cobre 99% dos intervalos reais de atualização do GPS).
4. Para a 1ª parada (terminal), usa-se o instante em que o ônibus passa 30 m do
   início da rota, i.e. a partida efetiva, e não o tempo parado no terminal.
5. A API associa trip_ids a fragmentos curtos de trajeto (veículos que aparecem
   poucos minutos, possivelmente em outro serviço ou com rótulo errado). Por isso
   mantêm-se só viagens com passagem calculada em pelo menos 50% das paradas.
   Quando dois veículos aparecem com o mesmo trip_id no mesmo dia, mantém-se o
   de maior cobertura.
6. A distância de cada parada é limitada a (fim do traçado - 30 m), para que a
   parada final, que fica no fim ou ligeiramente além do traçado, possa ser alcançada.
"""
from pathlib import Path
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
GTFS = RAIZ / "data/gtfs_4110"
PROC = RAIZ / "data/processed"
TAB = RAIZ / "outputs/tabelas"

R_TERRA = 6_371_000.0
LAT0 = np.radians(-19.95)
MAX_DIST_TRACADO = 80      # m
MAX_GAP_INTERP = 180       # s
OFFSET_TERMINAL = 30       # m
JANELA_TRAS, JANELA_FRENTE = 150, 4000  # m
import os
COBERTURA_MIN = float(os.environ.get("COBERTURA_MIN", "0.50"))


def xy(lat, lon):
    """Projeção equiretangular local (m) - erro desprezível numa área de ~20 km."""
    return (np.radians(lon) * np.cos(LAT0) * R_TERRA, np.radians(lat) * R_TERRA)


def densificar(shape):
    x, y = xy(shape.shape_pt_lat.values, shape.shape_pt_lon.values)
    d = shape.shape_dist_traveled.values * 1000.0
    pts_x, pts_y, pts_d = [], [], []
    for i in range(len(x) - 1):
        n = max(int(np.ceil((d[i + 1] - d[i]) / 5)), 1)
        f = np.arange(n) / n
        pts_x.append(x[i] + f * (x[i + 1] - x[i]))
        pts_y.append(y[i] + f * (y[i + 1] - y[i]))
        pts_d.append(d[i] + f * (d[i + 1] - d[i]))
    pts_x.append([x[-1]]); pts_y.append([y[-1]]); pts_d.append([d[-1]])
    return np.concatenate(pts_x), np.concatenate(pts_y), np.concatenate(pts_d)


def projetar_viagem(v, sx, sy, sd):
    """Distância ao longo da rota para cada ponto de GPS de uma viagem (NaN se inválido)."""
    gx, gy = xy(v.lat.values, v.lon.values)
    prog = np.full(len(v), np.nan)
    ultimo = None
    for k in range(len(v)):
        if ultimo is None:
            mask = np.ones_like(sd, dtype=bool)
        else:
            mask = (sd >= ultimo - JANELA_TRAS) & (sd <= ultimo + JANELA_FRENTE)
        idx = np.flatnonzero(mask)
        dist2 = (sx[idx] - gx[k]) ** 2 + (sy[idx] - gy[k]) ** 2
        j = idx[np.argmin(dist2)]
        if np.sqrt(dist2.min()) <= MAX_DIST_TRACADO:
            prog[k] = sd[j]
            ultimo = sd[j] if ultimo is None else max(ultimo, sd[j])
    # força monotonicidade (ruído de GPS pode "voltar" alguns metros)
    valid = ~np.isnan(prog)
    prog[valid] = np.maximum.accumulate(prog[valid])
    return prog


def passagens_viagem(t, prog, dist_paradas, dist_max):
    """Interpola o horário de passagem em cada parada."""
    ok = ~np.isnan(prog)
    t, prog = t[ok], prog[ok]
    out = np.full(len(dist_paradas), np.nan)
    if len(t) < 2:
        return out
    for s, ds in enumerate(dist_paradas):
        ds = min(max(ds, OFFSET_TERMINAL), dist_max - OFFSET_TERMINAL)
        acima = np.flatnonzero(prog >= ds)
        if len(acima) == 0 or acima[0] == 0:
            continue
        i1 = acima[0]; i0 = i1 - 1
        dt = t[i1] - t[i0]
        if dt > MAX_GAP_INTERP or prog[i1] == prog[i0]:
            continue
        out[s] = t[i0] + dt * (ds - prog[i0]) / (prog[i1] - prog[i0])
    return out


def hms_para_seg(h):
    hh, mm, ss = map(int, h.split(":"))
    return hh * 3600 + mm * 60 + ss  # GTFS permite hh >= 24 (viagens após meia-noite)


def main():
    gps = pd.read_csv(PROC / "gps_4110_limpo.csv", parse_dates=["ts"])
    trips = pd.read_csv(GTFS / "trips_4110.csv", dtype=str)
    st = pd.read_csv(GTFS / "stop_times_4110.csv", dtype=str)
    stops = pd.read_csv(GTFS / "stops_4110.csv", dtype=str)
    shapes = pd.read_csv(GTFS / "shapes_4110.csv")

    trips_obs = trips[trips.trip_id.isin(gps.trip_id.unique())]
    assert trips_obs.shape_id.nunique() == 1, "esperado um único traçado (sentido Belvedere -> Dom Cabral)"
    shape_id = int(trips_obs.shape_id.iloc[0])
    sx, sy, sd = densificar(shapes[shapes.shape_id == shape_id].sort_values("shape_pt_sequence"))

    st = st[st.trip_id.isin(trips_obs.trip_id)].copy()
    st["stop_sequence"] = st.stop_sequence.astype(int)
    st["dist_m"] = st.shape_dist_traveled.astype(float) * 1000
    st["prog_seg"] = st.arrival_time.map(hms_para_seg)
    st = st.sort_values(["trip_id", "stop_sequence"])

    linhas = []
    for viagem, v in gps.sort_values("ts").groupby("viagem"):
        data, trip_id, veiculo = viagem.split("|")
        sched = st[st.trip_id == trip_id]
        if sched.empty:
            continue
        prog = projetar_viagem(v, sx, sy, sd)
        t0 = pd.Timestamp(data)
        tsec = (v.ts - t0).dt.total_seconds().values
        obs = passagens_viagem(tsec, prog, sched.dist_m.values, sd.max())
        linhas.append(pd.DataFrame({
            "viagem": viagem, "data": data, "trip_id": trip_id, "veiculo": veiculo,
            "stop_sequence": sched.stop_sequence.values, "stop_id": sched.stop_id.values,
            "dist_m": sched.dist_m.values, "prog_seg": sched.prog_seg.values, "obs_seg": obs,
        }))
    p = pd.concat(linhas, ignore_index=True)
    n_paradas = st.groupby("trip_id").size().max()

    cob = p.groupby("viagem").obs_seg.apply(lambda s: s.notna().mean())
    boas = cob[cob >= COBERTURA_MIN].index
    p = p[p.viagem.isin(boas)].copy()

    # um veículo por (data, trip_id): o com mais paradas observadas
    melhor = (cob[cob >= COBERTURA_MIN].rename("cob").reset_index()
              .assign(data=lambda d: d.viagem.str.split("|").str[0],
                      trip_id=lambda d: d.viagem.str.split("|").str[1])
              .sort_values("cob", ascending=False).drop_duplicates(["data", "trip_id"]))
    n_dup = len(boas) - len(melhor)
    p = p[p.viagem.isin(melhor.viagem)].copy()

    # Virada do dia: a API às vezes já rotula, antes da meia-noite, o veículo com
    # a 1ª viagem do dia seguinte (ou o contrário). O dia de serviço correto é o
    # que deixa o atraso mediano da viagem mais próximo de zero (desloca +-24 h).
    bruto = (p.obs_seg - p.prog_seg) / 60
    med = bruto.groupby(p.viagem).transform("median")
    ajuste = np.where(med < -720, 1440, np.where(med > 720, -1440, 0))
    n_virada = p.loc[ajuste != 0, "viagem"].nunique()
    p["atraso_min"] = bruto + ajuste
    p = p.merge(stops[["stop_id", "stop_name"]], on="stop_id", how="left")
    p.to_csv(PROC / "passagens_4110.csv", index=False)

    resumo = pd.DataFrame({
        "indicador": [
            "paradas por viagem (GTFS)", "viagens reais com GPS",
            f"viagens com cobertura >= {int(COBERTURA_MIN*100)}% das paradas",
            "viagens duplicadas descartadas (mesmo trip_id e dia)",
            "viagens na análise", "viagens corrigidas na virada do dia",
            "passagens interpoladas",
            "cobertura média de paradas nas viagens analisadas",
        ],
        "valor": [
            n_paradas, len(cob), len(boas), n_dup, p.viagem.nunique(), n_virada,
            int(p.obs_seg.notna().sum()), round(p.groupby("viagem").obs_seg.apply(lambda s: s.notna().mean()).mean(), 3),
        ],
    })
    resumo.to_csv(TAB / "resumo_passagens.csv", index=False)
    print(resumo.to_string(index=False))


if __name__ == "__main__":
    main()
