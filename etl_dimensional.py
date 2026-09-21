"""ETL Olist -> Modelagem Dimensional (CSVs unicos em modelagens/)"""
import openpyxl
from pathlib import Path
from collections import defaultdict, Counter
import pandas as pd
from datetime import datetime
import os

DADOS = Path("dados")
OUT = Path("modelagens")
OUT.mkdir(exist_ok=True)

def parse_dt(v):
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v
    try:
        # '2017-09-19 09:45:35' / '2018-03-20 00:00:00'
        return datetime.fromisoformat(str(v).strip())
    except:
        try:
            return pd.to_datetime(v).to_pydatetime()
        except:
            return None

def iter_sheet(xlsx_path, sheet):
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb[sheet]
    rows = ws.iter_rows(values_only=True)
    header = [str(c) if c is not None else "" for c in next(rows)]
    idx = {h: i for i, h in enumerate(header)}
    ncols = len(header)
    count = 0
    for r in rows:
        count += 1
        # pad rows curtas (openpyxl omite trailing None)
        if len(r) < ncols:
            r = tuple(list(r) + [None] * (ncols - len(r)))
        yield idx, r
        if count % 200000 == 0:
            print(f"  ... {count} linhas lidas de {sheet}", flush=True)
    wb.close()

print("== 1. Traducao categorias ==", flush=True)
trad = {}
for idx, r in iter_sheet(DADOS/"olist_catalogo.xlsx", "product_category_name_translati"):
    trad[r[idx["product_category_name"]]] = r[idx["product_category_name_english"]]
print(f"trad: {len(trad)}", flush=True)

print("== 2. Produtos ==", flush=True)
prod_list = []
prod_dict = {}
for idx, r in iter_sheet(DADOS/"olist_catalogo.xlsx", "olist_products"):
    pid = r[idx["product_id"]]
    cat = r[idx["product_category_name"]]
    prod_dict[pid] = cat
    prod_list.append({
        "product_id": pid,
        "categoria_pt": cat,
        "categoria_en": trad.get(cat),
        "peso_g": r[idx["product_weight_g"]],
        "fotos_qty": r[idx["product_photos_qty"]],
        "comprimento_cm": r[idx["product_length_cm"]],
        "altura_cm": r[idx["product_height_cm"]],
        "largura_cm": r[idx["product_width_cm"]],
    })
print(f"produtos: {len(prod_list)}", flush=True)

print("== 3. Vendedores ==", flush=True)
seller_list = []
seller_dict = {}
for idx, r in iter_sheet(DADOS/"olist_catalogo.xlsx", "olist_sellers"):
    sid = r[idx["seller_id"]]
    z = r[idx["seller_zip_code_prefix"]]
    try: z = int(z)
    except: pass
    seller_dict[sid] = {"zip": z, "cidade": r[idx["seller_city"]], "estado": r[idx["seller_state"]]}
    seller_list.append({"seller_id": sid, "cep_prefix": z, "cidade": r[idx["seller_city"]], "estado": r[idx["seller_state"]]})
print(f"sellers: {len(seller_list)}", flush=True)

print("== 4. Clientes ==", flush=True)
cust_list = []
cust_dict = {}
for idx, r in iter_sheet(DADOS/"olist_pedidos_clientes.xlsx", "olist_customers"):
    cid = r[idx["customer_id"]]
    z = r[idx["customer_zip_code_prefix"]]
    try: z = int(z)
    except: pass
    cust_dict[cid] = {"zip": z, "cidade": r[idx["customer_city"]], "estado": r[idx["customer_state"]], "unique": r[idx["customer_unique_id"]]}
    cust_list.append({"customer_id": cid, "customer_unique_id": r[idx["customer_unique_id"]],
                      "cep_prefix": z, "cidade": r[idx["customer_city"]], "estado": r[idx["customer_state"]]})
print(f"clientes: {len(cust_list)}", flush=True)

print("== 5. Pedidos ==", flush=True)
order_dict = {}
datas = set()
for idx, r in iter_sheet(DADOS/"olist_pedidos_clientes.xlsx", "olist_orders"):
    oid = r[idx["order_id"]]
    dt = parse_dt(r[idx["order_purchase_timestamp"]])
    if dt: datas.add(dt.date())
    order_dict[oid] = {
        "customer_id": r[idx["customer_id"]],
        "status": r[idx["order_status"]],
        "purchase": dt,
        "approved": parse_dt(r[idx["order_approved_at"]]),
        "delivered_carrier": parse_dt(r[idx["order_delivered_carrier_date"]]),
        "delivered_customer": parse_dt(r[idx["order_delivered_customer_date"]]),
        "estimated": parse_dt(r[idx["order_estimated_delivery_date"]]),
    }
print(f"pedidos: {len(order_dict)}, datas distintas: {len(datas)}", flush=True)

print("== 6. Pagamentos (agregado por pedido) ==", flush=True)
pay_agg = {}  # order_id -> {total, max_parc, tipos, qtd}
for idx, r in iter_sheet(DADOS/"olist_itens_pagamentos_avaliacoes.xlsx", "olist_order_payments"):
    oid = r[idx["order_id"]]
    tipo = r[idx["payment_type"]]
    parc = r[idx["payment_installments"]] or 0
    val = float(r[idx["payment_value"]] or 0)
    a = pay_agg.get(oid)
    if not a:
        pay_agg[oid] = {"total": val, "max_parc": int(parc or 0), "tipos": [tipo], "qtd": 1}
    else:
        a["total"] += val
        a["max_parc"] = max(a["max_parc"], int(parc or 0))
        a["tipos"].append(tipo)
        a["qtd"] += 1
print(f"pedidos com pagamento: {len(pay_agg)}", flush=True)

print("== 7. Itens (base da fato) ==", flush=True)
items = []
items_por_pedido = Counter()
for idx, r in iter_sheet(DADOS/"olist_itens_pagamentos_avaliacoes.xlsx", "olist_order_items"):
    oid = r[idx["order_id"]]
    items.append({
        "order_id": oid,
        "order_item_id": r[idx["order_item_id"]],
        "product_id": r[idx["product_id"]],
        "seller_id": r[idx["seller_id"]],
        "shipping_limit": parse_dt(r[idx["shipping_limit_date"]]),
        "price": float(r[idx["price"]] or 0),
        "freight": float(r[idx["freight_value"]] or 0),
    })
    items_por_pedido[oid] += 1
print(f"itens: {len(items)}", flush=True)

print("== 8. Geolocalizacao (agregada por CEP) ==", flush=True)
geo = {}  # zip -> [sum_lat, sum_lng, count, cidade, estado]
for idx, r in iter_sheet(DADOS/"olist_geolocalizacao.xlsx", "olist_geolocation"):
    z = r[idx["geolocation_zip_code_prefix"]]
    try: z = int(z)
    except: continue
    lat = r[idx["geolocation_lat"]]
    lng = r[idx["geolocation_lng"]]
    cid = r[idx["geolocation_city"]]
    est = r[idx["geolocation_state"]]
    if z not in geo:
        geo[z] = [0.0, 0.0, 0, cid, est]
    g = geo[z]
    try:
        g[0] += float(lat or 0); g[1] += float(lng or 0)
    except: pass
    g[2] += 1
print(f"ceps distintos geo: {len(geo)}", flush=True)

# Incluir CEPs de clientes/vendedores que nao estao na geo
faltantes = set()
for c in cust_list:
    if c["cep_prefix"] not in geo:
        faltantes.add((c["cep_prefix"], c["cidade"], c["estado"]))
for s in seller_list:
    if s["cep_prefix"] not in geo:
        faltantes.add((s["cep_prefix"], s["cidade"], s["estado"]))
print(f"ceps faltantes (cliente/vendedor sem geo): {len(faltantes)}", flush=True)
for z, cid, est in faltantes:
    if z not in geo:
        geo[z] = [0.0, 0.0, 0, cid, est]

# ---------- DIMS ----------
print("== 9. Gerando DIMs ==", flush=True)

# DIM_TEMPO
tempo_rows = []
for d in sorted(datas):
    tempo_rows.append({
        "id_tempo": int(d.strftime("%Y%m%d")),
        "data": d.isoformat(),
        "ano": d.year, "mes": d.month,
        "mes_nome": f"{d.month:02d}",
        "trimestre": (d.month-1)//3+1,
        "dia_semana": d.strftime("%A"),
    })
dim_tempo = pd.DataFrame(tempo_rows)

# DIM_CLIENTE
dim_cliente = pd.DataFrame(cust_list)
dim_cliente.insert(0, "id_cliente", range(1, len(dim_cliente)+1))
map_cliente = dict(zip(dim_cliente["customer_id"], dim_cliente["id_cliente"]))

# DIM_PRODUTO
dim_prod = pd.DataFrame(prod_list)
dim_prod.insert(0, "id_produto", range(1, len(dim_prod)+1))
map_prod = dict(zip(dim_prod["product_id"], dim_prod["id_produto"]))

# DIM_VENDEDOR
dim_vend = pd.DataFrame(seller_list)
dim_vend.insert(0, "id_vendedor", range(1, len(dim_vend)+1))
map_vend = dict(zip(dim_vend["seller_id"], dim_vend["id_vendedor"]))

# DIM_LOCALIDADE
loc_rows = []
for z, (slat, slng, cnt, cid, est) in geo.items():
    lat = round(slat/cnt, 6) if cnt else None
    lng = round(slng/cnt, 6) if cnt else None
    fl_sp = "S" if (str(cid).strip().lower() == "sao paulo" and str(est).strip().upper() == "SP") else "N"
    loc_rows.append({"cep_prefix": z, "cidade": cid, "estado": est, "lat": lat, "lng": lng, "fl_sp_capital": fl_sp})
dim_loc = pd.DataFrame(loc_rows).sort_values("cep_prefix").reset_index(drop=True)
dim_loc.insert(0, "id_localidade", range(1, len(dim_loc)+1))
map_loc = dict(zip(dim_loc["cep_prefix"], dim_loc["id_localidade"]))

# DIM_PAGAMENTO
tipos = sorted({t for a in pay_agg.values() for t in a["tipos"]})
dim_pag = pd.DataFrame([{"tipo_pagamento": t} for t in tipos])
dim_pag.insert(0, "id_pagamento", range(1, len(dim_pag)+1))
map_pag = dict(zip(dim_pag["tipo_pagamento"], dim_pag["id_pagamento"]))

print(f"DIM_TEMPO={len(dim_tempo)} DIM_CLIENTE={len(dim_cliente)} DIM_PRODUTO={len(dim_prod)} DIM_VENDEDOR={len(dim_vend)} DIM_LOCAL={len(dim_loc)} DIM_PAG={len(dim_pag)}", flush=True)

# ---------- FATO ----------
print("== 10. Gerando FATO_VENDAS ==", flush=True)
fato_rows = []
sem_order = sem_cli = 0
for it in items:
    oid = it["order_id"]
    od = order_dict.get(oid)
    if not od:
        sem_order += 1
        continue
    cid = od["customer_id"]
    cinfo = cust_dict.get(cid, {})
    purchase = od["purchase"]
    id_tempo = int(purchase.strftime("%Y%m%d")) if purchase else None
    id_cliente = map_cliente.get(cid)
    if not id_cliente:
        sem_cli += 1
        continue
    id_prod = map_prod.get(it["product_id"])
    id_vend = map_vend.get(it["seller_id"])
    pag = pay_agg.get(oid, {"total": 0, "max_parc": 0, "tipos": ["desconhecido"]})
    tipo_main = pag["tipos"][0] if pag["tipos"] else "desconhecido"
    id_pag = map_pag.get(tipo_main)
    n_itens = items_por_pedido.get(oid, 1)
    vl_total = it["price"] + it["freight"]
    vl_rateado = pag["total"]/n_itens if n_itens else pag["total"]
    zip_cli = cinfo.get("zip")
    id_loc = map_loc.get(zip_cli)
    fato_rows.append({
        "order_id": oid,
        "order_item_id": it["order_item_id"],
        "id_tempo": id_tempo,
        "id_cliente": id_cliente,
        "id_produto": id_prod,
        "id_vendedor": id_vend,
        "id_localidade": id_loc,
        "id_pagamento": id_pag,
        "order_status": od["status"],
        "data_compra": purchase.isoformat() if purchase else None,
        "ano": purchase.year if purchase else None,
        "qtd_item": 1,
        "vl_preco": round(it["price"], 2),
        "vl_frete": round(it["freight"], 2),
        "vl_total_item": round(vl_total, 2),
        "vl_pagamento_pedido": round(pag["total"], 2),
        "vl_pagamento_rateado": round(vl_rateado, 2),
        "qtd_parcelas": pag["max_parc"],
        "tipo_pagamento": tipo_main,
        "cidade_cliente": cinfo.get("cidade"),
        "estado_cliente": cinfo.get("estado"),
        "cep_cliente": zip_cli,
    })
print(f"fato linhas: {len(fato_rows)}, sem_order={sem_order}, sem_cli={sem_cli}", flush=True)
fato = pd.DataFrame(fato_rows)

# ---------- SAVE ----------
dim_tempo.to_csv(OUT/"DIM_TEMPO.csv", index=False)
dim_cliente.to_csv(OUT/"DIM_CLIENTE.csv", index=False)
dim_prod.to_csv(OUT/"DIM_PRODUTO.csv", index=False)
dim_vend.to_csv(OUT/"DIM_VENDEDOR.csv", index=False)
dim_loc.to_csv(OUT/"DIM_LOCALIDADE.csv", index=False)
dim_pag.to_csv(OUT/"DIM_PAGAMENTO.csv", index=False)
fato.to_csv(OUT/"FATO_VENDAS.csv", index=False)

print("== OK ==", flush=True)
for f in sorted(OUT.glob("*.csv")):
    print(f"{f.name}: {f.stat().st_size/1024:.1f} KB", flush=True)

# Quick check da pergunta: <500, SP capital, 2017
q = fato[(fato["vl_total_item"] < 500) & (fato["cidade_cliente"] == "sao paulo") & (fato["estado_cliente"] == "SP") & (fato["ano"] == 2017)]
print(f"CHECK filtro (<500, sao paulo/SP, 2017): {len(q)} itens, {q['order_id'].nunique()} pedidos, receita={q['vl_total_item'].sum():.2f}", flush=True)
