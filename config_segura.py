"""Valores por defecto seguros de Lockbox (control DIS-03 del checklist).

Funciones puras, sin efectos secundarios ni dependencias de Flask o Tkinter,
para poder probarlas de forma aislada (ver ``test_dis03_defaults.py``).

Regla general: si falta una variable de entorno, o su valor no es válido,
se aplica la opción MÁS restrictiva, nunca la más cómoda.
"""

from typing import Dict, Iterable, List, Optional
from urllib.parse import parse_qs, urlsplit

# Autobloqueo del cliente de escritorio por inactividad (minutos).
AUTOBLOQUEO_MIN_POR_DEFECTO = 5
AUTOBLOQUEO_MIN_MINIMO = 1
AUTOBLOQUEO_MIN_MAXIMO = 60

# Hosts de base de datos considerados locales (desarrollo en la misma máquina).
_HOSTS_LOCALES = {"", "localhost", "127.0.0.1", "::1"}


def modo_debug(valor: Optional[str]) -> bool:
    """True solo si ``FLASK_DEBUG`` vale literalmente ``true`` (sin importar mayúsculas).

    Cualquier otro valor, o su ausencia, equivale a producción.
    """
    return (valor or "").strip().lower() == "true"


def resolver_origenes_permitidos(
    valor_env: Optional[str],
    debug: bool,
    origenes_desarrollo: Iterable[str],
) -> List[str]:
    """Calcula la lista blanca de orígenes CORS.

    - Con ``ALLOWED_ORIGINS`` definido, se usa exactamente esa lista.
    - Sin ella, solo en modo debug se permiten los orígenes locales de desarrollo.
    - Sin ella y fuera de debug, la lista queda vacía: ningún sitio web externo
      puede llamar a la API desde un navegador. Los clientes nativos (escritorio,
      móvil) y la extensión (que usa ``host_permissions``) no dependen de CORS.
    """
    if valor_env:
        return [o.strip() for o in valor_env.split(",") if o.strip()]
    if debug:
        return list(origenes_desarrollo)
    return []


def cabeceras_seguridad(es_https: bool) -> Dict[str, str]:
    """Cabeceras de seguridad HTTP que la API añade a TODAS las respuestas.

    - ``Cache-Control: no-store``: las respuestas pueden llevar contraseñas
      descifradas; ningún navegador, proxy o caché debe guardarlas.
    - HSTS solo se envía sobre HTTPS (sobre HTTP no tiene efecto).
    """
    cabeceras = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": "default-src 'none'",
        "Cache-Control": "no-store",
        "Pragma": "no-cache",
    }
    if es_https:
        cabeceras["Strict-Transport-Security"] = "max-age=31536000"
    return cabeceras


def exigir_ssl_por_defecto(database_url: str) -> bool:
    """True si la conexión a la base de datos debe forzar ``sslmode=require``.

    Se fuerza cuando la URL NO indica ``sslmode`` y el servidor no es local.
    Si la URL ya trae ``sslmode`` (incluido ``disable``), se respeta tal cual:
    es una decisión explícita de quien despliega.
    Si la URL no se puede interpretar, se exige SSL (fallar cerrado).
    """
    try:
        partes = urlsplit(database_url)
        host = (partes.hostname or "").lower()
        consulta = parse_qs(partes.query)
    except ValueError:
        return True

    # Solo aplica a PostgreSQL (el parámetro sslmode es de psycopg2/libpq).
    if not partes.scheme.lower().startswith("postgres"):
        return False
    if "sslmode" in consulta:
        return False
    return host not in _HOSTS_LOCALES


def inactividad_superada(
    ultima_actividad: Optional[float],
    ahora: float,
    limite_segundos: float,
) -> bool:
    """True si ya pasó el límite de inactividad (relojes monótonos, en segundos).

    Sin registro de última actividad se considera superada (fallar cerrado).
    """
    if ultima_actividad is None:
        return True
    return (ahora - ultima_actividad) >= limite_segundos


def leer_minutos_autobloqueo(
    valor_env: Optional[str],
    por_defecto: int = AUTOBLOQUEO_MIN_POR_DEFECTO,
    minimo: int = AUTOBLOQUEO_MIN_MINIMO,
    maximo: int = AUTOBLOQUEO_MIN_MAXIMO,
) -> int:
    """Minutos de inactividad antes de cerrar la sesión de escritorio.

    El autobloqueo no se puede desactivar: un valor ausente, no numérico o
    fuera del rango [minimo, maximo] se sustituye por ``por_defecto``.
    """
    try:
        minutos = int(str(valor_env).strip())
    except (TypeError, ValueError):
        return por_defecto
    if minutos < minimo or minutos > maximo:
        return por_defecto
    return minutos
