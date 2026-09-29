import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
# Rate limiting para proteger rutas críticas contra fuerza bruta
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
# Middleware para leer la IP real del usuario detrás de un proxy (Render, Nginx, etc.)
from werkzeug.middleware.proxy_fix import ProxyFix

from functools import wraps
from app_db import (
    get_db_session,
    Usuario,
    Credencial,
    Categoria,
    init_db,
    revocar_jti,
    es_jti_revocado
)
from seguridad import (
    verificar_hash_maestro,
    derivar_clave_fernet,
    cifrar_contrasena,
    descifrar_contrasena,
    generar_hash_maestro,
    generar_salt_derivacion,
    generar_clave_recuperacion,
    normalize_domain,
    generar_par_tokens,
    verificar_token
)
from sqlalchemy.exc import IntegrityError
import os
import sys
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

# Lista de variables obligatorias
REQUIRED_ENV_VARS = ["DATABASE_URL", "JWT_SECRET_KEY"]

# Verificación Fail-Fast
for var in REQUIRED_ENV_VARS:
    if not os.getenv(var):
        print(f"[ERROR CRÍTICO] La variable de entorno '{var}' no está definida. Deteniendo el servidor.")
        sys.exit(1)

# Inicialización de la aplicación Flask
app = Flask(__name__)

# Configurar Flask para leer la IP real del usuario detrás de Render u otro reverse proxy.
# Sin esto, flask-limiter ve siempre la IP interna del proxy y el rate limit no funciona bien.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

# ==========================================
# LISTA BLANCA DE ORÍGENES PERMITIDOS (CORS)
# ==========================================
# Orígenes de desarrollo local basados en app_api.py (puerto 5000) y servidores dev (8000).
# Para la extensión de Chrome o frontend en producción, configurar la variable de entorno ALLOWED_ORIGINS
# (valores separados por coma, ej: "chrome-extension://<ID_REAL>,https://midominio.com").
# NOTA: No se inventa un ID fijo para la extensión de Chrome porque Lockbox_Extension/manifest.json
# no define una clave 'key' fija; su ID varía entre instalaciones sin empaquetar o al publicarse.
DEFAULT_ALLOWED_ORIGINS = [
    "http://127.0.0.1:5000",
    "http://localhost:5000",
    "http://127.0.0.1:8000",
    "http://localhost:8000",
]

raw_allowed_origins = os.getenv("ALLOWED_ORIGINS")
if raw_allowed_origins:
    ALLOWED_ORIGINS = [o.strip() for o in raw_allowed_origins.split(",") if o.strip()]
else:
    ALLOWED_ORIGINS = list(DEFAULT_ALLOWED_ORIGINS)

# Soporte opcional para EXTENSION_ID (siguiendo el patrón observado en api.py)
extension_id = os.getenv("EXTENSION_ID")
if extension_id:
    chrome_ext_origin = f"chrome-extension://{extension_id.strip()}"
    if chrome_ext_origin not in ALLOWED_ORIGINS:
        ALLOWED_ORIGINS.append(chrome_ext_origin)

# Configuración de CORS con lista blanca explícita
CORS(
    app,
    resources={r"/api/*": {"origins": ALLOWED_ORIGINS}},
    supports_credentials=True,
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app_api")

# ==========================================
# RATE LIMITER — Protección contra fuerza bruta
# ==========================================
# get_remote_address identifica al solicitante por su IP
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["60 per minute"],  # Límite global por minuto por defecto
    storage_uri="memory://",            # Contadores almacenados en RAM del servidor
    strategy="fixed-window"             # Ventana fija
)


# ==========================================
# ENCABEZADOS DE SEGURIDAD HTTP
# ==========================================
@app.after_request
def apply_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Content-Security-Policy'] = "default-src 'none'"
    return response


# ==========================================
# PREFLIGHT CORS — Respuesta OPTIONS global
# ==========================================
@app.route('/api/<path:path>', methods=['OPTIONS'])
def cors_preflight(path):
    """Responde las peticiones preflight con 200 y cabeceras Access-Control-Allow-* solo si el origen está permitido."""
    response = jsonify({'message': 'CORS preflight OK'})
    origin = request.headers.get('Origin')
    if origin and origin in ALLOWED_ORIGINS:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Max-Age'] = '86400'
    return response, 200


# ==========================================
# DECORADOR AUTENTICACIÓN JWT Y LISTA NEGRA
# ==========================================
def token_requerido(f):
    @wraps(f)
    def decorator(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Token de acceso requerido"}), 401

        token = auth_header.split(" ")[1]
        payload, error = verificar_token(token, expected_type="access")

        if error:
            return jsonify({"error": error}), 401

        if es_jti_revocado(payload["jti"]):
            return jsonify({"error": "El token ha sido revocado"}), 401

        request.user_id = payload["sub"]
        request.token_jti = payload["jti"]
        return f(*args, **kwargs)
    return decorator


def token_opcional_log(f):
    @wraps(f)
    def decorator(*args, **kwargs):
        auth_header = request.headers.get("Authorization")

        if not auth_header or not auth_header.startswith("Bearer "):
            logger.warning(f"[JWT_SOFT_LAUNCH] sin_token ruta={request.path} metodo={request.method}")
            return f(*args, **kwargs)

        token = auth_header.split(" ")[1]

        try:
            payload, error = verificar_token(token, expected_type="access")
        except Exception:
            logger.warning(f"[JWT_SOFT_LAUNCH] error_verificacion ruta={request.path}")
            return f(*args, **kwargs)

        if error:
            logger.warning(f"[JWT_SOFT_LAUNCH] token_invalido ruta={request.path} metodo={request.method} motivo={error}")
        elif es_jti_revocado(payload["jti"]):
            logger.warning(f"[JWT_SOFT_LAUNCH] token_revocado ruta={request.path} sub={payload['sub']}")
        else:
            logger.info(f"[JWT_SOFT_LAUNCH] token_valido ruta={request.path} sub={payload['sub']}")

        return f(*args, **kwargs)
    return decorator


# Asegurar que las tablas estén inicializadas al arrancar la API
init_db()


@app.route("/api/ping", methods=["GET"])
def ping():
    """Ruta para verificar que la API está viva y respondiendo."""
    return jsonify({"status": "ok", "message": "Servidor del Gestor de Contraseñas activo"}), 200


# Endpoint: Refresh Token Rotativo
@app.route("/api/auth/refresh", methods=["POST"])
@limiter.limit("10 per minute")
def refresh():
    data = request.get_json() or {}
    refresh_token = data.get("refresh_token")

    if not refresh_token:
        return jsonify({"error": "refresh_token requerido"}), 400

    payload, error = verificar_token(refresh_token, expected_type="refresh")
    if error or es_jti_revocado(payload["jti"]):
        return jsonify({"error": "Refresh token inválido o revocado"}), 401

    # Rotación obligatoria: revocar el refresh_token usado
    revocar_jti(payload["jti"])

    # Emitir nuevo par de tokens
    new_access, new_refresh, _ = generar_par_tokens(payload["sub"])
    return jsonify({
        "access_token": new_access,
        "refresh_token": new_refresh
    }), 200


# Endpoint: Logout / Revocación
@app.route("/api/auth/logout", methods=["POST"])
@token_requerido
def logout():
    data = request.get_json() or {}
    refresh_token = data.get("refresh_token")

    # Revocar el access_token actual
    revocar_jti(request.token_jti)

    # Revocar el refresh_token asociado si se envía
    if refresh_token:
        payload, _ = verificar_token(refresh_token, expected_type="refresh")
        if payload:
            revocar_jti(payload["jti"])

    return jsonify({"mensaje": "Sesión cerrada correctamente"}), 200


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

    if len(master_password) < 8:
        return jsonify({"error": "La contraseña maestra debe tener al menos 8 caracteres"}), 400

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

        # Generar pareja de tokens JWT (Access + Refresh)
        access_token, refresh_token, _ = generar_par_tokens(str(usuario.id))

        return jsonify({
            "message": "Autenticación exitosa",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "username": usuario.username
        }), 200


@app.route("/api/credentials", methods=["POST"])
@limiter.limit("30 per minute", per_method=True)
@token_opcional_log
def get_credentials():
    """
    Obtiene y descifra las contraseñas del usuario, opcionalmente filtradas por query.
    Recibe JSON: { "username": "...", "master_password": "...", "query": "..." (opcional) }
    """
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    master_password = data.get("master_password", "").strip()
    query = data.get("query", "").strip().lower()

    if not username or not master_password:
        return jsonify({"error": "Autenticación requerida"}), 400

    with get_db_session() as session:
        usuario = session.query(Usuario).filter_by(username=username).first()
        if not usuario or not verificar_hash_maestro(master_password, usuario.master_hash):
            return jsonify({"error": "Credenciales inválidas"}), 401

        # Derivar clave para descifrar en memoria
        clave_cifrado = derivar_clave_fernet(master_password, usuario.salt_derivacion)

        credenciales_query = session.query(Credencial).filter(Credencial.usuario_id == usuario.id)

        if query:
            search_terms = [query]
            clean_query = query.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
            if clean_query not in search_terms:
                search_terms.append(clean_query)
            if "." in clean_query:
                base_domain = clean_query.split(".")[0]
                if len(base_domain) > 2 and base_domain not in search_terms:
                    search_terms.append(base_domain)

            from sqlalchemy import or_
            filters = [Credencial.sitio_web.ilike(f"%{term}%") for term in search_terms]
            filters.append(Credencial.login_user.ilike(f"%{query}%"))
            credenciales_query = credenciales_query.filter(or_(*filters))

        lista_credenciales = []
        for cred in credenciales_query.all():
            pass_descifrada = descifrar_contrasena(cred.password_cifrada, clave_cifrado)
            lista_credenciales.append({
                "id": str(cred.id),
                "sitio_web": cred.sitio_web,
                "login_user": cred.login_user,
                "password": pass_descifrada,
                "categoria": cred.categoria.nombre if cred.categoria else "Sin Categoría"
            })

        return jsonify({"credenciales": lista_credenciales}), 200


@app.route("/api/credentials/search", methods=["POST"])
@limiter.limit("30 per minute")
@token_opcional_log
def search_credentials():
    """
    Busca credenciales utilizando coincidencia inclusiva por FQDN y nombre base.
    """
    data = request.get_json() or {}
    query = data.get("query", "").strip().lower()
    username = data.get("username", "").strip()
    master_password = data.get("master_password", "").strip()

    if not username or not master_password:
        return jsonify({"error": "Parámetros username y master_password son requeridos"}), 400

    if not query:
        return jsonify([])

    with get_db_session() as session:
        usuario = session.query(Usuario).filter_by(username=username).first()
        if not usuario or not verificar_hash_maestro(master_password, usuario.master_hash):
            return jsonify({"error": "Credenciales inválidas"}), 401

        search_terms = [query]
        clean_query = query.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
        if clean_query not in search_terms:
            search_terms.append(clean_query)
        if "." in clean_query:
            base_domain = clean_query.split(".")[0]
            if len(base_domain) > 2 and base_domain not in search_terms:
                search_terms.append(base_domain)

        from sqlalchemy import or_
        filters = [Credencial.sitio_web.ilike(f"%{term}%") for term in search_terms]
        filters.append(Credencial.login_user.ilike(f"%{query}%"))

        results = session.query(Credencial).filter(
            Credencial.usuario_id == usuario.id,
            or_(*filters)
        ).all()

        clave_cifrado = derivar_clave_fernet(master_password, usuario.salt_derivacion)
        lista_resultados = []
        for c in results:
            pass_descifrada = descifrar_contrasena(c.password_cifrada, clave_cifrado)
            lista_resultados.append({
                "id": str(c.id),
                "sitio_web": c.sitio_web,
                "login_user": c.login_user,
                "password": pass_descifrada,
                "categoria": c.categoria.nombre if c.categoria else "Sin Categoría"
            })

        return jsonify(lista_resultados), 200




@app.route("/api/credentials/add", methods=["POST"])
@limiter.limit("10 per minute")  # Evita la inserción masiva automatizada de credenciales
@token_opcional_log
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
    raw_sitio = data.get("sitio_web", "").strip()
    login_user = data.get("login_user", "").strip()
    password_guardar = data.get("password", "").strip()
    categoria = data.get("categoria")

    sitio_web = normalize_domain(raw_sitio)

    if not all([username, master_password, sitio_web, login_user, password_guardar]):
        return jsonify({"error": "Todos los campos son obligatorios"}), 400

    try:
        with get_db_session() as session:
            usuario = session.query(Usuario).filter_by(username=username).first()
            if not usuario or not verificar_hash_maestro(master_password, usuario.master_hash):
                return jsonify({"error": "Credenciales inválidas"}), 401

            # Prevenir duplicados: ya existe una credencial con el mismo sitio normalizado y login_user
            existente = session.query(Credencial).filter_by(
                usuario_id=usuario.id,
                sitio_web=sitio_web,
                login_user=login_user
            ).first()
            if existente:
                return jsonify({
                    "error": "Ya existe una credencial para este sitio y usuario",
                    "existing_id": str(existente.id)
                }), 409

            # Derivar clave Fernet y cifrar la nueva contraseña
            clave_cifrado = derivar_clave_fernet(master_password, usuario.salt_derivacion)
            pass_cifrada = cifrar_contrasena(password_guardar, clave_cifrado)

            nueva_cred = Credencial(
                usuario_id=usuario.id,
                sitio_web=sitio_web,
                login_user=login_user,
                password_cifrada=pass_cifrada
            )

            if categoria:
                nombre_cat = categoria.strip()
                if nombre_cat.lower() != 'sin categoría':
                    cat = session.query(Categoria).filter_by(nombre=nombre_cat).first()
                    if not cat:
                        cat = Categoria(nombre=nombre_cat)
                        session.add(cat)
                        session.flush()
                    nueva_cred.categoria = cat

            session.add(nueva_cred)

        return jsonify({"message": f"Credencial para '{sitio_web}' guardada con éxito"}), 201

    except IntegrityError:
        return jsonify({"error": "Ya existe una credencial para este sitio y usuario"}), 409

# ==========================================
# ELIMINAR CREDENCIAL
# ==========================================
@app.route('/api/credentials/delete', methods=['POST'])
@limiter.limit("10 per minute")  # Previene eliminación masiva de credenciales
@token_opcional_log
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
@token_opcional_log
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
        categoria = data.get('categoria')

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

            nuevo_sitio = normalize_domain(sitio_web) if sitio_web is not None else credencial.sitio_web
            nuevo_login = login_user if login_user is not None else credencial.login_user

            conflicto = session.query(Credencial).filter(
                Credencial.usuario_id == usuario.id,
                Credencial.sitio_web == nuevo_sitio,
                Credencial.login_user == nuevo_login,
                Credencial.id != cred_uuid
            ).first()
            if conflicto:
                return jsonify({
                    'error': 'Ya existe una credencial para este sitio y usuario',
                    'existing_id': str(conflicto.id)
                }), 409

            if sitio_web is not None:
                credencial.sitio_web = nuevo_sitio
            if login_user is not None:
                credencial.login_user = nuevo_login

            if new_password:
                clave_cifrado = derivar_clave_fernet(master_password, usuario.salt_derivacion)
                pass_cifrada = cifrar_contrasena(new_password, clave_cifrado)
                credencial.password_cifrada = pass_cifrada

            if categoria is not None:
                nombre_cat = categoria.strip()
                if nombre_cat and nombre_cat.lower() != 'sin categoría':
                    cat = session.query(Categoria).filter_by(nombre=nombre_cat).first()
                    if not cat:
                        cat = Categoria(nombre=nombre_cat)
                        session.add(cat)
                        session.flush()
                    credencial.categoria = cat
                else:
                    credencial.categoria = None

        return jsonify({'message': 'Credencial actualizada con éxito'}), 200

    except IntegrityError:
        return jsonify({'error': 'Ya existe una credencial para este sitio y usuario'}), 409

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
# RESTABLECER CONTRASEÑA
# ==========================================
@app.route('/api/recover', methods=['POST'])
@limiter.limit("3 per minute")
def recover_password():
    """
    Restablece la contraseña maestra de un usuario usando su clave de recuperación.
    Recibe JSON: { "username": "...", "recovery_key": "...", "new_master_password": "..." }
    """
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    recovery_key = data.get("recovery_key", "").strip()
    new_master_password = data.get("new_master_password", "").strip()

    if not username or not recovery_key or not new_master_password:
        return jsonify({"error": "Todos los campos son obligatorios"}), 400

    if len(new_master_password) < 8:
        return jsonify({"error": "La nueva contraseña maestra debe tener al menos 8 caracteres"}), 400

    with get_db_session() as session:
        usuario = session.query(Usuario).filter_by(username=username).first()
        if not usuario:
            return jsonify({"error": "El usuario no existe"}), 404

        if not usuario.recovery_key_hash:
            return jsonify({"error": "El usuario no tiene una clave de recuperación configurada"}), 400

        if not verificar_hash_maestro(recovery_key, usuario.recovery_key_hash):
            return jsonify({"error": "La clave de recuperación es incorrecta"}), 401

        nuevo_salt = generar_salt_derivacion()
        nuevo_hash = generar_hash_maestro(new_master_password)

        usuario.master_hash = nuevo_hash
        usuario.salt_derivacion = nuevo_salt

    return jsonify({"message": "Contraseña maestra restablecida con éxito"}), 200


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
    DEBUG_MODE = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    print(f"🚀 Servidor API iniciando en http://127.0.0.1:5000 (Debug: {DEBUG_MODE})")
    app.run(debug=DEBUG_MODE, port=5000)