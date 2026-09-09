import os
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app_db import SessionLocal, Credencial, Categoria, Usuario
from seguridad import verificar_hash_maestro, derivar_clave_fernet, descifrar_contrasena

app = FastAPI(title="LOCKBOX API")

# Obtener ID de la extensión desde variable de entorno o usar el ID por defecto
EXTENSION_ID = os.getenv("EXTENSION_ID", "akahlajpbbkppfnijfoelpgdelfaikkl")

# Configurar middleware CORS con orígenes explícitos
origins = [
    "http://127.0.0.1:5000",
    "http://localhost:5000",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    f"chrome-extension://{EXTENSION_ID}",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)


# Dependencia para obtener la sesión de la base de datos
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/")
def read_root():
    return {"status": "Servidor LOCKBOX activo"}


@app.get("/test-db")
def test_db(db: Session = Depends(get_db)):
    try:
        # Consultamos las tablas para verificar la conexión
        total_usuarios = db.query(Usuario).count()
        total_credenciales = db.query(Credencial).count()
        total_categorias = db.query(Categoria).count()
        
        return {
            "status": "Conexión con PostgreSQL exitosa",
            "db_stats": {
                "usuarios_registrados": total_usuarios,
                "credenciales_almacenadas": total_credenciales,
                "categorias_disponibles": total_categorias
            }
        }
    except Exception:
        return {
            "status": "Error al conectar con la base de datos",
            "detail": "No se pudo establecer conexión con la base de datos."
        }


# Esquema Pydantic para la búsqueda segura de credenciales
class BuscarCredencialesRequest(BaseModel):
    sitio: str
    username: str  # Obligatorio para identificar al usuario
    master_password: str


@app.post("/api/buscar")
def buscar_credenciales(
    payload: BuscarCredencialesRequest,
    db: Session = Depends(get_db)
):
    """
    Busca credenciales por coincidencia parcial en el campo 'sitio_web'
    usando POST con payload JSON seguro y descifra las contraseñas retornadas.
    """
    # 1. Obtener usuario explícitamente
    usuario = db.query(Usuario).filter_by(username=payload.username.strip()).first()
    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado."
        )

    # 2. Validar la contraseña maestra
    if not verificar_hash_maestro(payload.master_password, usuario.master_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Contraseña maestra incorrecta."
        )

    # 3. Derivar la clave de encriptación Fernet con el salt del usuario
    try:
        clave_derivada = derivar_clave_fernet(payload.master_password, usuario.salt_derivacion)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error interno en la derivación de clave."
        )

    # 4. Realizar la búsqueda de las credenciales con coincidencia parcial (case-insensitive)
    credenciales = db.query(Credencial).filter(
        Credencial.usuario_id == usuario.id,
        Credencial.sitio_web.ilike(f"%{payload.sitio.strip()}%")
    ).all()

    # 5. Descifrar y estructurar los resultados de forma segura
    resultados = []
    for cred in credenciales:
        try:
            datos_cifrados = bytes(cred.password_cifrada)
            password_plana = descifrar_contrasena(datos_cifrados, clave_derivada)
            
            resultados.append({
                "id": str(cred.id),
                "sitio": cred.sitio_web,
                "usuario": cred.login_user,
                "password": password_plana
            })
        except Exception:
            # No exponer detalles internos de la excepción al cliente
            resultados.append({
                "id": str(cred.id),
                "sitio": cred.sitio_web,
                "usuario": cred.login_user,
                "password": "[Error al descifrar el registro]"
            })

    return resultados


class CredencialGuardarRequest(BaseModel):
    username: str
    sitio: str
    login_user: str
    encrypted_password: str  # Cadenas Hex / Bytes cifradas enviadas por el cliente
    iv: str | None = None


@app.post("/api/credentials/add")
def guardar_credencial(
    payload: CredencialGuardarRequest,
    db: Session = Depends(get_db)
):
    """Guarda credenciales pre-cifradas en el cliente (Zero-Knowledge)."""
    usuario = db.query(Usuario).filter_by(username=payload.username.strip()).first()
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    payload_cifrado = payload.encrypted_password
    if payload.iv:
        payload_cifrado = f"{payload.iv}:{payload.encrypted_password}"

    nueva_credencial = Credencial(
        usuario_id=usuario.id,
        sitio_web=payload.sitio.strip(),
        login_user=payload.login_user.strip(),
        password_cifrada=payload_cifrado.encode("utf-8")
    )

    db.add(nueva_credencial)
    db.commit()
    db.refresh(nueva_credencial)
    return {"status": "ok", "message": "Credencial guardada de forma segura (Zero-Knowledge)"}


class CredencialListRequest(BaseModel):
    username: str


@app.post("/api/credentials/list")
def listar_credenciales_cifradas(
    payload: CredencialListRequest,
    db: Session = Depends(get_db)
):
    """Devuelve los registros cifrados para que el cliente los descifre localmente."""
    usuario = db.query(Usuario).filter_by(username=payload.username.strip()).first()
    if not usuario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado")

    credenciales = db.query(Credencial).filter(Credencial.usuario_id == usuario.id).all()
    resultado = []
    for cred in credenciales:
        raw_val = bytes(cred.password_cifrada).decode("utf-8", errors="ignore")
        if ":" in raw_val:
            iv, enc = raw_val.split(":", 1)
        else:
            iv, enc = "", raw_val

        resultado.append({
            "id": str(cred.id),
            "sitio": cred.sitio_web,
            "login_user": cred.login_user,
            "encrypted_password": enc,
            "iv": iv
        })
    return resultado
