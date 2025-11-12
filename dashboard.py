from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List

from flask import Flask, jsonify, render_template

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


@app.route("/dashboard")
@app.route("/")
def dashboard_view():
    return render_template("dashboard.html")


@app.route("/api/data")
async def api_data():
    # Fetch raw datasets
    stock = await db.fetch_stock_overview()
    movements = await db.list_recent_all_movements(limit=300)

    # Aggregate metrics
    total_quantidade = sum(d(i.get("quantidade")) for i in stock)
    total_valor = sum(d(i.get("quantidade")) * d(i.get("preco")) for i in stock)

    brindes = 0
    entradas = 0
    saidas = 0

    line_points: List[Dict[str, Any]] = []

    # Build time series (simple aggregated counts per movement order)
    for idx, m in enumerate(sorted(movements, key=lambda x: x["data"])):
        tipo = m.get("tipo_movimentacao")
        observacao = (m.get("observacao") or "")
        qtd = d(m.get("quantidade"))
        is_brinde = "[BRINDE]" in observacao
        ts: datetime = m["data"]
        label = ts.strftime("%d/%m %H:%M")

        if tipo == "entrada":
            entradas += 1
        elif tipo == "saida":
            saidas += 1
        if is_brinde:
            brindes += 1

        line_points.append({
            "t": label,
            "entrada": 1 if tipo == "entrada" else 0,
            "saida": 1 if tipo == "saida" and not is_brinde else 0,
            "brinde": 1 if is_brinde else 0,
        })

    # Bar chart: quantity per product
    bar_labels = [i.get("nome") for i in stock]
    bar_values = [float(d(i.get("quantidade"))) for i in stock]

    # Pie chart: proportion by cafe category only
    cafe_items = [i for i in stock if i.get("categoria") == "cafes"]
    total_cafes_q = sum(d(i.get("quantidade")) for i in cafe_items) or Decimal("1")
    pie_labels = [i.get("nome") for i in cafe_items]
    pie_values = []
    for item in cafe_items:
        qtd = d(item.get("quantidade"))
        porc = (qtd / total_cafes_q) * Decimal("100") if total_cafes_q > 0 else Decimal("0")
        pie_values.append(float(porc))

    data = {
        "generated_at": datetime.utcnow().isoformat(),
        "metrics": {
            "total_itens": float(total_quantidade),
            "valor_estimado": currency(Decimal(total_valor)),
            "movimentos_recent": len(movements),
            "total_brindes": brindes,
        },
        "stock_table": [
            {
                "id": i.get("id"),
                "nome": i.get("nome"),
                "categoria": i.get("categoria"),
                "quantidade": float(d(i.get("quantidade"))),
                "preco": float(d(i.get("preco"))),
                "valor_total": float(d(i.get("quantidade")) * d(i.get("preco"))),
                "unidade": i.get("unidade"),
            }
            for i in stock
        ],
        "movements": [
            {
                "data": m["data"].isoformat(),
                "tipo": m.get("tipo_movimentacao"),
                "nome": m.get("nome"),
                "categoria": m.get("categoria"),
                "quantidade": float(d(m.get("quantidade"))),
                "unidade": m.get("unidade"),
                "is_brinde": "[BRINDE]" in (m.get("observacao") or ""),
            }
            for m in movements
        ],
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
    }

    return jsonify(data)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
