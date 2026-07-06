"""Unit tests for Product model computed properties. No database required —
effective_print_name is a pure Python property evaluated in memory."""

import uuid

from app.models.product import Product


def _make_product(**overrides) -> Product:
    """Build an in-memory Product with sane defaults for property tests."""
    defaults = {
        "id": uuid.uuid4(),
        "brand_id": uuid.uuid4(),
        "category_id": uuid.uuid4(),
        "name": "Coffee",
        "base_price_cents": 500,
    }
    defaults.update(overrides)
    return Product(**defaults)


def test_effective_print_name_falls_back_to_name_when_unset():
    """effective_print_name returns name when print_name is None."""
    product = _make_product(name="Latte", print_name=None)
    assert product.effective_print_name == "Latte"


def test_effective_print_name_uses_print_name_when_set():
    """effective_print_name returns print_name when it is set, even if different from name."""
    product = _make_product(name="Flat White", print_name="FLTWHT")
    assert product.effective_print_name == "FLTWHT"
