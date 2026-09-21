"""Streamlit - Leitura do lakehouse/olist.duckdb"""
import duckdb
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

DB = Path(__file__).parent / "lakehouse" / "olist.duckdb"

st.set_page_config(page_title="Olist Lakehouse - Vendas", layout="wide")
st.title("🏠 Lakehouse Olist — Vendas (DuckDB + Streamlit)")
st.caption(f"Fonte: `{DB}` • Tabelas: FATO_VENDAS + 6 DIMs • Views: vw_fato_enriquecida, vw_vendas_sp_2017_500")

@st.cache_resource
def get_tables():
    c = duckdb.connect(str(DB), read_only=True)
    tabs = [r[0] for r in c.execute("SHOW TABLES").fetchall()]
    c.close()
    return tabs

@st.cache_data(ttl=300)
def query(sql):
    c = duckdb.connect(str(DB), read_only=True)
    df = c.execute(sql).df()
    c.close()
    return df

tabs = get_tables()
with st.expander("🗂️ Tabelas no lakehouse"):
    st.write(tabs)
    st.dataframe(query("SELECT table_name, estimated_size, column_count FROM (SELECT * FROM duckdb_tables()) LIMIT 20"))

# ---- Sidebar filtros ----
st.sidebar.header("Filtros")
anos = query("SELECT DISTINCT ano FROM FATO_VENDAS ORDER BY ano")["ano"].tolist()
ano_sel = st.sidebar.multiselect("Ano", anos, default=[2017])
valor_max = st.sidebar.slider("Valor máx item (vl_total_item)", 50, 2000, 500, step=10)
estados = query("SELECT DISTINCT estado_cliente FROM FATO_VENDAS ORDER BY 1")["estado_cliente"].tolist()
estado_sel = st.sidebar.multiselect("Estado cliente", estados, default=["SP"])
cidade_default = ["sao paulo"] if "sao paulo" in query("SELECT DISTINCT lower(cidade_cliente) c FROM FATO_VENDAS LIMIT 100000")["c"].tolist() else []
cidade_txt = st.sidebar.text_input("Cidade cliente (minúsculo, vazio=todas)", value="sao paulo")
pags = query("SELECT DISTINCT tipo_pagamento FROM FATO_VENDAS ORDER BY 1")["tipo_pagamento"].tolist()
pag_sel = st.sidebar.multiselect("Pagamento", pags, default=pags)

ano_f = f"({','.join(map(str, ano_sel))})" if ano_sel else "(2017)"
est_f = "(" + ",".join(f"'{e}'" for e in estado_sel) + ")" if estado_sel else None
pag_f = "(" + ",".join(f"'{p}'" for p in pag_sel) + ")" if pag_sel else None

where = [f"ano IN {ano_f}", f"vl_total_item < {valor_max}"]
if est_f: where.append(f"estado_cliente IN {est_f}")
if cidade_txt.strip(): where.append(f"lower(cidade_cliente) = '{cidade_txt.strip().lower()}'")
if pag_f: where.append(f"tipo_pagamento IN {pag_f}")
W = " AND ".join(where)

kpi = query(f"SELECT COUNT(DISTINCT order_id) pedidos, COUNT(*) itens, SUM(vl_total_item) receita, AVG(vl_total_item) ticket FROM vw_fato_enriquecida WHERE {W}").iloc[0]
c1,c2,c3,c4 = st.columns(4)
c1.metric("Pedidos", f"{int(kpi.pedidos or 0):,}")
c2.metric("Itens", f"{int(kpi.itens or 0):,}")
c3.metric("Receita", f"R$ {(kpi.receita or 0):,.2f}")
c4.metric("Ticket médio item", f"R$ {(kpi.ticket or 0):,.2f}")

# ---- Linha mensal ----
st.subheader("📈 Linha — evolução mensal (receita x pedidos)")
mensal = query(f"""
SELECT MONTH(CAST(data_compra AS TIMESTAMP)) AS mes, COUNT(DISTINCT order_id) pedidos, SUM(vl_total_item) receita
FROM vw_fato_enriquecida WHERE {W} GROUP BY 1 ORDER BY 1
""")
if len(mensal):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=mensal.mes, y=mensal.receita, name="Receita R$", mode="lines+markers"))
    fig.add_trace(go.Scatter(x=mensal.mes, y=mensal.pedidos, name="Pedidos", mode="lines+markers", yaxis="y2"))
    fig.update_layout(yaxis=dict(title="Receita"), yaxis2=dict(title="Pedidos", overlaying="y", side="right"), xaxis=dict(title="Mês"))
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("Sem dados para os filtros.")

col1, col2 = st.columns(2)
with col1:
    st.subheader("📊 Barras — top categorias")
    topcat = query(f"SELECT categoria_pt, SUM(vl_total_item) receita, COUNT(*) itens FROM vw_fato_enriquecida WHERE {W} GROUP BY 1 ORDER BY receita DESC LIMIT 10")
    if len(topcat):
        st.plotly_chart(px.bar(topcat, x="receita", y="categoria_pt", orientation="h", text="itens", title="Receita por categoria"), use_container_width=True)
with col2:
    st.subheader("📊 Barras — por pagamento")
    porpag = query(f"SELECT tipo_pagamento, COUNT(DISTINCT order_id) pedidos, SUM(vl_total_item) receita FROM vw_fato_enriquecida WHERE {W} GROUP BY 1 ORDER BY receita DESC")
    if len(porpag):
        st.plotly_chart(px.bar(porpag, x="tipo_pagamento", y="pedidos", color="tipo_pagamento", title="Pedidos por pagamento"), use_container_width=True)

# ---- Radar SP vs Brasil ----
st.subheader("🕸️ Radar — recorte atual vs Brasil 2017 <500")
def perfil(df_where):
    return query(f"""SELECT SUM(vl_total_item)/NULLIF(COUNT(DISTINCT order_id),0) ticket,
        AVG(vl_frete) frete, SUM(vl_frete)/NULLIF(SUM(vl_total_item),0)*100 pct_frete,
        AVG(qtd_parcelas) parc, COUNT(*)*1.0/NULLIF(COUNT(DISTINCT order_id),0) ipp
        FROM vw_fato_enriquecida WHERE {df_where}""").iloc[0].tolist()
try:
    cur = perfil(W)
    br = perfil("ano=2017 AND vl_total_item < 500")
    labels = ["Ticket","Frete med","%frete","Parcelas","Itens/ped"]
    mx = [max(a,b,1e-9) for a,b in zip(cur,br)]
    cur_n = [a/m*100 for a,m in zip(cur,mx)]
    br_n = [a/m*100 for a,m in zip(cur,mx)]
    fig_r = go.Figure([
        go.Scatterpolar(r=cur_n, theta=labels, fill="toself", name=f"Recorte {cur[0]:.0f},{cur[1]:.1f},{cur[2]:.1f},{cur[3]:.1f},{cur[4]:.2f}"),
        go.Scatterpolar(r=br_n, theta=labels, fill="toself", name="Brasil"),
    ])
    fig_r.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0,100])))
    st.plotly_chart(fig_r, use_container_width=True)
except Exception as e:
    st.warning(f"Radar indisponível: {e}")

st.subheader("🔎 Amostra dos dados")
st.dataframe(query(f"SELECT order_id, data_compra, cidade_cliente, estado_cliente, categoria_pt, vl_total_item, tipo_pagamento FROM vw_fato_enriquecida WHERE {W} LIMIT 200"))
st.caption(f"SQL aplicado: WHERE {W}")
