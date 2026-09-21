"""Gera relatorio_vendas.html a partir dos CSVs em modelagens/"""
import pandas as pd, json
from pathlib import Path

MOD = Path("modelagens")
fato = pd.read_csv(MOD/"FATO_VENDAS.csv", usecols=["order_id","id_produto","data_compra","ano","vl_preco","vl_frete","vl_total_item","qtd_parcelas","tipo_pagamento","cidade_cliente","estado_cliente"])
dim_prod = pd.read_csv(MOD/"DIM_PRODUTO.csv", usecols=["id_produto","categoria_pt","categoria_en"])

fato["data_compra"] = pd.to_datetime(fato["data_compra"], errors="coerce")
fato["mes"] = fato["data_compra"].dt.month
fato["cidade_norm"] = fato["cidade_cliente"].astype(str).str.strip().str.lower()
fato["estado_norm"] = fato["estado_cliente"].astype(str).str.strip().str.upper()

# Recorte foco: <500, SP capital, 2017
rec = fato[(fato["vl_total_item"] < 500) & (fato["cidade_norm"]=="sao paulo") & (fato["estado_norm"]=="SP") & (fato["ano"]==2017)].copy()
base_br = fato[(fato["vl_total_item"] < 500) & (fato["ano"]==2017)].copy()  # Brasil <500 2017 p/ comparar

def kpis(df):
    return {
        "pedidos": int(df["order_id"].nunique()),
        "itens": int(len(df)),
        "receita": float(df["vl_total_item"].sum()),
        "ticket": float(df["vl_total_item"].sum()/df["order_id"].nunique()) if df["order_id"].nunique() else 0,
        "frete_medio": float(df["vl_frete"].mean()) if len(df) else 0,
        "parc_media": float(df["qtd_parcelas"].mean()) if len(df) else 0,
    }

k_sp, k_br = kpis(rec), kpis(base_br)

# 1. Linha mensal
mensal = rec.groupby("mes").agg(pedidos=("order_id","nunique"), itens=("order_id","count"), receita=("vl_total_item","sum")).reindex(range(1,13), fill_value=0)
meses = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]

# 2. Top categorias
rec_cat = rec.merge(dim_prod, on="id_produto", how="left")
rec_cat["categoria_pt"] = rec_cat["categoria_pt"].fillna("sem_categoria")
topcat = rec_cat.groupby("categoria_pt").agg(receita=("vl_total_item","sum"), itens=("vl_total_item","count")).sort_values("receita", ascending=False).head(10)

# 3. Por pagamento
pag = rec.groupby("tipo_pagamento").agg(pedidos=("order_id","nunique"), receita=("vl_total_item","sum")).sort_values("receita", ascending=False)

# 4. Radar SP vs BR (normalizado 0-100 pelo max)
def perfil(df):
    n_ped = df["order_id"].nunique() or 1
    return {
        "Ticket medio": df["vl_total_item"].sum()/n_ped,
        "Frete medio": df["vl_frete"].mean() or 0,
        "% frete/total": (df["vl_frete"].sum()/df["vl_total_item"].sum()*100) if df["vl_total_item"].sum() else 0,
        "Parcelas medias": df["qtd_parcelas"].mean() or 0,
        "Itens por pedido": len(df)/n_ped,
    }
p_sp, p_br = perfil(rec), perfil(base_br)
labels_radar = list(p_sp.keys())
maxs = {k: max(p_sp[k], p_br[k], 1e-9) for k in labels_radar}
sp_norm = [round(p_sp[k]/maxs[k]*100,1) for k in labels_radar]
br_norm = [round(p_br[k]/maxs[k]*100,1) for k in labels_radar]
sp_raw = [round(p_sp[k],2) for k in labels_radar]
br_raw = [round(p_br[k],2) for k in labels_radar]

data = {
    "meses": meses,
    "mensal_pedidos": mensal["pedidos"].tolist(),
    "mensal_receita": [round(x,2) for x in mensal["receita"].tolist()],
    "mensal_itens": mensal["itens"].tolist(),
    "topcat_labels": topcat.index.tolist(),
    "topcat_receita": [round(x,2) for x in topcat["receita"].tolist()],
    "topcat_itens": topcat["itens"].tolist(),
    "pag_labels": pag.index.tolist(),
    "pag_pedidos": pag["pedidos"].tolist(),
    "pag_receita": [round(x,2) for x in pag["receita"].tolist()],
    "radar_labels": labels_radar,
    "sp_norm": sp_norm, "br_norm": br_norm,
    "sp_raw": sp_raw, "br_raw": br_raw,
    "k_sp": k_sp, "k_br": k_br,
}

html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Relatório de Vendas — Olist | SP Capital 2017 < R$500</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  *{{box-sizing:border-box}} body{{font-family:Arial,Helvetica,sans-serif;margin:0;background:#f4f6fb;color:#1e2a3a}}
  header{{background:#0f2a44;color:#fff;padding:28px 24px}}
  header h1{{margin:0 0 6px;font-size:24px}} header p{{margin:0;opacity:.85}}
  .wrap{{max-width:1100px;margin:0 auto;padding:20px}}
  .kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:18px 0}}
  .kpi{{background:#fff;border-radius:12px;padding:14px;box-shadow:0 2px 8px rgba(0,0,0,.06)}}
  .kpi small{{color:#64748b}} .kpi b{{font-size:22px;display:block;margin-top:4px}}
  .card{{background:#fff;border-radius:12px;padding:18px;margin:14px 0;box-shadow:0 2px 8px rgba(0,0,0,.06)}}
  .card h2{{margin:0 0 4px;font-size:18px}} .card p{{margin:0 0 12px;color:#64748b;font-size:14px}}
  .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:14px}} @media(max-width:800px){{.grid2{{grid-template-columns:1fr}}}}
  canvas{{max-height:340px}} table{{width:100%;border-collapse:collapse;font-size:14px}}
  th,td{{padding:8px;border-bottom:1px solid #e5e7eb;text-align:right}} th:first-child,td:first-child{{text-align:left}}
  footer{{color:#64748b;font-size:12px;padding:20px;text-align:center}}
</style>
</head>
<body>
<header>
  <h1>Relatório de Vendas — Olist</h1>
  <p>Foco: valor do item &lt; R$500 &nbsp;•&nbsp; São Paulo capital (sao paulo/SP) &nbsp;•&nbsp; 2017 &nbsp;•&nbsp; Fonte: <code>modelagens/FATO_VENDAS.csv</code> + <code>DIM_PRODUTO.csv</code></p>
</header>
<div class="wrap">
  <div class="kpis">
    <div class="kpi"><small>Pedidos (recorte)</small><b>{k_sp['pedidos']:,}</b></div>
    <div class="kpi"><small>Itens vendidos</small><b>{k_sp['itens']:,}</b></div>
    <div class="kpi"><small>Receita (preço+frete)</small><b>R$ {k_sp['receita']:,.2f}</b></div>
    <div class="kpi"><small>Ticket médio / pedido</small><b>R$ {k_sp['ticket']:,.2f}</b></div>
    <div class="kpi"><small>Frete médio / item</small><b>R$ {k_sp['frete_medio']:,.2f}</b></div>
    <div class="kpi"><small>Brasil 2017 &lt;500 (pedidos)</small><b>{k_br['pedidos']:,}</b></div>
  </div>

  <div class="card">
    <h2>1. Evolução mensal — linha (SP capital, 2017, &lt;R$500)</h2>
    <p>Receita mensal (R$) e nº de pedidos. Grão da fato: 1 item por linha.</p>
    <canvas id="chLinha"></canvas>
  </div>

  <div class="grid2">
    <div class="card">
      <h2>2. Top categorias — barras (receita)</h2>
      <p>Top 10 <code>categoria_pt</code> via DIM_PRODUTO no recorte.</p>
      <canvas id="chBarCat"></canvas>
    </div>
    <div class="card">
      <h2>3. Vendas por pagamento — barras</h2>
      <p>Pedidos por <code>tipo_pagamento</code> no recorte.</p>
      <canvas id="chBarPag"></canvas>
    </div>
  </div>

  <div class="card">
    <h2>4. Perfil SP capital vs Brasil — radar</h2>
    <p>Comparativo 2017 &lt;R$500 normalizado 0–100 (passe o mouse para ver valores reais).</p>
    <canvas id="chRadar"></canvas>
  </div>

  <div class="card">
    <h2>Detalhamento mensal</h2>
    <table><thead><tr><th>Mês</th><th>Pedidos</th><th>Itens</th><th>Receita (R$)</th></tr></thead>
    <tbody>
    {"".join(f"<tr><td>{m}</td><td>{p}</td><td>{i}</td><td>{r:,.2f}</td></tr>" for m,p,i,r in zip(data['meses'], data['mensal_pedidos'], data['mensal_itens'], data['mensal_receita']))}
    </tbody></table>
  </div>
</div>
<footer>Gerado a partir de modelagens/DIM_*.csv e FATO_VENDAS.csv • Grão: 1 item/pedido • Filtros: vl_total_item&lt;500, cidade='sao paulo', estado='SP', ano=2017</footer>
<script>
const D = {json.dumps(data)};
new Chart(document.getElementById('chLinha'), {{type:'line',
  data:{{labels:D.meses, datasets:[{{label:'Receita (R$)', data:D.mensal_receita, yAxisID:'y', tension:.3}},{{label:'Pedidos', data:D.mensal_pedidos, yAxisID:'y1', tension:.3}}]}},
  options:{{responsive:true, interaction:{{mode:'index',intersect:false}}, scales:{{y:{{type:'linear',position:'left'}}, y1:{{type:'linear',position:'right',grid:{{drawOnChartArea:false}}}}}}}}}});
new Chart(document.getElementById('chBarCat'), {{type:'bar',
  data:{{labels:D.topcat_labels, datasets:[{{label:'Receita (R$)', data:D.topcat_receita}}]}},
  options:{{indexAxis:'y', responsive:true, plugins:{{legend:{{display:false}}}}}}}});
new Chart(document.getElementById('chBarPag'), {{type:'bar',
  data:{{labels:D.pag_labels, datasets:[{{label:'Pedidos', data:D.pag_pedidos}}]}},
  options:{{responsive:true, plugins:{{legend:{{display:false}}}}}}}});
new Chart(document.getElementById('chRadar'), {{type:'radar',
  data:{{labels:D.radar_labels, datasets:[
    {{label:'SP capital (real: '+D.sp_raw.join(', ')+')', data:D.sp_norm, fill:true}},
    {{label:'Brasil (real: '+D.br_raw.join(', ')+')', data:D.br_norm, fill:true}}]}},
  options:{{responsive:true, scales:{{r:{{min:0,max:100,ticks:{{stepSize:20}}}}}}}}}});
</script>
</body>
</html>"""

Path("relatorio_vendas.html").write_text(html, encoding="utf-8")
print("OK relatorio_vendas.html")
print(f"recorte: {k_sp} | brasil: {k_br}")
print("mensal:", list(zip(data['meses'], data['mensal_pedidos'], data['mensal_receita'])))
print("topcat:", list(zip(data['topcat_labels'], data['topcat_receita'])))
print("pag:", list(zip(data['pag_labels'], data['pag_pedidos'])))
