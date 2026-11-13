"""
Etapa 1 - Pré-processamento dos dados de GPS da linha 4110.

Entrada : data/raw/Monitoramento_Transporte_BH.xlsx (aba "4110")
Saída   : data/processed/gps_4110_limpo.csv
          outputs/tabelas/resumo_coleta.csv

Decisões:
- A planilha não tem cabeçalho. Colunas: timestamp da captura, linha, veículo,
  trip_id (GTFS), horário programado de saída, latitude, longitude e velocidade
  (km/h; a API devolve sempre 0, então a coluna não é usada).
- O trip_id da BHTRANS identifica o HORÁRIO DE SAÍDA programado e se repete em
  todos os dias. Uma viagem real é identificada por (data, trip_id, veículo).
- O crawler consultava a API a cada ~20 s, mas o GPS dos veículos atualiza com
  menos frequência (mediana ~46 s). Leituras consecutivas com a mesma posição do
  mesmo veículo são duplicatas e são removidas (mantém-se a primeira).
"""
from pathlib import Path
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
ENTRADA = RAIZ / "data/raw/Monitoramento_Transporte_BH.xlsx"
SAIDA = RAIZ / "data/processed/gps_4110_limpo.csv"
TAB = RAIZ / "outputs/tabelas"

COLUNAS = ["ts", "linha", "veiculo", "trip_id", "hora_prog", "lat", "lon", "velocidade_kmh"]


def main():
    df = pd.read_excel(ENTRADA, sheet_name="4110", header=None, names=COLUNAS)
    n_bruto = len(df)
    df["ts"] = pd.to_datetime(df["ts"].astype(str).str.strip())
    df["trip_id"] = df["trip_id"].astype(str).str.strip()
    df["hora_prog"] = df["hora_prog"].astype(str).str.strip()
    df["data"] = df["ts"].dt.date.astype(str)
    df = df[df["linha"] == 4110]

    # remove duplicatas exatas e posições repetidas consecutivas do mesmo veículo
    df = df.drop_duplicates(["ts", "veiculo"]).sort_values(["veiculo", "ts"])
    mesma_pos = (
        (df["lat"] == df["lat"].shift())
        & (df["lon"] == df["lon"].shift())
        & (df["veiculo"] == df["veiculo"].shift())
        & (df["trip_id"] == df["trip_id"].shift())
    )
    df = df[~mesma_pos].copy()
    df["viagem"] = df["data"] + "|" + df["trip_id"] + "|" + df["veiculo"].astype(str)

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    df.drop(columns=["velocidade_kmh"]).to_csv(SAIDA, index=False)

    resumo = pd.DataFrame(
        {
            "indicador": [
                "leituras brutas",
                "leituras após remover posições repetidas",
                "dias com coleta",
                "trip_ids distintos (horários programados)",
                "viagens reais (data+trip_id+veículo)",
                "veículos distintos",
                "início da coleta",
                "fim da coleta",
            ],
            "valor": [
                n_bruto,
                len(df),
                df["data"].nunique(),
                df["trip_id"].nunique(),
                df["viagem"].nunique(),
                df["veiculo"].nunique(),
                str(df["ts"].min()),
                str(df["ts"].max()),
            ],
        }
    )
    TAB.mkdir(parents=True, exist_ok=True)
    resumo.to_csv(TAB / "resumo_coleta.csv", index=False)
    print(resumo.to_string(index=False))


if __name__ == "__main__":
    main()
