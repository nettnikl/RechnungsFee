"""Einstellungen der lokalen Schnittstelle. Ohne Token, nur für die App selbst."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import Unternehmen

from .mcp_laufzeit import setze_vorgabe, setze_werkzeug, werkzeuge_fuer
from .schnittstelle_kern import (
    UMFANG_LESEN,
    aktivieren,
    deaktivieren,
    rotieren,
    sichtbares_token,
)

router = APIRouter(prefix="/api/schnittstelle", tags=["Schnittstelle"])


class WerkzeugStatus(BaseModel):
    name: str
    an: bool
    stufe: str


class WerkzeugSchaltung(BaseModel):
    name: str
    an: bool


class UmfangSchaltung(BaseModel):
    umfang: str


class SchnittstelleStatus(BaseModel):
    aktiv: bool
    token: str | None
    umfang: str
    werkzeuge: list[WerkzeugStatus]


def _zeile(db: Session) -> Unternehmen:
    firma = db.query(Unternehmen).first()
    if firma is None:
        raise HTTPException(status_code=404, detail="Zuerst das Unternehmen einrichten.")
    return firma


def _status(firma: Unternehmen) -> SchnittstelleStatus:
    return SchnittstelleStatus(
        aktiv=bool(firma.mcp_aktiv),
        token=sichtbares_token(firma),
        umfang=firma.mcp_umfang or UMFANG_LESEN,
        werkzeuge=werkzeuge_fuer(firma),
    )


@router.get("", response_model=SchnittstelleStatus)
def lesen(db: Session = Depends(get_db)) -> SchnittstelleStatus:
    return _status(_zeile(db))


@router.post("/aktivieren", response_model=SchnittstelleStatus)
def einschalten(db: Session = Depends(get_db)) -> SchnittstelleStatus:
    firma = _zeile(db)
    aktivieren(firma)
    db.commit()
    db.refresh(firma)
    return _status(firma)


@router.post("/deaktivieren", response_model=SchnittstelleStatus)
def ausschalten(db: Session = Depends(get_db)) -> SchnittstelleStatus:
    firma = _zeile(db)
    deaktivieren(firma)
    db.commit()
    db.refresh(firma)
    return _status(firma)


@router.post("/umfang", response_model=SchnittstelleStatus)
def umfang_setzen(daten: UmfangSchaltung, db: Session = Depends(get_db)) -> SchnittstelleStatus:
    firma = _zeile(db)
    try:
        setze_vorgabe(firma, daten.umfang)
    except ValueError as fehler:
        raise HTTPException(status_code=422, detail="Unbekannte Vorgabe.") from fehler
    db.commit()
    db.refresh(firma)
    return _status(firma)


@router.post("/werkzeug", response_model=SchnittstelleStatus)
def werkzeug_schalten(daten: WerkzeugSchaltung, db: Session = Depends(get_db)) -> SchnittstelleStatus:
    firma = _zeile(db)
    try:
        setze_werkzeug(firma, daten.name, daten.an)
    except ValueError as fehler:
        raise HTTPException(status_code=404, detail="Werkzeug nicht gefunden.") from fehler
    db.commit()
    db.refresh(firma)
    return _status(firma)


@router.post("/token-rotieren", response_model=SchnittstelleStatus)
def token_rotieren(db: Session = Depends(get_db)) -> SchnittstelleStatus:
    firma = _zeile(db)
    try:
        rotieren(firma)
    except ValueError as fehler:
        raise HTTPException(status_code=409, detail=str(fehler)) from fehler
    db.commit()
    db.refresh(firma)
    return _status(firma)
