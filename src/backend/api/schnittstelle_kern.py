"""Token und Umfang der lokalen Schnittstelle.

Ein globales Token. Aktivieren legt es an, wenn noch keines da ist, und lässt ein
vorhandenes stehen. Deaktivieren blendet es aus, löscht es aber nicht. Erneuern
ersetzt es und geht nur, solange die Schnittstelle an ist.

Umfang ist eine Leiter, kein Satz einzelner Schalter:

    lesen  <  entwuerfe  <  voll

Ein höherer Umfang darf alles, was die Stufen darunter dürfen. Werkzeuge und
Lese-Endpunkte nennen die Stufe, die sie brauchen. Heute ist nur „lesen“
verdrahtet; die anderen Stufen haben noch keine Endpunkte.
"""

from __future__ import annotations

import secrets
from typing import Protocol

UMFANG_LESEN = "lesen"
UMFANG_ENTWUERFE = "entwuerfe"
UMFANG_VOLL = "voll"

_RANG = {
    UMFANG_LESEN: 1,
    UMFANG_ENTWUERFE: 2,
    UMFANG_VOLL: 3,
}


class Schnittstelle(Protocol):
    mcp_aktiv: bool
    mcp_token: str | None
    mcp_umfang: str


def neuer_token() -> str:
    return secrets.token_urlsafe(32)


def darf(aktuell: str | None, benoetigt: str) -> bool:
    try:
        return _RANG[aktuell or ""] >= _RANG[benoetigt]
    except KeyError:
        return False


def token_gleich(erwartet: str | None, bekommen: str | None) -> bool:
    if not erwartet or not bekommen:
        return False
    links = erwartet.encode()
    rechts = bekommen.encode()
    if len(links) != len(rechts):
        return False
    return secrets.compare_digest(links, rechts)


def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    schema, trennzeichen, rest = authorization.partition(" ")
    if trennzeichen != " " or schema.lower() != "bearer" or not rest.strip():
        return None
    return rest.strip()


def aktivieren(zeile: Schnittstelle) -> None:
    if not zeile.mcp_token:
        zeile.mcp_token = neuer_token()
    zeile.mcp_aktiv = True


def deaktivieren(zeile: Schnittstelle) -> None:
    zeile.mcp_aktiv = False


def rotieren(zeile: Schnittstelle) -> None:
    if not zeile.mcp_aktiv:
        raise ValueError("Die Schnittstelle ist aus. Token bleibt unverändert.")
    zeile.mcp_token = neuer_token()


def sichtbares_token(zeile: Schnittstelle) -> str | None:
    if not zeile.mcp_aktiv:
        return None
    return zeile.mcp_token
