import phonenumbers

from app.core.errors import InvalidInput


def normalize_phone(raw: str, default_region: str = "BR") -> str:
    """Return the E.164 form of a phone number, or raise InvalidInput."""
    try:
        parsed = phonenumbers.parse(raw, default_region)
    except phonenumbers.NumberParseException as exc:
        raise InvalidInput("Invalid phone number") from exc
    if not phonenumbers.is_valid_number(parsed):
        raise InvalidInput("Invalid phone number")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
