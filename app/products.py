from dataclasses import dataclass
from decimal import Decimal
from typing import Final, List


@dataclass(frozen=True)
class ProductSeed:
    nome: str
    tipo: str
    unidade: str
    categoria: str
    preco: Decimal


PRODUCT_SEEDS: Final[List[ProductSeed]] = [
    ProductSeed("Café especial moído 250g", "produto_acabado", "un", "cafes", Decimal("28.90")),
    ProductSeed("Café especial moído 1kg", "produto_acabado", "un", "cafes", Decimal("86.00")),
    ProductSeed("Café especial em grãos 250g", "produto_acabado", "un", "cafes", Decimal("30.50")),
    ProductSeed("Café especial em grãos 1kg", "produto_acabado", "un", "cafes", Decimal("92.00")),
    ProductSeed("Café gourmet clássico 250g", "produto_acabado", "un", "cafes", Decimal("26.00")),
    ProductSeed("Café gourmet clássico 1kg", "produto_acabado", "un", "cafes", Decimal("82.00")),
    ProductSeed("Café gourmet intenso 1kg", "produto_acabado", "un", "cafes", Decimal("60.00")),
    ProductSeed("Embalagem 1kg", "materia_prima", "un", "embalagens", Decimal("3.00")),
    ProductSeed("Embalagem especial 250g", "materia_prima", "un", "embalagens", Decimal("1.20")),
    ProductSeed("Embalagem gourmet 250g", "materia_prima", "un", "embalagens", Decimal("1.50")),
    ProductSeed("Lote de café verde especial moído", "materia_prima", "kg", "insumos", Decimal("0")),
    ProductSeed("Lote de café verde especial em grãos", "materia_prima", "kg", "insumos", Decimal("0")),
    ProductSeed("Lote de café verde gourmet", "materia_prima", "kg", "insumos", Decimal("0")),
]
