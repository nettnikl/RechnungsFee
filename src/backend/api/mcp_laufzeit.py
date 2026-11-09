"""MCP im laufenden Backend. Nur Lese-Werkzeuge.

Der HTTP-Zugang liegt unter /mcp und lässt Lebenszyklus-Nachrichten der
Session durch. Solange die Schnittstelle aus ist, antwortet der Pfad mit 404.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

from database.connection import SessionLocal
from database.models import Unternehmen

from . import lesen
from .schnittstelle_kern import UMFANG_LESEN, bearer_token, darf, token_gleich


class _Gesperrt(Exception):
    pass


def _verlange(stufe: str) -> None:
    db = SessionLocal()
    try:
        firma = db.query(Unternehmen).first()
        if firma is None or not firma.mcp_aktiv or not darf(firma.mcp_umfang, stufe):
            raise _Gesperrt("Dieser Zugriff ist in der aktuellen Stufe nicht frei.")
    finally:
        db.close()


def _ausfuehren(stufe: str, funktion):
    try:
        _verlange(stufe)
        db = SessionLocal()
        try:
            return json.dumps(funktion(db), ensure_ascii=False, default=str)
        finally:
            db.close()
    except _Gesperrt as fehler:
        return json.dumps({"fehler": str(fehler)}, ensure_ascii=False)


def baue_server():
    from mcp.server.mcpserver import MCPServer

    mcp = MCPServer(
        "rechnungsfee",
        instructions=(
            "Nur-Lese-Zugriff auf Rechnungen und Stammdaten der lokalen RechnungsFee. "
            "Es wird nichts angelegt, geändert oder storniert."
        ),
    )

    @mcp.tool()
    def rechnungen_liste(typ: str = "", zahlungsstatus: str = "", limit: int = 50) -> str:
        """Rechnungen, neueste zuerst. typ: leer, eingang, ausgang. zahlungsstatus: leer, offen, teilweise, bezahlt, entwurf, storniert."""

        def lauf(db):
            if typ not in ("", "eingang", "ausgang"):
                raise _Gesperrt("typ muss leer, eingang oder ausgang sein.")
            return lesen.liste_rechnungen(db, typ=typ or None, zahlungsstatus=zahlungsstatus or None, limit=limit)

        return _ausfuehren(UMFANG_LESEN, lauf)

    @mcp.tool()
    def rechnung_lesen(rechnung_id: int) -> str:
        """Eine Rechnung mit Positionen."""

        def lauf(db):
            from database.models import Rechnung

            zeile = db.query(Rechnung).filter(Rechnung.id == rechnung_id).first()
            if zeile is None:
                raise _Gesperrt("Rechnung nicht gefunden.")
            return lesen.rechnung_detail(zeile)

        return _ausfuehren(UMFANG_LESEN, lauf)

    @mcp.tool()
    def offene_rechnungen(limit: int = 50) -> str:
        """Offene und teilweise bezahlte Rechnungen."""

        return _ausfuehren(UMFANG_LESEN, lambda db: lesen.offene_rechnungen(db, limit=limit))

    @mcp.tool()
    def faellige_rechnungen(tage: int = 7, limit: int = 50) -> str:
        """Unbezahlte Rechnungen, überfällig oder in den nächsten Tagen fällig."""

        return _ausfuehren(UMFANG_LESEN, lambda db: lesen.faellige_rechnungen(db, tage=tage, limit=limit))

    @mcp.tool()
    def kunden_liste(limit: int = 50) -> str:
        """Kundenstamm."""

        return _ausfuehren(UMFANG_LESEN, lambda db: lesen.liste_kunden(db, limit=limit))

    @mcp.tool()
    def lieferanten_liste(limit: int = 50) -> str:
        """Lieferantenstamm."""

        return _ausfuehren(UMFANG_LESEN, lambda db: lesen.liste_lieferanten(db, limit=limit))

    @mcp.tool()
    def artikel_liste(limit: int = 50) -> str:
        """Artikel und Dienstleistungen."""

        return _ausfuehren(UMFANG_LESEN, lambda db: lesen.liste_artikel(db, limit=limit))

    @mcp.tool()
    def kontenrahmen() -> str:
        """Aktive Buchungskategorien mit der Kontonummer des gewählten Kontenrahmens."""

        return _ausfuehren(UMFANG_LESEN, lesen.kontenrahmen)

    @mcp.tool()
    def ust_saetze() -> str:
        """Hinterlegte Umsatzsteuersätze."""

        return _ausfuehren(UMFANG_LESEN, lesen.ust_saetze)

    return mcp


_werkzeug_namen: list[str] | None = None


def werkzeug_namen() -> list[str]:
    global _werkzeug_namen
    if _werkzeug_namen is None:
        server = baue_server()
        _werkzeug_namen = [werkzeug.name for werkzeug in asyncio.run(server.list_tools())]
    return list(_werkzeug_namen)


def _kopf(scope: dict[str, Any], name: str) -> str | None:
    gesucht = name.lower().encode()
    for schluessel, wert in scope.get("headers") or []:
        if schluessel.lower() == gesucht:
            return wert.decode("latin-1")
    return None


async def _json(send, status: int, text: str) -> None:
    body = json.dumps({"detail": text}).encode()
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
    })
    await send({"type": "http.response.body", "body": body})


def _pruefe(authorization: str | None) -> int | None:
    db = SessionLocal()
    try:
        firma = db.query(Unternehmen).first()
        if firma is None or not firma.mcp_aktiv or not darf(firma.mcp_umfang, UMFANG_LESEN):
            return 404
        if not token_gleich(firma.mcp_token, bearer_token(authorization)):
            return 401
        return None
    finally:
        db.close()


class McpTor:
    """Lässt den Starlette-Lebenszyklus durch und prüft davor das Token."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        status = _pruefe(_kopf(scope, "authorization"))
        if status == 404:
            await _json(send, 404, "Not found")
            return
        if status == 401:
            await _json(send, 401, "Unauthorized")
            return
        await self.app(scope, receive, send)


_inner = None
_stack: contextlib.AsyncExitStack | None = None


def mcp_asgi():
    global _inner
    from mcp.server.transport_security import TransportSecuritySettings

    _inner = baue_server().streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        host="127.0.0.1",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"],
            allowed_origins=[
                "http://127.0.0.1:*",
                "http://localhost:*",
                "http://[::1]:*",
            ],
        ),
    )
    return McpTor(_inner)


async def lebenszyklus_starten() -> None:
    """Startet die MCP-Session. FastAPI reicht den Lebenszyklus eines Mounts nicht weiter."""
    global _stack
    if _stack is not None or _inner is None:
        return
    stack = contextlib.AsyncExitStack()
    await stack.__aenter__()
    try:
        await stack.enter_async_context(_inner.router.lifespan_context(_inner))
    except Exception:
        await stack.aclose()
        raise
    _stack = stack


async def lebenszyklus_stoppen() -> None:
    global _stack
    if _stack is None:
        return
    await _stack.aclose()
    _stack = None
