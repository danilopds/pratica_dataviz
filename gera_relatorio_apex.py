"""Gera relatorio_vendas.html com ApexCharts a partir dos CSVs em modelagens/"""
import pandas as pd, json
from pathlib import Path

MOD = Path("modelagens")
fato = pd.read_csv(MOD/"FATO_VENDAS.csv", usecols=["order_id","id_produto","data_compra","ano","vl_preco","vl_frete","vl_total_item","qtd_parcelas","tipo_pagamento","cidade_cliente","estado_cliente"])
dim_prod = pd.read_csv(MOD/"DIM_PRODUTO.csv", usecols=["id_produto","categoria_pt"])

fato["data_compra"] = pd.to_datetime(fato["data_compra"], errors="coerce")
fato["mes"] = fato["data_compra"].dt.month
fato["cidade_norm"] = fato["cidade_cliente"].astype(str).str.strip().str.lower()
fato["estado_norm"] = fato["estado_cliente"].astype(str).str.strip().str.upper()

rec = fato[(fato["vl_total_item"] < 500) & (fato["cidade_norm"]=="sao paulo") & (fato["estado_norm"]=="SP") & (fato["ano"]==2017)].copy()
base_br = fato[(fato["vl_total_item"] < 500) & (fato["ano"]==2017)].copy()

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
mensal = rec.groupby("mes").agg(pedidos=("order_id","nunique"), itens=("order_id","count"), receita=("vl_total_item","sum")).reindex(range(1,13), fill_value=0)
meses = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]

rec_cat = rec.merge(dim_prod, on="id_produto", how="left")
rec_cat["categoria_pt"] = rec_cat["categoria_pt"].fillna("sem_categoria")
topcat = rec_cat.groupby("categoria_pt").agg(receita=("vl_total_item","sum"), itens=("vl_total_item","count")).sort_values("receita", ascending=False).head(10)
pag = rec.groupby("tipo_pagamento").agg(pedidos=("order_id","nunique"), receita=("vl_total_item","sum")).sort_values("receita", ascending=False)

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
    "topcat_labels": topcat.index.tolist(),
    "topcat_receita": [round(x,2) for x in topcat["receita"].tolist()],
    "pag_labels": pag.index.tolist(),
    "pag_pedidos": pag["pedidos"].tolist(),
    "pag_receita": [round(x,2) for x in pag["receita"].tolist()],
    "radar_labels": labels_radar,
    "sp_norm": sp_norm, "br_norm": br_norm,
    "sp_raw": sp_raw, "br_raw": br_raw,
}

rows = "".join(f"<tr><td>{m}</td><td>{p}</td><td>{i}</td><td>{r:,.2f}</td></tr>" for m,p,i,r in zip(meses, data["mensal_pedidos"], mensal["itens"].tolist(), data["mensal_receita"]))

html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Relatório de Vendas — Olist | SP Capital 2017 &lt; R$500 (ApexCharts)</title>
<script src="https://cdn.jsdelivr.net/npm/apexcharts"></script>
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
  table{{width:100%;border-collapse:collapse;font-size:14px}}
  th,td{{padding:8px;border-bottom:1px solid #e5e7eb;text-align:right}} th:first-child,td:first-child{{text-align:left}}
  footer{{color:#64748b;font-size:12px;padding:20px;text-align:center}}
</style>
</head>
<body>
<header>
  <h1>Relatório de Vendas — Olist (ApexCharts)</h1>
  <p>Foco: valor do item &lt; R$500 • São Paulo capital (sao paulo/SP) • 2017 • Fonte: <code>modelagens/FATO_VENDAS.csv</code> + <code>DIM_PRODUTO.csv</code></p>
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
    <h2>1. Evolução mensal — linha</h2>
    <p>Receita mensal (R$, eixo esquerdo) e nº de pedidos (eixo direito). Grão da fato: 1 item por linha.</p>
    <div id="chLinha"></div>
  </div>

  <div class="grid2">
    <div class="card">
      <h2>2. Top categorias — barras</h2>
      <p>Top 10 <code>categoria_pt</code> por receita no recorte.</p>
      <div id="chBarCat"></div>
    </div>
    <div class="card">
      <h2>3. Vendas por pagamento — barras</h2>
      <p>Pedidos por <code>tipo_pagamento</code> no recorte.</p>
      <div id="chBarPag"></div>
    </div>
  </div>

  <div class="card">
    <h2>4. Perfil SP capital vs Brasil — radar</h2>
    <p>Comparativo 2017 &lt;R$500 normalizado 0–100. Reais SP: {', '.join(str(x) for x in sp_raw)} | Brasil: {', '.join(str(x) for x in br_raw)}</p>
    <div id="chRadar"></div>
  </div>

  <div class="card">
    <h2>Detalhamento mensal</h2>
    <table><thead><tr><th>Mês</th><th>Pedidos</th><th>Itens</th><th>Receita (R$)</th></tr></thead>
    <tbody>{rows}</tbody></table>
  </div>
</div>
<footer>Gerado a partir de modelagens/DIM_*.csv e FATO_VENDAS.csv • Grão: 1 item/pedido • Filtros: vl_total_item&lt;500, cidade='sao paulo', estado='SP', ano=2017 • ApexCharts</footer>
<script>
const D = {json.dumps(data)};
new ApexCharts(document.querySelector("#chLinha"), {{
  chart:{{type:'line', height:340, toolbar:{{show:true}}}},
  stroke:{{curve:'smooth', width:[3,3]}},
  series:[{{name:'Receita (R$)', data:D.mensal_receita}}, {{name:'Pedidos', data:D.mensal_pedidos}}],
  xaxis:{{categories:D.meses}},
  yaxis:[{{title:{{text:'Receita (R$)'}}}}, {{opposite:true, title:{{text:'Pedidos'}}}}],
  tooltip:{{shared:true}}
}}).render();
new ApexCharts(document.querySelector("#chBarCat"), {{
  chart:{{type:'bar', height:380, toolbar:{{show:true}}}},
  plotOptions:{{bar:{{horizontal:true, borderRadius:4}}}},
  dataLabels:{{enabled:false}},
  series:[{{name:'Receita (R$)', data:D.topcat_receita}}],
  xaxis:{{categories:D.topcat_labels}},
  tooltip:{{y:{{formatter:v=>'R$ '+v.toLocaleString('pt-BR')}}}}
}}).render();
new ApexCharts(document.querySelector("#chBarPag"), {{
  chart:{{type:'bar', height:340, toolbar:{{show:true}}}},
  plotOptions:{{bar:{{borderRadius:6, columnWidth:'55%'}}}},
  dataLabels:{{enabled:false}},
  series:[{{name:'Pedidos', data:D.pag_pedidos}}, {{name:'Receita (R$)', data:D.pag_receita}}],
  xaxis:{{categories:D.pag_labels}}
}}).render();
new ApexCharts(document.querySelector("#chRadar"), {{
  chart:{{type:'radar', height:380, toolbar:{{show:true}}}},
  series:[{{name:'SP capital', data:D.sp_norm}}, {{name:'Brasil', data:D.br_norm}}],
  xaxis:{{categories:D.radar_labels}},
  yaxis:{{min:0, max:100, tickAmount:5}},
  fill:{{opacity:0.25}}
}}).render();
</script>
</body>
</html>"""

Path("relatorio_vendas.html").write_text(html, encoding="utf-8")
print("OK relatorio_vendas.html (ApexCharts)")
