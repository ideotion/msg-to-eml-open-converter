from __future__ import annotations

from datetime import datetime, timezone

import vobject

from msg2eml.contact_convert import build_vcard
from tests.helpers import FakeContact


def _parse(raw: bytes):
    return vobject.readOne(raw.decode("utf-8"))


def test_minimal_contact_produces_valid_vcard() -> None:
    contact = FakeContact(displayName="Alice Dupont", email1EmailAddress="alice@example.com")
    warnings: list[str] = []
    raw = build_vcard(contact, warnings=warnings)

    assert raw.startswith(b"BEGIN:VCARD\r\nVERSION:3.0\r\n")
    card = _parse(raw)
    assert card.fn.value == "Alice Dupont"
    assert card.email.value == "alice@example.com"
    assert warnings == []


def test_full_contact_maps_all_fields_and_roundtrips() -> None:
    contact = FakeContact(
        displayName="Éloïse Martin",
        givenName="Éloïse",
        surname="Martin",
        middleName="Anne",
        companyName="Ideotion",
        jobTitle="Ingénieure",
        email1EmailAddress="eloise@example.com",
        email2EmailAddress="eloise.m@example.com",
        businessTelephoneNumber="+33 1 23 45 67 89",
        mobileTelephoneNumber="+33 6 12 34 56 78",
        workAddressStreet="1 Rue de Paris",
        workAddressLocality="Paris",
        workAddressPostalCode="75001",
        workAddressCountry="France",
        birthday=datetime(1990, 5, 12, 11, 59, tzinfo=timezone.utc),
        contactPhoto=b"\x89PNGfakebytes",
        body="Rencontrée à la conférence.",
        webpageUrl="https://example.com",
    )
    warnings: list[str] = []
    raw = build_vcard(contact, warnings=warnings)
    card = _parse(raw)

    assert card.fn.value == "Éloïse Martin"
    assert card.n.value.given == "Éloïse"
    assert card.n.value.family == "Martin"
    assert card.org.value == ["Ideotion"]
    assert card.title.value == "Ingénieure"
    emails = [e.value for e in card.contents["email"]]
    assert emails == ["eloise@example.com", "eloise.m@example.com"]
    tels = {t.value: t.type_param for t in card.contents["tel"]}
    assert tels["+33 1 23 45 67 89"] == "WORK"
    assert tels["+33 6 12 34 56 78"] == "CELL"
    assert card.adr.value.street == "1 Rue de Paris"
    assert card.adr.value.city == "Paris"
    assert card.adr.type_param == "WORK"
    assert card.bday.value == "1990-05-12"
    assert card.photo.value == b"\x89PNGfakebytes"
    assert card.note.value == "Rencontrée à la conférence."
    assert card.url.value == "https://example.com"
    assert warnings == []


def test_contact_without_name_falls_back_to_unknown() -> None:
    contact = FakeContact(email1EmailAddress="anon@example.com")
    raw = build_vcard(contact)
    card = _parse(raw)
    assert card.fn.value == "Unknown"


def test_contact_without_any_contact_method_warns() -> None:
    contact = FakeContact(displayName="No Contact Info")
    warnings: list[str] = []
    build_vcard(contact, warnings=warnings)
    assert any("no email address or phone number" in w for w in warnings)


def test_contact_only_home_and_other_addresses() -> None:
    contact = FakeContact(
        displayName="Test",
        homeAddressStreet="10 Home St",
        homeAddressLocality="Hometown",
        otherAddressStreet="20 Other Ave",
    )
    raw = build_vcard(contact)
    card = _parse(raw)
    adrs = {getattr(a, "type_param", ""): a.value.street for a in card.contents["adr"]}
    assert adrs["HOME"] == "10 Home St"
    assert adrs[""] == "20 Other Ave"
