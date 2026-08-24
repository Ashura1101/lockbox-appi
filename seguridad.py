import os
import base64
import bcrypt
import logging
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger("seguridad")

def generar_hash_maestro(password_maestra: str) -> str:
    """
    Genera un hash seguro y salado para la contraseña maestra utilizando bcrypt.
    
    Args:
        password_maestra: Contraseña maestra ingresada por el usuario.
        
    Returns:
        str: El hash generado codificado en UTF-8 para su almacenamiento en BD.
    """
    # bcrypt requiere la contraseña en bytes
    password_bytes = password_maestra.encode('utf-8')
    
    # Generar un salt único y calcular el hash
    # bcrypt incluye el salt dentro del hash resultante de manera estándar
    salt = bcrypt.gensalt(rounds=12)
    hash_bytes = bcrypt.hashpw(password_bytes, salt)
    
    return hash_bytes.decode('utf-8')


def verificar_hash_maestro(password_maestra: str, hash_guardado: str) -> bool:
    """
    Verifica si la contraseña maestra coincide con el hash almacenado utilizando bcrypt.
    
    Args:
        password_maestra: Contraseña maestra a verificar.
        hash_guardado: Hash obtenido desde la base de datos.
        
    Returns:
        bool: True si la contraseña es correcta, False de lo contrario.
    """
    password_bytes = password_maestra.encode('utf-8')
    hash_bytes = hash_guardado.encode('utf-8')
    
    # bcrypt.checkpw verifica el hash de manera segura contra ataques de temporización
    return bcrypt.checkpw(password_bytes, hash_bytes)


def generar_salt_derivacion() -> bytes:
    """
    Genera un salt criptográficamente seguro de 16 bytes para la derivación de clave.
    
    Returns:
        bytes: Salt de 16 bytes.
    """
    return os.urandom(16)


def derivar_clave_fernet(password_maestra: str, salt: bytes) -> bytes:
    """
    Deriva una clave de cifrado simétrico compatible con Fernet a partir de la 
    contraseña maestra del usuario y un salt aleatorio usando PBKDF2-HMAC-SHA256.
    
    Args:
        password_maestra: Contraseña maestra del usuario.
        salt: Salt aleatorio de 16 bytes específico del usuario.
        
    Returns:
        bytes: Clave derivada codificada en base64 url-safe (32 bytes decodificados).
    """
    # Configuración de PBKDF2 según estándares OWASP
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600000,  # Alta carga computacional para dificultar ataques de fuerza bruta
    )
    
    # Derivar la clave simétrica cruda
    clave_cruda = kdf.derive(password_maestra.encode('utf-8'))
    
    # Fernet requiere que la clave esté codificada en Base64 URL-safe
    return base64.urlsafe_b64encode(clave_cruda)


def cifrar_contrasena(password_plana: str, clave_derivada: bytes) -> bytes:
    """
    Cifra una contraseña en texto plano utilizando la clave derivada compatible con Fernet.
    
    Args:
        password_plana: Contraseña en texto plano a cifrar.
        clave_derivada: Clave Fernet derivada (Base64 URL-safe).
        
    Returns:
        bytes: Token Fernet cifrado (bytes).
    """
    f = Fernet(clave_derivada)
    return f.encrypt(password_plana.encode('utf-8'))


def descifrar_contrasena(datos_cifrados: bytes, clave_derivada: bytes) -> str:
    """
    Descifra una contraseña cifrada con un token Fernet usando la clave derivada.
    
    Args:
        datos_cifrados: Token Fernet cifrado en bytes o memoryview de BD.
        clave_derivada: Clave Fernet derivada (Base64 URL-safe).
        
    Returns:
        str: Contraseña descifrada en texto plano (UTF-8).
    """
    # Asegurar conversión de memoryview u otros tipos similares devueltos por DB
    datos_bytes = bytes(datos_cifrados)
    
    f = Fernet(clave_derivada)
    datos_descifrados = f.decrypt(datos_bytes)
    return datos_descifrados.decode('utf-8')



def generar_contrasena_segura(longitud: int = 16) -> str:
    """
    Genera una contraseña aleatoria criptográficamente segura usando el módulo secrets.
    Garantiza que incluya al menos una mayúscula, una minúscula, un número y un símbolo.
    
    Args:
        longitud: Longitud total de la contraseña (por defecto 16).
        
    Returns:
        str: Contraseña generada.
    """
    import secrets
    import string

    if longitud < 6:
        longitud = 6  # Evitar longitudes inseguras o que no permitan contener todos los sets

    # Definición de conjuntos de caracteres
    minusculas = string.ascii_lowercase
    mayusculas = string.ascii_uppercase
    digitos = string.digits
    # Símbolos especiales estándar y seguros
    simbolos = "!@#$%^&*()-_=+[]{}|;:,.<>?"

    # Garantizar la presencia de al menos un carácter de cada tipo
    caracteres_obligatorios = [
        secrets.choice(minusculas),
        secrets.choice(mayusculas),
        secrets.choice(digitos),
        secrets.choice(simbolos)
    ]

    # Completar la longitud requerida con una mezcla aleatoria de todos los conjuntos
    todos_caracteres = minusculas + mayusculas + digitos + simbolos
    caracteres_restantes = [secrets.choice(todos_caracteres) for _ in range(longitud - len(caracteres_obligatorios))]

    password_lista = caracteres_obligatorios + caracteres_restantes

    # Mezclar la lista de forma criptográficamente segura (usando ordenación por peso aleatorio de secrets)
    # secrets no posee un método shuffle directo
    password_mezclada = sorted(password_lista, key=lambda x: secrets.randbits(32))

    return "".join(password_mezclada)


def generar_clave_recuperacion() -> str:
    """
    Genera una clave de recuperación aleatoria fácil de anotar.
    Ejemplo: LOCK-A1B2-C3D4
    """
    import secrets
    bloque1 = secrets.token_hex(2).upper()
    bloque2 = secrets.token_hex(2).upper()
    return f"LOCK-{bloque1}-{bloque2}"


def normalize_domain(input_string: str) -> str:
    """
    Normaliza entradas de sitios web a un dominio estándar.
    Ej: 'youtube' -> 'youtube.com', 'https://www.facebook.com/login' -> 'facebook.com'
    """
    from urllib.parse import urlparse

    if not input_string:
        return ""

    cleaned = input_string.strip().lower()

    if cleaned.startswith("localhost") or cleaned.startswith("127.0.0.1"):
        return cleaned.split("/")[0]

    # 1. Si es un nombre plano sin puntos, protocolo ni puerto (ej: 'youtube')
    if "." not in cleaned and "://" not in cleaned and ":" not in cleaned:
        return f"{cleaned}.com"

    # 2. Si no tiene protocolo, agregarlo temporalmente para parsear correctamente
    if not cleaned.startswith("http://") and not cleaned.startswith("https://"):
        cleaned = "https://" + cleaned

    try:
        parsed = urlparse(cleaned)
        domain = parsed.netloc or parsed.path
        # Remover puerto si existe (ej. localhost:8080) y el prefijo www.
        domain = domain.split(":")[0]
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return input_string.strip().lower()




