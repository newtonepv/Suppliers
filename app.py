"""Monte Carlo do custo de importacao por quilo.

Historico vem da secao 7 do caderno (dataweb_price_series.csv). O leque a frente
vem da secao 8: sigma_h{h}_% e o desvio das variacoes de log em h meses. Entre os
horizontes estimados (1, 3, 6 e 12) o sigma e interpolado — nao extrapolado por
raiz de h, porque nestas series sigma_h1 ja e quase sigma_h12 e a raiz inventaria
um acumulo que o dado nao mostra.

Sem tendencia: o scorecard nao estima nenhuma, entao a mediana projetada e o ultimo
preco observado e so a incerteza cresce.

    .venv/bin/streamlit run app.py
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import streamlit as st

HORIZONTES = [1, 3, 6, 12]
COUNTRY_COLOR = {"Brazil": "#2a78d6", "Canada": "#eb6834",
                 "India": "#1baf7a", "Mexico": "#4a3aa7"}
SURFACE = "#fcfcfb"

st.set_page_config(layout="wide")
st.title("Custo de importacao por quilo — historico e leque Monte Carlo")

serie = pd.read_csv("dataweb_price_series.csv", dtype={"HTS Number": str},
                    parse_dates=["date"])
score = pd.read_csv("dataweb_scorecard.csv", dtype={"HTS Number": str})

hts = st.sidebar.selectbox("HTS", sorted(serie["HTS Number"].unique()))
hmax = st.sidebar.select_slider("Horizonte (meses)", HORIZONTES, value=12)
faixa = st.sidebar.select_slider("Faixa mostrada", [50, 80, 90, 95], value=95)
n = st.sidebar.select_slider("Simulacoes", [1_000, 10_000, 100_000], value=10_000)
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
lo, hi = (100 - faixa) / 200, 1 - (100 - faixa) / 200
rng = np.random.default_rng(0)

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
    sim = ultimo * np.exp(rng.normal(0, 1, (n, len(meses))) * s)
    datas = fim + pd.to_timedelta(meses * 30.4, unit="D")

    ax.fill_between(datas, np.quantile(sim, lo, axis=0), np.quantile(sim, hi, axis=0),
                    color=cor, alpha=0.16, linewidth=0)
    ax.plot(datas, np.median(sim, axis=0), color=cor, linewidth=1.2, linestyle=(0, (3, 2)))
    resumo[pais] = {"hoje": ultimo, f"p{int(lo*100):02d}": np.quantile(sim[:, -1], lo),
                    "mediana": np.median(sim[:, -1]), f"p{int(hi*100)}": np.quantile(sim[:, -1], hi),
                    "P(subir >20%)": (sim[:, -1] > ultimo * 1.2).mean()}

ax.axvline(hist["date"].max(), color="#8a8983", linewidth=0.9, linestyle=(0, (4, 3)))
ax.set_ylabel("US$ / kg")
ax.grid(axis="y", color="#e8e8e4", linewidth=0.8)
ax.set_axisbelow(True)
for lado in ("top", "right", "left"):
    ax.spines[lado].set_visible(False)
ax.legend(frameon=False, ncol=4, loc="upper left", fontsize=9)
st.pyplot(fig)

st.caption(f"Linha cheia: observado ate {hist['date'].max():%m/%Y}. Tracejada e area: "
           f"mediana e faixa de {faixa}% simulados. Paises sem sigma nos quatro "
           f"horizontes aparecem so com historico.")

st.subheader(f"US$/kg daqui a {hmax} meses")
st.write(pd.DataFrame(resumo).T.round(3))

st.subheader(f"Custo de {kg:,.0f} kg")
st.write((pd.DataFrame(resumo).T.drop(columns="P(subir >20%)") * kg).round(0))

# Fornecedores da secao 5b do caderno, ja sem transportadora e sem cativo. O custo
# vem do pais, nao do fornecedor: nenhuma fonte tem preco por exportador, entao a
# coluna repete dentro do mesmo pais e so separa lanes, nunca concorrentes.
st.subheader("Fornecedores (ImportYeti, top 3 por pais)")
alto = f"p{int(hi * 100)}"
forn = pd.read_csv("suppliers_ranked.csv", dtype={"hts": str})
forn = forn[forn["hts"] == hts].drop(columns="hts")
forn["Country"] = forn["country"].str.capitalize()
forn = (forn.drop(columns="country")
        .join(pd.DataFrame(resumo).T[["mediana", alto]], on="Country")
        .rename(columns={"mediana": f"US$/kg mediana h{hmax}", alto: f"US$/kg {alto} h{hmax}"}))
st.write(forn.set_index("name").round(2))
st.caption("`escala` = embarques por trimestre nos ultimos 4; `tendencia` = ultimos 4 "
           "trimestres sobre os 4 anteriores; `liveness_tri` = trimestres desde o "
           "ultimo embarque. US$/kg e do pais, herdado — nao separa fornecedores da "
           "mesma origem.")
