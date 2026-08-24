import logging
from app_db import get_db_session, Credencial, init_db
from seguridad import normalize_domain

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sanitize_db")


def sanitize_existing_db_records():
    """Recorre las credenciales guardadas y normaliza los nombres de sitios web."""
    init_db()

    with get_db_session() as session:
        credentials = session.query(Credencial).all()
        logger.info(f"Revisando {len(credentials)} credenciales en la base de datos...")
        updated_count = 0

        for cred in credentials:
            normalized = normalize_domain(cred.sitio_web)
            if cred.sitio_web != normalized:
                logger.info(f"Normalizando ID {cred.id}: '{cred.sitio_web}' -> '{normalized}'")
                cred.sitio_web = normalized
                updated_count += 1

        if updated_count > 0:
            logger.info(f"Se normalizaron y guardaron {updated_count} registros en la base de datos.")
        else:
            logger.info("Todas las credenciales en la base de datos ya están normalizadas.")


if __name__ == "__main__":
    sanitize_existing_db_records()
