"""Schreib-Werkzeuge für die lokale Schnittstelle.

Lesen bleibt die unterste Stufe. Lesen + Entwürfe legt Eingangsrechnungen als
Entwurf an, hängt den Beleg an und löscht Entwürfe. Finalisieren und Storno
brauchen die Stufe Alles.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import HTTPException
from pydantic import ValidationError

from database.models import Beleg, Kategorie, Lieferant, Rechnung
from database.connection import APP_DATA_DIR

from .lesen import rechnung_kurz
from .lieferanten import create_lieferant
from .rechnungen import (
    BELEG_DIR,
    ERLAUBTE_MIME_TYPES,
    create_rechnung,
    delete_rechnung,
    finalisiere_rechnung,
    storno_rechnung,
)
from .schemas import LieferantCreate, StornoRequest
from .schemas_rechnungen import RechnungCreate, RechnungspositionCreate
from .schnittstelle_kern import UMFANG_ENTWUERFE, UMFANG_VOLL

_MIME = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}
_MAX_BELEG = 20 * 1024 * 1024


class SchreibFehler(Exception):
    pass


def _text(fehler: Exception) -> str:
    if isinstance(fehler, HTTPException):
        detail = fehler.detail
        if isinstance(detail, list):
            return "; ".join(str(eintrag.get("msg", eintrag)) if isinstance(eintrag, dict) else str(eintrag) for eintrag in detail)
        return str(detail)
    if isinstance(fehler, ValidationError):
        return "; ".join(str(eintrag["msg"]) for eintrag in fehler.errors())
    return str(fehler)


def _ruf(funktion):
    try:
        return funktion()
    except (HTTPException, ValidationError, SchreibFehler) as fehler:
        raise SchreibFehler(_text(fehler)) from fehler


def _betrag(wert: str, name: str) -> Decimal:
    try:
        betrag = Decimal(str(wert).strip().replace(",", "."))
    except InvalidOperation as fehler:
        raise SchreibFehler(f"{name} ist keine Zahl.") from fehler
    return betrag


def _datum(wert: str, name: str, *, leer_ist_heute: bool = False) -> date | None:
    text = wert.strip()
    if not text:
        return date.today() if leer_ist_heute else None
    try:
        return date.fromisoformat(text)
    except ValueError as fehler:
        raise SchreibFehler(f"{name} muss JJJJ-MM-TT sein.") from fehler


def _eingang(db, rechnung_id: int) -> Rechnung:
    rechnung = db.query(Rechnung).filter(Rechnung.id == rechnung_id).first()
    if rechnung is None:
        raise SchreibFehler("Rechnung nicht gefunden.")
    if rechnung.typ != "eingang" or (rechnung.dokument_typ or "Rechnung") != "Rechnung":
        raise SchreibFehler("Nur Eingangsrechnungen.")
    return rechnung


def lieferant_speichern(db, firmenname: str, strasse: str, hausnummer: str, plz: str, ort: str, land: str, email: str, telefon: str, ust_idnr: str) -> dict:
    name = firmenname.strip()
    if len(name) < 2:
        raise SchreibFehler("firmenname braucht mindestens 2 Zeichen.")

    def lauf():
        daten = {"firmenname": name, "land": (land.strip() or "DE").upper()}
        for feld, wert in (
            ("strasse", strasse), ("hausnummer", hausnummer), ("plz", plz), ("ort", ort),
            ("email", email), ("telefon", telefon), ("ust_idnr", ust_idnr),
        ):
            text = wert.strip()
            if text:
                daten[feld] = text
        return create_lieferant(LieferantCreate(**daten), db)

    angelegt = _ruf(lauf)
    lieferant = db.query(Lieferant).filter(Lieferant.id == angelegt.id).first()
    return {
        "angelegt": True,
        "id": lieferant.id,
        "firmenname": lieferant.firmenname,
        "lieferantennummer": lieferant.lieferantennummer,
    }


def eingang_anlegen(
    db,
    kategorie_id: int,
    beschreibung: str,
    netto: str,
    lieferant_id: int,
    lieferant_name: str,
    externe_belegnr: str,
    datum: str,
    faellig_am: str,
    menge: str,
    einheit: str,
    ust_satz: str,
    als_entwurf: bool,
    notizen: str,
) -> dict:
    text = beschreibung.strip()
    if len(text) < 2:
        raise SchreibFehler("beschreibung braucht mindestens 2 Zeichen.")
    name = lieferant_name.strip()
    if lieferant_id <= 0 and len(name) < 2:
        raise SchreibFehler("lieferant_id oder lieferant_name ist nötig.")
    kategorie = db.query(Kategorie).filter(Kategorie.id == kategorie_id).first()
    if kategorie is None:
        raise SchreibFehler("Kategorie nicht gefunden. Zuerst kontenrahmen abfragen.")
    satz = ust_satz.strip() or str(kategorie.ust_satz_standard or 0)
    ust = _betrag(satz, "ust_satz")
    if ust < 0 or ust > 100:
        raise SchreibFehler("ust_satz muss zwischen 0 und 100 liegen.")

    def lauf():
        payload = {
            "typ": "eingang",
            "datum": _datum(datum, "datum", leer_ist_heute=True),
            "ist_entwurf": als_entwurf,
            "dokument_typ": "Rechnung",
            "kategorie_id": kategorie_id,
            "positionen": [
                RechnungspositionCreate(
                    beschreibung=text,
                    menge=_betrag(menge, "menge"),
                    einheit=einheit.strip() or "Stück",
                    netto=_betrag(netto, "netto"),
                    ust_satz=ust,
                    kategorie_id=kategorie_id,
                )
            ],
        }
        if lieferant_id > 0:
            payload["lieferant_id"] = lieferant_id
        else:
            payload["partner_freitext"] = name
        faellig = _datum(faellig_am, "faellig_am")
        if faellig:
            payload["faellig_am"] = faellig
        belegnr = externe_belegnr.strip()
        if belegnr:
            payload["externe_belegnr"] = belegnr
        notiz = notizen.strip()
        if notiz:
            payload["notizen"] = notiz
        return create_rechnung(RechnungCreate(**payload), db)

    erzeugt = _ruf(lauf)
    zeile = db.query(Rechnung).filter(Rechnung.id == erzeugt.id).first()
    return {
        "angelegt": True,
        "finalisiert": not bool(zeile.ist_entwurf),
        "rechnung": rechnung_kurz(zeile),
    }


def eingang_finalisieren(db, rechnung_id: int) -> dict:
    _eingang(db, rechnung_id)
    erzeugt = _ruf(lambda: finalisiere_rechnung(rechnung_id, db))
    zeile = db.query(Rechnung).filter(Rechnung.id == erzeugt.id).first()
    return {"finalisiert": True, "rechnung": rechnung_kurz(zeile)}


def eingang_stornieren(db, rechnung_id: int, grund: str) -> dict:
    if len(grund.strip()) < 3:
        raise SchreibFehler("grund braucht mindestens 3 Zeichen.")
    _eingang(db, rechnung_id)
    erzeugt = _ruf(lambda: storno_rechnung(rechnung_id, StornoRequest(grund=grund.strip()), db))
    zeile = db.query(Rechnung).filter(Rechnung.id == erzeugt.id).first()
    return {"storniert": True, "rechnung": rechnung_kurz(zeile)}


def eingang_loeschen(db, rechnung_id: int) -> dict:
    _eingang(db, rechnung_id)
    _ruf(lambda: delete_rechnung(rechnung_id, db))
    return {"geloescht": True, "rechnung_id": rechnung_id}


def eingang_beleg(db, rechnung_id: int, pfad: str) -> dict:
    rechnung = _eingang(db, rechnung_id)
    datei = Path(pfad).expanduser()
    if not datei.is_file():
        raise SchreibFehler("Datei nicht gefunden.")
    mime = _MIME.get(datei.suffix.lower())
    if mime not in ERLAUBTE_MIME_TYPES:
        raise SchreibFehler("Erlaubt sind PDF, JPEG, PNG und TIFF.")
    inhalt = datei.read_bytes()
    if not inhalt or len(inhalt) > _MAX_BELEG:
        raise SchreibFehler("Die Datei ist leer oder größer als 20 MB.")

    jetzt = datetime.now()
    ziel_dir = BELEG_DIR / str(jetzt.year) / jetzt.strftime("%m")
    ziel_dir.mkdir(parents=True, exist_ok=True)
    stem = datei.stem[:50]
    suffix = datei.suffix.lower()
    dateiname_lokal = f"{stem}_{uuid.uuid4().hex[:8]}{suffix}"
    rel_pfad = f"belege/{jetzt.year}/{jetzt.strftime('%m')}/{dateiname_lokal}"
    (ziel_dir / dateiname_lokal).write_bytes(inhalt)

    if rechnung.beleg_id:
        alter = db.query(Beleg).filter(Beleg.id == rechnung.beleg_id).first()
        if alter:
            alter_pfad = APP_DATA_DIR / "uploads" / alter.dateiname
            if alter_pfad.is_file():
                alter_pfad.unlink()
            db.delete(alter)

    beleg = Beleg(
        dateiname=rel_pfad,
        original_name=datei.name,
        mime_type=mime,
        dateigroesse=len(inhalt),
        sha256=hashlib.sha256(inhalt).hexdigest(),
    )
    db.add(beleg)
    db.flush()
    rechnung.beleg_id = beleg.id
    db.commit()
    return {"angehaengt": True, "rechnung_id": rechnung_id, "beleg_id": beleg.id, "dateiname": datei.name}


def registriere(mcp, werkzeug, ausfuehren, verlange, gesperrt) -> None:
    def sicher(stufe: str, funktion):
        def lauf(db):
            try:
                return funktion(db)
            except SchreibFehler as fehler:
                raise gesperrt(str(fehler)) from fehler
        return ausfuehren(stufe, lauf)

    @werkzeug(UMFANG_ENTWUERFE)
    def lieferant_anlegen(
        firmenname: str,
        strasse: str = "",
        hausnummer: str = "",
        plz: str = "",
        ort: str = "",
        land: str = "DE",
        email: str = "",
        telefon: str = "",
        ust_idnr: str = "",
    ) -> str:
        """Legt einen Lieferanten an. Die Nummer vergibt RechnungsFee."""

        return sicher(
            UMFANG_ENTWUERFE,
            lambda db: lieferant_speichern(
                db, firmenname, strasse, hausnummer, plz, ort, land, email, telefon, ust_idnr,
            ),
        )

    @werkzeug(UMFANG_ENTWUERFE)
    def eingangsrechnung_anlegen(
        kategorie_id: int,
        beschreibung: str,
        netto: str,
        lieferant_id: int = 0,
        lieferant_name: str = "",
        externe_belegnr: str = "",
        datum: str = "",
        faellig_am: str = "",
        menge: str = "1",
        einheit: str = "Stück",
        ust_satz: str = "",
        als_entwurf: bool = True,
        notizen: str = "",
    ) -> str:
        """Legt eine Eingangsrechnung an. netto ist der Einzelpreis netto. als_entwurf=true bleibt Entwurf. false finalisiert und braucht die Stufe Alles."""

        def lauf(db):
            if not als_entwurf:
                verlange(UMFANG_VOLL)
            return eingang_anlegen(
                db, kategorie_id, beschreibung, netto, lieferant_id, lieferant_name,
                externe_belegnr, datum, faellig_am, menge, einheit, ust_satz, als_entwurf, notizen,
            )

        return sicher(UMFANG_ENTWUERFE, lauf)

    @werkzeug(UMFANG_VOLL)
    def eingangsrechnung_finalisieren(rechnung_id: int) -> str:
        """Finalisiert einen Eingangsrechnungs-Entwurf. Danach ist er nicht mehr änderbar."""

        return sicher(UMFANG_VOLL, lambda db: eingang_finalisieren(db, rechnung_id))

    @werkzeug(UMFANG_ENTWUERFE)
    def eingangsrechnung_beleg(rechnung_id: int, pfad: str) -> str:
        """Hängt eine lokale PDF- oder Bilddatei an eine Eingangsrechnung."""

        return sicher(UMFANG_ENTWUERFE, lambda db: eingang_beleg(db, rechnung_id, pfad))

    @werkzeug(UMFANG_ENTWUERFE)
    def eingangsrechnung_loeschen(rechnung_id: int) -> str:
        """Löscht eine Eingangsrechnung im Entwurfsstatus."""

        return sicher(UMFANG_ENTWUERFE, lambda db: eingang_loeschen(db, rechnung_id))

    @werkzeug(UMFANG_VOLL)
    def eingangsrechnung_stornieren(rechnung_id: int, grund: str) -> str:
        """Storniert eine finalisierte Eingangsrechnung. Das ist endgültig."""

        return sicher(UMFANG_VOLL, lambda db: eingang_stornieren(db, rechnung_id, grund))
