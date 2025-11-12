from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional
from typing import Any, Dict, List, Optional

import psycopg
from psycopg.rows import dict_row

from .config import Settings
from .products import PRODUCT_SEEDS

CREATE_TABLE_PRODUCTS = """
CREATE TABLE IF NOT EXISTS tb_produtos (
    id SERIAL PRIMARY KEY,
    nome TEXT NOT NULL UNIQUE,
    tipo TEXT NOT NULL CHECK (tipo IN ('produto_acabado', 'materia_prima')),
    quantidade NUMERIC(14, 3) NOT NULL DEFAULT 0,
    unidade TEXT NOT NULL DEFAULT 'un',
    categoria TEXT NOT NULL DEFAULT 'cafes',
    preco NUMERIC(14, 2) DEFAULT 0,
    data_ultima_movimentacao TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);
"""

CREATE_TABLE_MOVIMENTACOES = """
CREATE TABLE IF NOT EXISTS tb_movimentacoes (
    id SERIAL PRIMARY KEY,
    id_produto INTEGER NOT NULL REFERENCES tb_produtos(id) ON DELETE CASCADE,
    tipo_movimentacao TEXT NOT NULL CHECK (tipo_movimentacao IN ('entrada', 'saida')),
    quantidade NUMERIC(14, 3) NOT NULL,
    valor_unitario NUMERIC(14, 2),
    data TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW(),
    observacao TEXT
);
"""

CREATE_TABLE_BRINDES = """
CREATE TABLE IF NOT EXISTS tb_brindes (
    id SERIAL PRIMARY KEY,
    descricao TEXT NOT NULL,
    chat_id BIGINT,
    data TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT NOW()
);
"""

ALTER_TABLE_PRODUTOS_CATEGORIA = "ALTER TABLE tb_produtos ADD COLUMN IF NOT EXISTS categoria TEXT NOT NULL DEFAULT 'cafes';"
ALTER_TABLE_PRODUTOS_PRECO = "ALTER TABLE tb_produtos ADD COLUMN IF NOT EXISTS preco NUMERIC(14, 2) DEFAULT 0;"
ALTER_TABLE_MOV_VALOR_UNITARIO = "ALTER TABLE tb_movimentacoes ADD COLUMN IF NOT EXISTS valor_unitario NUMERIC(14, 2);"


class DatabaseError(RuntimeError):
    """Base error for database issues."""


class ProductNotFoundError(DatabaseError):
    """Raised when a product cannot be located in the database."""


class InsufficientStockError(DatabaseError):
    """Raised when a stock deduction would result in a negative quantity."""


@dataclass
class DatabaseManager:
    settings: Settings

    def __post_init__(self) -> None:
        self._settings = self.settings

    @contextmanager
    def _get_connection(self):
        connection = psycopg.connect(
            dbname=self._settings.db_name,
            user=self._settings.db_user,
            password=self._settings.db_password,
            host=self._settings.db_host,
            port=self._settings.db_port,
            row_factory=dict_row,  # type: ignore[arg-type]
        )
        try:
            yield connection
        finally:
            connection.close()

    async def ensure_schema(self) -> None:
        def _create():
            with self._get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(CREATE_TABLE_PRODUCTS)
                    cursor.execute(CREATE_TABLE_MOVIMENTACOES)
                    cursor.execute(CREATE_TABLE_BRINDES)
                    cursor.execute(ALTER_TABLE_PRODUTOS_CATEGORIA)
                    cursor.execute(ALTER_TABLE_PRODUTOS_PRECO)
                    cursor.execute(ALTER_TABLE_MOV_VALOR_UNITARIO)
                    connection.commit()

        await asyncio.to_thread(_create)

    async def seed_products(self) -> None:
        def _seed():
            with self._get_connection() as connection:
                with connection.cursor() as cursor:
                    for item in PRODUCT_SEEDS:
                        cursor.execute(
                            """
                            INSERT INTO tb_produtos (nome, tipo, unidade, categoria, preco)
                            VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT (nome) DO UPDATE
                            SET tipo = EXCLUDED.tipo,
                                unidade = EXCLUDED.unidade,
                                categoria = EXCLUDED.categoria,
                                preco = EXCLUDED.preco
                            """,
                            (item.nome, item.tipo, item.unidade, item.categoria, item.preco),
                        )
                connection.commit()

        await asyncio.to_thread(_seed)

    async def fetch_products(self) -> List[dict]:
        def _fetch():
            with self._get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT id, nome, tipo, quantidade, unidade, categoria, preco FROM tb_produtos ORDER BY nome;"
                    )
                    return [dict(row) for row in cursor.fetchall()]

        return await asyncio.to_thread(_fetch)

    async def fetch_products_by_category(self, category: str) -> List[dict]:
        def _fetch():
            with self._get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT id, nome, quantidade, unidade, preco
                        FROM tb_produtos
                        WHERE categoria = %s
                        ORDER BY nome
                        """,
                        (category,),
                    )
                    return [dict(row) for row in cursor.fetchall()]

        return await asyncio.to_thread(_fetch)

    async def fetch_stock_overview(self) -> List[dict]:
        def _fetch():
            with self._get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT id, nome, quantidade, unidade, categoria, preco
                        FROM tb_produtos
                        ORDER BY categoria, nome
                        """
                    )
                    return [dict(row) for row in cursor.fetchall()]

        return await asyncio.to_thread(_fetch)

    async def get_product(self, product_id: int) -> Optional[dict]:
        def _get():
            with self._get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT id, nome, tipo, quantidade, unidade, preco FROM tb_produtos WHERE id = %s",
                        (product_id,),
                    )
                    row = cursor.fetchone()
                    return dict(row) if row else None

        return await asyncio.to_thread(_get)

    async def adjust_stock(
        self,
        *,
        product_id: int,
        movement_type: str,
        quantity: Decimal,
        valor_unitario: Optional[Decimal],
        observacao: str,
    ) -> Decimal:
        if quantity <= 0:
            raise DatabaseError("A quantidade deve ser positiva.")

        def _adjust() -> Decimal:
            with self._get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT quantidade FROM tb_produtos WHERE id = %s FOR UPDATE",
                        (product_id,),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        raise ProductNotFoundError("Produto não encontrado.")

                    row_dict = dict(row)
                    current_quantity = Decimal(row_dict["quantidade"])
                    delta = quantity if movement_type == "entrada" else -quantity
                    new_quantity = current_quantity + delta

                    if new_quantity < 0:
                        raise InsufficientStockError(
                            "Estoque insuficiente para registrar a saída."
                        )

                    cursor.execute(
                        """
                        UPDATE tb_produtos
                        SET quantidade = %s, data_ultima_movimentacao = NOW()
                        WHERE id = %s
                        """,
                        (new_quantity, product_id),
                    )
                    cursor.execute(
                        """
                        INSERT INTO tb_movimentacoes (id_produto, tipo_movimentacao, quantidade, valor_unitario, observacao)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (product_id, movement_type, quantity, (valor_unitario if valor_unitario is not None else None), observacao),
                    )
                    connection.commit()
                    return new_quantity

        return await asyncio.to_thread(_adjust)

    async def list_recent_movements(self, *, movement_type: str, limit: int = 10) -> List[dict]:
        def _list():
            with self._get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT m.data, m.quantidade, m.valor_unitario, p.nome, p.unidade
                        FROM tb_movimentacoes m
                        JOIN tb_produtos p ON p.id = m.id_produto
                        WHERE m.tipo_movimentacao = %s
                        ORDER BY m.data DESC
                        LIMIT %s
                        """,
                        (movement_type, limit),
                    )
                    return [dict(row) for row in cursor.fetchall()]

        return await asyncio.to_thread(_list)

    async def list_recent_saidas_with_brindes(self, limit: int = 10) -> List[dict]:
        def _list():
            with self._get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT m.data, m.quantidade, m.valor_unitario, p.nome, p.unidade, p.preco
                        FROM tb_movimentacoes m
                        JOIN tb_produtos p ON p.id = m.id_produto
                        WHERE m.tipo_movimentacao = 'saida'
                        ORDER BY m.data DESC
                        LIMIT %s
                        """,
                        (limit,),
                    )
                    saidas = []
                    for row in cursor.fetchall():
                        row_dict = dict(row)
                        saidas.append(
                            {
                                "tipo": "saida",
                                "data": row_dict["data"],
                                "nome": row_dict["nome"],
                                "quantidade": Decimal(row_dict["quantidade"]),
                                "unidade": row_dict["unidade"],
                                "valor_unitario": (Decimal(row_dict["valor_unitario"]) if row_dict.get("valor_unitario") is not None else None),
                                "preco": Decimal(row_dict["preco"]) if row_dict["preco"] is not None else Decimal("0"),
                            }
                        )

                    cursor.execute(
                        """
                        SELECT data, descricao, chat_id
                        FROM tb_brindes
                        ORDER BY data DESC
                        LIMIT %s
                        """,
                        (limit,),
                    )
                    brindes = []
                    for row in cursor.fetchall():
                        row_dict = dict(row)
                        brindes.append(
                            {
                                "tipo": "brinde",
                                "data": row_dict["data"],
                                "descricao": row_dict["descricao"],
                                "chat_id": row_dict.get("chat_id"),
                            }
                        )

            combined = saidas + brindes
            combined.sort(key=lambda item: item["data"], reverse=True)
            return combined[:limit]

        return await asyncio.to_thread(_list)

    async def record_brinde(self, descricao: str, *, chat_id: Optional[int]) -> None:
        def _record():
            with self._get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO tb_brindes (descricao, chat_id) VALUES (%s, %s)",
                        (descricao, chat_id),
                    )
                    connection.commit()

        await asyncio.to_thread(_record)

    async def sales_totals_by_date(self, days: int = 30) -> List[dict]:
        def _list():
            with self._get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT DATE(m.data) AS dia,
                               SUM(m.quantidade * COALESCE(p.preco, 0)) AS total
                        FROM tb_movimentacoes m
                        JOIN tb_produtos p ON p.id = m.id_produto
                        WHERE m.tipo_movimentacao = 'saida'
                        GROUP BY dia
                        ORDER BY dia DESC
                        LIMIT %s
                        """,
                        (days,),
                    )
                    return [dict(row) for row in cursor.fetchall()]

        return await asyncio.to_thread(_list)

    async def sales_totals_by_product(self, days: int = 30) -> List[dict]:
        def _list():
            with self._get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT p.nome,
                               SUM(m.quantidade) AS quantidade,
                               SUM(m.quantidade * COALESCE(p.preco, 0)) AS total
                        FROM tb_movimentacoes m
                        JOIN tb_produtos p ON p.id = m.id_produto
                        WHERE m.tipo_movimentacao = 'saida'
                          AND m.data >= NOW() - (%s * INTERVAL '1 day')
                        GROUP BY p.nome
                        ORDER BY total DESC
                        """,
                        (days,),
                    )
                    return [dict(row) for row in cursor.fetchall()]

        return await asyncio.to_thread(_list)

    async def sales_total_for_date(self, target_date: date) -> Decimal:
        def _fetch() -> Decimal:
            with self._get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT COALESCE(SUM(m.quantidade * COALESCE(p.preco, 0)), 0) AS total
                        FROM tb_movimentacoes m
                        JOIN tb_produtos p ON p.id = m.id_produto
                        WHERE m.tipo_movimentacao = 'saida'
                          AND DATE(m.data) = %s
                        """,
                        (target_date,),
                    )
                    row = cursor.fetchone()
                    if not row:
                        return Decimal("0")
                    row_dict = dict(row)
                    value = row_dict.get("total")
                    return Decimal(value) if value is not None else Decimal("0")

        return await asyncio.to_thread(_fetch)

    async def list_recent_all_movements(self, limit: int = 10) -> List[dict]:
        def _list():
            with self._get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT m.data, m.quantidade, m.valor_unitario, m.observacao, m.tipo_movimentacao,
                               p.nome, p.unidade, p.preco, p.categoria
                        FROM tb_movimentacoes m
                        JOIN tb_produtos p ON p.id = m.id_produto
                        ORDER BY m.data DESC
                        LIMIT %s
                        """,
                        (limit,),
                    )
                    return [dict(row) for row in cursor.fetchall()]

        return await asyncio.to_thread(_list)

    async def clear_stock(self) -> None:
        """Zero all product quantities."""
        def _clear():
            with self._get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("UPDATE tb_produtos SET quantidade = 0;")
                    connection.commit()

        await asyncio.to_thread(_clear)

    async def clear_saidas_history(self) -> None:
        """Remove all 'saida' movements."""
        def _clear():
            with self._get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM tb_movimentacoes WHERE tipo_movimentacao = 'saida';")
                    connection.commit()

        await asyncio.to_thread(_clear)

    async def clear_all_history(self) -> None:
        """Remove all movements (entrada and saida)."""
        def _clear():
            with self._get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM tb_movimentacoes;")
                    connection.commit()

        await asyncio.to_thread(_clear)
