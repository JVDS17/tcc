# Previsibilidade dos tempos de viagem da linha 4110 (Belo Horizonte) com Modelos Mistos

Código e dados do TCC de João Victor dos Santos (ICEI – PUC Minas), sob orientação de
Felipe Domingos da Cunha.

O trabalho replica a metodologia de **Pasquim, Fonseca e Melo Jr. (2025)**, *"Quando chega?
Análise de previsibilidade de tempos de espera em transporte público urbano utilizando
Modelos Mistos"* (IX Workshop de Computação Urbana, SBC, doi:10.5753/courb.2025.7932),
aplicada à linha 4110 de Belo Horizonte. Como extensão, analisa o atraso em relação ao
horário programado no GTFS da BHTRANS.

**Recorte:** sentido Belvedere → Dom Cabral (64 paradas, 19,5 km), dados de GPS coletados de
30/03/2026 a 19/04/2026 (16 dias com coleta). A coleta não registrou viagens no sentido
contrário.

## Como rodar

Requisitos: Python 3.10+ e R 4.x.

```bash
pip install -r requirements.txt
Rscript -e 'install.packages(c("nlme", "lme4", "forecast", "tseries"))'
./run_all.sh
```

O pipeline completo leva menos de 1 minuto e regenera tudo em `data/processed/`,
`outputs/tabelas/` e `outputs/figuras/`.

## Estrutura

| Caminho | Conteúdo |
|---|---|
| `crawler/crawler_gtfs_rt.py` | Coletor de posições GTFS-Realtime (**reimplementado** após a coleta; ver abaixo) |
| `data/raw/` | Planilha original da coleta (aba `4110` = linha estudada) |
| `data/gtfs_4110/` | Recorte do GTFS estático da BHTRANS com só a linha 4110 |
| `src/01_preprocessar_gps.py` | Limpeza do GPS e identificação das viagens reais |
| `src/02_passagens_paradas.py` | Projeção no traçado e interpolação do horário em cada parada |
| `src/03_montar_bases_modelo.py` | Bases de tempos de trecho e de atrasos |
| `src/04_replica_pasquim.R` | Réplica dos modelos M1, M2, M3 e M3 sazonal + validação |
| `src/05_modelo_atraso.R` | Extensão: modelos mistos do atraso programado |
| `src/06_sensibilidade.py` | Sensibilidade ao critério de cobertura mínima |
| `src/07_figuras_tabelas.py` | Figuras e tabelas descritivas |

## Decisões metodológicas importantes

- **Viagem real = data + trip_id + veículo.** O `trip_id` da BHTRANS identifica o horário de
  partida programado e se repete todos os dias (95 trip_ids para 995 viagens reais).
- **GPS:** o crawler consultava a API a cada ~20 s, mas os veículos atualizam a posição com
  mediana de 46 s; posições repetidas foram removidas (105.207 → 41.643 leituras).
- **Passagem nas paradas:** cada ponto de GPS é projetado no traçado (`shapes.txt`) e o horário
  na parada é interpolado linearmente entre os dois pontos que a envolvem; intervalos acima
  de 180 s são descartados (cobrem 99% das atualizações reais).
- **Filtro de viagens:** a API associa trip_ids a muitos fragmentos curtos de trajeto. Ficam as
  viagens com passagem calculada em ≥ 50% das paradas (394 viagens, 21.924 passagens).
- **Horário programado:** no GTFS só a 1ª parada é ponto de controle; os horários das demais são
  estimativas da operadora. O atraso em parada intermediária é medido contra essa estimativa.
- **Virada do dia:** horários GTFS ≥ 24:00 e rótulos trocados na meia-noite são corrigidos.

## Principais resultados

**Réplica de Pasquim et al. (tempo entre paradas consecutivas, 21.401 trechos):**

| Modelo | EQM no ajuste (s²) | RMSE validação S2 (s) | MAE validação S2 (s) |
|---|---|---|---|
| M1 – efeito fixo | 3.696 | 61,8 | 42,7 |
| M2 – + intercepto aleatório por trecho | 1.356 | 38,6 | 23,0 |
| M3 – + AR(1) por trecho | 1.151 | 34,8 | 22,1 |
| M3 sazonal – + AR sazonal (período 60) | 1.318 | 34,9 | 21,9 |

Intercepto fixo de 72,3 s por trecho; o trecho explica 63% da variância (ICC). Os trechos mais
lentos ficam entre a Av. Luiz Paulo Franco e a BR-356/Av. Raja Gabaglia (≈ 3,5 min cada).
Validação: treino 30/03–12/04, teste 13–19/04 (e treino qua 08/04, teste qua 15/04, como no artigo).

**Extensão (atraso vs. horário programado):**

- Tempo de viagem observado: 69,7 min em média, contra 53,7 min programados (259 viagens completas).
- O atraso cresce ao longo do percurso: ~3,8 min na primeira parada observada e ~20,2 min no fim.
- Cada km percorrido acrescenta 0,88 min de atraso (IC95%: 0,82–0,93), controlando faixa horária e tipo de dia.
- Sábados têm 3,8 min e domingos 10,6 min a menos de atraso que dias úteis.
- **Pico da tarde:** só 7 viagens completas em dias úteis entre 16h e 20h. O efeito estimado
  (+3,4 min, IC95%: −0,8 a 7,5) não é significativo e muda com o critério de cobertura;
  ver `outputs/tabelas/atraso_sensibilidade_cobertura.csv`.

## Sobre o crawler

O script original de coleta não foi preservado. `crawler/crawler_gtfs_rt.py` é uma
reimplementação que grava no mesmo formato da planilha de coleta, para quem quiser repetir
o estudo. Confira o endereço do feed GTFS-RT no Portal de Dados Abertos da PBH antes de usar.

## Créditos e licenças

- `src/04_replica_pasquim.R` adapta o código de
  [Brendonpasquim/mixed-model-bus-wait-time-forecast](https://github.com/Brendonpasquim/mixed-model-bus-wait-time-forecast)
  (Apache-2.0). Ver `NOTICE`.
- Dados GTFS: BHTRANS / Prefeitura de Belo Horizonte, Portal de Dados Abertos (CC-BY).
