import os
import uuid
import logging
from datetime import datetime
from contextlib import contextmanager
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import (
    create_engine,
    ForeignKey,
    String,
    LargeBinary,
    DateTime,
    Integer,
    func
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
    Session
)
from sqlalchemy.exc import SQLAlchemyError

# Configuración del sistema de logging para trazabilidad y depuración en producción
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger("app_db")

# Cargar las variables de entorno desde el archivo .env si existe
load_dotenv()

# Cargar la URL de conexión directa desde el archivo .env si existe (p. ej. Supabase en la nube)
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # Si no existe DATABASE_URL, usamos los valores individuales locales
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "password_manager")
    DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
else:
    # Ajuste de compatibilidad para SQLAlchemy (asegura el driver psycopg2)
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
    elif DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+psycopg2://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

try:
    # Creación del motor de SQLAlchemy con pool de conexiones configurado
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,      # Verifica la validez de la conexión antes de usarla
        pool_recycle=3600,       # Recicla conexiones después de una hora
        echo=False               # Establecer en True para depuración de consultas SQL
    )
    # Fábrica de sesiones configurada para no hacer commit ni autoflush automático
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
except Exception as e:
    logger.critical(f"Error al inicializar el motor de la base de datos: {e}")
    raise

# Clase base declarativa (SQLAlchemy 2.0 Style)
class Base(DeclarativeBase):
    pass


class Usuario(Base):
    """
    Modelo que representa la tabla de Usuarios.
    Almacena las credenciales maestras y la identidad única de cada usuario local.
    """
    __tablename__ = "usuarios"

    # UUID nativo autogenerado para seguridad de identificadores expuestos
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    username: Mapped[str] = mapped_column(
        String(150),
        unique=True,
        nullable=False,
        index=True
    )
    # Almacena el hash derivado de la contraseña maestra (usando bcrypt)
    master_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    # Salt aleatorio de 16 bytes único por usuario para derivar la clave de encriptación simétrica Fernet
    salt_derivacion: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False
    )
    # Almacena el hash de la clave de recuperación
    recovery_key_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True
    )

    # Relación uno-a-muchos con las credenciales del usuario
    credenciales: Mapped[list["Credencial"]] = relationship(
        "Credencial",
        back_populates="usuario",
        cascade="all, delete-orphan"  # Borrado en cascada al eliminar el usuario
    )

    def __repr__(self) -> str:
        return f"<Usuario(username={self.username})>"


class Categoria(Base):
    """
    Modelo que representa la tabla de Categorías para clasificar las credenciales.
    Por ejemplo: 'Redes Sociales', 'Bancos', 'Trabajo'.
    """
    __tablename__ = "categorias"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )
    nombre: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False
    )

    # Relación uno-a-muchos con las credenciales asociadas a esta categoría
    credenciales: Mapped[list["Credencial"]] = relationship(
        "Credencial",
        back_populates="categoria"
    )

    def __repr__(self) -> str:
        return f"<Categoria(nombre={self.nombre})>"


class Credencial(Base):
    """
    Modelo que representa la tabla de Credenciales.
    Almacena la información de inicio de sesión cifrada de cada sitio o aplicación.
    """
    __tablename__ = "credenciales"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True
    )
    # Llave foránea que asocia la credencial a un usuario específico
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False
    )
    # Llave foránea opcional que asocia la credencial a una categoría
    categoria_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("categorias.id", ondelete="SET NULL"),
        nullable=True
    )
    
    sitio_web: Mapped[str] = mapped_column(
        String(255),
        nullable=False
    )
    login_user: Mapped[str] = mapped_column(
        String(150),
        nullable=False
    )
    # Almacenamiento en formato bytea (binario) para almacenar la contraseña cifrada
    password_cifrada: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False
    )
    # Marca de tiempo de la última modificación
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    # Relaciones SQLAlchemy para navegación entre objetos
    usuario: Mapped["Usuario"] = relationship(
        "Usuario",
        back_populates="credenciales"
    )
    categoria: Mapped["Categoria | None"] = relationship(
        "Categoria",
        back_populates="credenciales"
    )

    def __repr__(self) -> str:
        return f"<Credencial(sitio_web={self.sitio_web}, login_user={self.login_user})>"


class RevokedToken(Base):
    """
    Modelo que representa la tabla de tokens revocados (lista negra de JTI).
    """
    __tablename__ = "revoked_tokens"

    jti: Mapped[str] = mapped_column(
        String(255),
        primary_key=True,
        index=True
    )
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        nullable=False
    )

    def __repr__(self) -> str:
        return f"<RevokedToken(jti={self.jti})>"


def revocar_jti(jti: str):
    """Agrega un JTI a la lista negra para invalidarlo de inmediato."""
    try:
        with get_db_session() as session:
            existente = session.query(RevokedToken).filter_by(jti=jti).first()
            if not existente:
                nuevo = RevokedToken(jti=jti)
                session.add(nuevo)
    except Exception as e:
        logger.error(f"Error al revocar JTI '{jti}': {e}")


def es_jti_revocado(jti: str) -> bool:
    """Consulta si un JTI ya fue revocado."""
    try:
        with get_db_session() as session:
            res = session.query(RevokedToken).filter_by(jti=jti).first()
            return res is not None
    except Exception as e:
        logger.error(f"Error al consultar JTI revocado '{jti}': {e}")
        return False


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Administrador de contexto (Context Manager) para gestionar las sesiones de la BD.
    Garantiza que la sesión se cierre correctamente y realiza rollback en caso de error.
    
    Yields:
        Session: Sesión activa de SQLAlchemy.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"Error en la transacción de base de datos. Se ejecutó Rollback: {e}")
        raise
    finally:
        session.close()


def poblar_categorias_defecto(session: Session):
    """Puebla la base de datos con las categorías por defecto si estas no existen."""
    categorias_defecto = ["Trabajo", "Redes Sociales", "Bancos", "Juegos", "Otros"]
    for nombre in categorias_defecto:
        existe = session.query(Categoria).filter_by(nombre=nombre).first()
        if not existe:
            nueva_cat = Categoria(nombre=nombre)
            session.add(nueva_cat)


def init_db() -> bool:
    """
    Inicializa la base de datos creando las tablas definidas si no existen.
    Puebla las categorías por defecto en una transacción segura.
    
    Returns:
        bool: True si la inicialización fue exitosa, False en caso contrario.
    """
    logger.info("Iniciando creación de tablas en la base de datos...")
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Tablas inicializadas correctamente o ya existentes.")
        
        # Asegurar que la columna recovery_key_hash exista (en caso de que la tabla ya exista de antes)
        from sqlalchemy import text
        try:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS recovery_key_hash VARCHAR(255);"))
            logger.info("Columna 'recovery_key_hash' verificada/creada con éxito.")
        except Exception as e:
            logger.warning(f"No se pudo asegurar la columna 'recovery_key_hash' mediante ALTER TABLE (puede no ser compatible o ya existir): {e}")

        # Poblar categorías por defecto
        with SessionLocal() as session:
            try:
                poblar_categorias_defecto(session)
                session.commit()
                logger.info("Categorías por defecto verificadas/pobladas con éxito.")
            except Exception as e:
                session.rollback()
                logger.error(f"Error al poblar categorías por defecto: {e}")
                
        return True
    except SQLAlchemyError as e:
        logger.error(f"Error crítico al crear las tablas en la base de datos: {e}")
        return False


def restablecer_password(username: str, clave_recuperacion: str, nueva_password_maestra: str):
    """
    Restablece la contraseña maestra de un usuario utilizando su clave de recuperación.
    """
    from seguridad import generar_hash_maestro, generar_salt_derivacion, verificar_hash_maestro
    
    try:
        with get_db_session() as session:
            # 1. Buscar al usuario
            usuario = session.query(Usuario).filter(Usuario.username == username).first()
            if not usuario:
                return False, "El usuario no existe."

            # 2. Verificar que la clave de recuperación sea correcta
            if not usuario.recovery_key_hash:
                return False, "El usuario no tiene una clave de recuperación configurada."
                
            if not verificar_hash_maestro(clave_recuperacion, usuario.recovery_key_hash):
                return False, "La Clave de Recuperación es incorrecta."

            # 3. Si es correcta, generar nuevo salt y hash para la NUEVA contraseña maestra
            nuevo_salt = generar_salt_derivacion()
            nuevo_hash = generar_hash_maestro(nueva_password_maestra)

            usuario.master_hash = nuevo_hash
            usuario.salt_derivacion = nuevo_salt
            
            return True, "Contraseña actualizada con éxito."

    except Exception as e:
        logger.error(f"Error al restablecer contraseña: {e}")
        return False, f"Error en la base de datos: {str(e)}"


if __name__ == "__main__":
    from seguridad import (
        generar_hash_maestro,
        verificar_hash_maestro,
        generar_salt_derivacion,
        derivar_clave_fernet,
        cifrar_contrasena,
        descifrar_contrasena
    )

    print("=== Probando Conexión e Inicialización de la Base de Datos ===")
    
    try:
        with engine.connect() as connection:
            print(" Conexión exitosa a la base de datos PostgreSQL.")
            
            # Proceder a inicializar las tablas
            db_initialized = init_db()
            if not db_initialized:
                print(" No se pudieron inicializar las tablas. Revisa el log de errores.")
                exit(1)
            
            print(" Estructura de tablas inicializada exitosamente.")
            
    except Exception as err:
        print(" Error al conectar con la base de datos.")
        print(f"Detalle del error: {err}")
        print("\nConsejo: Asegúrate de configurar la variable DATABASE_URL en tu archivo .env con el enlace de Supabase.")
        exit(1)

    print("\n=== Iniciando Demostración del Flujo de Seguridad ===")
    
    # 1. Definir datos de prueba del usuario
    TEST_USER = "usuario_demo"
    TEST_MASTER_PASS = "MiPasswordMaestraSegura123!"
    
    with get_db_session() as session:
        # Limpieza previa para poder ejecutar el script múltiples veces sin errores de clave única
        existing_user = session.query(Usuario).filter_by(username=TEST_USER).first()
        if existing_user:
            print(f" Limpiando datos previos del usuario de prueba '{TEST_USER}'...")
            session.delete(existing_user)
            session.flush()
        
        # 2. Registrar el nuevo usuario
        print(f" Registrando usuario de prueba: '{TEST_USER}'...")
        # Generar hash de la contraseña maestra y salt para la derivación de clave
        hash_maestro = generar_hash_maestro(TEST_MASTER_PASS)
        salt_usuario = generar_salt_derivacion()
        
        nuevo_usuario = Usuario(
            username=TEST_USER,
            master_hash=hash_maestro,
            salt_derivacion=salt_usuario
        )
        session.add(nuevo_usuario)
        session.flush()  # Para obtener el ID generado del usuario
        
        print(" Usuario registrado con éxito en la base de datos.")
        print(f"   -> ID del Usuario (UUID): {nuevo_usuario.id}")
        print(f"   -> Salt Derivación (Hex): {nuevo_usuario.salt_derivacion.hex()}")
        print(f"   -> Hash Maestro: {nuevo_usuario.master_hash}")

    # 3. Simular el login y verificar la contraseña maestra
    print("\n Simulando Login de Usuario...")
    contrasena_ingresada = "MiPasswordMaestraSegura123!" # Cambiar para probar error
    
    with get_db_session() as session:
        usuario_db = session.query(Usuario).filter_by(username=TEST_USER).first()
        if not usuario_db:
            print(" Error: Usuario no encontrado.")
            exit(1)
            
        credenciales_correctas = verificar_hash_maestro(contrasena_ingresada, usuario_db.master_hash)
        if not credenciales_correctas:
            print(" Error: Contraseña maestra incorrecta.")
            exit(1)
            
        print(" ¡Login Exitoso! Contraseña maestra verificada con bcrypt.")
        
        # 4. Derivar clave de cifrado simétrico usando la contraseña ingresada y el salt almacenado
        print(" Derivando clave de cifrado simétrico mediante PBKDF2...")
        clave_cifrado = derivar_clave_fernet(contrasena_ingresada, usuario_db.salt_derivacion)
        print(f"   -> Clave Fernet Derivada (Base64): {clave_cifrado.decode('utf-8')[:15]}...")

        # 5. Cifrar una contraseña de servicio y guardarla
        print("\n Cifrando y guardando credencial de prueba...")
        SITIO = "https://github.com"
        LOGIN = "desarrollador_senior"
        PASS_PLANA = "MiTokenUltraSecretoGithub2026!"
        
        pass_encriptada = cifrar_contrasena(PASS_PLANA, clave_cifrado)
        
        nueva_credencial = Credencial(
            usuario_id=usuario_db.id,
            sitio_web=SITIO,
            login_user=LOGIN,
            password_cifrada=pass_encriptada
        )
        session.add(nueva_credencial)
        session.flush()
        
        print(f" Credencial de prueba guardada para '{SITIO}':")
        print(f"   -> ID Credencial: {nueva_credencial.id}")
        print(f"   -> Contraseña Cifrada (Bytes en BD): {nueva_credencial.password_cifrada[:20]}...")

    # 6. Recuperar la credencial de la BD y descifrarla
    print("\n Recuperando credencial de la base de datos y descifrando...")
    with get_db_session() as session:
        # Obtener el usuario de nuevo (simula una nueva consulta en sesión limpia)
        usuario_db = session.query(Usuario).filter_by(username=TEST_USER).first()
        
        # Volver a derivar la clave (usando la contraseña maestra ingresada anteriormente)
        clave_cifrado = derivar_clave_fernet(contrasena_ingresada, usuario_db.salt_derivacion)
        
        # Obtener las credenciales asociadas al usuario
        credenciales_usuario = usuario_db.credenciales
        for cred in credenciales_usuario:
            decrypted_pass = descifrar_contrasena(cred.password_cifrada, clave_cifrado)
            print(f" Credencial encontrada:")
            print(f"   -> Sitio: {cred.sitio_web}")
            print(f"   -> Login: {cred.login_user}")
            print(f"   -> Contraseña Cifrada (En BD): {cred.password_cifrada[:20]}...")
            print(f"   -> Contraseña Descifrada: {decrypted_pass}")
            
            # Verificación lógica
            if decrypted_pass == PASS_PLANA:
                print(" ¡Prueba superada con éxito! La contraseña coincide con la original.")
            else:
                print(" Error: Las contraseñas no coinciden.")