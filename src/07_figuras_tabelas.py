"""
Etapa 7 - Figuras e tabelas descritivas para o texto do TCC.

Saídas em outputs/figuras e outputs/tabelas.
"""
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
PROC = RAIZ / "data/processed"
FIG = RAIZ / "outputs/figuras"
TAB = RAIZ / "outputs/tabelas"
AZUL, LARANJA, CINZA = "#1f5fa8", "#d9822b", "#8a8a8a"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})

DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


def main():
    a = pd.read_csv(PROC / "atrasos_4110.csv")
    tr = pd.read_csv(PROC / "trechos_4110.csv")

    # 1) atraso ao longo do percurso
    g = a.groupby("stop_sequence").atraso_min
    q = pd.DataFrame({"med": g.median(), "q1": g.quantile(.25), "q3": g.quantile(.75), "n": g.size()})
    q = q[q.n >= 30]
    dist = a.groupby("stop_sequence").dist_m.first().loc[q.index] / 1000
    fig, ax = plt.subplots(figsize=(8, 3.8))
    ax.fill_between(dist, q.q1, q.q3, color=AZUL, alpha=.2, label="intervalo interquartil")
    ax.plot(dist, q.med, color=AZUL, lw=2, label="mediana")
    ax.axhline(0, color=CINZA, lw=.8)
    ax.set_xlabel("Distância percorrida desde o Belvedere (km)")
    ax.set_ylabel("Atraso vs. horário programado (min)")
    ax.set_title("Linha 4110 (Belvedere → Dom Cabral): atraso ao longo do percurso")
    ax.legend(frameon=False, loc="upper left")
    fig.tight_layout(); fig.savefig(FIG / "atraso_ao_longo_percurso.png", dpi=200); plt.close(fig)

    # 2) tempo total de viagem observado vs programado
    v = a.groupby("viagem").agg(s0=("stop_sequence", "min"), s1=("stop_sequence", "max"),
                                o0=("obs_seg", "min"), o1=("obs_seg", "max"),
                                p0=("prog_seg", "min"), p1=("prog_seg", "max"))
    comp = v[(v.s0 <= 3) & (v.s1 >= 60)]
    rt = pd.DataFrame({"observado_min": (comp.o1 - comp.o0) / 60, "programado_min": (comp.p1 - comp.p0) / 60})
    rt.describe().round(1).to_csv(TAB / "tempo_viagem_obs_vs_prog.csv")

    # 3) atraso médio por hora de partida programada, por semana (dias úteis)
    u = a[a.tipo_dia == "util"]
    viag = u.groupby("viagem").agg(semana=("semana", "first"), hora=("hora_partida", "first"),
                                   atraso=("atraso_min", "mean"))
    fig, ax = plt.subplots(figsize=(8, 3.8))
    for sem, cor, rot, dy in [("S1", AZUL, "Semana 1 (06–10/04)", 6), ("S2", LARANJA, "Semana 2 (13–17/04)", -12)]:
        x = viag[viag.semana == sem].groupby("hora").atraso.agg(["mean", "size"])
        ax.plot(x.index, x["mean"], "o-", color=cor, label=rot)
        for h, row in x.iterrows():
            ax.annotate(int(row["size"]), (h, row["mean"]), textcoords="offset points", xytext=(0, dy),
                        ha="center", fontsize=7, color=cor)
    ax.axvspan(16, 19.9, color=CINZA, alpha=.12, lw=0)
    ax.text(18, ax.get_ylim()[1] * .97, "pico da tarde", ha="center", va="top", fontsize=8, color=CINZA)
    ax.set_xlabel("Hora da partida programada"); ax.set_ylabel("Atraso médio da viagem (min)")
    ax.set_title("Dias úteis: atraso médio por hora de partida (números = viagens)")
    ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(FIG / "atraso_por_hora_semanas.png", dpi=200); plt.close(fig)

    # 4) tabela semanal por dia da semana (substitui a Tabela 2 do TCC 1)
    vd = a.groupby("viagem").agg(semana=("semana", "first"), dia=("dia_semana", "first"),
                                 atraso=("atraso_min", "mean"))
    vd = vd[vd.semana.isin(["S1", "S2"])]
    t = vd.groupby(["dia", "semana"]).atraso.agg(["mean", "size"]).unstack("semana")
    tab = pd.DataFrame({
        "dia": [DIAS[i] for i in t.index],
        "S1_atraso_medio_min": t[("mean", "S1")].round(1).values,
        "S1_viagens": t[("size", "S1")].values,
        "S2_atraso_medio_min": t[("mean", "S2")].round(1).values,
        "S2_viagens": t[("size", "S2")].values,
    })
    tab["variacao_min"] = (tab.S2_atraso_medio_min - tab.S1_atraso_medio_min).round(1)
    tab.to_csv(TAB / "comparacao_semanal.csv", index=False)

    # 5) viagens analisadas por faixa horária e tipo de dia
    cnt = a.groupby(["tipo_dia", "faixa"]).viagem.nunique().unstack(fill_value=0)
    cnt.to_csv(TAB / "viagens_por_faixa_tipo_dia.csv")

    print(rt.describe().round(1)); print(tab.to_string(index=False)); print(cnt)


if __name__ == "__main__":
    main()
