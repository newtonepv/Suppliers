"""Custo de importacao por quilo: historico e leque de incerteza.

Historico vem da secao 7 do caderno (dataweb_price_series.csv). O leque a frente
vem da secao 8: sigma_h{h}_% e o desvio das variacoes de log em h meses. Entre os
horizontes estimados (1, 3, 6 e 12) o sigma e interpolado — nao extrapolado por
raiz de h, porque nestas series sigma_h1 ja e quase sigma_h12 e a raiz inventaria
um acumulo que o dado nao mostra.

Sem tendencia: o scorecard nao estima nenhuma, entao a mediana projetada e o ultimo
preco observado e so a incerteza cresce.

O preco a frente e lognormal, P_h = P0 * exp(sigma_h * Z). Os quantis dela tem
forma fechada, entao nao ha simulacao aqui: um Monte Carlo so aproximaria com ruido
amostral o que NormalDist calcula exato.

    .venv/bin/streamlit run app.py
"""
from statistics import NormalDist

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

HORIZONTES = [1, 3, 6, 12]
COUNTRY_COLOR = {"Brazil": "#2a78d6", "Canada": "#eb6834",
                 "India": "#1baf7a", "Mexico": "#4a3aa7"}
SURFACE = "#fcfcfb"

st.set_page_config(layout="wide")
st.title("Custo de importacao por quilo — historico e leque de incerteza")

serie = pd.read_csv("dataweb_price_series.csv", dtype={"HTS Number": str},
                    parse_dates=["date"])
score = pd.read_csv("dataweb_scorecard.csv", dtype={"HTS Number": str})

hts = st.sidebar.selectbox("HTS", sorted(serie["HTS Number"].unique()))
hmax = st.sidebar.select_slider("Horizonte (meses)", HORIZONTES, value=12)
certeza_porcentagem = st.sidebar.select_slider("Faixa mostrada", [50, 80, 90, 95], value=95)
kg = st.sidebar.number_input("Volume a importar (kg)", value=100_000, step=10_000)

hist = serie[(serie["HTS Number"] == hts) & serie["reliable"]]
# so paises com os quatro sigmas: a interpolacao precisa da grade inteira, e um
# pais com sigma faltando apareceria com leque estreito por falta de dado, nao
# por estabilidade
sig = score[(score["HTS Number"] == hts)].dropna(
    subset=[f"sigma_h{h}_%" for h in HORIZONTES]).set_index("Country")

# comeca em 0 com sigma 0 para o leque nascer do ultimo ponto observado em vez
# de aparecer ja aberto um mes a frente
meses = np.arange(0, hmax + 1)
calendario = pd.date_range(hist["date"].min(), hist["date"].max(), freq="MS")
lower_limit, hihger_limit = (100 - certeza_porcentagem) / 200, 1 - (100 - certeza_porcentagem) / 200 # de 90%: 2.5% e 97.5%
z = NormalDist().inv_cdf(hihger_limit)          # simetrico: o quantil de baixo e -z

fig, ax = plt.subplots(figsize=(11, 5), facecolor=SURFACE)
ax.set_facecolor(SURFACE)
resumo = {}

for pais, cor in COUNTRY_COLOR.items():
    h = hist[hist["Country"] == pais].sort_values("date")
    if h.empty:
        continue
    # reindexado no calendario cheio: mes suprimido vira NaN e quebra a linha, em
    # vez de virar reta atravessando o buraco como se fosse dado
    obs = h.set_index("date")["usd_per_kg_landed"].reindex(calendario)
    ax.plot(obs.index, obs.values, color=cor, linewidth=1.8, label=pais)
    if pais not in sig.index:
        continue

    ultimo, fim = h["usd_per_kg_landed"].iloc[-1], h["date"].iloc[-1]
    s = np.interp(meses, [0] + HORIZONTES,
                  [0] + [sig.loc[pais, f"sigma_h{k}_%"] for k in HORIZONTES]) / 100
    baixo, alto = ultimo * np.exp(-s * z), ultimo * np.exp(s * z)
    datas = fim + pd.to_timedelta(meses * 30.4, unit="D")

    ax.fill_between(datas, baixo, alto, color=cor, alpha=0.16, linewidth=0)
    # sem deriva a mediana e o proprio ultimo preco, em todo horizonte
    ax.plot(datas, np.full(len(meses), ultimo), color=cor, linewidth=1.2,
            linestyle=(0, (3, 2)))
    resumo[pais] = {"ultimo registro": ultimo,
                    # imprecisao do nivel medio pos-tarifa, vinda do scorecard
                    "ep_nivel_%": sig.loc[pais, "ep_nivel_%"],
                    f"p{int(lower_limit*100):02d}": baixo[-1], "mediana": ultimo,
                    f"p{int(hihger_limit*100)}": alto[-1],
                    "P(subir >20%)": 1 - NormalDist().cdf(np.log(1.2) / s[-1])}

ax.axvline(hist["date"].max(), color="#8a8983", linewidth=0.9, linestyle=(0, (4, 3)))
ax.set_ylabel("US$ / kg")
ax.grid(axis="y", color="#e8e8e4", linewidth=0.8)
ax.set_axisbelow(True)
for lado in ("top", "right", "left"):
    ax.spines[lado].set_visible(False)
ax.legend(frameon=False, ncol=4, loc="upper left", fontsize=9)
st.pyplot(fig)

st.caption(f"Linha cheia: observado ate {hist['date'].max():%m/%Y}. Tracejada e area: "
           f"mediana e faixa de {certeza_porcentagem}% (lognormal, forma fechada). Paises sem sigma "
           f"horizontes aparecem so com historico.")

# Nivel medio pos-tarifa com sua imprecisao: barras que nao se tocam sao paises
# com preco de fato diferente. Tocar nao prova o contrario, so nao prova a favor.
st.subheader("Nivel de preco e a imprecisao da medida")
niveis = (score[score["HTS Number"] == hts].dropna(subset=["usd_kg", "ep_nivel_%"])
          .set_index("Country").sort_values("usd_kg"))
z95 = NormalDist().inv_cdf(0.975)

fig2, ax2 = plt.subplots(figsize=(8, 2.4), facecolor=SURFACE)
ax2.set_facecolor(SURFACE)
for pais, linha in niveis.iterrows():
    ax2.errorbar(linha["usd_kg"], pais, fmt="o", capsize=5, markersize=7,
                 xerr=linha["usd_kg"] * linha["ep_nivel_%"] / 100 * z95,
                 color=COUNTRY_COLOR.get(pais, "#8a8983"))
ax2.set_xlabel("US$ / kg")
ax2.grid(axis="x", color="#e8e8e4", linewidth=0.8)
ax2.set_axisbelow(True)
for lado in ("top", "right", "left"):
    ax2.spines[lado].set_visible(False)
ax2.tick_params(length=0)
st.pyplot(fig2)
st.caption("Ponto: nivel medio desde 04/2025. Barra: intervalo de 95% desse nivel "
           "(ep_nivel_%). Barras separadas = diferenca real entre os dois paises.")

st.subheader(f"Custo de {kg:,.0f} kg")
st.write((pd.DataFrame(resumo).T.drop(columns=["P(subir >20%)", "ep_nivel_%"]) * kg).round(0))

# Fornecedores da secao 5b do caderno, ja sem transportadora e sem cativo. O custo
# vem do pais, nao do fornecedor: nenhuma fonte tem preco por exportador, entao a
# coluna repete dentro do mesmo pais e so separa lanes, nunca concorrentes.
st.subheader("Fornecedores (ImportYeti, top 3 por pais)")
alto = f"p{int(hihger_limit * 100)}"
forn = pd.read_csv("suppliers_ranked.csv", dtype={"hts": str})
forn = forn[forn["hts"] == hts].drop(columns="hts")
forn["Country"] = forn["country"].str.capitalize()
forn = (forn.drop(columns="country")
        .join(pd.DataFrame(resumo).T[["mediana", alto]], on="Country")
        .rename(columns={"mediana": f"US$/kg mediana h{hmax}", alto: f"US$/kg {alto} h{hmax}"})
        .sort_values(["Country", "score"], ascending=[True, False]))
st.write(forn.set_index(["Country", "name"]).round(2))
st.caption("`embarques/trimestre` = media dos ultimos 4 trimestres; `crescimento` = ultimos 4 "
           "trimestres sobre os 4 anteriores; `liveness_tri` = trimestres desde o "
           "ultimo embarque. US$/kg e do pais, herdado — nao separa fornecedores da "
           "mesma origem.")
