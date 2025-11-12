from typing import Iterable, List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_main_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("☕ Entrada", callback_data="menu:entrada"),
            InlineKeyboardButton("🚚 Saída", callback_data="menu:saida"),
        ],
        [
            InlineKeyboardButton("📦 Estoque", callback_data="menu:estoque"),
            InlineKeyboardButton("📊 Histórico", callback_data="menu:historico"),
        ],
        [InlineKeyboardButton("🤖 IA", callback_data="menu:iaeos")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_category_keyboard(action: str) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = []

    buttons.append(
        [
            InlineKeyboardButton(
                "☕ Cafés",
                callback_data=f"categoria:{action}:cafes",
            ),
            InlineKeyboardButton(
                "📦 Embalagens",
                callback_data=f"categoria:{action}:embalagens",
            ),
        ]
    )

    if action == "saida":
        buttons.append(
            [InlineKeyboardButton("🎁 Brindes", callback_data="categoria:saida:brindes")]
        )

    buttons.append([InlineKeyboardButton("🏠 Voltar ao menu principal", callback_data="menu:home")])
    return InlineKeyboardMarkup(buttons)


def build_products_keyboard(
    action: str,
    products: Iterable[dict],
    *,
    category: str,
) -> InlineKeyboardMarkup:
    buttons: List[List[InlineKeyboardButton]] = []
    current_row: List[InlineKeyboardButton] = []

    for index, product in enumerate(products, start=1):
        icon = "☕" if category == "cafes" else "📦"
        label = f"{icon} {product['nome']}"
        current_row.append(
            InlineKeyboardButton(label, callback_data=f"produto:{action}:{product['id']}")
        )
        if index % 2 == 0:
            buttons.append(current_row)
            current_row = []

    if current_row:
        buttons.append(current_row)

    buttons.append(
        [
            InlineKeyboardButton(
                "🔙 Voltar às categorias",
                callback_data=f"flow:{action}:back_to_categories",
            ),
            InlineKeyboardButton("🏠 Menu principal", callback_data="menu:home"),
        ]
    )
    return InlineKeyboardMarkup(buttons)


def build_stock_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔄 Atualizar estoque", callback_data="menu:estoque")],
            [InlineKeyboardButton("🧹 Limpar estoque", callback_data="admin:confirm_clear_stock")],
            [InlineKeyboardButton("🔙 Voltar ao menu principal", callback_data="menu:home")],
        ]
    )


def build_history_actions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🧹 Limpar histórico", callback_data="admin:confirm_clear_history")],
            [InlineKeyboardButton("🔙 Voltar ao menu principal", callback_data="menu:home")],
        ]
    )


def build_quantity_keyboard(action: str) -> InlineKeyboardMarkup:
    icon = "➕" if action == "entrada" else "➖"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(f"{icon}1", callback_data=f"quantidade:{action}:1"),
                InlineKeyboardButton(f"{icon}5", callback_data=f"quantidade:{action}:5"),
                InlineKeyboardButton(f"{icon}10", callback_data=f"quantidade:{action}:10"),
            ],
            [
                InlineKeyboardButton(f"{icon}15", callback_data=f"quantidade:{action}:15"),
                InlineKeyboardButton(f"{icon}30", callback_data=f"quantidade:{action}:30"),
                InlineKeyboardButton(f"{icon}50", callback_data=f"quantidade:{action}:50"),
            ],
            [
                InlineKeyboardButton(
                    "✏️ Inserir valor manualmente",
                    callback_data=f"quantidade:{action}:custom",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 Trocar produto",
                    callback_data=f"flow:{action}:back_to_products",
                ),
                InlineKeyboardButton("🏠 Menu principal", callback_data="menu:home"),
            ],
        ]
    )


def build_ia_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💡 Sugestões automáticas", callback_data="iaeos:sugestoes")],
            [InlineKeyboardButton("📈 Relatórios rápidos", callback_data="iaeos:relatorios")],
            [InlineKeyboardButton("🧾 Resumo semanal", callback_data="iaeos:resumo")],
            [InlineKeyboardButton("🔙 Voltar ao menu principal", callback_data="menu:home")],
        ]
    )


def build_value_keyboard(action: str) -> InlineKeyboardMarkup:
    # Quick unit price suggestions geared towards saída (sales). Still shown for completeness.
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("💵 R$ 9,90", callback_data=f"valor:{action}:9.90"),
                InlineKeyboardButton("💵 R$ 15,90", callback_data=f"valor:{action}:15.90"),
                InlineKeyboardButton("💵 R$ 29,90", callback_data=f"valor:{action}:29.90"),
            ],
            [
                InlineKeyboardButton("💵 R$ 49,90", callback_data=f"valor:{action}:49.90"),
                InlineKeyboardButton("✏️ Personalizar", callback_data=f"valor:{action}:custom"),
            ],
            [
                InlineKeyboardButton(
                    "🔙 Ajustar quantidade",
                    callback_data=f"flow:{action}:back_to_quantity",
                ),
                InlineKeyboardButton("🏠 Menu principal", callback_data="menu:home"),
            ],
        ]
    )


def build_post_movement_keyboard(action: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📈 Ver Estoque", callback_data="menu:estoque"), InlineKeyboardButton("📊 Ver Histórico", callback_data="menu:historico")],
            [
                InlineKeyboardButton(
                    "➕ Registrar nova movimentação",
                    callback_data=f"flow:{action}:restart",
                )
            ],
            [InlineKeyboardButton("🏠 Voltar ao menu principal", callback_data="menu:home")],
        ]
    )


def build_brinde_quantity_keyboard() -> InlineKeyboardMarkup:
    """Quantity chooser for Brindes (always uses plus labels but triggers saída callbacks)."""
    action = "saida"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(f"➕1", callback_data=f"quantidade:{action}:1"),
                InlineKeyboardButton(f"➕5", callback_data=f"quantidade:{action}:5"),
                InlineKeyboardButton(f"➕10", callback_data=f"quantidade:{action}:10"),
            ],
            [
                InlineKeyboardButton(f"➕15", callback_data=f"quantidade:{action}:15"),
                InlineKeyboardButton(f"➕30", callback_data=f"quantidade:{action}:30"),
                InlineKeyboardButton(f"➕50", callback_data=f"quantidade:{action}:50"),
            ],
            [
                InlineKeyboardButton(
                    "✏️ Personalizado",
                    callback_data=f"quantidade:{action}:custom",
                )
            ],
            [
                InlineKeyboardButton(
                    "🔙 Trocar produto",
                    callback_data=f"flow:{action}:back_to_products",
                ),
                InlineKeyboardButton("🏠 Menu principal", callback_data="menu:home"),
            ],
        ]
    )


def build_confirm_clear_keyboard(target: str) -> InlineKeyboardMarkup:
    """Confirmation keyboard for destructive actions.

    target: 'stock' or 'saidas' or 'history'
    """
    if target == "stock":
        do_code = "admin:do_clear_stock"
    elif target == "history":
        do_code = "admin:do_clear_history"
    else:
        do_code = "admin:do_clear_saidas"

    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Confirmar", callback_data=do_code), InlineKeyboardButton("❌ Cancelar", callback_data="admin:cancel")],
            [InlineKeyboardButton("🏠 Menu principal", callback_data="menu:home")],
        ]
    )
