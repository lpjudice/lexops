import uuid

from fastapi import Depends, Header, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.auth_service import decodificar_token


def get_current_user(
    authorization: str | None = Header(None),
    token: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """Extract and validate JWT from the Authorization: Bearer <token> header.

    Falls back to a ?token= query param so file-download links opened via plain
    browser navigation (<a href>, which carries no Authorization header) can still
    authenticate.
    """
    from jose import JWTError
    from app.models.usuario import Usuario

    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Não autenticado")

    try:
        payload = decodificar_token(token)
        uid = uuid.UUID(payload["sub"])
    except (JWTError, Exception):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido")

    user = db.query(Usuario).filter(Usuario.id == uid, Usuario.ativo == True).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário não encontrado")
    return user


def get_optional_user(
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
):
    """Like get_current_user but returns None instead of raising if not authenticated."""
    from jose import JWTError
    from app.models.usuario import Usuario

    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ")
    try:
        payload = decodificar_token(token)
        uid = uuid.UUID(payload["sub"])
        return db.query(Usuario).filter(Usuario.id == uid, Usuario.ativo == True).first()
    except (JWTError, Exception):
        return None
