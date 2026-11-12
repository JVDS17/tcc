# Etapa 5 - Extensão: atraso em relação ao horário programado (GTFS)
#
# Atraso_ij = horário observado de passagem na parada j da viagem i
#             - horário programado da parada j (stop_times.txt)
# Obs.: no GTFS da BHTRANS só a 1ª parada é ponto de controle (timepoint = 1);
# os horários das demais são estimados pela operadora. O atraso nas paradas
# intermediárias é, portanto, medido contra uma estimativa.
#
# E1 : atraso ~ pico + (1 | viagem)                      formulação do TCC 1, com a
#                                                        viagem real (data+trip_id+veículo)
# E1b: atraso ~ pico + (1 | trip_id)                     formulação do TCC 1 como foi
#                                                        rodada (trip_id agrupa dias diferentes)
# E2 : atraso ~ faixa + tipo_dia + dist_km + (1 | viagem) + (1 | parada)
#
# Entrada : data/processed/atrasos_4110.csv
# Saídas  : outputs/tabelas/atraso_*.csv

suppressPackageStartupMessages(library(lme4))
args <- commandArgs(trailingOnly = FALSE)
raiz <- normalizePath(file.path(dirname(sub("--file=", "", args[grep("--file=", args)])), ".."))
tab <- file.path(raiz, "outputs/tabelas")

a <- read.csv(file.path(raiz, "data/processed/atrasos_4110.csv"), stringsAsFactors = FALSE)
a$dist_km <- a$dist_m / 1000
a$tipo_dia <- factor(a$tipo_dia, levels = c("util", "sabado", "domingo"))
a$faixa <- factor(a$faixa)
a$parada <- factor(a$stop_sequence)

e1  <- lmer(atraso_min ~ pico + (1 | viagem), data = a, REML = TRUE)
e1b <- lmer(atraso_min ~ pico + (1 | trip_id), data = a, REML = TRUE)
e2  <- lmer(atraso_min ~ faixa + tipo_dia + dist_km + (1 | viagem) + (1 | parada), data = a, REML = TRUE)

coefs <- function(m, nome) {
  s <- summary(m)$coefficients
  ci <- confint(m, method = "Wald", parm = "beta_")
  vc <- as.data.frame(VarCorr(m))
  out <- data.frame(modelo = nome, termo = rownames(s), estimativa = s[, 1], erro_padrao = s[, 2],
                    t = s[, 3], IC95_inf = ci[rownames(s), 1], IC95_sup = ci[rownames(s), 2],
                    row.names = NULL)
  ve <- data.frame(modelo = nome, termo = paste0("DP aleatório: ", vc$grp), estimativa = vc$sdcor,
                   erro_padrao = NA, t = NA, IC95_inf = NA, IC95_sup = NA)
  rbind(out, ve)
}
res <- rbind(coefs(e1, "E1: pico + (1|viagem real)"),
             coefs(e1b, "E1b: pico + (1|trip_id) [como no TCC 1]"),
             coefs(e2, "E2: faixa + tipo de dia + distância + (1|viagem) + (1|parada)"))
write.csv(res, file.path(tab, "atraso_modelos.csv"), row.names = FALSE)

icc <- function(m) { v <- as.data.frame(VarCorr(m))$vcov; v / sum(v) }
info <- data.frame(
  modelo = c("E1", "E1b", "E2"),
  n_obs = c(nobs(e1), nobs(e1b), nobs(e2)),
  n_grupos = c(ngrps(e1)[1], ngrps(e1b)[1], ngrps(e2)["viagem"]),
  AIC = c(AIC(e1), AIC(e1b), AIC(e2)),
  ICC_grupo_principal = c(icc(e1)[1], icc(e1b)[1], icc(e2)[1])
)
write.csv(info, file.path(tab, "atraso_info_modelos.csv"), row.names = FALSE)

# descritivo: atraso médio na chegada ao fim do percurso (última parada observada)
ult <- a[ave(a$stop_sequence, a$viagem, FUN = max) == a$stop_sequence, ]
pri <- a[ave(a$stop_sequence, a$viagem, FUN = min) == a$stop_sequence, ]
desc <- data.frame(
  indicador = c("atraso médio em todas as passagens (min)", "mediana (min)",
                "atraso médio na 1ª parada observada (min)", "atraso médio na última parada observada (min)",
                "% passagens com atraso > 5 min", "% passagens adiantadas (< -1 min)"),
  valor = c(mean(a$atraso_min), median(a$atraso_min), mean(pri$atraso_min), mean(ult$atraso_min),
            100 * mean(a$atraso_min > 5), 100 * mean(a$atraso_min < -1))
)
write.csv(desc, file.path(tab, "atraso_descritivo.csv"), row.names = FALSE)

print(res, digits = 3); print(info, digits = 4); print(desc, digits = 3)
