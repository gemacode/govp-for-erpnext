"""Pure functions shared by the Frappe handlers and the self-contained tests."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlparse


DEFAULT_EXCHANGE_URL = "https://partners.gemacode.org/api/exchange"


def _text(value):
    return "" if value is None else str(value).strip()


def canonical_quantity(value):
    number = Decimal(_text(value) or "0")
    return format(number.normalize(), "f") if number else "0"


def canonical_lines(items):
    lines = []
    for item in items:
        serials = sorted(filter(None, (_text(value) for value in _text(item.get("serial_no")).replace(",", "\n").splitlines())))
        lines.append({
            "item": _text(item.get("item_code")),
            "quantity": canonical_quantity(item.get("qty")),
            "uom": _text(item.get("uom")),
            "warehouse": _text(item.get("warehouse")),
            "batch": _text(item.get("batch_no")) or None,
            "serials": serials,
        })
    return sorted(lines, key=lambda row: json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")))


def evidence_digest(items):
    encoded = json.dumps(canonical_lines(items), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def idempotency_key(site, company, doctype, name):
    scope = hashlib.sha256(f"{site}\0{company}".encode()).hexdigest()[:16]
    document = hashlib.sha256(f"{doctype}\0{name}".encode()).hexdigest()[:24]
    return f"erpnext:{scope}:{document}:submitted"


def issuance_payload(document, site, validity_days=365, now=None):
    now = now or datetime.now(timezone.utc)
    document_items = document.get("items", [])
    name = _text(document.get("name"))
    company = _text(document.get("company"))
    return {
        "issuer": {"name": company},
        "subject": {
            "type": "shipment",
            "id": name,
            "name": f"Expedición {name}",
            "description": _text(document.get("po_no")) or _text(document.get("against_sales_order")) or None,
        },
        "requirement": "Demostrar la expedición y sus líneas antes de aceptar la recepción.",
        "evidence": [{"label": "Huella canónica de líneas, lotes y series", "sha256": evidence_digest(document_items)}],
        "validUntil": (now + timedelta(days=int(validity_days))).isoformat().replace("+00:00", "Z"),
        "source": {
            "platform": "erpnext",
            "externalId": idempotency_key(site, company, "Delivery Note", name),
        },
    }


def validate_exchange_url(value, resolver=socket.getaddrinfo):
    parsed = urlparse(_text(value))
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("GOVP Exchange debe usar una URL HTTPS sin credenciales, consulta ni fragmento")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"}:
        raise ValueError("GOVP Exchange no puede apuntar a localhost")
    try:
        addresses = {entry[4][0] for entry in resolver(host, parsed.port or 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as error:
        raise ValueError("No se puede resolver el host de GOVP Exchange") from error
    if not addresses:
        raise ValueError("El host de GOVP Exchange no tiene direcciones")
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%")[0])
        if not ip.is_global:
            raise ValueError("GOVP Exchange no puede apuntar a una red privada o reservada")
    return value.rstrip("/")


def retry_delay(attempt):
    return min(6 * 60 * 60, 30 * (2 ** max(0, int(attempt) - 1)))
