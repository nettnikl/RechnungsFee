"""Token-Lebenszyklus, Umfang-Leiter und Migration 183. Kein Zugriff auf die echte Buchhaltung."""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import main
from api import mcp_laufzeit
from api.schnittstelle import ausschalten, einschalten, lesen, token_rotieren
from api.schnittstelle_kern import (
    UMFANG_ENTWUERFE,
    UMFANG_LESEN,
    UMFANG_VOLL,
    aktivieren,
    darf,
    deaktivieren,
    rotieren,
    sichtbares_token,
)
from database.connection import Base
from database.models import Unternehmen


def test_token_bleibt_beim_aus_und_einschalten():
    zeile = SimpleNamespace(mcp_aktiv=False, mcp_token=None, mcp_umfang=UMFANG_LESEN)
    aktivieren(zeile)
    token = zeile.mcp_token
    assert token
    deaktivieren(zeile)
    assert zeile.mcp_aktiv is False
    assert zeile.mcp_token == token
    assert sichtbares_token(zeile) is None
    aktivieren(zeile)
    assert zeile.mcp_token == token
    assert sichtbares_token(zeile) == token


def test_rotieren_nur_wenn_an():
    zeile = SimpleNamespace(mcp_aktiv=False, mcp_token="alt", mcp_umfang=UMFANG_LESEN)
    with pytest.raises(ValueError):
        rotieren(zeile)
    assert zeile.mcp_token == "alt"
    zeile.mcp_aktiv = True
    rotieren(zeile)
    assert zeile.mcp_token != "alt"


def test_umfang_leiter():
    assert darf(UMFANG_LESEN, UMFANG_LESEN)
    assert not darf(UMFANG_LESEN, UMFANG_ENTWUERFE)
    assert not darf(UMFANG_LESEN, UMFANG_VOLL)
    assert darf(UMFANG_ENTWUERFE, UMFANG_LESEN)
    assert darf(UMFANG_ENTWUERFE, UMFANG_ENTWUERFE)
    assert not darf(UMFANG_ENTWUERFE, UMFANG_VOLL)
    assert darf(UMFANG_VOLL, UMFANG_ENTWUERFE)
    assert not darf("anders", UMFANG_LESEN)
    assert not darf(None, UMFANG_LESEN)


def _firma_db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'schnittstelle.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as session:
        session.add(Unternehmen(
            firmenname="Test", strasse="Weg", hausnummer="1", plz="12345", ort="Ort",
        ))
        session.commit()
    return Session


def _status(aufruf):
    with pytest.raises(HTTPException) as gefangen:
        aufruf()
    return gefangen.value.status_code


def test_api_token_unsichtbar_wenn_aus(tmp_path, monkeypatch):
    Session = _firma_db(tmp_path)
    monkeypatch.setattr(mcp_laufzeit, "SessionLocal", Session)
    with Session() as db:
        assert lesen(db).token is None
        assert mcp_laufzeit._pruefe(None) == 404

        an = einschalten(db)
        assert an.aktiv is True
        token = an.token
        assert token

        aus = ausschalten(db)
        assert aus.aktiv is False
        assert aus.token is None
        assert mcp_laufzeit._pruefe(f"Bearer {token}") == 404

        wieder = einschalten(db)
        assert wieder.token == token
        assert mcp_laufzeit._pruefe(None) == 401
        assert mcp_laufzeit._pruefe(f"Bearer {token}") is None

        neu = token_rotieren(db)
        assert neu.token != token
        ausschalten(db)
        assert _status(lambda: token_rotieren(db)) == 409
        assert db.query(Unternehmen).one().mcp_token == neu.token
        assert db.query(Unternehmen).one().mcp_umfang == UMFANG_LESEN


def test_mcp_tor_und_werkzeuge(tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    Session = _firma_db(tmp_path)
    with Session() as session:
        firma = session.query(Unternehmen).one()
        aktivieren(firma)
        firma.mcp_umfang = UMFANG_LESEN
        session.commit()
        token = firma.mcp_token

    monkeypatch.setattr(mcp_laufzeit, "SessionLocal", Session)
    assert mcp_laufzeit._pruefe(None) == 401
    assert mcp_laufzeit._pruefe(f"Bearer {token}") is None

    with Session() as session:
        firma = session.query(Unternehmen).one()
        deaktivieren(firma)
        session.commit()
    assert mcp_laufzeit._pruefe(f"Bearer {token}") == 404

    with Session() as session:
        firma = session.query(Unternehmen).one()
        aktivieren(firma)
        session.commit()

    server = mcp_laufzeit.baue_server()
    namen = {werkzeug.name for werkzeug in asyncio.run(server.list_tools())}
    assert {"rechnungen_liste", "kontenrahmen", "kunden_liste"} <= namen
    assert not any("anlegen" in name or "storno" in name or "loesch" in name for name in namen)

    text_ausgabe = mcp_laufzeit._ausfuehren(UMFANG_ENTWUERFE, lambda db: {"ok": True})
    assert "nicht frei" in text_ausgabe


async def _post(app, path: str, body: bytes, authorization: str | None):
    messages = []
    gesendet = False
    fertig = asyncio.Event()
    headers = [
        (b"host", b"127.0.0.1:8002"),
        (b"content-type", b"application/json"),
        (b"accept", b"application/json, text/event-stream"),
    ]
    if authorization:
        headers.append((b"authorization", authorization.encode()))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 8002),
    }

    async def receive():
        nonlocal gesendet
        if gesendet:
            await fertig.wait()
            return {"type": "http.disconnect"}
        gesendet = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)
        if message["type"] == "http.response.body" and not message.get("more_body", False):
            fertig.set()

    await app(scope, receive, send)
    status = next(eintrag["status"] for eintrag in messages if eintrag["type"] == "http.response.start")
    inhalt = b"".join(eintrag.get("body", b"") for eintrag in messages if eintrag["type"] == "http.response.body")
    return status, inhalt


def test_mcp_http_nur_wenn_aktiv(tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    from fastapi import FastAPI

    Session = _firma_db(tmp_path)
    with Session() as session:
        firma = session.query(Unternehmen).one()
        aktivieren(firma)
        session.commit()
        token = firma.mcp_token

    monkeypatch.setattr(mcp_laufzeit, "SessionLocal", Session)
    app = FastAPI()
    app.mount("/mcp", mcp_laufzeit.mcp_asgi())
    body = b'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"0"}}}'

    async def lauf():
        await mcp_laufzeit.lebenszyklus_starten()
        try:
            ohne = await _post(app, "/mcp/", body, None)
            mit = await _post(app, "/mcp/", body, f"Bearer {token}")
            kurz = await _post(app, "/mcp", body, f"Bearer {token}")
            return ohne, mit, kurz
        finally:
            await mcp_laufzeit.lebenszyklus_stoppen()

    ohne, mit, kurz = asyncio.run(lauf())
    assert ohne[0] == 401
    assert mit[0] == 200
    assert b"Nur-Lese-Zugriff" in mit[1]
    assert kurz[0] == 307

    with Session() as session:
        deaktivieren(session.query(Unternehmen).one())
        session.commit()
    status, _inhalt = asyncio.run(_post(app, "/mcp/", body, f"Bearer {token}"))
    assert status == 404


def test_migration_183(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'alt.db'}")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        session.add(Unternehmen(firmenname="T", strasse="S", hausnummer="1", plz="12345", ort="O"))
        session.commit()
    with engine.begin() as conn:
        for spalte in ("mcp_aktiv", "mcp_token", "mcp_umfang"):
            conn.execute(text(f"ALTER TABLE unternehmen DROP COLUMN {spalte}"))
        conn.execute(text("PRAGMA user_version = 182"))
    monkeypatch.setattr(main, "engine", engine)
    main._run_migrations()
    main._run_migrations()
    with engine.connect() as conn:
        spalten = {r[1] for r in conn.execute(text("PRAGMA table_info(unternehmen)"))}
        version = conn.execute(text("PRAGMA user_version")).scalar()
    assert version == 183
    assert {"mcp_aktiv", "mcp_token", "mcp_umfang"} <= spalten


def test_ohne_firma_ist_404(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'leer.db'}")
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        assert _status(lambda: lesen(db)) == 404
