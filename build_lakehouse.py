"""Build lakehouse/olist.duckdb a partir de modelagens/*.csv"""
import duckdb
from pathlib import Path

MOD = Path("modelagens")
LH = Path("lakehouse")
LH.mkdir(exist_ok=True)
DB = LH / "olist.duckdb"
if DB.exists():
    DB.unlink()

con = duckdb.connect(str(DB))
tabelas = ["DIM_TEMPO","DIM_CLIENTE","DIM_PRODUTO","DIM_VENDEDOR","DIM_LOCALIDADE","DIM_PAGAMENTO","FATO_VENDAS"]
for t in tabelas:
    csv = MOD / f"{t}.csv"
    print(f"load {t} <- {csv} ...", flush=True)
    con.execute(f"CREATE TABLE {t} AS SELECT * FROM read_csv('{csv}', header=true, auto_detect=true)")
    n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"  {t}: {n} linhas", flush=True)

# Views analíticas (gold)
con.execute("""
CREATE OR REPLACE VIEW vw_fato_enriquecida AS
SELECT f.*, p.categoria_pt, p.categoria_en, t.mes AS mes_ref
FROM FATO_VENDAS f
LEFT JOIN DIM_PRODUTO p ON p.id_produto = f.id_produto
LEFT JOIN DIM_TEMPO t ON t.id_tempo = f.id_tempo
""")
con.execute("""
CREATE OR REPLACE VIEW vw_vendas_sp_2017_500 AS
SELECT * FROM vw_fato_enriquecida
WHERE vl_total_item < 500
  AND lower(cidade_cliente) = 'sao paulo'
  AND upper(estado_cliente) = 'SP'
  AND ano = 2017
""")
con.execute("""
CREATE OR REPLACE VIEW vw_mensal_sp AS
SELECT CAST(CAST(data_compra AS TIMESTAMP) AS DATE) AS dt,
       MONTH(CAST(data_compra AS TIMESTAMP)) AS mes,
       COUNT(DISTINCT order_id) AS pedidos,
       COUNT(*) AS itens,
       SUM(vl_total_item) AS receita
FROM vw_vendas_sp_2017_500 GROUP BY 1,2 ORDER BY 1
""")
print("views OK", flush=True)
for v in ["vw_fato_enriquecida","vw_vendas_sp_2017_500","vw_mensal_sp"]:
    n = con.execute(f"SELECT COUNT(*) FROM {v}").fetchone()[0]
    print(f"  {v}: {n}", flush=True)
con.close()
print(f"OK {DB} ({DB.stat().st_size/1024/1024:.1f} MB)", flush=True)
