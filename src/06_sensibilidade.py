"""
Etapa 6 - Análise de sensibilidade ao critério de cobertura mínima.

A coleta tem poucas viagens completas no pico da tarde (a API devolveu poucos
registros entre 16h e 20h). Esta etapa reprocessa os dados com cobertura mínima
de 25% das paradas (em vez de 50%) e compara o efeito estimado do pico.

Saída: outputs/tabelas/atraso_sensibilidade_cobertura.csv
"""
import os
import shutil
import subprocess
from pathlib import Path
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
TAB = RAIZ / "outputs/tabelas"
SRC = RAIZ / "src"


def rodar(cobertura):
    env = dict(os.environ, COBERTURA_MIN=str(cobertura))
    for cmd in (["python3", SRC / "02_passagens_paradas.py"],
                ["python3", SRC / "03_montar_bases_modelo.py"],
                ["Rscript", SRC / "05_modelo_atraso.R"]):
        subprocess.run([str(c) for c in cmd], env=env, check=True, capture_output=True)
    r = pd.read_csv(TAB / "atraso_modelos.csv")
    a = pd.read_csv(RAIZ / "data/processed/atrasos_4110.csv")
    r = r[r.termo.isin(["(Intercept)", "pico", "faixa3_pico_tarde_16_20h"])].copy()
    r["cobertura_min"] = cobertura
    r["viagens"] = a.viagem.nunique()
    r["viagens_util_pico"] = a[(a.tipo_dia == "util") & (a.pico == 1)].viagem.nunique()
    return r


def main():
    backup = TAB / "_atraso_modelos_principal.csv"
    res = [rodar(0.25), rodar(0.50)]  # termina no cenário principal (50%)
    out = pd.concat(res)[["cobertura_min", "viagens", "viagens_util_pico", "modelo", "termo",
                          "estimativa", "erro_padrao", "IC95_inf", "IC95_sup"]]
    out.to_csv(TAB / "atraso_sensibilidade_cobertura.csv", index=False)
    if backup.exists():
        backup.unlink()
    print(out.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
