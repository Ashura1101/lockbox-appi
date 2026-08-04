import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
# Rate limiting para proteger rutas críticas contra fuerza bruta
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
# Middleware para leer la IP real del usuario detrás de un proxy (Render, Nginx, etc.)
from werkzeug.middleware.proxy_fix import ProxyFix

from app_db import (
    get_db_session,
    Usuario,
    Credencial,
    Categoria,
    init_db
)
from seguridad import (
    verificar_hash_maestro,
    derivar_clave_fernet,
    cifrar_contrasena,
    descifrar_contrasena,
    generar_hash_maestro,
    generar_salt_derivacion,
    generar_clave_recuperacion
)

# Inicialización de la aplicación Flask
app = Flask(__name__)

# Configurar Flask para leer la IP real del usuario detrás de Render u otro reverse proxy.
# Sin esto, flask-limiter ve siempre la IP interna del proxy y el rate limit no funciona bien.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

# Habilitar CORS para permitir que la extensión de Chrome haga peticiones al backend
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app_api")

# ==========================================
# RATE LIMITER — Protección contra fuerza bruta
# ==========================================
# get_remote_address identifica al solicitante por su IP
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],  # Límite global para rutas sin decorador propio
    storage_uri="memory://",  # Contadores almacenados en RAM del servidor
    strategy="fixed-window"   # Ventana fija: cuenta TODAS las peticiones (incluyendo errores 401/400)
)

# Asegurar que las tablas estén inicializadas al arrancar la API
init_db()


@app.route("/api/ping", methods=["GET"])
def ping():
    """Ruta para verificar que la API está viva y respondiendo."""
    return jsonify({"status": "ok", "message": "Servidor del Gestor de Contraseñas activo"}), 200


@app.route("/api/register", methods=["POST"])
@limiter.limit("3 per minute")  # Máximo 3 registros por minuto desde la misma IP
def register():
    """
    Registra un nuevo usuario.
    Recibe JSON: { "username": "...", "master_password": "..." }
    """
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    master_password = data.get("master_password", "").strip()

    if not username or not master_password:
        return jsonify({"error": "El nombre de usuario y la contraseña son requeridos"}), 400

    with get_db_session() as session:
        # Verificar si el usuario ya existe
        usuario_existente = session.query(Usuario).filter_by(username=username).first()
        if usuario_existente:
            return jsonify({"error": "El usuario ya existe"}), 400

        # Crear nuevo usuario con sus sales y hash maestro
        hash_maestro = generar_hash_maestro(master_password)
        salt_derivacion = generar_salt_derivacion()
        clave_raw = generar_clave_recuperacion()
        hash_recuperacion = generar_hash_maestro(clave_raw)

        nuevo_usuario = Usuario(
            username=username,
            master_hash=hash_maestro,
            salt_derivacion=salt_derivacion,
            recovery_key_hash=hash_recuperacion
        )
        session.add(nuevo_usuario)

    return jsonify({
        "message": f"Usuario '{username}' registrado con éxito",
        "recovery_key": clave_raw
    }), 201


@app.route("/api/login", methods=["POST"])
@limiter.limit("5 per minute")  # Bloquea intentos de adivinar la contraseña maestra
def login():
    """
    Autentica al usuario con su contraseña maestra.
    Recibe JSON: { "username": "...", "master_password": "..." }
    """
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    master_password = data.get("master_password", "").strip()

    if not username or not master_password:
        return jsonify({"error": "Faltan credenciales"}), 400

    with get_db_session() as session:
        usuario = session.query(Usuario).filter_by(username=username).first()
        if not usuario:
            return jsonify({"error": "Usuario o contraseña incorrectos"}), 401

        # Verificar contraseña con Bcrypt
        if not verificar_hash_maestro(master_password, usuario.master_hash):
            return jsonify({"error": "Usuario o contraseña incorrectos"}), 401

        return jsonify({
            "message": "Autenticación exitosa",
            "username": usuario.username
        }), 200


@app.route("/api/credentials", methods=["POST"])
@limiter.limit("30 per minute", per_method=True)  # 🧪 TEMPORAL — Restaurar a "30 per minute" después
def get_credentials():
    """
    Obtiene y descifra todas las contraseñas del usuario.
    Recibe JSON: { "username": "...", "master_password": "..." }
    """
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    master_password = data.get("master_password", "").strip()

    if not username or not master_password:
        return jsonify({"error": "Autenticación requerida"}), 400

    with get_db_session() as session:
        usuario = session.query(Usuario).filter_by(username=username).first()
        if not usuario or not verificar_hash_maestro(master_password, usuario.master_hash):
            return jsonify({"error": "Credenciales inválidas"}), 401

        # Derivar clave para descifrar en memoria
        clave_cifrado = derivar_clave_fernet(master_password, usuario.salt_derivacion)

        lista_credenciales = []
        for cred in usuario.credenciales:
            pass_descifrada = descifrar_contrasena(cred.password_cifrada, clave_cifrado)
            lista_credenciales.append({
                "id": str(cred.id),
                "sitio_web": cred.sitio_web,
                "login_user": cred.login_user,
                "password": pass_descifrada,
                "categoria": cred.categoria.nombre if cred.categoria else "Sin Categoría"
            })

        return jsonify({"credenciales": lista_credenciales}), 200


@app.route("/api/credentials/add", methods=["POST"])
@limiter.limit("10 per minute")  # Evita la inserción masiva automatizada de credenciales
def add_credential():
    """
    Guarda una nueva contraseña encriptada en la base de datos.
    Recibe JSON: { 
        "username": "...", 
        "master_password": "...", 
        "sitio_web": "...", 
        "login_user": "...", 
        "password": "..." 
    }
    """
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    master_password = data.get("master_password", "").strip()
    sitio_web = data.get("sitio_web", "").strip()
    login_user = data.get("login_user", "").strip()
    password_guardar = data.get("password", "").strip()

    if not all([username, master_password, sitio_web, login_user, password_guardar]):
        return jsonify({"error": "Todos los campos son obligatorios"}), 400

    with get_db_session() as session:
        usuario = session.query(Usuario).filter_by(username=username).first()
        if not usuario or not verificar_hash_maestro(master_password, usuario.master_hash):
            return jsonify({"error": "Credenciales inválidas"}), 401

        # Derivar clave Fernet y cifrar la nueva contraseña
        clave_cifrado = derivar_clave_fernet(master_password, usuario.salt_derivacion)
        pass_cifrada = cifrar_contrasena(password_guardar, clave_cifrado)

        nueva_cred = Credencial(
            usuario_id=usuario.id,
            sitio_web=sitio_web,
            login_user=login_user,
            password_cifrada=pass_cifrada
        )
        session.add(nueva_cred)

        return jsonify({"message": f"Credencial para '{sitio_web}' guardada con éxito"}), 201

# ==========================================
# ELIMINAR CREDENCIAL
# ==========================================
@app.route('/api/credentials/delete', methods=['POST'])
@limiter.limit("10 per minute")  # Previene eliminación masiva de credenciales
def delete_credential():
    try:
        import uuid
        data = request.json or {}
        cred_id = data.get('id')
        username = data.get('username')
        master_password = data.get('master_password')

        if not cred_id or not username or not master_password:
            return jsonify({'error': 'Faltan parámetros requeridos'}), 400

        try:
            cred_uuid = uuid.UUID(cred_id)
        except ValueError:
            return jsonify({'error': 'ID de credencial inválido'}), 400

        with get_db_session() as session:
            usuario = session.query(Usuario).filter_by(username=username).first()
            if not usuario or not verificar_hash_maestro(master_password, usuario.master_hash):
                return jsonify({'error': 'Contraseña maestra incorrecta'}), 401

            credencial = session.query(Credencial).filter_by(id=cred_uuid, usuario_id=usuario.id).first()
            if not credencial:
                return jsonify({'error': 'Credencial no encontrada'}), 404

            session.delete(credencial)

        return jsonify({'message': 'Credencial eliminada exitosamente'}), 200

    except Exception as e:
        logger.error(f"Error al eliminar: {str(e)}")
        return jsonify({'error': f'Error interno: {str(e)}'}), 500


# ==========================================
# EDITAR CREDENCIAL
# ==========================================
@app.route('/api/credentials/update', methods=['POST'])
@limiter.limit("10 per minute")  # Previene modificaciones masivas automatizadas
def update_credential():
    try:
        import uuid
        data = request.json or {}
        cred_id = data.get('id')
        username = data.get('username')
        master_password = data.get('master_password')
        sitio_web = data.get('sitio_web')
        login_user = data.get('login_user')
        new_password = data.get('password')

        if not cred_id or not username or not master_password:
            return jsonify({'error': 'Faltan parámetros requeridos'}), 400

        try:
            cred_uuid = uuid.UUID(cred_id)
        except ValueError:
            return jsonify({'error': 'ID de credencial inválido'}), 400

        with get_db_session() as session:
            usuario = session.query(Usuario).filter_by(username=username).first()
            if not usuario or not verificar_hash_maestro(master_password, usuario.master_hash):
                return jsonify({'error': 'Contraseña maestra incorrecta'}), 401

            credencial = session.query(Credencial).filter_by(id=cred_uuid, usuario_id=usuario.id).first()
            if not credencial:
                return jsonify({'error': 'Credencial no encontrada'}), 404

            if sitio_web is not None:
                credencial.sitio_web = sitio_web
            if login_user is not None:
                credencial.login_user = login_user

            if new_password:
                clave_cifrado = derivar_clave_fernet(master_password, usuario.salt_derivacion)
                pass_cifrada = cifrar_contrasena(new_password, clave_cifrado)
                credencial.password_cifrada = pass_cifrada

        return jsonify({'message': 'Credencial actualizada con éxito'}), 200

    except Exception as e:
        logger.error(f"Error al actualizar: {str(e)}")
        return jsonify({'error': f'Error interno: {str(e)}'}), 500


# ==========================================
# BUSCAR CATEGORÍAS
# ==========================================
@app.route('/api/categories', methods=['GET'])
def get_categories():
    """Obtiene todas las categorías disponibles."""
    try:
        with get_db_session() as session:
            categorias = session.query(Categoria).order_by(Categoria.nombre).all()
            return jsonify({
                'categories': [{"id": str(c.id), "nombre": c.nombre} for c in categorias]
            }), 200
    except Exception as e:
        logger.error(f"Error al obtener categorías: {str(e)}")
        return jsonify({'error': 'Error interno'}), 500


# ==========================================
# MANEJADOR DE ERROR 429 — Rate Limit Superado
# ==========================================
@app.errorhandler(429)
def ratelimit_handler(e):
    """Responde de forma limpia cuando un cliente supera el límite de peticiones."""
    return jsonify({
        "error": "Has superado el límite de intentos. Por favor, espera un momento y vuelve a intentarlo."
    }), 429


if __name__ == "__main__":
    print("🚀 Servidor API iniciando en http://127.0.0.1:5000")
    app.run(debug=True, port=5000)