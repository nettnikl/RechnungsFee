"""Einstellungen der lokalen Schnittstelle. Ohne Token, nur für die App selbst."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database.connection import get_db
from database.models import Unternehmen

from .mcp_laufzeit import werkzeug_namen
from .schnittstelle_kern import (
    UMFANG_LESEN,
    aktivieren,
    deaktivieren,
    rotieren,
    sichtbares_token,
)

router = APIRouter(prefix="/api/schnittstelle", tags=["Schnittstelle"])


class SchnittstelleStatus(BaseModel):
    aktiv: bool
    token: str | None
    umfang: str
    werkzeuge: list[str]


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
        werkzeuge=werkzeug_namen(),
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
