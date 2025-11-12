from __future__ import annotations

import asyncio
import csv
import html
import logging
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from io import StringIO
from typing import Any, Dict, List, Optional, cast

from telegram import InputFile, Message, Update
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from telegram.ext import (
    AIORateLimiter,
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import Settings
from .database import (
    DatabaseError,
    DatabaseManager,
    InsufficientStockError,
    ProductNotFoundError,
)
from .groq_client import GroqClient, GroqClientError
from .keyboards import (
    build_category_keyboard,
    build_history_actions_keyboard,
    build_ia_panel_keyboard,
    build_main_menu,
    build_confirm_clear_keyboard,
    build_post_movement_keyboard,
    build_products_keyboard,
    build_quantity_keyboard,
    build_brinde_quantity_keyboard,
    build_stock_keyboard,
    build_value_keyboard,
)

logger = logging.getLogger(__name__)


CATALOG_LABEL_OVERRIDES: Dict[str, str] = {
    "Café especial moído 250g": "Moído 250g",
    "Café especial moído 1kg": "Moído 1kg",
    "Café especial em grãos 250g": "Grãos 250g",
    "Café especial em grãos 1kg": "Grãos 1kg",
    "Café gourmet clássico 250g": "Clássico 250g",
    "Café gourmet clássico 1kg": "Clássico 1kg",
    "Café gourmet intenso 1kg": "Intenso 1kg",
    "Embalagem 1kg": "Pacote 1kg",
    "Embalagem especial 250g": "Especial 250g",
    "Embalagem gourmet 250g": "Gourmet 250g",
}


def format_quantity(value: Decimal) -> str:
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def format_currency(value: Decimal) -> str:
    quantized = value.quantize(Decimal("0.01"))
    formatted = f"{quantized:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


@dataclass
class UserSession:
    action: Optional[str] = None
    awaiting: Optional[str] = None
    product_id: Optional[int] = None
    category: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EosBot:
    settings: Settings
    db: DatabaseManager = field(init=False)
    groq: GroqClient = field(init=False)
    sessions: Dict[int, UserSession] = field(default_factory=dict, init=False)
    application: Optional[Application] = field(default=None, init=False)

    def __post_init__(self) -> None:
        self.db = DatabaseManager(self.settings)
        self.groq = GroqClient(api_key=self.settings.groq_api_key)

    def _catalog_label(self, name: str) -> str:
        return CATALOG_LABEL_OVERRIDES.get(name, name)

    def _humanize_unit(self, unit: str, quantity: Optional[Decimal] = None) -> str:
        if unit.lower() == "un":
            if quantity is not None and quantity == Decimal("1"):
                return "unidade"
            return "unidades"
        return unit

    def _escape_markdown_v2(self, value: str) -> str:
        return escape_markdown(value, version=2)

    def _strip_accents(self, value: str) -> str:
        normalized = unicodedata.normalize("NFD", value)
        return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")

    def _build_category_intro(self, action: str) -> str:
        if action == "saida":
            return "\n".join(
                [
                    "☕ <b>Escolha a categoria de saída:</b>",
                    "━━━━━━━━━━━━━━━━━━━━━━━",
                    "☕ Cafés",
                    "📦 Embalagens",
                    "🎁 Brindes",
                    "━━━━━━━━━━━━━━━━━━━━━━━",
                    "🔙 Voltar ao Menu Principal",
                ]
            )

        title = "🟢 <b>Entrada de produtos</b>"
        subtitle = "Vamos abastecer o estoque. Escolha por onde começar:"
        body = [
            title,
            "",
            subtitle,
            "",
            "☕ Cafés — blends especiais e gourmets",
            "📦 Embalagens — valorize a apresentação",
            "",
            "Toque no botão desejado abaixo 👇",
        ]
        return "\n".join(body)
        title = "� <b>Entrada de produtos</b>"
        subtitle = "Vamos abastecer o estoque. Escolha por onde começar:".strip()
        body = [
            title,
            "",
            subtitle,
            "",
            "☕ Cafés — blends especiais e gourmets",
            "📦 Embalagens — valorize a apresentação",
            "",
            "Toque no botão desejado abaixo 👇",
        ]
        return "\n".join(body)

    def _pair_labels(self, labels: List[str], icon: str) -> List[str]:
        rows: List[str] = []
        for index in range(0, len(labels), 2):
            left = labels[index]
            right = labels[index + 1] if index + 1 < len(labels) else None
            left_piece = f"{icon} {html.escape(left)}"
            if right:
                row = f"{left_piece}&emsp;{icon} {html.escape(right)}"
            else:
                row = left_piece
            rows.append(row)
        return rows

    def _build_product_showcase(self, category: str, products: List[dict]) -> str:
        if category == "cafes":
            special: List[str] = []
            gourmet: List[str] = []
            others: List[str] = []
            for item in products:
                label = self._catalog_label(item["nome"])
                lowered = item["nome"].lower()
                if "especial" in lowered:
                    special.append(label)
                elif "gourmet" in lowered:
                    gourmet.append(label)
                else:
                    others.append(label)

            lines: List[str] = [
                "☕✨ <b>Escolha o sabor da sua próxima movimentação</b> ✨☕",
                "",
            ]
            if special:
                lines.append("🌿 <b>Linha Especial</b>")
                lines.extend(self._pair_labels(special, "🌱"))
                lines.append("")
            if gourmet:
                lines.append("🍫 <b>Linha Gourmet</b>")
                lines.extend(self._pair_labels(gourmet, "☕"))
                lines.append("")
            if others:
                lines.append("✨ <b>Outros lançamentos</b>")
                lines.extend(self._pair_labels(others, "⭐"))
                lines.append("")

            lines.append("Selecione uma opção nos botões abaixo ou volte quando quiser 🔄")
            return "\n".join(line for line in lines if line is not None)

        # Default showcase for embalagens or demais categorias
        premium: List[str] = []
        classic: List[str] = []
        for item in products:
            label = self._catalog_label(item["nome"])
            lowered = item["nome"].lower()
            if any(keyword in lowered for keyword in ("especial", "gourmet")):
                premium.append(label)
            else:
                classic.append(label)

        lines = ["📦✨ <b>Escolha a embalagem ideal</b> ✨📦", ""]
        if premium:
            lines.append("🎀 <b>Linha Premium</b>")
            lines.extend(self._pair_labels(premium, "🎁"))
            lines.append("")
        if classic:
            lines.append("📦 <b>Linha Clássica</b>")
            lines.extend(self._pair_labels(classic, "📦"))
            lines.append("")

        lines.append("Toque no produto desejado para continuar ou volte quando preferir 🔙")
        return "\n".join(lines)

    def _build_manual_quantity_prompt(self, action: str, product_name: str) -> str:
        action_label = "ENTRADA" if action == "entrada" else "SAÍDA"
        return (
            f"✏️ <b>Informe manualmente a quantidade</b>\n"
            f"Produto selecionado: {html.escape(product_name)}\n\n"
            f"Envie apenas números. Você pode usar vírgula ou ponto para decimais.\n"
            f"Exemplo: 12,5 para registrar uma {action_label.lower()} parcial."
        )

    def _build_quantity_prompt(self, action: str, product: dict) -> str:
        stock = Decimal(product["quantidade"])
        stock_value = format_quantity(stock)
        unit_label = self._humanize_unit(product["unidade"], stock)
        action_label = "ENTRADA" if action == "entrada" else "SAÍDA"
        return (
            f"🏷️ <b>Produto:</b> {html.escape(product['nome'])}\n"
            f"📦 <b>Estoque atual:</b> {stock_value} {unit_label}\n\n"
            f"🎯 Escolha a quantidade de {action_label} 👇"
        )

    def _build_value_prompt(self, product: dict, quantity: Decimal) -> str:
        quantity_value = format_quantity(quantity)
        unit_label = self._humanize_unit(product["unidade"], quantity)
        return (
            f"💰 <b>Informe o valor unitário da movimentação</b>\n"
            f"Para {quantity_value} {unit_label} de {html.escape(product['nome'])}.\n\n"
            "Você pode tocar em um valor rápido abaixo ou digitar manualmente. O total será calculado automaticamente."
        )

    def _stock_ratio(self, quantity: Decimal, max_quantity: Decimal) -> Decimal:
        if max_quantity <= 0:
            return Decimal("0")
        ratio = quantity / max_quantity
        if ratio < Decimal("0"):
            return Decimal("0")
        if ratio > Decimal("1"):
            return Decimal("1")
        return ratio

    def _stock_progress_bar(self, ratio: Decimal) -> str:
        ratio = max(Decimal("0"), min(Decimal("1"), ratio))
        filled = int((ratio * Decimal("10")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        filled = max(0, min(10, filled))
        return "█" * filled + "░" * (10 - filled)

    def _stock_status_icon(self, quantity: Decimal, ratio: Decimal) -> str:
        if quantity <= 0:
            return "🔴"
        if ratio >= Decimal("0.7"):
            return "🟢"
        if ratio >= Decimal("0.35"):
            return "🟡"
        return "🔴"

    def _stock_item_icon(self, item: dict) -> str:
        category = item.get("categoria", "")
        base_icon = "☕" if category == "cafes" else "📦"
        name = item.get("nome", "")
        normalized = self._strip_accents(name).lower()

        if "intenso" in normalized:
            return "🔥"
        if "classico" in normalized:
            return "🍫"
        if "moido" in normalized:
            return "🍃"
        if "grao" in normalized:
            return "🌿"
        if "lote" in normalized:
            return "🌱"
        if category != "cafes" and "especial" in normalized:
            return "🎀"
        return base_icon

    def _format_stock_line(self, item: dict, *, max_quantity: Decimal) -> str:
        name = self._catalog_label(item["nome"])
        icon = self._stock_item_icon(item)
        quantity = Decimal(item["quantidade"])
        ratio = self._stock_ratio(quantity, max_quantity)
        status = self._stock_status_icon(quantity, ratio)
        bar = self._stock_progress_bar(ratio)
        quantity_text = self._escape_markdown_v2(format_quantity(quantity))
        unit = item.get("unidade", "").strip()
        spacer = "\u2003"
        unit_suffix = f" {self._escape_markdown_v2(unit)}" if unit else ""
        name_md = self._escape_markdown_v2(name)
        return f"{icon} {name_md}{spacer}{status} \\[{bar}\\] {quantity_text}{unit_suffix}"

    def _render_stock_overview(self, overview: List[dict]) -> str:
        if not overview:
            return (
                f"{self._escape_markdown_v2('⚡️  Status de Estoque ⚡️')}\n\n"
                f"{self._escape_markdown_v2('📅 Atualizado em: sem registros')}\n"
                f"{self._escape_markdown_v2('━━━━━━━━━━━━━━━━━━━━━━━')}\n\n"
                f"{self._escape_markdown_v2('Nenhum produto cadastrado')}"
            )

        timestamp = datetime.now().strftime("%d/%m — %H:%M")
        cafes = [item for item in overview if item.get("categoria") == "cafes"]
        others = [item for item in overview if item.get("categoria") != "cafes"]

        cafes_max = max((Decimal(item["quantidade"]) for item in cafes), default=Decimal("0")) or Decimal("1")
        others_max = max((Decimal(item["quantidade"]) for item in others), default=Decimal("0")) or Decimal("1")

        lines: List[str] = [
            self._escape_markdown_v2("⚡️  Status de Estoque ⚡️"),
            "",
            f"{self._escape_markdown_v2('📅 Atualizado em:')} {self._escape_markdown_v2(timestamp)}",
            self._escape_markdown_v2("━━━━━━━━━━━━━━━━━━━━━━━"),
            "",
            self._escape_markdown_v2("☕️ Cafés Torrados e Moídos"),
        ]

        if cafes:
            for item in sorted(cafes, key=lambda i: self._catalog_label(i["nome"])):
                lines.append(self._format_stock_line(item, max_quantity=cafes_max))
        else:
            lines.append(self._escape_markdown_v2("Nenhum item disponível"))

        lines.append("")
        lines.append(self._escape_markdown_v2("📦 Embalagens e Matérias-Primas"))

        if others:
            for item in sorted(others, key=lambda i: self._catalog_label(i["nome"])):
                lines.append(self._format_stock_line(item, max_quantity=others_max))
        else:
            lines.append(self._escape_markdown_v2("Nenhum item disponível"))

        return "\n".join(lines)

    async def _show_quantity_prompt(
        self,
        *,
        session: UserSession,
        product: dict,
        context: ContextTypes.DEFAULT_TYPE,
        message: Optional[Message],
        chat_id: int,
    ) -> None:
        action = session.action or ""
        session.awaiting = "quantity_choice"
        session.metadata["product_name"] = product["nome"]
        session.metadata["product_unit"] = product["unidade"]
        session.metadata["product_price"] = product.get("preco")
        session.metadata["product_stock"] = str(product.get("quantidade", "0"))

        prompt = self._build_quantity_prompt(action, product)
        keyboard = build_brinde_quantity_keyboard() if session.metadata.get("is_brinde") else build_quantity_keyboard(action)

        if message:
            await self._edit_with_typing(
                message,
                context,
                prompt,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
                session=session,
            )
        else:
            await self._ensure_typing(context=context, chat_id=chat_id)
            sent = await context.bot.send_message(
                chat_id=chat_id,
                text=prompt,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
            self._store_message_reference(session, sent)

    async def _show_category_prompt(
        self,
        *,
        session: UserSession,
        context: ContextTypes.DEFAULT_TYPE,
        message: Optional[Message],
        chat_id: int,
    ) -> None:
        action = session.action or "entrada"
        session.awaiting = "category"
        session.category = None
        session.metadata.pop("pending_quantity", None)
        intro = self._build_category_intro(action)
        keyboard = build_category_keyboard(action)

        if message:
            await self._edit_with_typing(
                message,
                context,
                intro,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
                session=session,
            )
        else:
            await self._ensure_typing(context=context, chat_id=chat_id)
            sent = await context.bot.send_message(
                chat_id=chat_id,
                text=intro,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
    async def _show_products_prompt(
        self,
        *,
        session: UserSession,
        context: ContextTypes.DEFAULT_TYPE,
        message: Optional[Message],
        chat_id: int,
    ) -> None:
        action = session.action or "entrada"
        session.metadata.pop("pending_quantity", None)
        if not session.category:
            await self._show_category_prompt(session=session, context=context, message=message, chat_id=chat_id)
            return

        products = await self.db.fetch_products_by_category(session.category)
        if not products:
            info = (
                "📭 Ainda não há produtos nessa categoria.\n"
                "Escolha outra opção a seguir."
            )
            edited = await self._edit_session_message(
                context,
                session,
                info,
                reply_markup=build_main_menu(),
                parse_mode=ParseMode.HTML,
            )
            if edited is None:
                await self._ensure_typing(context=context, chat_id=chat_id)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=info,
                    reply_markup=build_main_menu(),
                    parse_mode=ParseMode.HTML,
                )
            self.sessions.pop(chat_id, None)
            return

        session.awaiting = "product"
        session.metadata["category_label"] = "☕ Cafés" if session.category == "cafes" else "📦 Embalagens"
        showcase = self._build_product_showcase(session.category, products)
        keyboard = build_products_keyboard(action, products, category=session.category)

        if message:
            await self._edit_with_typing(
                message,
                context,
                showcase,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
                session=session,
            )
        else:
            await self._ensure_typing(context=context, chat_id=chat_id)
            sent = await context.bot.send_message(
                chat_id=chat_id,
                text=showcase,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
            self._store_message_reference(session, sent)

    async def _handle_confirmed_quantity(
        self,
        *,
        session: UserSession,
        product: dict,
        quantity: Decimal,
        context: ContextTypes.DEFAULT_TYPE,
        message: Optional[Message],
        chat_id: int,
    ) -> None:
        action = session.action or ""

        if quantity <= 0:
            session.awaiting = "quantity_choice"
            warn = "A quantidade precisa ser maior que zero. Tente novamente."
            keyboard = build_quantity_keyboard(action)
            if message:
                await self._edit_with_typing(
                    message,
                    context,
                    warn,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML,
                    session=session,
                )
            else:
                edited = await self._edit_session_message(
                    context,
                    session,
                    warn,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML,
                )
                if edited is None:
                    await self._ensure_typing(context=context, chat_id=chat_id)
                    sent = await context.bot.send_message(
                        chat_id=chat_id,
                        text=warn,
                        reply_markup=keyboard,
                        parse_mode=ParseMode.HTML,
                    )
                    self._store_message_reference(session, sent)
            return

        if action == "saida":
            available = Decimal(product["quantidade"])
            if quantity > available:
                session.awaiting = "quantity_choice"
                available_text = format_quantity(available)
                unit_label = self._humanize_unit(product["unidade"], available)
                warn = (
                    "😕 Estoque insuficiente para essa saída.\n"
                    f"📦 Disponível: {available_text} {unit_label}.\n"
                    "Ajuste a quantidade abaixo."
                )
                keyboard = build_brinde_quantity_keyboard() if session.metadata.get("is_brinde") else build_quantity_keyboard(action)
                if message:
                    await self._edit_with_typing(
                        message,
                        context,
                        warn,
                        reply_markup=keyboard,
                        parse_mode=ParseMode.HTML,
                        session=session,
                    )
                else:
                    edited = await self._edit_session_message(
                        context,
                        session,
                        warn,
                        reply_markup=keyboard,
                        parse_mode=ParseMode.HTML,
                    )
                    if edited is None:
                        await self._ensure_typing(context=context, chat_id=chat_id)
                        sent = await context.bot.send_message(
                            chat_id=chat_id,
                            text=warn,
                            reply_markup=keyboard,
                            parse_mode=ParseMode.HTML,
                        )
                        self._store_message_reference(session, sent)
                return
            # Brinde: aplicar saída com valor 0,00 diretamente
            if session.metadata.get("is_brinde"):
                session.awaiting = None
                await self._apply_stock_movement(
                    session=session,
                    user_id=chat_id,
                    product=product,
                    quantity=quantity,
                    context=context,
                    total_value=Decimal("0.00"),
                    unit_price=Decimal("0.00"),
                )
                return

            session.metadata["pending_quantity"] = str(quantity)
            session.awaiting = "saida_value"
            value_prompt = self._build_value_prompt(product, quantity)
            value_keyboard = build_value_keyboard(action)
            if message:
                await self._edit_with_typing(
                    message,
                    context,
                    value_prompt,
                    reply_markup=value_keyboard,
                    parse_mode=ParseMode.HTML,
                    session=session,
                )
            else:
                edited = await self._edit_session_message(
                    context,
                    session,
                    value_prompt,
                    reply_markup=value_keyboard,
                    parse_mode=ParseMode.HTML,
                )
                if edited is None:
                    await self._ensure_typing(context=context, chat_id=chat_id)
                    sent = await context.bot.send_message(
                        chat_id=chat_id,
                        text=value_prompt,
                        reply_markup=value_keyboard,
                        parse_mode=ParseMode.HTML,
                    )
                    self._store_message_reference(session, sent)
            return

        # Entrada
        session.awaiting = None
        await self._apply_stock_movement(
            session=session,
            user_id=chat_id,
            product=product,
            quantity=quantity,
            context=context,
            total_value=None,
        )
    def _store_message_reference(self, session: UserSession, message: Message) -> None:
        session.metadata["last_message_id"] = message.message_id
        session.metadata["last_message_chat_id"] = message.chat_id

    async def _ensure_typing(
        self,
        *,
        message: Optional[Message] = None,
        context: Optional[ContextTypes.DEFAULT_TYPE] = None,
        chat_id: Optional[int] = None,
    ) -> None:
        if message is not None:
            method = getattr(message, "answer_chat_action", None)
            if callable(method):  # type: ignore[misc]
                await method("typing")  # type: ignore[call-arg]
                return  # type: ignore[unreachable]

        if context is not None:
            cid = chat_id or (message.chat_id if message else None)
            if cid is not None:
                await context.bot.send_chat_action(chat_id=cid, action="typing")

    async def _reply_with_typing(
        self,
        message: Message,
        context: ContextTypes.DEFAULT_TYPE,
        text: str,
        *,
        reply_markup=None,
        parse_mode: Optional[str] = None,
        session: Optional[UserSession] = None,
    ) -> Message:
        await self._ensure_typing(message=message, context=context)
        sent = await message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        if session is not None:
            self._store_message_reference(session, sent)
        return sent

    async def _edit_with_typing(
        self,
        message: Message,
        context: ContextTypes.DEFAULT_TYPE,
        text: str,
        *,
        reply_markup=None,
        parse_mode: Optional[str] = None,
        session: Optional[UserSession] = None,
    ) -> Message:
        await self._ensure_typing(message=message, context=context)
        updated = cast(
            Message,
            await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode),
        )
        if session is not None:
            self._store_message_reference(session, updated)
        return updated

    async def _edit_session_message(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        session: UserSession,
        text: str,
        *,
        reply_markup=None,
        parse_mode: Optional[str] = None,
    ) -> Optional[Message]:
        chat_id = session.metadata.get("last_message_chat_id")
        message_id = session.metadata.get("last_message_id")
        if chat_id is None or message_id is None:
            return None

        await self._ensure_typing(context=context, chat_id=chat_id)
        updated = cast(
            Message,
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
            ),
        )
        self._store_message_reference(session, updated)
        return updated

    async def run(self) -> None:
        await self.db.ensure_schema()
        await self.db.seed_products()

        self.application = (
            ApplicationBuilder()
            .token(self.settings.telegram_token)
            .rate_limiter(AIORateLimiter())
            .build()
        )

        self._register_handlers(self.application)

        await self.application.initialize()
        await self.application.start()

        updater = self.application.updater
        if updater is None:
            raise RuntimeError("Aplicação foi construída sem Updater para polling.")

        await updater.start_polling()
        logger.info("Bot da Eos Cafés Especiais iniciado.")
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            logger.info("Encerrando bot...")
        finally:
            await updater.stop()
            await self.application.stop()
            await self.application.shutdown()

    def _register_handlers(self, application: Application) -> None:
        application.add_handler(CommandHandler("start", self.handle_start))
        application.add_handler(CommandHandler("estoque", self.handle_estoque_command))
        application.add_handler(CommandHandler("entrada", self.handle_entrada_command))
        application.add_handler(CommandHandler("saida", self.handle_saida_command))
        application.add_handler(CommandHandler("historico", self.handle_historico_command))
        application.add_handler(CommandHandler("historicoSaida", self.handle_historico_command))
        application.add_handler(CommandHandler("IAEos", self.handle_iaeos_command))

        application.add_handler(CallbackQueryHandler(self.handle_menu_selection, pattern=r"^menu:"))
        application.add_handler(CallbackQueryHandler(self.handle_category_selection, pattern=r"^categoria:"))
        application.add_handler(CallbackQueryHandler(self.handle_product_selection, pattern=r"^produto:"))
        application.add_handler(CallbackQueryHandler(self.handle_quantity_selection, pattern=r"^quantidade:"))
        application.add_handler(CallbackQueryHandler(self.handle_flow_navigation, pattern=r"^flow:"))
        application.add_handler(CallbackQueryHandler(self.handle_value_selection, pattern=r"^valor:"))
        application.add_handler(CallbackQueryHandler(self.handle_admin_actions, pattern=r"^admin:"))
        application.add_handler(CallbackQueryHandler(self.handle_ia_panel_selection, pattern=r"^iaeos:"))

        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        self.sessions.pop(user_id, None)
        await self._reply_with_typing(
            update.message,
            context,
            "Olá 👋 Bem-vindo ao seu painel de controle do Café!\nEscolha uma das opções abaixo para começar ⬇️",
            reply_markup=build_main_menu(),
        )

    async def handle_estoque_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        await self._send_estoque(update, context)

    async def handle_entrada_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        await self._start_stock_flow(update, context, action="entrada")

    async def handle_saida_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        await self._start_stock_flow(update, context, action="saida")

    async def handle_historico_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        await self._send_historico(update, context)

    async def handle_iaeos_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        await self._start_iaeos(update, context)

    async def handle_menu_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not query.from_user or not query.data:
            return

        await query.answer()
        user_id = query.from_user.id
        action = query.data.split(":", maxsplit=1)[1]
        message = query.message if isinstance(query.message, Message) else None

        if action == "home":
            self.sessions.pop(user_id, None)
            if message:
                await self._edit_with_typing(
                    message,
                    context,
                    "Olá 👋 Bem-vindo ao seu painel de controle do Café!\nEscolha uma das opções abaixo para começar ⬇️",
                    reply_markup=build_main_menu(),
                )
            return

        if action == "estoque":
            await self._send_estoque(update, context, from_callback=True)
            return
        if action == "entrada":
            await self._start_stock_flow(update, context, action="entrada", from_callback=True)
            return
        if action == "saida":
            await self._start_stock_flow(update, context, action="saida", from_callback=True)
            return
        if action == "historico":
            await self._send_historico(update, context, from_callback=True)
            return
        if action == "iaeos":
            await self._start_iaeos(update, context, from_callback=True)

    async def handle_category_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not query.from_user or not query.data:
            return

        await query.answer()
        try:
            _, action, category = query.data.split(":", maxsplit=2)
        except ValueError:
            return

        user_id = query.from_user.id
        session = self.sessions.get(user_id)
        if session is None:
            session = UserSession(action=action, awaiting="category")
            self.sessions[user_id] = session
        else:
            session.action = action
            session.awaiting = "category"

        session.category = category
        message = query.message if isinstance(query.message, Message) else None

        if action not in {"entrada", "saida"}:
            warning = "Use o menu principal para iniciar uma movimentação válida ☕"
            if message:
                await self._edit_with_typing(
                    message,
                    context,
                    warning,
                    reply_markup=build_main_menu(),
                )
            else:
                await self._ensure_typing(context=context, chat_id=user_id)
                await context.bot.send_message(
                    chat_id=user_id,
                    text=warning,
                    reply_markup=build_main_menu(),
                )
            self.sessions.pop(user_id, None)
            return

        if action == "saida" and category == "brindes":
            # Novo fluxo de BRINDES: lista cafés, registra saída com valor zero
            session.metadata["is_brinde"] = True
            session.category = "cafes"
            products = await self.db.fetch_products_by_category("cafes")
            if not products:
                info = (
                    "📭 Ainda não há cafés cadastrados para brinde.\n"
                    "Use o menu para outra ação."
                )
                if message:
                    await self._edit_with_typing(
                        message,
                        context,
                        info,
                        reply_markup=build_main_menu(),
                        parse_mode=ParseMode.HTML,
                    )
                else:
                    await self._ensure_typing(context=context, chat_id=query.from_user.id)
                    sent = await context.bot.send_message(
                        chat_id=query.from_user.id,
                        text=info,
                        reply_markup=build_main_menu(),
                        parse_mode=ParseMode.HTML,
                    )
                    self._store_message_reference(session, sent)
                self.sessions.pop(user_id, None)
                return

            session.awaiting = "product"
            session.metadata["category_label"] = "🎁 Brindes — Cafés"
            showcase = self._build_product_showcase("cafes", products)
            keyboard = build_products_keyboard("saida", products, category="cafes")
            if message:
                await self._edit_with_typing(
                    message,
                    context,
                    showcase,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML,
                    session=session,
                )
            else:
                await self._ensure_typing(context=context, chat_id=query.from_user.id)
                sent = await context.bot.send_message(
                    chat_id=query.from_user.id,
                    text=showcase,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.HTML,
                )
                self._store_message_reference(session, sent)
            return

        products = await self.db.fetch_products_by_category(category)

        if not products:
            info = (
                "📭 Ainda não há produtos nessa categoria.\n"
                "Selecione outra opção no menu principal."
            )
            if message:
                await self._edit_with_typing(
                    message,
                    context,
                    info,
                    reply_markup=build_main_menu(),
                    parse_mode=ParseMode.HTML,
                )
            else:
                await self._ensure_typing(context=context, chat_id=query.from_user.id)
                sent = await context.bot.send_message(
                    chat_id=query.from_user.id,
                    text=info,
                    reply_markup=build_main_menu(),
                    parse_mode=ParseMode.HTML,
                )
                self._store_message_reference(session, sent)
            self.sessions.pop(user_id, None)
            return

        session.awaiting = "product"
        session.metadata["category_label"] = "☕ Cafés" if category == "cafes" else "📦 Embalagens"
        showcase = self._build_product_showcase(category, products)
        keyboard = build_products_keyboard(action, products, category=category)

        if message:
            await self._edit_with_typing(
                message,
                context,
                showcase,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
                session=session,
            )
        else:
            await self._ensure_typing(context=context, chat_id=query.from_user.id)
            sent = await context.bot.send_message(
                chat_id=query.from_user.id,
                text=showcase,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
            )
            self._store_message_reference(session, sent)

    async def handle_product_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not query.from_user or not query.data:
            return

        await query.answer()
        try:
            _, action, product_id_str = query.data.split(":", maxsplit=2)
        except ValueError:
            return

        user_id = query.from_user.id
        session = self.sessions.get(user_id)
        if session is None:
            session = UserSession(action=action, awaiting="product")
            self.sessions[user_id] = session
        else:
            session.action = action

        if session.action not in {"entrada", "saida"}:
            message = query.message
            if isinstance(message, Message):
                await self._edit_with_typing(
                    message,
                    context,
                    "Use o menu principal para iniciar uma movimentação de estoque ☕",
                    reply_markup=build_main_menu(),
                )
            self.sessions.pop(user_id, None)
            return

        session.product_id = int(product_id_str)
        product = await self.db.get_product(session.product_id)
        if not product:
            message = query.message
            if isinstance(message, Message):
                await self._edit_with_typing(
                    message,
                    context,
                    "Produto não encontrado. Vamos voltar ao menu principal ☕",
                    reply_markup=build_main_menu(),
                )
            self.sessions.pop(user_id, None)
            return

        message = query.message if isinstance(query.message, Message) else None
        await self._show_quantity_prompt(
            session=session,
            product=product,
            context=context,
            message=message,
            chat_id=query.from_user.id,
        )

    async def handle_quantity_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not query.from_user or not query.data:
            return

        await query.answer()
        parts = query.data.split(":", maxsplit=2)
        if len(parts) != 3:
            return

        _, action, value = parts
        user_id = query.from_user.id
        session = self.sessions.get(user_id)

        if session is None or session.product_id is None:
            message = query.message
            if isinstance(message, Message):
                await self._edit_with_typing(
                    message,
                    context,
                    "Vamos começar novamente pelo menu principal ☕",
                    reply_markup=build_main_menu(),
                )
            self.sessions.pop(user_id, None)
            return

        session.action = action
        product = await self.db.get_product(session.product_id)
        if not product:
            edited = await self._edit_session_message(
                context,
                session,
                "Não encontrei o produto selecionado. Voltando ao menu principal ☕",
                reply_markup=build_main_menu(),
            )
            fallback_message = query.message if isinstance(query.message, Message) else None
            if edited is None and fallback_message:
                await self._edit_with_typing(
                    fallback_message,
                    context,
                    "Não encontrei o produto selecionado. Voltando ao menu principal ☕",
                    reply_markup=build_main_menu(),
                )
            self.sessions.pop(user_id, None)
            return

        message = query.message if isinstance(query.message, Message) else None

        if value == "custom":
            session.awaiting = "quantity_manual"
            prompt = self._build_manual_quantity_prompt(action, product["nome"])
            if message:
                await self._edit_with_typing(
                    message,
                    context,
                    prompt,
                    parse_mode=ParseMode.HTML,
                    session=session,
                )
            else:
                await self._ensure_typing(context=context, chat_id=query.from_user.id)
                sent = await context.bot.send_message(
                    chat_id=query.from_user.id,
                    text=prompt,
                    parse_mode=ParseMode.HTML,
                )
                self._store_message_reference(session, sent)
            return

        try:
            quantity = Decimal(value)
        except InvalidOperation:
            await query.answer("Quantidade inválida", show_alert=True)
            return

        await self._handle_confirmed_quantity(
            session=session,
            product=product,
            quantity=quantity,
            context=context,
            message=message,
            chat_id=user_id,
        )

    async def handle_flow_navigation(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not query.from_user or not query.data:
            return

        await query.answer()
        parts = query.data.split(":", maxsplit=2)
        if len(parts) < 3:
            return

        _, action, command = parts
        user_id = query.from_user.id
        session = self.sessions.get(user_id)
        if session is None:
            session = UserSession(action=action)
            self.sessions[user_id] = session
        else:
            session.action = action

        message = query.message if isinstance(query.message, Message) else None

        if command == "back_to_categories":
            await self._show_category_prompt(
                session=session,
                context=context,
                message=message,
                chat_id=user_id,
            )
            return

        if command == "back_to_products":
            await self._show_products_prompt(
                session=session,
                context=context,
                message=message,
                chat_id=user_id,
            )
            return

        if command == "back_to_quantity":
            if session.product_id is None:
                await self._show_products_prompt(
                    session=session,
                    context=context,
                    message=message,
                    chat_id=user_id,
                )
                return

            product = await self.db.get_product(session.product_id)
            if not product:
                await self._show_products_prompt(
                    session=session,
                    context=context,
                    message=message,
                    chat_id=user_id,
                )
                return

            await self._show_quantity_prompt(
                session=session,
                product=product,
                context=context,
                message=message,
                chat_id=user_id,
            )
            return

        if command == "restart":
            await self._start_stock_flow(update, context, action=action, from_callback=True)
            return

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return

        user_id = update.effective_user.id
        session = self.sessions.get(user_id)

        if not session:
            await self._reply_with_typing(
                update.message,
                context,
                "Não entendi. Use o menu principal para escolher uma ação ☕",
                reply_markup=build_main_menu(),
            )
            return

        if (
            session.action in {"entrada", "saida"}
            and session.awaiting in {"quantity_choice", "quantity_manual"}
        ):
            await self._process_quantity(update, context, session)
            return

        if session.action == "saida" and session.awaiting == "saida_value":
            await self._process_saida_value(update, context, session)
            return

        if session.awaiting == "brinde_description":
            await self._process_brinde_description(update, context, session)
            return

        if session.action == "iaeos" and session.awaiting == "iaeos_question":
            await self._process_iaeos_question(update, context)
            return

        await self._reply_with_typing(
            update.message,
            context,
            "Vamos recomeçar? Escolha uma opção no menu principal ☕",
            reply_markup=build_main_menu(),
        )
        self.sessions.pop(user_id, None)

    async def _start_stock_flow(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        *,
        action: str,
        from_callback: bool = False,
    ) -> None:
        if not update.effective_user:
            return

        user_id = update.effective_user.id
        session = UserSession(action=action, awaiting="category")
        self.sessions[user_id] = session

        menu_text = self._build_category_intro(action)

        reply_markup = build_category_keyboard(action)

        if from_callback:
            query = update.callback_query
            if not query:
                return
            message = query.message
            if isinstance(message, Message):
                await self._edit_with_typing(
                    message,
                    context,
                    menu_text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML,
                    session=session,
                )
        else:
            message = update.message
            if message:
                await self._reply_with_typing(
                    message,
                    context,
                    menu_text,
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.HTML,
                    session=session,
                )

    async def _process_quantity(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        session: UserSession,
    ) -> None:
        user = update.effective_user
        if not user:
            return

        message_text = update.message.text if update.message else None
        if message_text is None:
            session.awaiting = "quantity_manual"
            notice = "Não recebi nenhum número. Digite novamente a quantidade desejada ☕"
            edited = await self._edit_session_message(
                context,
                session,
                notice,
                parse_mode=ParseMode.HTML,
            )
            if edited is None and update.message:
                await self._reply_with_typing(
                    update.message,
                    context,
                    notice,
                    parse_mode=ParseMode.HTML,
                    session=session,
                )
            return

        raw_value = message_text.strip().replace(",", ".")

        try:
            quantity = Decimal(raw_value)
        except InvalidOperation:
            session.awaiting = "quantity_manual"
            warn = (
                "Não entendi 🤔 Digite um número válido usando apenas números, vírgula ou ponto."
            )
            edited = await self._edit_session_message(
                context,
                session,
                warn,
                parse_mode=ParseMode.HTML,
            )
            if edited is None and update.message:
                await self._reply_with_typing(
                    update.message,
                    context,
                    warn,
                    parse_mode=ParseMode.HTML,
                    session=session,
                )
            return

        if quantity <= 0:
            session.awaiting = "quantity_manual"
            warn = "A quantidade precisa ser maior que zero. Tente novamente ☕"
            edited = await self._edit_session_message(
                context,
                session,
                warn,
                parse_mode=ParseMode.HTML,
            )
            if edited is None and update.message:
                await self._reply_with_typing(
                    update.message,
                    context,
                    warn,
                    parse_mode=ParseMode.HTML,
                    session=session,
                )
            return

        if session.product_id is None:
            fallback = "Produto não identificado. Voltando ao menu principal ☕"
            edited = await self._edit_session_message(
                context,
                session,
                fallback,
                reply_markup=build_main_menu(),
                parse_mode=ParseMode.HTML,
            )
            if edited is None and update.message:
                await self._reply_with_typing(
                    update.message,
                    context,
                    fallback,
                    reply_markup=build_main_menu(),
                    parse_mode=ParseMode.HTML,
                    session=session,
                )
            self.sessions.pop(user.id, None)
            return

        product = await self.db.get_product(session.product_id)
        if not product:
            fallback = "Produto não encontrado. Vamos recomeçar pelo menu principal ☕"
            edited = await self._edit_session_message(
                context,
                session,
                fallback,
                reply_markup=build_main_menu(),
                parse_mode=ParseMode.HTML,
            )
            if edited is None and update.message:
                await self._reply_with_typing(
                    update.message,
                    context,
                    fallback,
                    reply_markup=build_main_menu(),
                    parse_mode=ParseMode.HTML,
                    session=session,
                )
            self.sessions.pop(user.id, None)
            return

        await self._handle_confirmed_quantity(
            session=session,
            product=product,
            quantity=quantity,
            context=context,
            message=None,
            chat_id=user.id,
        )

    async def _process_saida_value(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        session: UserSession,
    ) -> None:
        if not update.message or update.message.text is None or not update.effective_user:
            return

        message_text = update.message.text.strip().replace(",", ".")
        try:
            unit_price = Decimal(message_text)
        except InvalidOperation:
            warn = "Não consegui entender o valor. Envie apenas números, com vírgula ou ponto nos centavos."
            session.awaiting = "saida_value"
            edited = await self._edit_session_message(
                context,
                session,
                warn,
                parse_mode=ParseMode.HTML,
            )
            if edited is None:
                await self._reply_with_typing(
                    update.message,
                    context,
                    warn,
                    parse_mode=ParseMode.HTML,
                    session=session,
                )
            return

        if unit_price <= 0:
            warn = "O valor precisa ser maior que zero. Informe novamente, por favor."
            session.awaiting = "saida_value"
            edited = await self._edit_session_message(
                context,
                session,
                warn,
                parse_mode=ParseMode.HTML,
            )
            if edited is None:
                await self._reply_with_typing(
                    update.message,
                    context,
                    warn,
                    parse_mode=ParseMode.HTML,
                    session=session,
                )
            return

        quantity_raw = session.metadata.get("pending_quantity")
        if quantity_raw is None:
            fallback = "Não encontrei a quantidade selecionada. Vamos começar novamente pelo menu principal."
            await self._reply_with_typing(
                update.message,
                context,
                fallback,
                reply_markup=build_main_menu(),
                parse_mode=ParseMode.HTML,
                session=session,
            )
            self.sessions.pop(update.effective_user.id, None)
            return

        try:
            quantity = Decimal(quantity_raw)
        except InvalidOperation:
            fallback = "Não consegui confirmar a quantidade anterior. Vamos reiniciar o processo."
            await self._reply_with_typing(
                update.message,
                context,
                fallback,
                reply_markup=build_main_menu(),
                parse_mode=ParseMode.HTML,
                session=session,
            )
            self.sessions.pop(update.effective_user.id, None)
            return

        product_id = session.product_id
        if product_id is None:
            fallback = "Produto não identificado. Voltando ao menu principal ☕"
            await self._reply_with_typing(
                update.message,
                context,
                fallback,
                reply_markup=build_main_menu(),
                parse_mode=ParseMode.HTML,
                session=session,
            )
            self.sessions.pop(update.effective_user.id, None)
            return

        product = await self.db.get_product(product_id)
        if not product:
            fallback = "Produto não encontrado. Vamos recomeçar pelo menu principal ☕"
            await self._reply_with_typing(
                update.message,
                context,
                fallback,
                reply_markup=build_main_menu(),
                parse_mode=ParseMode.HTML,
                session=session,
            )
            self.sessions.pop(update.effective_user.id, None)
            return

        session.awaiting = None
        total_value = (quantity * unit_price).quantize(Decimal("0.01"))
        await self._apply_stock_movement(
            session=session,
            user_id=update.effective_user.id,
            product=product,
            quantity=quantity,
            context=context,
            total_value=total_value,
            unit_price=unit_price,
        )

    async def _apply_stock_movement(
        self,
        *,
        session: UserSession,
        user_id: int,
        product: dict,
        quantity: Decimal,
        context: ContextTypes.DEFAULT_TYPE,
        total_value: Optional[Decimal] = None,
        unit_price: Optional[Decimal] = None,
    ) -> None:
        action = session.action
        if action not in {"entrada", "saida"}:
            warning = "Não identifiquei o tipo de movimentação. Voltando ao menu principal ☕"
            edited = await self._edit_session_message(
                context,
                session,
                warning,
                reply_markup=build_main_menu(),
                parse_mode=ParseMode.HTML,
            )
            if edited is None:
                await self._ensure_typing(context=context, chat_id=user_id)
                await context.bot.send_message(
                    chat_id=user_id,
                    text=warning,
                    reply_markup=build_main_menu(),
                    parse_mode=ParseMode.HTML,
                )
            self.sessions.pop(user_id, None)
            return

        product_id = session.product_id
        if product_id is None:
            fallback = "Produto não identificado. Voltando ao menu principal ☕"
            edited = await self._edit_session_message(
                context,
                session,
                fallback,
                reply_markup=build_main_menu(),
                parse_mode=ParseMode.HTML,
            )
            if edited is None:
                await self._ensure_typing(context=context, chat_id=user_id)
                await context.bot.send_message(
                    chat_id=user_id,
                    text=fallback,
                    reply_markup=build_main_menu(),
                    parse_mode=ParseMode.HTML,
                )
            self.sessions.pop(user_id, None)
            return

        observacao = "Movimentação registrada via bot Telegram"
        is_brinde = bool(session.metadata.get("is_brinde"))
        if action == "saida":
            if unit_price is not None:
                observacao += f" | Valor unitário: {format_currency(unit_price)}"
            if total_value is not None:
                observacao += f" | Total: {format_currency(total_value)}"
            if is_brinde:
                observacao = "[BRINDE] " + observacao

        try:
            new_quantity = await self.db.adjust_stock(
                product_id=product_id,
                movement_type=action,
                quantity=quantity,
                valor_unitario=(unit_price if action == "saida" else None),
                observacao=observacao,
            )
        except InsufficientStockError:
            session.awaiting = "quantity_choice"
            available = format_quantity(Decimal(product["quantidade"]))
            unit_label = self._humanize_unit(product["unidade"], Decimal(product["quantidade"]))
            warn = (
                "😕 Estoque insuficiente para essa saída.\n"
                f"📦 Disponível: {available} {unit_label}.\n"
                "Ajuste a quantidade usando os botões abaixo."
            )
            edited = await self._edit_session_message(
                context,
                session,
                warn,
                reply_markup=(build_brinde_quantity_keyboard() if session.metadata.get("is_brinde") else build_quantity_keyboard(action)),
                parse_mode=ParseMode.HTML,
            )
            if edited is None:
                await self._ensure_typing(context=context, chat_id=user_id)
                sent = await context.bot.send_message(
                    chat_id=user_id,
                    text=warn,
                    reply_markup=(build_brinde_quantity_keyboard() if session.metadata.get("is_brinde") else build_quantity_keyboard(action)),
                    parse_mode=ParseMode.HTML,
                )
                self._store_message_reference(session, sent)
            return
        except ProductNotFoundError:
            fallback = "Produto não encontrado. Voltando ao menu principal ☕"
            edited = await self._edit_session_message(
                context,
                session,
                fallback,
                reply_markup=build_main_menu(),
                parse_mode=ParseMode.HTML,
            )
            if edited is None:
                await self._ensure_typing(context=context, chat_id=user_id)
                await context.bot.send_message(
                    chat_id=user_id,
                    text=fallback,
                    reply_markup=build_main_menu(),
                    parse_mode=ParseMode.HTML,
                )
            self.sessions.pop(user_id, None)
            return
        except DatabaseError:
            logger.exception("Erro ao ajustar estoque")
            fallback = "Tivemos um problema ao registrar a movimentação. Tente novamente em instantes."
            edited = await self._edit_session_message(
                context,
                session,
                fallback,
                parse_mode=ParseMode.HTML,
            )
            if edited is None:
                await self._ensure_typing(context=context, chat_id=user_id)
                await context.bot.send_message(
                    chat_id=user_id,
                    text=fallback,
                    parse_mode=ParseMode.HTML,
                )
            return

        session.metadata["product_stock"] = str(new_quantity)
        session.metadata.pop("pending_quantity", None)
        session.awaiting = None

        quantity_label = self._humanize_unit(product["unidade"], quantity)
        new_stock_label = self._humanize_unit(product["unidade"], Decimal(new_quantity))
        quantity_value = format_quantity(quantity)
        new_stock_value = format_quantity(new_quantity)

        if action == "entrada":
            header = "✅ Entrada registrada com sucesso!"
            details = [
                header,
                f"📦 <b>Produto:</b> {html.escape(product['nome'])}",
                f"➕ <b>Quantidade:</b> {quantity_value} {quantity_label}",
                f"📦 <b>Novo estoque:</b> {new_stock_value} {new_stock_label}",
            ]
        else:
            is_brinde = bool(session.metadata.get("is_brinde"))
            if is_brinde:
                details = [
                    "🎁 <b>BRINDE REGISTRADO COM SUCESSO!</b>",
                    "━━━━━━━━━━━━━━━━━━━━━━━",
                    f"☕ <b>Produto:</b> {html.escape(product['nome'])}",
                    f"🎯 <b>Quantidade:</b> {quantity_value} {quantity_label}",
                    f"💰 <b>Valor:</b> {format_currency(Decimal('0'))}",
                    "📦 Estoque atualizado automaticamente.",
                    "━━━━━━━━━━━━━━━━━━━━━━━",
                ]
            else:
                header = "✅ Movimentação registrada com sucesso!"
                if total_value is None:
                    unit_p = unit_price if unit_price is not None else Decimal(product.get("preco") or 0)
                    total_value = (quantity * unit_p).quantize(Decimal("0.01")) if unit_p > 0 else Decimal("0")
                unit_line = (
                    f"💰 <b>Valor unitário:</b> {format_currency(unit_price)}" if unit_price is not None and unit_price > 0 else "💰 <b>Valor unitário:</b> não informado"
                )
                total_line = (
                    f"💵 <b>Total:</b> {format_currency(total_value)}" if total_value and total_value > 0 else "💵 <b>Total:</b> —"
                )
                details = [
                    header,
                    f"📦 <b>Produto:</b> {html.escape(product['nome'])}",
                    f"➖ <b>Quantidade:</b> {quantity_value} {quantity_label}",
                    unit_line,
                    total_line,
                    f"📦 <b>Novo estoque:</b> {new_stock_value} {new_stock_label}",
                ]

        details.append("")
        details.append("O que você gostaria de fazer a seguir?")

        confirmation = "\n".join(details)
        post_keyboard = build_post_movement_keyboard(action)

        edited = await self._edit_session_message(
            context,
            session,
            confirmation,
            reply_markup=post_keyboard,
            parse_mode=ParseMode.HTML,
        )
        if edited is None:
            await self._ensure_typing(context=context, chat_id=user_id)
            await context.bot.send_message(
                chat_id=user_id,
                text=confirmation,
                reply_markup=post_keyboard,
                parse_mode=ParseMode.HTML,
            )

        self.sessions.pop(user_id, None)

    async def handle_value_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not query.from_user or not query.data:
            return

        await query.answer()
        try:
            _, action, value = query.data.split(":", maxsplit=2)
        except ValueError:
            return

        user_id = query.from_user.id
        session = self.sessions.get(user_id)
        if session is None or session.action != "saida":
            # Only handle value selection in saída flow
            message = query.message
            if isinstance(message, Message):
                await self._edit_with_typing(
                    message,
                    context,
                    "Use o menu principal para iniciar uma movimentação ☕",
                    reply_markup=build_main_menu(),
                )
            self.sessions.pop(user_id, None)
            return

        message = query.message if isinstance(query.message, Message) else None

        if value == "custom":
            session.awaiting = "saida_value"
            prompt = "✏️ Informe manualmente o valor unitário. Envie apenas números (use vírgula ou ponto nos centavos)."
            if message:
                await self._edit_with_typing(
                    message,
                    context,
                    prompt,
                    parse_mode=ParseMode.HTML,
                    session=session,
                )
            else:
                await self._ensure_typing(context=context, chat_id=user_id)
                sent = await context.bot.send_message(chat_id=user_id, text=prompt, parse_mode=ParseMode.HTML)
                self._store_message_reference(session, sent)
            return

        # Quick price chosen
        try:
            unit_price = Decimal(value)
        except InvalidOperation:
            await query.answer("Valor inválido", show_alert=True)
            return

        quantity_raw = session.metadata.get("pending_quantity")
        if quantity_raw is None:
            # quantity lost; restart
            if message:
                await self._edit_with_typing(
                    message,
                    context,
                    "Não encontrei a quantidade selecionada. Vamos começar novamente.",
                    reply_markup=build_main_menu(),
                )
            self.sessions.pop(user_id, None)
            return

        try:
            quantity = Decimal(quantity_raw)
        except InvalidOperation:
            if message:
                await self._edit_with_typing(
                    message,
                    context,
                    "Não consegui confirmar a quantidade anterior. Vamos reiniciar.",
                    reply_markup=build_main_menu(),
                )
            self.sessions.pop(user_id, None)
            return

        if session.product_id is None:
            if message:
                await self._edit_with_typing(
                    message,
                    context,
                    "Produto não identificado. Voltando ao menu principal ☕",
                    reply_markup=build_main_menu(),
                )
            self.sessions.pop(user_id, None)
            return

        product = await self.db.get_product(session.product_id)
        if not product:
            if message:
                await self._edit_with_typing(
                    message,
                    context,
                    "Produto não encontrado. Vamos recomeçar ☕",
                    reply_markup=build_main_menu(),
                )
            self.sessions.pop(user_id, None)
            return

        session.awaiting = None
        total_value = (quantity * unit_price).quantize(Decimal("0.01"))
        await self._apply_stock_movement(
            session=session,
            user_id=user_id,
            product=product,
            quantity=quantity,
            context=context,
            total_value=total_value,
            unit_price=unit_price,
        )

    async def handle_admin_actions(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not query.from_user or not query.data:
            return

        await query.answer()
        action = query.data.split(":", maxsplit=1)[1]
        user_id = query.from_user.id
        message = query.message if isinstance(query.message, Message) else None

        if action == "confirm_clear_stock":
            text = (
                "⚠️ Esta ação vai zerar o estoque de todos os produtos.\n\n"
                "Deseja continuar?"
            )
            if message:
                await self._edit_with_typing(
                    message,
                    context,
                    text,
                    reply_markup=build_confirm_clear_keyboard("stock"),
                )
            return

        if action == "do_clear_stock":
            await self.db.clear_stock()
            # Refresh stock view
            await self._send_estoque(update, context, from_callback=True)
            return

        if action == "confirm_clear_saidas":
            text = (
                "⚠️ Esta ação vai apagar todo o histórico de saídas.\n\n"
                "Deseja continuar?"
            )
            if message:
                await self._edit_with_typing(
                    message,
                    context,
                    text,
                    reply_markup=build_confirm_clear_keyboard("saidas"),
                )
            return

        if action == "do_clear_saidas":
            await self.db.clear_saidas_history()
            # Refresh history view
            await self._send_historico(update, context, from_callback=True)
            return

        if action == "confirm_clear_history":
            text = (
                "⚠️ Esta ação vai apagar TODO o histórico de movimentações (entradas e saídas).\n\n"
                "Deseja continuar?"
            )
            if message:
                await self._edit_with_typing(
                    message,
                    context,
                    text,
                    reply_markup=build_confirm_clear_keyboard("history"),
                )
            return

        if action == "do_clear_history":
            await self.db.clear_all_history()
            # Refresh history view
            await self._send_historico(update, context, from_callback=True)
            return

        if action == "cancel":
            # Return to main menu
            if message:
                await self._edit_with_typing(
                    message,
                    context,
                    "Ação cancelada. Escolha uma opção:",
                    reply_markup=build_main_menu(),
                )
            return

    async def _send_estoque(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        *,
        from_callback: bool = False,
    ) -> None:
        overview = await self.db.fetch_stock_overview()
        text = self._render_stock_overview(overview)

        keyboard = build_stock_keyboard()

        if from_callback:
            query = update.callback_query
            if not query:
                return
            message = query.message
            if isinstance(message, Message):
                await self._edit_with_typing(
                    message,
                    context,
                    text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
        else:
            message = update.message
            if message:
                await self._reply_with_typing(
                    message,
                    context,
                    text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN_V2,
                )

    async def _send_historico(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        *,
        from_callback: bool = False,
    ) -> None:
        movimentos = await self.db.list_recent_movements(movement_type="saida", limit=10)

        if not movimentos:
            text = "📊 Nenhuma saída registrada até o momento."
        else:
            linhas: List[str] = ["📊 Últimas saídas:"]
            for item in movimentos:
                data: datetime = item["data"]
                quantidade: Decimal = item["quantidade"]
                linhas.append(
                    f"{data.strftime('%d/%m %H:%M')} • {item['nome']} → {format_quantity(quantidade)} {item['unidade']}"
                )
            text = "\n".join(linhas)
        movimentos = await self.db.list_recent_all_movements(limit=25)

        if not movimentos:
            text = "📜 <b>HISTÓRICO DE MOVIMENTAÇÕES</b>\n━━━━━━━━━━━━━━━━━━━━━━━\nNenhum registro até o momento."
        else:
            linhas: List[str] = ["📜 <b>HISTÓRICO DE MOVIMENTAÇÕES</b>", "━━━━━━━━━━━━━━━━━━━━━━━"]
            for item in movimentos:
                data: datetime = item["data"]
                quantidade: Decimal = item["quantidade"]
                tipo: str = item["tipo_movimentacao"]
                unidade = item.get("unidade", "un")
                nome = item.get("nome", "—")
                observ = (item.get("observacao") or "")
                is_brinde = "[BRINDE]" in observ
                categoria = item.get("categoria")
                preco_base = Decimal(item.get("preco") or 0)
                valor_unit = item.get("valor_unitario")
                sinal = "+" if tipo == "entrada" else "-"
                if valor_unit is not None:
                    try:
                        unit_price_dec = Decimal(valor_unit)
                    except Exception:
                        unit_price_dec = preco_base
                else:
                    unit_price_dec = preco_base
                total_val = Decimal("0")
                if tipo == "entrada":
                    total_val = (quantidade * preco_base).quantize(Decimal("0.01")) if preco_base > 0 else Decimal("0")
                elif tipo == "saida":
                    if is_brinde:
                        total_val = Decimal("0")
                    else:
                        total_val = (quantidade * unit_price_dec).quantize(Decimal("0.01")) if unit_price_dec > 0 else Decimal("0")
                money_icon = "💰" if is_brinde else "💵"
                valor_texto = f"{money_icon} {format_currency(total_val)}"
                if is_brinde:
                    linhas.append(
                        f"{data.strftime('%d/%m %H:%M')} • 🎁 BRINDE — {nome} → {sinal}{format_quantity(quantidade)} {unidade} ({valor_texto})"
                    )
                else:
                    produto_icon = "☕" if categoria == "cafes" else "📦"
                    linhas.append(
                        f"{data.strftime('%d/%m %H:%M')} • {produto_icon} {nome} → {sinal}{format_quantity(quantidade)} {unidade} ({valor_texto})"
                    )
            text = "\n".join(linhas)

        keyboard = build_history_actions_keyboard()

        if from_callback:
            query = update.callback_query
            if not query:
                return
            message = query.message
            if isinstance(message, Message):
                await self._edit_with_typing(message, context, text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
        else:
            message = update.message
            if message:
                await self._reply_with_typing(message, context, text, reply_markup=keyboard, parse_mode=ParseMode.HTML)

    async def _start_iaeos(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        *,
        from_callback: bool = False,
    ) -> None:
        user = update.effective_user
        if not user:
            return

        user_id = user.id
        session = UserSession(action="iaeos", awaiting="iaeos_question")
        self.sessions[user_id] = session

        text = (
            "🤖 Painel IA da Eos Cafés\n\n"
            "Escolha uma opção para obter insights ou envie uma pergunta sobre o estoque."
        )
        keyboard = build_ia_panel_keyboard()

        if from_callback:
            query = update.callback_query
            if not query:
                return
            message = query.message
            if isinstance(message, Message):
                await self._edit_with_typing(
                    message,
                    context,
                    text,
                    reply_markup=keyboard,
                    session=session,
                )
        else:
            message = update.message
            if message:
                await self._reply_with_typing(
                    message,
                    context,
                    text,
                    reply_markup=keyboard,
                    session=session,
                )

    async def handle_ia_panel_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not query.from_user or not query.data:
            return

        await query.answer()
        option = query.data.split(":", maxsplit=1)[1]
        user_id = query.from_user.id
        session = self.sessions.get(user_id)
        if session is None or session.action != "iaeos":
            session = UserSession(action="iaeos", awaiting="iaeos_question")
            self.sessions[user_id] = session

        session.awaiting = "iaeos_question"

        if option == "sugestoes":
            overview = await self.db.fetch_stock_overview()
            baixos = [
                item
                for item in overview
                if Decimal(item["quantidade"]) <= Decimal("10")
            ]
            if baixos:
                linhas = ["💡 Sugestões automáticas:"]
                for item in baixos:
                    icon = "☕" if item.get("categoria") == "cafes" else "📦"
                    quantidade = format_quantity(Decimal(item["quantidade"]))
                    linhas.append(
                        f"{icon} {item['nome']} está com {quantidade} {item['unidade']} — considere repor."
                    )
                text = "\n".join(linhas)
            else:
                text = "💡 Sugestões automáticas:\nTudo em dia! Nenhum item crítico no momento ☕"
        elif option == "relatorios":
            vendas = await self.db.sales_totals_by_product(days=7)
            if not vendas:
                text = "📈 Relatórios rápidos:\nAinda não registramos saídas nos últimos 7 dias."
            else:
                linhas = ["📈 Relatórios rápidos (últimos 7 dias):"]
                for item in vendas[:3]:
                    quantidade = format_quantity(Decimal(item["quantidade"]))
                    total = Decimal(item["total"] or 0)
                    linhas.append(
                        f"• {item['nome']}: {quantidade} un • {format_currency(total)}"
                    )
                text = "\n".join(linhas)
        elif option == "resumo":
            today = date.today()
            yesterday = today - timedelta(days=1)
            today_total = await self.db.sales_total_for_date(today)
            yesterday_total = await self.db.sales_total_for_date(yesterday)
            trend = "⬆️" if today_total > yesterday_total else ("⬇️" if today_total < yesterday_total else "➡️")
            text = (
                "🧾 Resumo semanal:\n"
                f"Hoje ({today.strftime('%d/%m')}): {format_currency(today_total)}\n"
                f"Ontem ({yesterday.strftime('%d/%m')}): {format_currency(yesterday_total)}\n"
                f"{trend} Continue acompanhando pelo painel!"
            )
        else:
            text = "🤖 Escolha uma das opções ou envie sua pergunta sobre o estoque ☕"

        message = query.message if isinstance(query.message, Message) else None
        if message:
            await self._edit_with_typing(
                message,
                context,
                text,
                reply_markup=build_ia_panel_keyboard(),
                session=session,
            )

    async def _process_iaeos_question(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not update.message or not update.effective_user or update.message.text is None:
            return

        user_id = update.effective_user.id
        session = self.sessions.get(user_id)
        if session is None or session.action != "iaeos":
            session = UserSession(action="iaeos", awaiting="iaeos_question")
            self.sessions[user_id] = session

        question = update.message.text.strip()
        if not question:
            notice = "Pode enviar sua pergunta quando quiser ☕"
            edited = await self._edit_session_message(context, session, notice)
            if edited is None:
                await self._reply_with_typing(update.message, context, notice, session=session)
            return

        products = await self.db.fetch_products()
        stock_lines = [
            f"- {p['nome']} ({p['tipo']}): {p['quantidade']} {p['unidade']}"
            for p in products
        ]
        stock_context = "\n".join(stock_lines)

        try:
            answer = await self.groq.ask(question, stock_context=stock_context)
        except GroqClientError:
            logger.exception("Erro na consulta à Groq")
            fallback = "Não consegui falar com a IA agora. Tente novamente em instantes."
            edited = await self._edit_session_message(context, session, fallback)
            if edited is None:
                await self._reply_with_typing(update.message, context, fallback, session=session)
            return

        session.awaiting = "iaeos_question"
        response = (
            "🤖 Resposta da IA:\n\n"
            f"{answer}\n\n"
            "Envie outra pergunta ou escolha uma opção abaixo ☕"
        )

        edited = await self._edit_session_message(
            context,
            session,
            response,
            reply_markup=build_ia_panel_keyboard(),
            parse_mode=ParseMode.MARKDOWN,
        )
        if edited is None:
            await self._reply_with_typing(
                update.message,
                context,
                response,
                reply_markup=build_ia_panel_keyboard(),
                parse_mode=ParseMode.MARKDOWN,
                session=session,
            )

    async def _process_brinde_description(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        session: UserSession,
    ) -> None:
        if not update.message or update.message.text is None or not update.effective_user:
            return

        description = update.message.text.strip()
        if not description:
            prompt = "Pode descrever rapidamente o brinde? ☕"
            edited = await self._edit_session_message(context, session, prompt)
            if edited is None:
                await self._reply_with_typing(update.message, context, prompt, session=session)
            return

        chat_id = update.effective_chat.id if update.effective_chat else None
        await self.db.record_brinde(description, chat_id=chat_id)

        confirmation = (
            "🎁 Brinde registrado com carinho!\n"
            "A equipe já foi avisada para preparar a surpresa.\n\n"
            "Escolha a próxima ação no menu abaixo ☕"
        )

        edited = await self._edit_session_message(
            context,
            session,
            confirmation,
            reply_markup=build_main_menu(),
        )
        if edited is None:
            await self._reply_with_typing(
                update.message,
                context,
                confirmation,
                reply_markup=build_main_menu(),
                session=session,
            )
        self.sessions.pop(update.effective_user.id, None)



def run_bot(settings: Settings) -> None:
    bot = EosBot(settings)
    asyncio.run(bot.run())
