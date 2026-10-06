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

from seguridad import (  # noqa: E402
    generar_hash_maestro,
    generar_salt_derivacion,
    derivar_clave_fernet,
    cifrar_contrasena,
    descifrar_contrasena,
    generar_hash_contrasena,
    normalize_domain,
)

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
            self.salt_derivacion = user.salt_derivacion
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

    def _add(self, sitio, login, password="pw123!", **extra):
        payload = {
            "username": self.test_user,
            "master_password": self.test_pass,
            "sitio_web": sitio,
            "login_user": login,
            "password": password,
        }
        payload.update(extra)
        return self.client.post(
            "/api/credentials/add",
            json=payload,
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

    def _first(self, sitio, login):
        s = TestSession()
        try:
            return (
                s.query(app_db.Credencial)
                .filter_by(usuario_id=self.user_id, sitio_web=sitio, login_user=login)
                .first()
            )
        finally:
            s.close()

    def _get_cred(self, cred_id):
        s = TestSession()
        try:
            return (
                s.query(app_db.Credencial).filter_by(id=uuid.UUID(cred_id)).first()
            )
        finally:
            s.close()

    # 1. Alta nueva -> 201, la fila queda con password_hash calculado.
    def test_add_new_credential_returns_201_with_hash(self):
        resp = self._add("netflix.com", "user1")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(self._count("netflix.com", "user1"), 1)
        cred = self._first("netflix.com", "user1")
        self.assertIsNotNone(cred.password_hash)
        expected = generar_hash_contrasena(
            "pw123!", derivar_clave_fernet(self.test_pass, self.salt_derivacion)
        )
        self.assertEqual(cred.password_hash, expected)

    # 2. Mismo sitio_web + login_user, password DISTINTA -> 201 (ya no 409).
    def test_same_site_login_different_password_returns_201(self):
        self.assertEqual(self._add("spotify.com", "u1", "pw123!").status_code, 201)
        resp = self._add("spotify.com", "u1", "pw456!")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(self._count("spotify.com", "u1"), 2)

    # 3. Mismo sitio_web + login_user + MISMA password, sin confirm -> 409.
    def test_same_password_without_confirm_returns_409(self):
        self.assertEqual(self._add("spotify.com", "u1", "pw123!").status_code, 201)
        dup = self._add("spotify.com", "u1", "pw123!")
        self.assertEqual(dup.status_code, 409)
        self.assertEqual(dup.get_json()["warning"], "duplicate_password")
        self.assertIn("existing_id", dup.get_json())
        self.assertEqual(self._count("spotify.com", "u1"), 1)

    # 4. Mismo caso pero con confirm_duplicate: true -> 201, 2 filas.
    def test_same_password_with_confirm_returns_201(self):
        self.assertEqual(self._add("spotify.com", "u1", "pw123!").status_code, 201)
        resp = self._add("spotify.com", "u1", "pw123!", confirm_duplicate=True)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(self._count("spotify.com", "u1"), 2)

    # 5. update a password usada en OTRA fila del mismo sitio+login -> 409.
    def test_update_to_duplicate_password_returns_409(self):
        self._add("spotify.com", "u1", "pw123!")
        self._add("spotify.com", "u1", "pw456!")
        # La primera fila intenta actualizar su password a la de la segunda
        cred_id = self._id_of("spotify.com", "u1")
        resp = self._update(cred_id, password="pw456!")
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.get_json()["warning"], "duplicate_password")

    # 5b. update cambiando sitio/login para coincidir con B y ademas con la password
    # de B, sin confirm -> 409 y la credencial A NO queda modificada (rollback).
    def test_update_cross_site_duplicate_rolls_back(self):
        self._add("site-a.com", "userA", "pwA!")
        self._add("site-b.com", "userB", "pwB!")
        id_a = self._id_of("site-a.com", "userA")

        # Intentar mover A hacia sitio/login/password de B
        resp = self._update(
            id_a, sitio_web="site-b.com", login_user="userB", password="pwB!"
        )
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.get_json()["warning"], "duplicate_password")

        # A debe quedar intacta: misma sitio/login/password_hash
        a = self._get_cred(id_a)
        self.assertEqual(a.sitio_web, "site-a.com")
        self.assertEqual(a.login_user, "userA")
        clave = derivar_clave_fernet(self.test_pass, self.salt_derivacion)
        self.assertEqual(a.password_hash, generar_hash_contrasena("pwA!", clave))
        self.assertEqual(descifrar_contrasena(a.password_cifrada, clave), "pwA!")

    # 6. update editando solo sitio_web, sin password -> 200 directo.
    def test_update_site_only_returns_200(self):
        self._add("spotify.com", "u1")
        cred_id = self._id_of("spotify.com", "u1")
        resp = self._update(cred_id, sitio_web="netflix.com")
        self.assertEqual(resp.status_code, 200)

    # 7. Backfill perezoso: fila con password_hash=None se puebla al actualizar.
    def test_backfill_password_hash_on_update(self):
        # Insertar directamente una credencial "vieja" con password_hash None
        s = TestSession()
        try:
            clave = derivar_clave_fernet(self.test_pass, self.salt_derivacion)
            pass_cifrada = cifrar_contrasena("oldpass!", clave)
            cred = app_db.Credencial(
                usuario_id=self.user_id,
                sitio_web="old.com",
                login_user="olduser",
                password_cifrada=pass_cifrada,
                password_hash=None,
            )
            s.add(cred)
            s.commit()
            cred_id = str(cred.id)
        finally:
            s.close()

        resp = self._update(cred_id, password="newpass!")
        self.assertEqual(resp.status_code, 200)

        s = TestSession()
        try:
            refreshed = (
                s.query(app_db.Credencial).filter_by(id=uuid.UUID(cred_id)).first()
            )
            self.assertIsNotNone(refreshed.password_hash)
            self.assertEqual(
                refreshed.password_hash,
                generar_hash_contrasena(
                    "newpass!", derivar_clave_fernet(self.test_pass, self.salt_derivacion)
                ),
            )
        finally:
            s.close()

    def test_normalize_domain_equivalence(self):
        self.assertEqual(normalize_domain("https://spotify.com"), "spotify.com")
        self.assertEqual(normalize_domain("spotify.com"), "spotify.com")
        self.assertEqual(normalize_domain("spotify"), "spotify.com")


if __name__ == "__main__":
    unittest.main(verbosity=2)