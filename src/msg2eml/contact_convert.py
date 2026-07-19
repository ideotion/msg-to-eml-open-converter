"""Build a vCard (.vcf) from an Outlook contact (IPM.Contact) .msg object.

Written against duck-typed "parsed message" objects (only ``getattr``, never
``isinstance`` checks against ``extract_msg`` classes), matching the rest of
this package -- see :mod:`msg2eml.convert`.

vCard 3.0 is used rather than 4.0: it is the version most broadly supported
by mail clients (including Thunderbird's Address Book), and the ``vobject``
library used here targets it specifically. Text values are escaped by
``vobject`` itself (backslash/comma/semicolon/embedded-newline escaping per
RFC 6350), so -- unlike the stdlib ``email`` headers this package also
builds -- no separate injection-hardening layer is needed here.
"""

from __future__ import annotations

from typing import Any

import vobject


def _text(msg: Any, attr: str) -> str | None:
    value = getattr(msg, attr, None)
    return str(value) if value else None


def _add_name(card: Any, msg: Any) -> None:
    given = _text(msg, "givenName") or ""
    family = _text(msg, "surname") or ""
    middle = _text(msg, "middleName") or ""
    prefix = _text(msg, "displayNamePrefix") or ""
    suffix = _text(msg, "generation") or ""

    display_name = (
        _text(msg, "displayName") or " ".join(p for p in (given, family) if p) or "Unknown"
    )
    card.add("fn").value = display_name

    if any((given, family, middle, prefix, suffix)):
        card.add("n").value = vobject.vcard.Name(
            family=family, given=given, additional=middle, prefix=prefix, suffix=suffix
        )
    else:
        card.add("n").value = vobject.vcard.Name(family=display_name)


def _add_organization(card: Any, msg: Any) -> None:
    company = _text(msg, "companyName")
    if company:
        card.add("org").value = [company]
    title = _text(msg, "jobTitle")
    if title:
        card.add("title").value = title


def _add_emails(card: Any, msg: Any) -> None:
    for attr in ("email1EmailAddress", "email2EmailAddress", "email3EmailAddress"):
        address = _text(msg, attr)
        if address:
            card.add("email").value = address


_PHONE_ATTRS: tuple[tuple[str, str], ...] = (
    ("businessTelephoneNumber", "WORK"),
    ("homeTelephoneNumber", "HOME"),
    ("mobileTelephoneNumber", "CELL"),
    ("businessFaxNumber", "WORK,FAX"),
    ("homeFaxNumber", "HOME,FAX"),
)


def _add_phones(card: Any, msg: Any) -> None:
    for attr, type_param in _PHONE_ATTRS:
        number = _text(msg, attr)
        if number:
            tel = card.add("tel")
            tel.value = number
            tel.type_param = type_param


_ADDRESS_KINDS: tuple[tuple[str, str], ...] = (
    ("work", "WORK"),
    ("home", "HOME"),
    ("other", ""),
)


def _add_addresses(card: Any, msg: Any) -> None:
    for prefix, type_param in _ADDRESS_KINDS:
        street = _text(msg, f"{prefix}AddressStreet")
        locality = _text(msg, f"{prefix}AddressLocality")
        region = _text(msg, f"{prefix}AddressStateOrProvince")
        postal_code = _text(msg, f"{prefix}AddressPostalCode")
        country = _text(msg, f"{prefix}AddressCountry")
        po_box = _text(msg, f"{prefix}AddressPostOfficeBox")
        if not any((street, locality, region, postal_code, country, po_box)):
            continue
        adr = card.add("adr")
        adr.value = vobject.vcard.Address(
            box=po_box or "",
            street=street or "",
            city=locality or "",
            region=region or "",
            code=postal_code or "",
            country=country or "",
        )
        if type_param:
            adr.type_param = type_param


def _add_dates(card: Any, msg: Any) -> None:
    birthday = getattr(msg, "birthday", None)
    if birthday is not None:
        card.add("bday").value = birthday.date().isoformat()


def _add_photo(card: Any, msg: Any) -> None:
    photo_bytes = getattr(msg, "contactPhoto", None)
    if not photo_bytes:
        return
    photo = card.add("photo")
    photo.value = photo_bytes
    photo.encoding_param = "b"
    photo.type_param = "JPEG"


def _add_notes_and_web(card: Any, msg: Any) -> None:
    note = _text(msg, "body")
    if note:
        card.add("note").value = note
    webpage = _text(msg, "webpageUrl")
    if webpage:
        card.add("url").value = webpage


def build_vcard(msg: Any, *, warnings: list[str] | None = None) -> bytes:
    """Build a vCard 3.0 (.vcf) document from a parsed contact .msg object."""
    if warnings is None:
        warnings = []

    card = vobject.vCard()
    _add_name(card, msg)
    _add_organization(card, msg)
    _add_emails(card, msg)
    _add_phones(card, msg)
    _add_addresses(card, msg)
    _add_dates(card, msg)
    _add_photo(card, msg)
    _add_notes_and_web(card, msg)

    if not any(
        _text(msg, attr)
        for attr in (
            "email1EmailAddress",
            "businessTelephoneNumber",
            "homeTelephoneNumber",
            "mobileTelephoneNumber",
        )
    ):
        warnings.append("Contact has no email address or phone number")

    return card.serialize().encode("utf-8")
