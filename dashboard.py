from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List

from flask import Flask, jsonify, render_template, send_from_directory
import logging
import os
from pathlib import Path

from app.config import get_settings, SettingsError
from app.database import DatabaseManager

app = Flask(__name__, template_folder="templates", static_folder="static")

try:
    settings = get_settings()
except SettingsError as exc:
    raise RuntimeError(f"Erro ao carregar configurações: {exc}")

db = DatabaseManager(settings)

# ---- Helpers ----

def d(val) -> Decimal:
    try:
        return Decimal(str(val))
    except Exception:
        return Decimal("0")


def currency(val: Decimal) -> str:
    q = d(val).quantize(Decimal("0.01"))
    formatted = f"{q:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


# ---- One-time app initialization (cria tabelas e seeds) ----
_initialized = False


@app.before_request
def _init_app_once() -> None:
    global _initialized
    if _initialized:
        return
    try:
        # Garante que as tabelas existam e produtos base estejam cadastrados
        asyncio.run(db.ensure_schema())
        asyncio.run(db.seed_products())
        _initialized = True
        logging.getLogger(__name__).info("Banco inicializado para o dashboard (schema + seeds)")
    except Exception as exc:  # pragma: no cover
        logging.getLogger(__name__).exception("Falha ao inicializar o banco: %s", exc)


FRONTEND_DIR = Path(__file__).resolve().parent / "client" / "dist"


@app.route("/dashboard")
def dashboard_view_legacy():
    # Fallback legacy server-rendered dashboard (for dev only)
    return render_template("dashboard.html")


@app.route("/assets/<path:path>")
def assets_proxy(path: str):
    # Serve Vite-built assets if available
    if FRONTEND_DIR.exists():
        return send_from_directory(FRONTEND_DIR / "assets", path)
    return ("Assets não encontrados. Construa o front-end (npm run build).", 404)


@app.route("/")
@app.route("/<path:path>")
def serve_frontend(path: str | None = None):
    # Serve React build na raiz
    index_html = FRONTEND_DIR / "index.html"
    if FRONTEND_DIR.exists() and index_html.exists():
        # Se requisitou um arquivo específico dentro de dist
        if path and (FRONTEND_DIR / path).exists():
            # Segurança básica: limitar a dist
            full = (FRONTEND_DIR / path).resolve()
            if str(full).startswith(str(FRONTEND_DIR.resolve())):
                return send_from_directory(FRONTEND_DIR, path)
        # SPA fallback
        return send_from_directory(FRONTEND_DIR, "index.html")
    # Se ainda não há build do front, usa o HTML legado
    return render_template("dashboard.html")


@app.get("/server-products")
async def server_products():
    """Página simples renderizada no servidor para listar produtos (prova de conexão DB->HTML)."""
    items = await db.fetch_products()
    # Converte Decimals de forma segura para o template
    def norm(x: dict) -> dict:
        return {
            "id": x.get("id"),
            "nome": x.get("nome"),
            "tipo": x.get("tipo"),
            "quantidade": float(d(x.get("quantidade"))),
            "unidade": x.get("unidade"),
            "categoria": x.get("categoria"),
            "preco": float(d(x.get("preco"))),
            "valor_total": float(d(x.get("quantidade")) * d(x.get("preco"))),
        }
    return render_template("index_server.html", produtos=[norm(i) for i in items])


@app.get("/dashboard-corona")
def dashboard_corona():
    """Dashboard dark mode inspirado no Corona para Eos Cafés Especiais."""
    return render_template("dashboard_corona.html")

@app.get("/api/dashboard")
async def api_dashboard():
    """Retorna agregados do painel no formato solicitado.

    Estrutura JSON:
    {
      "vendas_hoje": number,
      "vendas_mes": number,
      "total_produtos": number,
      "vendas_categoria": [ { "categoria": str, "total": number }, ... ],
      "evolucao_mensal": [ { "mes": "YYYY-MM", "total": number }, ... ]
    }
    """
    try:
        today = datetime.utcnow().date()
        vendas_hoje = await db.sales_total_for_date(today)
        vendas_mes = await db.sales_total_for_month(year=today.year, month=today.month)
        total_produtos = await db.count_products()
        cat_rows = await db.sales_totals_by_category_last_30_days()
        monthly_rows = await db.monthly_sales_last_n_months(n=12)

        resp = {
            "vendas_hoje": float(d(vendas_hoje)),
            "vendas_mes": float(d(vendas_mes)),
            "total_produtos": int(total_produtos),
            "vendas_categoria": [
                {"categoria": r.get("categoria"), "total": float(d(r.get("total")))} for r in cat_rows
            ],
            "evolucao_mensal": [
                {"mes": r.get("mes"), "total": float(d(r.get("total")))} for r in monthly_rows
            ],
        }
        return jsonify(resp)
    except Exception as exc:  # pragma: no cover
        logging.getLogger(__name__).exception("/api/dashboard error: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/data")
async def api_data():
    try:
        # Fetch raw datasets
        stock = await db.fetch_stock_overview()
        movements = await db.list_recent_all_movements(limit=300)
    except Exception as exc:
        logging.getLogger(__name__).exception("/api/data error: %s", exc)
        return jsonify({"error": str(exc)}), 500

    # Aggregate metrics for stock
    total_quantidade = Decimal("0")
    total_valor = Decimal("0")
    for i in stock:
        qty = d(i.get("quantidade"))
        total_quantidade += qty
        total_valor += qty * d(i.get("preco"))

    # Pre-compute date values once
    now_date = datetime.utcnow().date()
    today_str = now_date.isoformat()

    # Initialize accumulators
    brindes = 0
    entradas = 0
    saidas = 0
    line_points: List[Dict[str, Any]] = []
    sales_by_day: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    top_map: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

    # Sort movements once
    sorted_movements = sorted(movements, key=lambda x: x["data"])

    # Single pass through sorted movements to gather all data
    for m in sorted_movements:
        tipo = m.get("tipo_movimentacao")
        observacao = m.get("observacao") or ""
        is_brinde = "[BRINDE]" in observacao
        ts: datetime = m["data"]
        label = ts.strftime("%d/%m %H:%M")

        # Count movement types
        if tipo == "entrada":
            entradas += 1
        elif tipo == "saida":
            saidas += 1
        if is_brinde:
            brindes += 1

        # Build line chart point
        line_points.append({
            "t": label,
            "entrada": 1 if tipo == "entrada" else 0,
            "saida": 1 if tipo == "saida" and not is_brinde else 0,
            "brinde": 1 if is_brinde else 0,
        })

        # Process sales data (only non-brinde saidas)
        if tipo == "saida" and not is_brinde:
            qty = d(m.get("quantidade"))
            vu = m.get("valor_unitario")
            unit = d(vu) if vu is not None else d(m.get("preco"))
            total = qty * unit
            day_key = ts.date().isoformat()
            sales_by_day[day_key] += total

            # Track top cafés
            if m.get("categoria") == "cafes":
                top_map[m.get("nome") or "?"] += qty

    # Compute rolling window totals
    sales_total_day = Decimal("0")
    sales_total_7 = Decimal("0")
    sales_total_30 = Decimal("0")

    for day_key, value in sales_by_day.items():
        try:
            day_dt = datetime.fromisoformat(day_key).date()
        except Exception:
            continue
        delta_days = (now_date - day_dt).days
        if day_key == today_str:
            sales_total_day += value
        if 0 <= delta_days <= 7:
            sales_total_7 += value
        if 0 <= delta_days <= 30:
            sales_total_30 += value

    sales_series_labels = sorted(sales_by_day.keys())
    sales_series_values = [float(d(sales_by_day[k])) for k in sales_series_labels]

    # Top cafés (already computed during single pass)
    top_pairs = sorted(top_map.items(), key=lambda x: x[1], reverse=True)[:10]
    top_labels = [name for name, _ in top_pairs]
    top_values = [float(q) for _, q in top_pairs]

    # Pre-compute stock data for charts and table
    bar_labels: List[str] = []
    bar_values: List[float] = []
    pie_labels: List[str] = []
    pie_values: List[float] = []
    stock_table: List[Dict[str, Any]] = []
    cafe_items: List[Dict[str, Any]] = []

    for i in stock:
        nome = i.get("nome")
        qty = d(i.get("quantidade"))
        preco = d(i.get("preco"))
        bar_labels.append(nome)
        bar_values.append(float(qty))
        stock_table.append({
            "id": i.get("id"),
            "nome": nome,
            "categoria": i.get("categoria"),
            "quantidade": float(qty),
            "preco": float(preco),
            "valor_total": float(qty * preco),
            "unidade": i.get("unidade"),
        })
        if i.get("categoria") == "cafes":
            cafe_items.append({"nome": nome, "quantidade": qty})

    # Pie chart: proportion by cafe category
    total_cafes_q = sum(ci["quantidade"] for ci in cafe_items) or Decimal("1")
    for ci in cafe_items:
        pie_labels.append(ci["nome"])
        porc = (ci["quantidade"] / total_cafes_q) * Decimal("100") if total_cafes_q > 0 else Decimal("0")
        pie_values.append(float(porc))

    # Pre-compute movements data for response
    movements_data: List[Dict[str, Any]] = []
    for m in movements:
        obs = m.get("observacao") or ""
        movements_data.append({
            "data": m["data"].isoformat(),
            "tipo": m.get("tipo_movimentacao"),
            "nome": m.get("nome"),
            "categoria": m.get("categoria"),
            "quantidade": float(d(m.get("quantidade"))),
            "unidade": m.get("unidade"),
            "preco": float(d(m.get("preco"))) if m.get("preco") is not None else None,
            "valor_unitario": float(d(m.get("valor_unitario"))) if m.get("valor_unitario") is not None else None,
            "is_brinde": "[BRINDE]" in obs,
        })

    data = {
        "generated_at": datetime.utcnow().isoformat(),
        "metrics": {
            "total_itens": float(total_quantidade),
            "valor_estimado": currency(total_valor),
            "movimentos_recent": len(movements),
            "total_brindes": brindes,
        },
        "stock_table": stock_table,
        "movements": movements_data,
        "charts": {
            "bar": {"labels": bar_labels, "data": bar_values},
            "pie": {"labels": pie_labels, "data": pie_values},
            "line": {
                "labels": [p["t"] for p in line_points],
                "entrada": [p["entrada"] for p in line_points],
                "saida": [p["saida"] for p in line_points],
                "brinde": [p["brinde"] for p in line_points],
            },
        },
        "sales": {
            "totals": {
                "day": float(sales_total_day),
                "seven_days": float(sales_total_7),
                "thirty_days": float(sales_total_30),
            },
            "series": {"labels": sales_series_labels, "values": sales_series_values},
        },
        "top_cafes": {"labels": top_labels, "data": top_values},
    }

    return jsonify(data)


@app.get("/api/health")
def api_health():
    """Quick health check for app and database connectivity."""
    try:
        def _probe():
            with db._get_connection() as conn:  # noqa: SLF001 (internal ok for health)
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    one = cur.fetchone()
                    cur.execute("SELECT COUNT(*) AS c FROM tb_produtos")
                    cnt = cur.fetchone()
                    return {
                        "ok": (one is not None),
                        "produtos": (dict(cnt).get("c") if cnt else 0),
                    }
        info = _probe()
        return jsonify({
            "status": "ok",
            "db": info,
            "env": {
                "has_database_url": bool(os.getenv("DATABASE_URL")),
                "db_host": os.getenv("DB_HOST"),
                "db_name": os.getenv("DB_NAME"),
                "db_sslmode": os.getenv("DB_SSLMODE"),
            },
        })
    except Exception as exc:
        logging.getLogger(__name__).exception("/api/health error: %s", exc)
        return jsonify({"status": "error", "error": str(exc)}), 500


@app.get("/api/produtos")
async def api_produtos():
    items = await db.fetch_products()
    # Normaliza tipos para JSON amigável ao front
    def norm(x):
        return {
            "id": x.get("id"),
            "nome": x.get("nome"),
            "tipo": x.get("tipo"),
            "quantidade": float(d(x.get("quantidade"))),
            "unidade": x.get("unidade"),
            "categoria": x.get("categoria"),
            "preco": float(d(x.get("preco"))),
        }

    return jsonify({"items": [norm(i) for i in items]})


@app.get("/api/vendas")
async def api_vendas():
    # Usa uma janela grande para estatísticas (ajuste conforme necessidade)
    movs = await db.list_recent_all_movements(limit=5000)

    # Totais do dia e mês corrente
    now = datetime.utcnow()
    now_date = now.date()
    today_key = now_date.isoformat()
    month_key = now.strftime("%Y-%m")
    total_day = Decimal("0")
    total_month = Decimal("0")

    # Por categoria (últimos 30 dias)
    cat_totals: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

    # Comparativo Cafés vs Outros (30 dias)
    comp_cafes = Decimal("0")
    comp_outros = Decimal("0")

    # Série mensal (últimos 12 meses)
    monthly: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    start_12m = (now.replace(day=1) - timedelta(days=365)).date()

    # Single pass through movements
    for m in movs:
        tipo = m.get("tipo_movimentacao")
        obs = m.get("observacao") or ""
        # Check if it's a valid sale (saida and not a brinde)
        if tipo != "saida" or "[BRINDE]" in obs:
            continue

        day = m["data"].date()
        day_key = day.isoformat()
        month_k = day.strftime("%Y-%m")
        qty = d(m.get("quantidade"))
        vu = m.get("valor_unitario")
        unit = d(vu) if vu is not None else d(m.get("preco"))
        val = qty * unit

        # Totais
        if day_key == today_key:
            total_day += val
        if month_k == month_key:
            total_month += val

        # Por categoria e comparativo (últimos 30 dias)
        delta_days = (now_date - day).days
        if delta_days <= 30:
            cat = m.get("categoria") or "outros"
            cat_totals[cat] += val
            if cat == "cafes":
                comp_cafes += val
            else:
                comp_outros += val

        # Mensal (12 meses)
        if day >= start_12m:
            monthly[month_k] += val

    # Ordena meses
    months_sorted = sorted(monthly.keys())
    resp = {
        "totals": {
            "day": float(total_day),
            "month": float(total_month),
        },
        "por_categoria": {
            "labels": list(cat_totals.keys()),
            "values": [float(v) for v in cat_totals.values()],
        },
        "mensal": {
            "labels": months_sorted,
            "values": [float(monthly[m]) for m in months_sorted],
        },
        "comparativo": {
            "labels": ["Cafés", "Outros"],
            "values": [float(comp_cafes), float(comp_outros)],
        },
    }
    return jsonify(resp)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
