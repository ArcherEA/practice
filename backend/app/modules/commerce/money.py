"""Money helpers: allowed currencies, minor-unit exponents and formatting (pure).

Amounts are integers in the currency's minor unit. Stripe's zero-decimal and
three-decimal currencies are hard-coded, so no dependency is needed.
"""

from decimal import Decimal

from app.core.config import settings

# Stripe: https://docs.stripe.com/currencies#zero-decimal
ZERO_DECIMAL = frozenset(
    {
        "bif",
        "clp",
        "djf",
        "gnf",
        "jpy",
        "kmf",
        "krw",
        "mga",
        "pyg",
        "rwf",
        "ugx",
        "vnd",
        "vuv",
        "xaf",
        "xof",
        "xpf",
    }
)
# Stripe: https://docs.stripe.com/currencies#three-decimal
THREE_DECIMAL = frozenset({"bhd", "jod", "kwd", "omr", "tnd"})


def allowed_currencies() -> list[str]:
    return list(settings.STORE_CURRENCIES)


def default_currency() -> str:
    return settings.STORE_DEFAULT_CURRENCY or settings.STORE_CURRENCIES[0]


def normalize_currency(code: str) -> str:
    return code.strip().lower()


def is_allowed(code: str) -> bool:
    return normalize_currency(code) in settings.STORE_CURRENCIES


def exponent(currency: str) -> int:
    """Digits after the decimal point: 0 (jpy), 2 (usd) or 3 (kwd)."""
    code = normalize_currency(currency)
    if code in ZERO_DECIMAL:
        return 0
    if code in THREE_DECIMAL:
        return 3
    return 2


def to_decimal(amount: int, currency: str) -> Decimal:
    """Major-unit value of `amount` minor units (exact, no floats)."""
    return Decimal(amount).scaleb(-exponent(currency))


def format_amount(amount: int, currency: str) -> str:
    """Text for emails: ``1,234.50 USD`` / ``1,500 JPY`` (the code, not a symbol)."""
    digits = exponent(currency)
    return f"{to_decimal(amount, currency):,.{digits}f} {currency.upper()}"
