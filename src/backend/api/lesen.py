"""Kompakte Leseabfragen für Rechnungen und Stammdaten.

Keine SMTP-Daten, keine Bankzugänge, kein Schnittstellen-Token.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from database.models import Artikel, Kategorie, Kunde, Lieferant, Rechnung, Unternehmen, UstSatz


def _text(wert: Any) -> str | None:
    if wert is None:
        return None
    if isinstance(wert, Decimal):
        return format(wert, "f")
    if isinstance(wert, date):
        return wert.isoformat()
    return str(wert)


def _person(name_firma: str | None, vorname: str | None, nachname: str | None) -> str | None:
    if name_firma:
        return name_firma
    name = " ".join(teil for teil in (vorname, nachname) if teil)
    return name or None


def _grenze(limit: int) -> int:
    return min(max(limit, 1), 200)


def rechnung_kurz(rechnung: Rechnung) -> dict[str, Any]:
    kunde = rechnung.kunde
    lieferant = rechnung.lieferant
    freitext = rechnung.partner_freitext
    return {
        "id": rechnung.id,
        "typ": rechnung.typ,
        "dokument_typ": rechnung.dokument_typ,
        "nummer": rechnung.rechnungsnummer,
        "externe_belegnr": rechnung.externe_belegnr,
        "datum": _text(rechnung.datum),
        "faellig_am": _text(rechnung.faellig_am),
        "kunde_id": rechnung.kunde_id,
        "kunde": _person(kunde.firmenname, kunde.vorname, kunde.nachname) if kunde else (freitext if rechnung.typ == "ausgang" else None),
        "lieferant_id": rechnung.lieferant_id,
        "lieferant": lieferant.firmenname if lieferant else (freitext if rechnung.typ == "eingang" else None),
        "kategorie_id": rechnung.kategorie_id,
        "netto": _text(rechnung.netto_gesamt),
        "ust": _text(rechnung.ust_gesamt),
        "brutto": _text(rechnung.brutto_gesamt),
        "bezahlt": _text(rechnung.bezahlt_betrag),
        "zahlungsstatus": rechnung.zahlungsstatus,
        "ist_entwurf": rechnung.ist_entwurf,
        "storniert": rechnung.storniert,
    }


def rechnung_detail(rechnung: Rechnung) -> dict[str, Any]:
    daten = rechnung_kurz(rechnung)
    daten["notizen"] = rechnung.notizen
    daten["positionen"] = [
        {
            "beschreibung": position.beschreibung,
            "menge": _text(position.menge),
            "einheit": position.einheit,
            "netto": _text(position.netto),
            "ust_satz": _text(position.ust_satz),
            "brutto": _text(position.brutto),
            "kategorie_id": position.kategorie_id,
        }
        for position in rechnung.positionen
    ]
    return daten


def liste_rechnungen(
    db: Session,
    *,
    typ: str | None = None,
    zahlungsstatus: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    query = db.query(Rechnung).order_by(Rechnung.datum.desc(), Rechnung.id.desc())
    if typ:
        query = query.filter(Rechnung.typ == typ)
    if zahlungsstatus == "entwurf":
        query = query.filter(Rechnung.ist_entwurf == True)  # noqa: E712
    elif zahlungsstatus == "storniert":
        query = query.filter(Rechnung.storniert == True)  # noqa: E712
    elif zahlungsstatus:
        query = query.filter(
            Rechnung.zahlungsstatus == zahlungsstatus,
            Rechnung.storniert == False,  # noqa: E712
            Rechnung.ist_entwurf == False,  # noqa: E712
        )
    return [rechnung_kurz(zeile) for zeile in query.limit(_grenze(limit)).all()]


def offene_rechnungen(db: Session, *, limit: int = 50) -> list[dict[str, Any]]:
    zeilen = (
        db.query(Rechnung)
        .filter(Rechnung.zahlungsstatus.in_(["offen", "teilweise"]))
        .filter(Rechnung.storniert == False)  # noqa: E712
        .filter(Rechnung.verrechnet_in_rechnung_id.is_(None))
        .order_by(Rechnung.datum.desc())
        .limit(_grenze(limit))
        .all()
    )
    return [rechnung_kurz(zeile) for zeile in zeilen]


def faellige_rechnungen(db: Session, *, tage: int = 7, limit: int = 50) -> list[dict[str, Any]]:
    bis = date.today() + timedelta(days=tage)
    zeilen = (
        db.query(Rechnung)
        .filter(Rechnung.faellig_am.is_not(None))
        .filter(Rechnung.faellig_am <= bis)
        .filter(Rechnung.zahlungsstatus.in_(["offen", "teilweise"]))
        .filter(Rechnung.storniert == False)  # noqa: E712
        .filter(Rechnung.ist_entwurf == False)  # noqa: E712
        .filter(Rechnung.verrechnet_in_rechnung_id.is_(None))
        .order_by(Rechnung.faellig_am.asc())
        .limit(_grenze(limit))
        .all()
    )
    return [rechnung_kurz(zeile) for zeile in zeilen]


def _kunde(kunde: Kunde) -> dict[str, Any]:
    return {
        "id": kunde.id,
        "name": _person(kunde.firmenname, kunde.vorname, kunde.nachname),
        "kundennummer": kunde.kundennummer,
        "email": kunde.email,
        "telefon": kunde.telefon,
        "strasse": kunde.strasse,
        "hausnummer": kunde.hausnummer,
        "plz": kunde.plz,
        "ort": kunde.ort,
        "land": kunde.land,
        "ust_idnr": kunde.ust_idnr,
        "aktiv": kunde.aktiv,
    }


def _lieferant(lieferant: Lieferant) -> dict[str, Any]:
    return {
        "id": lieferant.id,
        "name": lieferant.firmenname,
        "lieferantennummer": lieferant.lieferantennummer,
        "email": lieferant.email,
        "telefon": lieferant.telefon,
        "strasse": lieferant.strasse,
        "hausnummer": lieferant.hausnummer,
        "plz": lieferant.plz,
        "ort": lieferant.ort,
        "land": lieferant.land,
        "ust_idnr": lieferant.ust_idnr,
        "aktiv": lieferant.aktiv,
    }


def liste_kunden(db: Session, *, limit: int = 50) -> list[dict[str, Any]]:
    zeilen = db.query(Kunde).order_by(Kunde.firmenname, Kunde.nachname).limit(_grenze(limit)).all()
    return [_kunde(zeile) for zeile in zeilen]


def liste_lieferanten(db: Session, *, limit: int = 50) -> list[dict[str, Any]]:
    zeilen = db.query(Lieferant).order_by(Lieferant.firmenname).limit(_grenze(limit)).all()
    return [_lieferant(zeile) for zeile in zeilen]


def artikel_kurz(zeile: Artikel) -> dict[str, Any]:
    return {
        "id": zeile.id,
        "artikelnummer": zeile.artikelnummer,
        "typ": zeile.typ,
        "bezeichnung": zeile.bezeichnung,
        "einheit": zeile.einheit,
        "steuersatz": _text(zeile.steuersatz),
        "vk_netto": _text(zeile.vk_netto),
        "vk_brutto": _text(zeile.vk_brutto),
        "aktiv": zeile.aktiv,
    }


def liste_artikel(db: Session, *, limit: int = 50) -> list[dict[str, Any]]:
    zeilen = db.query(Artikel).order_by(Artikel.bezeichnung).limit(_grenze(limit)).all()
    return [artikel_kurz(zeile) for zeile in zeilen]


def kontenrahmen(db: Session) -> dict[str, Any]:
    firma = db.query(Unternehmen).first()
    rahmen = firma.kontenrahmen if firma else "SKR03"
    feld = {"SKR03": "konto_skr03", "SKR04": "konto_skr04", "SKR49": "konto_skr49"}.get(rahmen, "konto_skr03")
    zeilen = (
        db.query(Kategorie)
        .filter(Kategorie.aktiv == True)  # noqa: E712
        .order_by(Kategorie.kontenart, Kategorie.name)
        .all()
    )
    return {
        "rahmen": rahmen,
        "kategorien": [
            {
                "id": zeile.id,
                "name": zeile.name,
                "kontenart": zeile.kontenart,
                "konto": getattr(zeile, feld),
                "ust_satz_standard": zeile.ust_satz_standard,
                "euer_zeile": zeile.euer_zeile,
            }
            for zeile in zeilen
        ],
    }


def ust_saetze(db: Session) -> list[dict[str, Any]]:
    return [
        {
            "id": zeile.id,
            "satz": _text(zeile.satz),
            "bezeichnung": zeile.bezeichnung,
            "ist_aktiv": zeile.ist_aktiv,
            "ist_default": zeile.ist_default,
        }
        for zeile in db.query(UstSatz).order_by(UstSatz.satz).all()
    ]
