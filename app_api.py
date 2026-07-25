import logging
from flask import Flask, request, jsonify
from flask_cors import CORS

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
    generar_salt_derivacion
)

# Inicialización de la aplicación Flask
app = Flask(__name__)

# Habilitar CORS para permitir que la extensión de Chrome haga peticiones al backend
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app_api")

# Asegurar que las tablas estén inicializadas al arrancar la API
init_db()


@app.route("/api/ping", methods=["GET"])
def ping():
    """Ruta para verificar que la API está viva y respondiendo."""
    return jsonify({"status": "ok", "message": "Servidor del Gestor de Contraseñas activo"}), 200


@app.route("/api/register", methods=["POST"])
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

        nuevo_usuario = Usuario(
            username=username,
            master_hash=hash_maestro,
            salt_derivacion=salt_derivacion
        )
        session.add(nuevo_usuario)

    return jsonify({"message": f"Usuario '{username}' registrado con éxito"}), 201


@app.route("/api/login", methods=["POST"])
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


if __name__ == "__main__":
    print("🚀 Servidor API iniciando en http://127.0.0.1:5000")
    app.run(debug=True, port=5000)