"""Pruebas de DIS-03 · seguro por defecto.

Cubren la lógica de ``config_segura.py`` (pura, sin dependencias) y el cableado
del autobloqueo del cliente de escritorio. No necesitan base de datos, red ni
pantalla: la interfaz gráfica se sustituye por stubs.

Ejecutar:  python -m unittest test_dis03_defaults -v
"""

import importlib
import sys
import types
import unittest
from unittest import mock

from config_segura import (
    AUTOBLOQUEO_MIN_POR_DEFECTO,
    cabeceras_seguridad,
    exigir_ssl_por_defecto,
    inactividad_superada,
    leer_minutos_autobloqueo,
    modo_debug,
    resolver_origenes_permitidos,
)

ORIGENES_DEV = ["http://127.0.0.1:5000", "http://localhost:5000"]


class TestModoDebug(unittest.TestCase):
    def test_solo_true_activa_debug(self):
        for valor in ("true", "TRUE", " True ", "tRuE"):
            self.assertTrue(modo_debug(valor), valor)

    def test_cualquier_otro_valor_es_produccion(self):
        for valor in (None, "", "false", "False", "1", "yes", "on", "tru", "0"):
            self.assertFalse(modo_debug(valor), repr(valor))


class TestOrigenesCors(unittest.TestCase):
    def test_sin_configurar_y_sin_debug_no_hay_origenes(self):
        self.assertEqual(resolver_origenes_permitidos(None, False, ORIGENES_DEV), [])
        self.assertEqual(resolver_origenes_permitidos("", False, ORIGENES_DEV), [])

    def test_sin_configurar_en_debug_se_permiten_los_locales(self):
        self.assertEqual(resolver_origenes_permitidos(None, True, ORIGENES_DEV), ORIGENES_DEV)

    def test_la_lista_devuelta_en_debug_es_una_copia(self):
        resultado = resolver_origenes_permitidos(None, True, ORIGENES_DEV)
        resultado.append("https://otro.example")
        self.assertEqual(len(ORIGENES_DEV), 2)

    def test_la_configuracion_explicita_manda_incluso_en_debug(self):
        valor = " https://a.example , chrome-extension://abc ,, "
        esperado = ["https://a.example", "chrome-extension://abc"]
        self.assertEqual(resolver_origenes_permitidos(valor, False, ORIGENES_DEV), esperado)
        self.assertEqual(resolver_origenes_permitidos(valor, True, ORIGENES_DEV), esperado)

    def test_una_configuracion_solo_con_comas_queda_vacia(self):
        self.assertEqual(resolver_origenes_permitidos(" , ,", False, ORIGENES_DEV), [])


class TestCabecerasSeguridad(unittest.TestCase):
    def test_siempre_incluye_no_store_y_las_cabeceras_base(self):
        for https in (True, False):
            h = cabeceras_seguridad(https)
            self.assertEqual(h["Cache-Control"], "no-store")
            self.assertEqual(h["Pragma"], "no-cache")
            self.assertEqual(h["X-Content-Type-Options"], "nosniff")
            self.assertEqual(h["X-Frame-Options"], "DENY")
            self.assertEqual(h["Content-Security-Policy"], "default-src 'none'")

    def test_hsts_solo_sobre_https(self):
        self.assertIn("Strict-Transport-Security", cabeceras_seguridad(True))
        self.assertNotIn("Strict-Transport-Security", cabeceras_seguridad(False))
        self.assertIn("max-age=", cabeceras_seguridad(True)["Strict-Transport-Security"])


class TestSslPorDefecto(unittest.TestCase):
    def test_base_remota_sin_sslmode_exige_ssl(self):
        for url in (
            "postgresql+psycopg2://u:p@db.ejemplo.supabase.co:5432/postgres",
            "postgresql://u:p@10.0.0.5/lockbox",
            "postgres://u:p@dpg-abc.render.com/lockbox",
            "postgresql+psycopg2://u:p@db.ejemplo.co:5432/postgres?application_name=lockbox",
        ):
            self.assertTrue(exigir_ssl_por_defecto(url), url)

    def test_un_sslmode_explicito_se_respeta(self):
        for url in (
            "postgresql://u:p@db.ejemplo.co/lockbox?sslmode=require",
            "postgresql://u:p@db.ejemplo.co/lockbox?sslmode=verify-full",
            "postgresql://u:p@db.ejemplo.co/lockbox?sslmode=disable",
        ):
            self.assertFalse(exigir_ssl_por_defecto(url), url)

    def test_base_local_no_exige_ssl(self):
        for url in (
            "postgresql+psycopg2://postgres:@localhost:5432/password_manager",
            "postgresql://u:p@127.0.0.1/lockbox",
            "postgresql://u:p@[::1]/lockbox",
            "postgresql:///lockbox",
        ):
            self.assertFalse(exigir_ssl_por_defecto(url), url)

    def test_otros_motores_no_se_tocan(self):
        self.assertFalse(exigir_ssl_por_defecto("sqlite:///prueba.db"))
        self.assertFalse(exigir_ssl_por_defecto("sqlite://"))

    def test_url_ininterpretable_falla_cerrado(self):
        self.assertTrue(exigir_ssl_por_defecto("postgresql://u:p@[::1/lockbox"))


class TestAutobloqueoMinutos(unittest.TestCase):
    def test_por_defecto_son_5_minutos(self):
        self.assertEqual(AUTOBLOQUEO_MIN_POR_DEFECTO, 5)
        self.assertEqual(leer_minutos_autobloqueo(None), 5)
        self.assertEqual(leer_minutos_autobloqueo(""), 5)

    def test_valores_validos_se_respetan(self):
        self.assertEqual(leer_minutos_autobloqueo("1"), 1)
        self.assertEqual(leer_minutos_autobloqueo("10"), 10)
        self.assertEqual(leer_minutos_autobloqueo(" 7 "), 7)
        self.assertEqual(leer_minutos_autobloqueo("60"), 60)

    def test_no_se_puede_desactivar_ni_salir_del_rango(self):
        for valor in ("0", "-1", "61", "1000", "abc", "5.5", "∞", "None"):
            self.assertEqual(leer_minutos_autobloqueo(valor), 5, valor)


class TestInactividadSuperada(unittest.TestCase):
    def test_antes_del_limite_no(self):
        self.assertFalse(inactividad_superada(100.0, 399.0, 300))

    def test_en_el_limite_y_despues_si(self):
        self.assertTrue(inactividad_superada(100.0, 400.0, 300))
        self.assertTrue(inactividad_superada(100.0, 10_000.0, 300))

    def test_sin_registro_de_actividad_falla_cerrado(self):
        self.assertTrue(inactividad_superada(None, 0.0, 300))


# ---------------------------------------------------------------------------
# Cableado del autobloqueo en el cliente de escritorio (con la GUI sustituida)
# ---------------------------------------------------------------------------

class _Base:
    """Sustituye a las clases de customtkinter: sin ventana ni pantalla."""

    def __init__(self, *args, **kwargs):
        pass


class _FakeCtk(types.ModuleType):
    def __getattr__(self, nombre):
        if nombre.startswith("__"):
            raise AttributeError(nombre)
        if nombre.startswith("CTk"):
            clase = type(nombre, (_Base,), {})
            setattr(self, nombre, clase)
            return clase
        return lambda *a, **k: None


def _importar_app_gui_con_stubs():
    tk = types.ModuleType("tkinter")
    messagebox = types.ModuleType("tkinter.messagebox")
    tk.messagebox = messagebox
    stubs = {
        "customtkinter": _FakeCtk("customtkinter"),
        "tkinter": tk,
        "tkinter.messagebox": messagebox,
    }
    with mock.patch.dict(sys.modules, stubs):
        sys.modules.pop("app_gui", None)
        return importlib.import_module("app_gui")


class TestAutobloqueoEscritorio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.app_gui = _importar_app_gui_con_stubs()
        except ImportError as e:  # p. ej. falta bcrypt o requests en este entorno
            raise unittest.SkipTest(f"No se pudo importar app_gui: {e}")

    def _app(self, dashboard=True, ultima=0.0):
        App = self.app_gui.App
        app = App.__new__(App)
        app._ultima_actividad = ultima
        app._vigilancia_id = None
        app.dashboard_frame = object() if dashboard else None
        app.agendados = []
        app.cancelados = []
        app.cierres = []
        app.after = lambda ms, fn: app.agendados.append((ms, fn)) or f"id-{len(app.agendados)}"
        app.after_cancel = lambda ident: app.cancelados.append(ident)
        app.handle_logout = lambda mensaje="": app.cierres.append(mensaje)
        return app

    def test_el_limite_por_defecto_son_5_minutos(self):
        # Con LOCKBOX_AUTOBLOQUEO_MIN sin definir, el límite es 5 min = 300 s.
        with mock.patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("LOCKBOX_AUTOBLOQUEO_MIN", None)
            esperado = leer_minutos_autobloqueo(os.environ.get("LOCKBOX_AUTOBLOQUEO_MIN")) * 60
        self.assertEqual(esperado, 300)
        self.assertGreaterEqual(self.app_gui.AUTOBLOQUEO_SEGUNDOS, 60)
        self.assertLessEqual(self.app_gui.AUTOBLOQUEO_SEGUNDOS, 3600)

    def test_con_actividad_reciente_no_cierra_y_vuelve_a_comprobar(self):
        app = self._app(ultima=1000.0)
        with mock.patch.object(self.app_gui.time, "monotonic", return_value=1000.0 + 10):
            app._comprobar_inactividad()
        self.assertEqual(app.cierres, [])
        self.assertEqual(len(app.agendados), 1)
        self.assertEqual(app.agendados[0][0], self.app_gui.INTERVALO_COMPROBACION_MS)

    def test_pasado_el_limite_cierra_la_sesion_con_mensaje_y_no_reagenda(self):
        app = self._app(ultima=1000.0)
        ahora = 1000.0 + self.app_gui.AUTOBLOQUEO_SEGUNDOS
        with mock.patch.object(self.app_gui.time, "monotonic", return_value=ahora):
            app._comprobar_inactividad()
        self.assertEqual(len(app.cierres), 1)
        self.assertIn("inactividad", app.cierres[0])
        self.assertEqual(app.agendados, [])

    def test_sin_sesion_abierta_no_hace_nada(self):
        app = self._app(dashboard=False, ultima=0.0)
        with mock.patch.object(self.app_gui.time, "monotonic", return_value=10**9):
            app._comprobar_inactividad()
        self.assertEqual(app.cierres, [])
        self.assertEqual(app.agendados, [])

    def test_la_actividad_actualiza_la_marca(self):
        app = self._app(ultima=0.0)
        with mock.patch.object(self.app_gui.time, "monotonic", return_value=555.0):
            app._registrar_actividad()
        self.assertEqual(app._ultima_actividad, 555.0)

    def test_iniciar_vigilancia_reinicia_la_marca_y_agenda_la_comprobacion(self):
        app = self._app(ultima=0.0)
        with mock.patch.object(self.app_gui.time, "monotonic", return_value=777.0):
            app._iniciar_vigilancia_inactividad()
        self.assertEqual(app._ultima_actividad, 777.0)
        self.assertEqual(len(app.agendados), 1)
        self.assertEqual(app._vigilancia_id, "id-1")

    def test_iniciar_vigilancia_dos_veces_cancela_la_anterior(self):
        app = self._app()
        app._iniciar_vigilancia_inactividad()
        app._iniciar_vigilancia_inactividad()
        self.assertEqual(app.cancelados, ["id-1"])
        self.assertEqual(app._vigilancia_id, "id-2")

    def test_logout_cancela_la_vigilancia_y_muestra_el_mensaje(self):
        App = self.app_gui.App
        app = App.__new__(App)
        app._vigilancia_id = "id-9"
        app._clipboard_timer = None
        app.dashboard_frame = None
        app.username = "ana"
        app.master_password = "maestra"
        app.access_token = "a"
        app.refresh_token = "r"
        app.cancelados = []
        app.mensajes = []
        app.after_cancel = lambda ident: app.cancelados.append(ident)
        app.limpiar_portapapeles = lambda *a, **k: None
        app.geometry = lambda *a, **k: None
        app.resizable = lambda *a, **k: None
        app.center_window = lambda: None
        app.setup_login_ui = lambda: None
        app.show_status = lambda msg, is_error=False: app.mensajes.append((msg, is_error))

        app.handle_logout(mensaje="Sesión cerrada por inactividad.")

        self.assertEqual(app.cancelados, ["id-9"])
        self.assertIsNone(app._vigilancia_id)
        self.assertEqual(app.mensajes, [("Sesión cerrada por inactividad.", False)])
        self.assertIsNone(app.master_password)
        self.assertIsNone(app.access_token)

    def test_logout_sin_argumentos_mantiene_el_mensaje_de_siempre(self):
        App = self.app_gui.App
        app = App.__new__(App)
        app._vigilancia_id = None
        app._clipboard_timer = None
        app.dashboard_frame = None
        app.mensajes = []
        app.after_cancel = lambda ident: None
        app.limpiar_portapapeles = lambda *a, **k: None
        app.geometry = lambda *a, **k: None
        app.resizable = lambda *a, **k: None
        app.center_window = lambda: None
        app.setup_login_ui = lambda: None
        app.show_status = lambda msg, is_error=False: app.mensajes.append(msg)

        app.handle_logout()

        self.assertEqual(app.mensajes, ["Sesión cerrada correctamente."])


if __name__ == "__main__":
    unittest.main(verbosity=2)
