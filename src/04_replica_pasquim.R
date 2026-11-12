# Etapa 4 - Réplica dos modelos de Pasquim, Fonseca e Melo Jr. (2025)
#
# Adaptado de github.com/Brendonpasquim/mixed-model-bus-wait-time-forecast
# (main.Rmd, licença Apache-2.0). Créditos aos autores originais.
#
# Variável resposta: tempo de deslocamento entre paradas consecutivas (s)
#   M1           : y = b0 + e                         (só efeito fixo)
#   M2           : y = b0 + u_trecho + e              (intercepto aleatório por trecho)
#   M3           : M2 com erro AR(1) dentro de cada trecho (corAR1)
#   M3 sazonal   : M3 + AR(1) com componente sazonal ajustado nos resíduos,
#                  período = nº de trechos por viagem
#
# Diferenças em relação ao artigo original (todas documentadas no TCC):
#   - o artigo modela um veículo em um dia; aqui todas as viagens da linha 4110
#     no sentido Belvedere -> Dom Cabral (16 dias) entram no modelo;
#   - o coeficiente AR é estimado (o script original usa phi = 0.3037 fixo);
#   - além do EQM no ajuste, há validação fora da amostra com RMSE e MAE;
#   - o SARIMA dos resíduos é estimado por soma de quadrados condicional (CSS):
#     a máxima verossimilhança exata do arima() não converge numa série de
#     ~24 mil pontos com período 60 e lacunas (NA).
#
# Entrada : data/processed/trechos_4110.csv
# Saídas  : outputs/tabelas/pasquim_*.csv, outputs/figuras/pasquim_*.png

suppressPackageStartupMessages({
  library(nlme); library(forecast); library(tseries)
})
args <- commandArgs(trailingOnly = FALSE)
raiz <- normalizePath(file.path(dirname(sub("--file=", "", args[grep("--file=", args)])), ".."))
tab <- file.path(raiz, "outputs/tabelas"); fig <- file.path(raiz, "outputs/figuras")
set.seed(42)

tr <- read.csv(file.path(raiz, "data/processed/trechos_4110.csv"), stringsAsFactors = FALSE)
paradas <- read.csv(file.path(raiz, "data/processed/atrasos_4110.csv"), stringsAsFactors = FALSE)
nomes <- unique(paradas[, c("stop_sequence", "stop_name")])

# trechos com poucas observações (início no terminal e chegada final) ficam fora
cont <- table(tr$trecho[!is.na(tr$tempo_s)])
trechos_ok <- as.integer(names(cont)[cont >= 100])
tr <- tr[tr$trecho %in% trechos_ok, ]
n_trechos <- length(trechos_ok)
tr$trecho_f <- factor(tr$trecho)
cat("trechos no modelo:", n_trechos, " (", min(trechos_ok), "a", max(trechos_ok), ")\n")

eqm  <- function(y, yhat) mean((y - yhat)^2, na.rm = TRUE)
rmse <- function(y, yhat) sqrt(eqm(y, yhat))
mae  <- function(y, yhat) mean(abs(y - yhat), na.rm = TRUE)

ajustar <- function(d) {
  d <- d[!is.na(d$tempo_s), ]
  m2 <- lme(tempo_s ~ 1, data = d, random = ~ 1 | trecho_f, method = "ML")
  m3 <- lme(tempo_s ~ 1, data = d, random = ~ 1 | trecho_f,
            correlation = corAR1(form = ~ 1 | trecho_f), method = "ML",
            control = lmeControl(opt = "optim"))
  list(dados = d, m2 = m2, m3 = m3)
}

# série completa (viagem x trecho, com NA) para o componente sazonal
grade_residuos <- function(d_completo, d_obs, residuos) {
  d_completo$res <- NA_real_
  chave_c <- paste(d_completo$viagem, d_completo$trecho)
  chave_o <- paste(d_obs$viagem, d_obs$trecho)
  d_completo$res[match(chave_o, chave_c)] <- residuos
  d_completo$res
}

# ---------------------------------------------------------------- ajuste completo
fit <- ajustar(tr)
d <- fit$dados
phi <- coef(fit$m3$modelStruct$corStruct, unconstrained = FALSE)

res_m3 <- grade_residuos(tr, d, residuals(fit$m3, level = 1))
sar <- Arima(res_m3, order = c(1, 0, 0), seasonal = list(order = c(1, 0, 0), period = n_trechos),
             include.mean = FALSE, method = "CSS")
ajuste_sar <- fitted(sar)[match(paste(d$viagem, d$trecho), paste(tr$viagem, tr$trecho))]

# previsões no ajuste (como no artigo: valores ajustados)
pred_m1 <- fitted(fit$m2, level = 0)
pred_m2 <- fitted(fit$m2, level = 1)
pred_m3 <- fitted(fit$m3, level = 1)
# M3 com o termo AR(1): usa o resíduo da viagem anterior no mesmo trecho
res_m3_obs <- residuals(fit$m3, level = 1)
ar_termo <- ave(res_m3_obs, d$trecho_f, FUN = function(r) c(0, head(r, -1))) * phi
pred_m3_ar <- pred_m3 + ar_termo
pred_m3s <- pred_m3 + ifelse(is.na(ajuste_sar), 0, ajuste_sar)

res_sar <- residuals(sar)
lb <- Box.test(as.numeric(na.omit(as.numeric(res_sar))), lag = 10, type = "Ljung-Box")
adf <- suppressWarnings(adf.test(as.numeric(na.omit(as.numeric(res_sar)))))

tab_ajuste <- data.frame(
  modelo = c("M1 (efeito fixo)", "M2 (+ efeito aleatório por trecho)",
             "M3 (+ AR(1) por trecho)", "M3 sazonal (+ AR sazonal nos resíduos)"),
  EQM_s2 = c(eqm(d$tempo_s, pred_m1), eqm(d$tempo_s, pred_m2),
             eqm(d$tempo_s, pred_m3_ar), eqm(d$tempo_s, pred_m3s)),
  AIC = c(AIC(lm(tempo_s ~ 1, data = d)), AIC(fit$m2), AIC(fit$m3), NA)
)
tab_ajuste$RMSE_s <- sqrt(tab_ajuste$EQM_s2)
write.csv(tab_ajuste, file.path(tab, "pasquim_ajuste_modelos.csv"), row.names = FALSE)

vc <- VarCorr(fit$m2)
sigma_u <- as.numeric(vc[1, "StdDev"]); sigma_e <- as.numeric(vc[2, "StdDev"])
param <- data.frame(
  parametro = c("intercepto fixo b0 (s) - M2", "erro padrão de b0 (s)",
                "desvio padrão entre trechos sigma_u (s)", "desvio padrão residual sigma_e (s)",
                "ICC (fração da variância explicada pelo trecho)",
                "phi AR(1) por trecho (M3)", "AR(1) não sazonal - M3 sazonal", "AR sazonal - M3 sazonal",
                "período sazonal (trechos por viagem)",
                "Ljung-Box (lag 10) X2", "Ljung-Box p-valor", "ADF estatística", "ADF p-valor",
                "observações (trechos)", "viagens"),
  valor = c(fixef(fit$m2)[1], sqrt(vcov(fit$m2)[1, 1]), sigma_u, sigma_e,
            sigma_u^2 / (sigma_u^2 + sigma_e^2), phi, coef(sar)["ar1"], coef(sar)["sar1"],
            n_trechos, lb$statistic, lb$p.value, adf$statistic, adf$p.value,
            nrow(d), length(unique(d$viagem)))
)
write.csv(param, file.path(tab, "pasquim_parametros.csv"), row.names = FALSE)

re <- ranef(fit$m2); re <- data.frame(trecho = as.integer(rownames(re)), efeito_s = re[, 1])
re$tempo_previsto_s <- fixef(fit$m2)[1] + re$efeito_s
re$de <- nomes$stop_name[match(re$trecho, nomes$stop_sequence)]
re$para <- nomes$stop_name[match(re$trecho + 1, nomes$stop_sequence)]
re$media_obs_s <- tapply(d$tempo_s, d$trecho, mean)[as.character(re$trecho)]
re <- re[order(re$trecho), ]
write.csv(re, file.path(tab, "pasquim_efeitos_trecho.csv"), row.names = FALSE)

# ---------------------------------------------------------------- validação fora da amostra
validar <- function(treino, teste, rotulo) {
  f <- ajustar(treino)
  b0 <- fixef(f$m2)[1]
  u2 <- ranef(f$m2)[, 1]; names(u2) <- rownames(ranef(f$m2))
  u3 <- ranef(f$m3)[, 1]; names(u3) <- rownames(ranef(f$m3))
  b03 <- fixef(f$m3)[1]
  ph <- coef(f$m3$modelStruct$corStruct, unconstrained = FALSE)
  te <- teste
  k <- as.character(te$trecho)
  p1 <- rep(b0, nrow(te)); p2 <- b0 + u2[k]; p3base <- b03 + u3[k]
  # M3: um passo à frente - usa o resíduo observado da viagem anterior no mesmo trecho
  r <- te$tempo_s - p3base
  r_ant <- ave(r, te$trecho, FUN = function(x) {
    out <- c(NA, head(x, -1))
    for (i in seq_along(out)) if (is.na(out[i]) && i > 1) out[i] <- out[i - 1]
    out
  })
  p3 <- p3base + ph * ifelse(is.na(r_ant), 0, r_ant)
  # M3 sazonal: aplica o modelo SARIMA do treino à série de resíduos do teste
  res_tr <- grade_residuos(treino, f$dados, residuals(f$m3, level = 1))
  s <- Arima(res_tr, order = c(1, 0, 0), seasonal = list(order = c(1, 0, 0), period = n_trechos),
             include.mean = FALSE, method = "CSS")
  s_te <- Arima(r, model = s)
  p3s <- p3base + ifelse(is.na(fitted(s_te)), 0, fitted(s_te))
  y <- te$tempo_s
  data.frame(validacao = rotulo, modelo = c("M1", "M2", "M3", "M3 sazonal"),
             n_teste = sum(!is.na(y)),
             RMSE_s = c(rmse(y, p1), rmse(y, p2), rmse(y, p3), rmse(y, p3s)),
             MAE_s = c(mae(y, p1), mae(y, p2), mae(y, p3), mae(y, p3s)),
             cobertura_IC95_M2 = c(NA, mean(abs(y - p2) <= 1.96 * f$m2$sigma, na.rm = TRUE), NA, NA))
}

v1 <- validar(tr[tr$semana %in% c("S0", "S1"), ], tr[tr$semana == "S2", ],
              "treino 30/03-12/04, teste 13-19/04")
v2 <- validar(tr[tr$data == "2026-04-08", ], tr[tr$data == "2026-04-15", ],
              "treino qua 08/04, teste qua 15/04 (como no artigo)")
val <- rbind(v1, v2)
write.csv(val, file.path(tab, "pasquim_validacao.csv"), row.names = FALSE)

# ---------------------------------------------------------------- figuras
png(file.path(fig, "pasquim_efeitos_trecho.png"), width = 1600, height = 800, res = 160)
par(mar = c(4.5, 4.5, 2, 1))
plot(re$trecho, re$media_obs_s, pch = 16, col = "grey60", ylim = range(c(0, re$media_obs_s, re$tempo_previsto_s)),
     xlab = "Trecho (parada j -> j+1)", ylab = "Tempo de deslocamento (s)",
     main = "Linha 4110 (Belvedere -> Dom Cabral): tempo por trecho - M2")
lines(re$trecho, re$tempo_previsto_s, type = "b", pch = 16, col = "#1f5fa8")
abline(h = fixef(fit$m2)[1], lty = 2)
legend("topright", c("média observada", "M2: b0 + efeito do trecho", "efeito fixo b0"),
       col = c("grey60", "#1f5fa8", "black"), pch = c(16, 16, NA), lty = c(NA, 1, 2), bty = "n")
dev.off()

png(file.path(fig, "pasquim_acf_residuos.png"), width = 1600, height = 700, res = 160)
par(mfrow = c(1, 2), mar = c(4.5, 4.5, 3, 1))
acf(as.numeric(na.omit(grade_residuos(tr, d, residuals(fit$m2, level = 1)))), lag.max = 3 * n_trechos,
    main = "Resíduos M2", xlab = "Defasagem (trechos)")
acf(as.numeric(na.omit(as.numeric(res_sar))), lag.max = 3 * n_trechos, main = "Resíduos M3 sazonal", xlab = "Defasagem (trechos)")
dev.off()

print(tab_ajuste); print(param); print(val)
