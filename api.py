from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from app_db import SessionLocal, Credencial, Categoria, Usuario
from seguridad import verificar_hash_maestro, derivar_clave_fernet, descifrar_contrasena

app = FastAPI(title="LOCKBOX API")

# Configurar middleware CORS para permitir peticiones desde la extensión de Chrome
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Permite todos los orígenes para desarrollo local
    allow_credentials=True,
    allow_methods=["*"],  # Permite todos los métodos HTTP
    allow_headers=["*"],  # Permite todos los encabezados HTTP
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
    except Exception as e:
        return {
            "status": "Error al conectar con la base de datos",
            "detail": str(e)
        }

@app.get("/api/buscar")
def buscar_credenciales(
    sitio: str = Query(..., description="Nombre o dominio del sitio web a buscar"),
    username: str = Query(None, description="Nombre del usuario dueño de la bóveda (opcional para pruebas locales)"),
    master_password: str = Query(None, description="Contraseña maestra necesaria para descifrar las contraseñas"),
    db: Session = Depends(get_db)
):
    """
    Busca credenciales por coincidencia parcial en el campo 'sitio_web'
    y descifra las contraseñas antes de retornarlas.
    """
    # 1. Obtener el usuario dueño de la bóveda
    if not username:
        # Si no se proporciona usuario, intentamos tomar el primero registrado (útil para entorno local monousuario)
        usuario = db.query(Usuario).first()
        if not usuario:
            raise HTTPException(status_code=404, detail="No se encontraron usuarios registrados en la base de datos.")
        username = usuario.username
    else:
        usuario = db.query(Usuario).filter_by(username=username).first()
        if not usuario:
            raise HTTPException(status_code=404, detail=f"El usuario '{username}' no existe.")

    # 2. Verificar que se haya enviado la contraseña maestra para realizar el descifrado
    if not master_password:
        raise HTTPException(
            status_code=400, 
            detail="Se requiere el parámetro 'master_password' para autenticar y descifrar los datos."
        )

    # 3. Validar la contraseña maestra
    if not verificar_hash_maestro(master_password, usuario.master_hash):
        raise HTTPException(status_code=401, detail="Contraseña maestra incorrecta.")

    # 4. Derivar la clave de encriptación Fernet con el salt del usuario
    try:
        clave_derivada = derivar_clave_fernet(master_password, usuario.salt_derivacion)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al derivar la clave: {str(e)}")

    # 5. Realizar la búsqueda de las credenciales con coincidencia parcial (case-insensitive)
    credenciales = db.query(Credencial).filter(
        Credencial.usuario_id == usuario.id,
        Credencial.sitio_web.ilike(f"%{sitio}%")
    ).all()

    # 6. Descifrar y estructurar los resultados
    resultados = []
    for cred in credenciales:
        try:
            # Asegurar conversión de memoryview u otros tipos similares a bytes
            datos_cifrados = bytes(cred.password_cifrada)
            password_plana = descifrar_contrasena(datos_cifrados, clave_derivada)
            
            resultados.append({
                "id": str(cred.id),
                "sitio": cred.sitio_web,
                "usuario": cred.login_user,
                "password": password_plana
            })
        except Exception as e:
            # Si falla la desencripción de algún registro individual (ej. datos corruptos)
            resultados.append({
                "id": str(cred.id),
                "sitio": cred.sitio_web,
                "usuario": cred.login_user,
                "password": f"[Error al descifrar: {str(e)}]"
            })

    return resultados
