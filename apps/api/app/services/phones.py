import phonenumbers

from app.core.errors import InvalidInput


def canonical_e164(e164: str) -> str:
    """Brazilian mobiles in their current 9-digit form. WhatsApp often reports older
    numbers without the extra 9 (+55 11 8765-4321 for +55 11 98765-4321), and people type
    either; both must reach the same person."""
    digits = "".join(ch for ch in e164 if ch.isdigit())
    national = digits[2:]
    if digits.startswith("55") and len(national) == 10 and national[2] in "6789":
        return f"+55{national[:2]}9{national[2:]}"
    return "+" + digits


def normalize_phone(raw: str, default_region: str = "BR") -> str:
    """Return the canonical E.164 form of a phone number, or raise InvalidInput."""
    try:
        parsed = phonenumbers.parse(raw, default_region)
    except phonenumbers.NumberParseException as exc:
        raise InvalidInput("Invalid phone number") from exc
    e164 = canonical_e164(phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164))
    if not phonenumbers.is_valid_number(phonenumbers.parse(e164)):
        raise InvalidInput("Invalid phone number")
    return e164
