import unittest
import uuid
from contextlib import contextmanager
from unittest import mock

import app_db

# Evita que `import app_api` ejecute init_db() contra la base de datos real.
app_db.init_db = lambda: True

import app_api  # noqa: E402
from app_api import app  # noqa: E402

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from seguridad import generar_hash_maestro, generar_salt_derivacion, normalize_domain  # noqa: E402

# Base de datos SQLite en memoria, independiente de PostgreSQL. Nunca toca producción.
TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
app_db.Base.metadata.create_all(bind=TEST_ENGINE)
TestSession = sessionmaker(bind=TEST_ENGINE, autoflush=False, autocommit=False)


@contextmanager
def sqlite_scoped_session():
    s = TestSession()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


@contextmanager
def commit_raises_integrity():
    """Simula la violación de UNIQUE en el commit (índice de BD aún no creado)."""
    s = TestSession()
    try:
        yield s
        raise IntegrityError("stmt", {}, Exception("UniqueViolation duplicado"))
    except IntegrityError:
        s.rollback()
        raise
    finally:
        s.close()


class CredentialDedupTests(unittest.TestCase):
    def setUp(self):
        self.test_user = f"user_test_{uuid.uuid4().hex[:8]}"
        self.test_pass = "TestMasterPass123!"
        user = app_db.Usuario(
            username=self.test_user,
            master_hash=generar_hash_maestro(self.test_pass),
            salt_derivacion=generar_salt_derivacion(),
        )
        s = TestSession()
        try:
            s.add(user)
            s.commit()
            self.user_id = user.id
        finally:
            s.close()

        self.patcher = mock.patch("app_api.get_db_session", sqlite_scoped_session)
        self.patcher.start()
        self.client = app.test_client()
        self._ip = 0

    def tearDown(self):
        self.patcher.stop()

    def _ip4(self):
        self._ip += 1
        return f"10.9.9.{self._ip}"

    def _add(self, sitio, login, password="pw123!"):
        return self.client.post(
            "/api/credentials/add",
            json={
                "username": self.test_user,
                "master_password": self.test_pass,
                "sitio_web": sitio,
                "login_user": login,
                "password": password,
            },
            environ_base={"REMOTE_ADDR": self._ip4()},
        )

    def _update(self, cred_id, **fields):
        return self.client.post(
            "/api/credentials/update",
            json={
                "id": cred_id,
                "username": self.test_user,
                "master_password": self.test_pass,
                **fields,
            },
            environ_base={"REMOTE_ADDR": self._ip4()},
        )

    def _count(self, sitio, login):
        s = TestSession()
        try:
            return (
                s.query(app_db.Credencial)
                .filter_by(usuario_id=self.user_id, sitio_web=sitio, login_user=login)
                .count()
            )
        finally:
            s.close()

    def _id_of(self, sitio, login):
        s = TestSession()
        try:
            c = (
                s.query(app_db.Credencial)
                .filter_by(usuario_id=self.user_id, sitio_web=sitio, login_user=login)
                .first()
            )
            return str(c.id)
        finally:
            s.close()

    # 1. Alta normal -> 201, una sola fila
    def test_add_new_credential_returns_201(self):
        resp = self._add("netflix.com", "user1")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(self._count("netflix.com", "user1"), 1)

    # 2. Alta duplicada exacta -> 409, se conserva una fila
    def test_duplicate_exact_returns_409(self):
        self.assertEqual(self._add("spotify.com", "u1").status_code, 201)
        dup = self._add("spotify.com", "u1")
        self.assertEqual(dup.status_code, 409)
        self.assertIn("existing_id", dup.get_json())
        self.assertEqual(self._count("spotify.com", "u1"), 1)

    # 3. Mismo login, sitio diferente -> no falso positivo
    def test_different_site_same_login(self):
        self.assertEqual(self._add("spotify.com", "u1").status_code, 201)
        self.assertEqual(self._add("netflix.com", "u1").status_code, 201)
        self.assertEqual(self._count("spotify.com", "u1"), 1)
        self.assertEqual(self._count("netflix.com", "u1"), 1)

    # 4. Mismo sitio, login diferente -> no falso positivo
    def test_different_login_same_site(self):
        self.assertEqual(self._add("spotify.com", "u1").status_code, 201)
        self.assertEqual(self._add("spotify.com", "u2").status_code, 201)
        self.assertEqual(self._count("spotify.com", "u1"), 1)
        self.assertEqual(self._count("spotify.com", "u2"), 1)

    # 5. Normalización: 'https://...' y 'spotify.com' colisionan
    def test_normalization_duplicate(self):
        self.assertEqual(self._add("https://github.com", "g").status_code, 201)
        dup = self._add("github.com", "g")
        self.assertEqual(dup.status_code, 409)
        self.assertEqual(self._count("github.com", "g"), 1)

    def test_normalize_domain_equivalence(self):
        self.assertEqual(normalize_domain("https://spotify.com"), "spotify.com")
        self.assertEqual(normalize_domain("spotify.com"), "spotify.com")
        self.assertEqual(normalize_domain("spotify"), "spotify.com")

    # 6. Update sin cambiar sitio/login -> no choca consigo mismo
    def test_update_same_site_login_no_conflict(self):
        self._add("spotify.com", "u1")
        cred_id = self._id_of("spotify.com", "u1")
        resp = self._update(cred_id, password="nuevapass!")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._count("spotify.com", "u1"), 1)

    # 7. Update que colisiona con otra credencial -> 409, nunca 500
    def test_update_collision_returns_409(self):
        self._add("spotify.com", "u1")
        self._add("spotify.com", "u2")
        id_a = self._id_of("spotify.com", "u1")
        resp = self._update(id_a, login_user="u2")
        self.assertEqual(resp.status_code, 409)
        self.assertIn("existing_id", resp.get_json())
        self.assertEqual(self._count("spotify.com", "u1"), 1)
        self.assertEqual(self._count("spotify.com", "u2"), 1)

    # 8. Si se dispara IntegrityError (índice UNIQUE futuro), se responde 409 y no 500
    def test_integrity_error_maps_to_409(self):
        with mock.patch("app_api.get_db_session", commit_raises_integrity):
            resp = self.client.post(
                "/api/credentials/add",
                json={
                    "username": self.test_user,
                    "master_password": self.test_pass,
                    "sitio_web": "unique.test",
                    "login_user": "x",
                    "password": "pw123!",
                },
                environ_base={"REMOTE_ADDR": self._ip4()},
            )
        self.assertEqual(resp.status_code, 409)


if __name__ == "__main__":
    unittest.main(verbosity=2)