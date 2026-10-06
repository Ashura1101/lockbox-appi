import logging
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from typing import Callable
import requests
import threading

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("lockbox_theme.json")

from dotenv import load_dotenv
load_dotenv()

from seguridad import generar_contrasena_segura, normalize_domain

# URL de la API desplegada en Render
API_BASE_URL = "https://lockbox-appi.onrender.com/api"

# Configuración del logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger("app_gui")

# Mensajes amigables para errores de conexión al actualizar la bóveda
SIN_CONEXION_MSG = "Sin conexión a Internet. No se pudo actualizar la bóveda."
ERROR_GENERICO_MSG = "Error al actualizar la bóveda. Inténtalo de nuevo."


def copiar_contrasena_segura(root_window, texto_secreto):
    """Copia una contraseña al portapapeles y programa su borrado automático tras 30 segundos."""
    try:
        root_window.clipboard_clear()
        root_window.clipboard_append(texto_secreto)
        root_window.update()
        root_window.after(30000, lambda: _limpiar_portapapeles(root_window, texto_secreto))
    except Exception as e:
        logger.error(f"Error al escribir en el portapapeles: {e}")


def _limpiar_portapapeles(root_window, texto_copiado):
    """Borra el portapapeles si la contraseña actual coincide con la que fue copiada."""
    try:
        if root_window.clipboard_get() == texto_copiado:
            root_window.clipboard_clear()
            root_window.update()
            logger.info("Portapapeles efímero limpiado automáticamente tras 30 segundos.")
    except Exception:
        pass  # El portapapeles ya estaba vacío o fue modificado por el usuario


def obtener_categorias_api():
    """Consulta la API en Render para obtener las categorías disponibles."""
    try:
        response = requests.get(f"{API_BASE_URL}/categories", timeout=10)
        if response.status_code == 200:
            return response.json().get("categories", [])
        return []
    except requests.exceptions.RequestException as e:
        logger.error(f"Error al conectar con la API para categorías: {e}")
        return []


class AgregarCredencialWindow(ctk.CTkToplevel):
    """
    Ventana emergente (modal) para agregar una nueva credencial vía la API.
    """
    def __init__(self, parent: ctk.CTkFrame, username: str, master_password: str, on_save_callback: Callable):
        super().__init__(parent)
        self.parent_window = parent.parent
        self.username = username
        self.master_password = master_password
        self.on_save_callback = on_save_callback

        # Configuración de ventana
        self.title("Agregar Nueva Credencial")
        self.geometry("440x590")
        self.resizable(False, False)
        self.configure(fg_color="#0B0F19")

        # Comportamiento modal
        self.transient(parent)
        self.grab_set()
        self.focus_force()
        self.center_toplevel(parent)

        # Encabezado
        self.label_titulo = ctk.CTkLabel(
            self,
            text="Nueva Credencial",
            font=ctk.CTkFont(family="Helvetica", size=20, weight="bold"),
            text_color="#E2E8F0"
        )
        self.label_titulo.pack(pady=(24, 18))

        # Campos del formulario
        self.entry_sitio = ctk.CTkEntry(
            self,
            width=360,
            placeholder_text="Sitio Web / Aplicación (ej. github.com)"
        )
        self.entry_sitio.pack(pady=(0, 12))

        self.entry_usuario = ctk.CTkEntry(
            self,
            width=360,
            placeholder_text="Usuario / Correo Electrónico"
        )
        self.entry_usuario.pack(pady=(0, 12))

        # Fila de contraseña + botón Generar en línea
        self.pass_row = ctk.CTkFrame(self, fg_color="transparent")
        self.pass_row.pack(pady=(0, 6))

        self.entry_password = ctk.CTkEntry(
            self.pass_row,
            width=260,
            placeholder_text="Contraseña",
            show="*"
        )
        self.entry_password.pack(side="left", padx=(0, 10))

        self.btn_generar = ctk.CTkButton(
            self.pass_row,
            text="🎲 Generar",
            width=88,
            height=34,
            fg_color="#1E293B",
            hover_color="#334155",
            command=self.generar_y_rellenar
        )
        self.btn_generar.pack(side="left")

        # Fila del Slider de longitud + etiqueta dinámica
        self.longitud_pass = 16

        self.slider_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.slider_frame.pack(pady=(8, 4), padx=30, fill="x")

        self.label_longitud = ctk.CTkLabel(
            self.slider_frame,
            text=f"Longitud: {self.longitud_pass} caracteres",
            font=ctk.CTkFont(size=12),
            text_color="#94A3B8",
            anchor="w"
        )
        self.label_longitud.pack(anchor="w", pady=(0, 6))

        self.slider_longitud = ctk.CTkSlider(
            self.slider_frame,
            from_=8,
            to=30,
            number_of_steps=22,
            command=self._on_slider_move
        )
        self.slider_longitud.set(self.longitud_pass)
        self.slider_longitud.pack(fill="x", pady=(0, 4))

        # Checkbox para mostrar/ocultar contraseña
        self.show_pass_var = tk.StringVar(value="off")
        self.check_show_pass = ctk.CTkCheckBox(
            self,
            text="Mostrar contraseña",
            variable=self.show_pass_var,
            onvalue="on",
            offvalue="off",
            command=self.toggle_password_visibility,
            font=ctk.CTkFont(size=12),
            text_color="#94A3B8"
        )
        self.check_show_pass.pack(pady=(10, 14))

        # Selector de categoría: se muestra inmediato y se carga sin bloquear.
        # Reutiliza las categorías ya disponibles en el Dashboard (caché local).
        self._dashboard = parent
        self.categorias_map = {}
        self.option_categoria = ctk.CTkOptionMenu(
            self,
            width=360,
            values=["Sin Categoría"]
        )
        self.option_categoria.set("Sin Categoría")
        self.option_categoria.pack(pady=(0, 14))
        self._cargar_categorias_async()

        # Mensaje de error interno
        self.label_error = ctk.CTkLabel(
            self,
            text="",
            text_color="#FF5555",
            font=ctk.CTkFont(size=12)
        )
        self.label_error.pack(pady=(0, 4))

        # Botón de guardar
        self.btn_guardar = ctk.CTkButton(
            self,
            text="Guardar Credencial",
            width=220,
            height=40,
            fg_color="#6366F1",
            hover_color="#4F46E5",
            font=ctk.CTkFont(family="Helvetica", size=14, weight="bold"),
            command=self.guardar_credencial
        )
        self.btn_guardar.pack(pady=(4, 20))

    def _cargar_categorias_async(self):
        """Carga categorías sin bloquear. Reutiliza la caché del Dashboard si ya está disponible."""
        cached = list(getattr(self._dashboard, "_categorias_nombres", []) or [])
        if cached:
            self._aplicar_categorias(cached)
            return

        def _worker():
            cats = obtener_categorias_api()
            nombres = [c.get("nombre") for c in cats if c.get("nombre")]
            try:
                self.after(0, lambda: self._aplicar_categorias(nombres))
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def _aplicar_categorias(self, nombres):
        if not self.winfo_exists():
            return
        valores = ["Sin Categoría"] + [n for n in nombres if n and n != "Sin Categoría"]
        actual = self.option_categoria.get()
        self.option_categoria.configure(values=valores)
        if actual in valores:
            self.option_categoria.set(actual)
        else:
            self.option_categoria.set("Sin Categoría")

    def center_toplevel(self, parent):
        """Centra esta ventana sobre su ventana padre."""
        self.update_idletasks()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()
        w = self.winfo_width()
        h = self.winfo_height()
        x = parent_x + (parent_w - w) // 2
        y = parent_y + (parent_h - h) // 2
        self.geometry(f"+{x}+{y}")

    def _on_slider_move(self, valor):
        self.longitud_pass = int(valor)
        self.label_longitud.configure(text=f"Longitud: {self.longitud_pass} caracteres")

    def toggle_password_visibility(self):
        if self.show_pass_var.get() == "on":
            self.entry_password.configure(show="")
        else:
            self.entry_password.configure(show="*")

    def generar_y_rellenar(self):
        nueva_pass = generar_contrasena_segura(self.longitud_pass)
        self.entry_password.configure(show="")
        self.entry_password.delete(0, tk.END)
        self.entry_password.insert(0, nueva_pass)
        self.show_pass_var.set("on")
        self.check_show_pass.select()

    def guardar_credencial(self):
        sitio = normalize_domain(self.entry_sitio.get())
        usuario = self.entry_usuario.get().strip()
        password = self.entry_password.get()

        if not sitio or not usuario or not password:
            self.label_error.configure(text="Por favor, completa todos los campos.")
            return

        categoria_seleccionada = self.option_categoria.get().strip()
        payload = {
            "username": self.username,
            "master_password": self.master_password,
            "sitio_web": sitio,
            "login_user": usuario,
            "password": password,
            "categoria": categoria_seleccionada
        }

        def _fetch():
            try:
                response = self.parent_window.authenticated_post(
                    f"{API_BASE_URL}/credentials/add",
                    json=payload,
                    timeout=10
                )
                try:
                    self.after(0, lambda: _on_result(response))
                except Exception:
                    pass  # Ventana cerrada antes de que el hilo terminara
            except requests.exceptions.RequestException as e:
                err = str(e)
                try:
                    self.after(0, lambda: _on_error(err))
                except Exception:
                    pass
            except Exception as e:
                err = str(e)
                try:
                    self.after(0, lambda: _on_error(err))
                except Exception:
                    pass

        def _on_result(response):
            if not self.winfo_exists():
                return
            if response.status_code == 409:
                try:
                    resp_data = response.json()
                except Exception:
                    resp_data = {}
                if resp_data.get("warning") == "duplicate_password":
                    confirmar = messagebox.askyesno(
                        "Contraseña repetida",
                        f"{resp_data.get('error')}\n¿Guardar de todas formas?"
                    )
                    if confirmar:
                        payload["confirm_duplicate"] = True
                        threading.Thread(target=_fetch, daemon=True).start()
                    else:
                        _restore_button()
                    return
                self.label_error.configure(text=resp_data.get("error", "Error al guardar la credencial."))
                _restore_button()
                return
            if response.status_code == 201:
                try:
                    resp_data = response.json()
                except Exception:
                    resp_data = {}
                new_cred = {
                    "id": resp_data.get("id"),
                    "sitio_web": sitio,
                    "login_user": usuario,
                    "password": password,
                    "categoria": categoria_seleccionada,
                    "created_at": resp_data.get("created_at"),
                    "updated_at": resp_data.get("updated_at")
                }
                logger.info(f"Credencial para '{sitio}' guardada con éxito vía API.")
                self.on_save_callback(new_cred)
                self.destroy()
            elif response.status_code == 429:
                self.label_error.configure(text="Has superado el límite de peticiones. Espera un momento.")
                _restore_button()
            else:
                try:
                    data = response.json()
                except Exception:
                    data = {}
                self.label_error.configure(text=data.get("error", "Error al guardar la credencial."))
                _restore_button()

        def _on_error(err: str):
            if not self.winfo_exists():
                return
            logger.error(f"Error al conectar con la API al guardar credencial: {err}")
            self.label_error.configure(text="Error de conexión con el servidor.")
            _restore_button()

        def _restore_button():
            if self.winfo_exists():
                self.btn_guardar.configure(state="normal", text="Guardar Credencial")

        self.btn_guardar.configure(state="disabled", text="Guardando...")
        threading.Thread(target=_fetch, daemon=True).start()


class GenerarContrasenaWindow(ctk.CTkToplevel):
    """
    Ventana emergente (modal) que actúa como generador seguro de contraseñas.
    """
    def __init__(self, parent: ctk.CTkFrame, app_root: ctk.CTk):
        super().__init__(parent)
        self.app_root = app_root

        self.title("Generador Seguro de Contraseñas")
        self.geometry("420x380")
        self.resizable(False, False)

        self.transient(parent)
        self.grab_set()
        self.focus_force()
        self.center_toplevel(parent)

        self.longitud = 16

        self.label_titulo = ctk.CTkLabel(
            self,
            text="Generador de Contraseñas",
            font=ctk.CTkFont(family="Helvetica", size=20, weight="bold")
        )
        self.label_titulo.pack(pady=(20, 15))

        self.entry_pass = ctk.CTkEntry(
            self,
            width=320,
            height=40,
            font=ctk.CTkFont(family="Consolas", size=16, weight="bold"),
            justify="center"
        )
        self.entry_pass.pack(pady=10)

        self.label_longitud = ctk.CTkLabel(
            self,
            text=f"Longitud: {self.longitud} caracteres",
            font=ctk.CTkFont(family="Helvetica", size=13)
        )
        self.label_longitud.pack(pady=(10, 0))

        self.slider = ctk.CTkSlider(
            self,
            from_=8,
            to=32,
            number_of_steps=24,
            command=self.on_slider_move
        )
        self.slider.set(self.longitud)
        self.slider.pack(pady=10, padx=40, fill="x")

        self.buttons_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.buttons_frame.pack(pady=15)

        self.btn_regenerar = ctk.CTkButton(
            self.buttons_frame,
            text="Regenerar",
            width=120,
            fg_color="#3A3A3A",
            hover_color="#555555",
            command=self.regenerar_password
        )
        self.btn_regenerar.grid(row=0, column=0, padx=10)

        self.btn_copiar = ctk.CTkButton(
            self.buttons_frame,
            text="Copiar",
            width=120,
            fg_color="#1F6AA5",
            hover_color="#144870",
            command=self.copiar_resultado
        )
        self.btn_copiar.grid(row=0, column=1, padx=10)

        self.label_info = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=12)
        )
        self.label_info.pack(pady=5)

        self.regenerar_password()

    def center_toplevel(self, parent):
        self.update_idletasks()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()
        w = self.winfo_width()
        h = self.winfo_height()
        x = parent_x + (parent_w - w) // 2
        y = parent_y + (parent_h - h) // 2
        self.geometry(f"+{x}+{y}")

    def on_slider_move(self, val):
        self.longitud = int(val)
        self.label_longitud.configure(text=f"Longitud: {self.longitud} caracteres")
        self.regenerar_password()

    def regenerar_password(self):
        self.password_actual = generar_contrasena_segura(self.longitud)
        self.entry_pass.configure(state="normal")
        self.entry_pass.delete(0, tk.END)
        self.entry_pass.insert(0, self.password_actual)
        self.entry_pass.configure(state="readonly")

    def copiar_resultado(self):
        self.app_root.copiar_al_portapapeles(self.password_actual)
        self.btn_copiar.configure(text="¡Copiada!", fg_color="#2ECC71", state="disabled")
        self.after(3000, lambda: self.btn_copiar.configure(text="Copiar", fg_color="#1F6AA5", state="normal"))
        self.label_info.configure(text="Contraseña copiada. Portapapeles se limpiará en 30 segundos.", text_color="#2ECC71")
        self.after(4000, lambda: self.label_info.configure(text=""))


class EditarCredencialWindow(ctk.CTkToplevel):
    """
    Ventana modal para editar una credencial existente a través de la API.
    """
    def __init__(
        self,
        parent: ctk.CTkFrame,
        credencial_id: str,
        sitio_web_actual: str,
        login_user_actual: str,
        categoria_nombre_actual: str,
        username: str,
        master_password: str,
        on_save_callback: Callable
    ):
        super().__init__(parent)
        self.credencial_id = credencial_id
        self.parent_window = parent.parent
        self.username = username
        self.master_password = master_password
        self.on_save_callback = on_save_callback

        self.title("Editar Credencial")
        self.geometry("400x560")
        self.resizable(False, False)

        self.transient(parent)
        self.grab_set()
        self.focus_force()
        self.center_toplevel(parent)

        ctk.CTkLabel(
            self,
            text="Editar Credencial",
            font=ctk.CTkFont(family="Helvetica", size=20, weight="bold")
        ).pack(pady=(20, 15))

        self.entry_sitio = ctk.CTkEntry(self, width=300, placeholder_text="Sitio Web / Aplicación")
        self.entry_sitio.insert(0, sitio_web_actual)
        self.entry_sitio.pack(pady=8)

        self.entry_usuario = ctk.CTkEntry(self, width=300, placeholder_text="Usuario / Correo Electrónico")
        self.entry_usuario.insert(0, login_user_actual)
        self.entry_usuario.pack(pady=8)

        self.pass_row = ctk.CTkFrame(self, fg_color="transparent")  
        self.pass_row.pack(pady=8)

        self.entry_password = ctk.CTkEntry(
            self.pass_row,
            width=210,
            placeholder_text="Nueva contraseña (vacío = actual)",
            show="*"
        )
        self.entry_password.pack(side="left", padx=(0, 8))

        self.btn_generar = ctk.CTkButton(
            self.pass_row,
            text="🎲 Generar",
            width=80,
            height=32,
            fg_color="#3A3A3A",
            hover_color="#555555",
            command=self.generar_y_rellenar
        )
        self.btn_generar.pack(side="left")

        self.longitud_pass = 16

        self.slider_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.slider_frame.pack(pady=(4, 2), padx=20, fill="x")

        self.label_longitud = ctk.CTkLabel(
            self.slider_frame,
            text=f"Longitud: {self.longitud_pass} caracteres",
            font=ctk.CTkFont(size=12),
            anchor="w"
        )
        self.label_longitud.pack(anchor="w", pady=(0, 4))

        self.slider_longitud = ctk.CTkSlider(
            self.slider_frame,
            from_=8,
            to=30,
            number_of_steps=22,
            command=self._on_slider_move
        )
        self.slider_longitud.set(self.longitud_pass)
        self.slider_longitud.pack(fill="x", pady=(0, 4))

        self.show_pass_var = tk.StringVar(value="off")
        self.check_show_pass = ctk.CTkCheckBox(
            self,
            text="Mostrar contraseña",
            variable=self.show_pass_var,
            onvalue="on",
            offvalue="off",
            command=self.toggle_password_visibility,
            font=ctk.CTkFont(size=12)
        )
        self.check_show_pass.pack(pady=(5, 10))

        # Selector de categoría: se muestra inmediato y se carga sin bloquear.
        # Reutiliza las categorías ya disponibles en el Dashboard (caché local).
        self._dashboard = parent
        self.categorias_map = {}
        nombre_cat_actual = categoria_nombre_actual or "Sin Categoría"
        self.option_categoria = ctk.CTkOptionMenu(self, width=300, values=["Sin Categoría"])
        self.option_categoria.set(nombre_cat_actual)
        self.option_categoria.pack(pady=8)
        self._cargar_categorias_async(nombre_cat_actual)

        self.label_error = ctk.CTkLabel(self, text="", text_color="#FF3333", font=ctk.CTkFont(size=12))
        self.label_error.pack(pady=4)

        self.btn_guardar_cambios = ctk.CTkButton(
            self,
            text="Guardar Cambios",
            width=200,
            fg_color="#1F6AA5",
            hover_color="#144870",
            command=self.guardar_cambios
        )
        self.btn_guardar_cambios.pack(pady=(5, 15))

    def _cargar_categorias_async(self, valor_actual):
        """Carga categorías sin bloquear. Reutiliza la caché del Dashboard si ya está disponible."""
        cached = list(getattr(self._dashboard, "_categorias_nombres", []) or [])
        if cached:
            self._aplicar_categorias(cached, valor_actual)
            return

        def _worker():
            cats = obtener_categorias_api()
            nombres = [c.get("nombre") for c in cats if c.get("nombre")]
            try:
                self.after(0, lambda: self._aplicar_categorias(nombres, valor_actual))
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def _aplicar_categorias(self, nombres, valor_actual):
        if not self.winfo_exists():
            return
        valores = ["Sin Categoría"] + [n for n in nombres if n and n != "Sin Categoría"]
        self.option_categoria.configure(values=valores)
        if valor_actual in valores:
            self.option_categoria.set(valor_actual)
        else:
            self.option_categoria.set("Sin Categoría")

    def center_toplevel(self, parent):
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _on_slider_move(self, valor):
        self.longitud_pass = int(valor)
        self.label_longitud.configure(text=f"Longitud: {self.longitud_pass} caracteres")

    def generar_y_rellenar(self):
        nueva_pass = generar_contrasena_segura(self.longitud_pass)
        self.entry_password.configure(show="")
        self.entry_password.delete(0, tk.END)
        self.entry_password.insert(0, nueva_pass)
        self.show_pass_var.set("on")
        self.check_show_pass.select()

    def toggle_password_visibility(self):
        self.entry_password.configure(show="" if self.show_pass_var.get() == "on" else "*")

    def guardar_cambios(self):
        sitio = normalize_domain(self.entry_sitio.get())
        usuario = self.entry_usuario.get().strip()
        nueva_pass = self.entry_password.get()

        if not sitio or not usuario:
            self.label_error.configure(text="Sitio web y usuario no pueden estar vacíos.")
            return

        categoria_seleccionada = self.option_categoria.get().strip()
        payload = {
            "id": self.credencial_id,
            "username": self.username,
            "master_password": self.master_password,
            "sitio_web": sitio,
            "login_user": usuario,
            "categoria": categoria_seleccionada
        }
        if nueva_pass:
            payload["password"] = nueva_pass

        def _fetch():
            try:
                response = self.parent_window.authenticated_post(
                    f"{API_BASE_URL}/credentials/update",
                    json=payload,
                    timeout=10
                )
                try:
                    self.after(0, lambda: _on_result(response))
                except Exception:
                    pass  # Ventana cerrada antes de que el hilo terminara
            except requests.exceptions.RequestException as e:
                err = str(e)
                try:
                    self.after(0, lambda: _on_error(err))
                except Exception:
                    pass
            except Exception as e:
                err = str(e)
                try:
                    self.after(0, lambda: _on_error(err))
                except Exception:
                    pass

        def _on_result(response):
            if not self.winfo_exists():
                return
            if response.status_code == 409:
                try:
                    resp_data = response.json()
                except Exception:
                    resp_data = {}
                if resp_data.get("warning") == "duplicate_password":
                    confirmar = messagebox.askyesno(
                        "Contraseña repetida",
                        f"{resp_data.get('error')}\n¿Guardar de todas formas?"
                    )
                    if confirmar:
                        payload["confirm_duplicate"] = True
                        threading.Thread(target=_fetch, daemon=True).start()
                    else:
                        _restore_button()
                    return
                self.label_error.configure(text=resp_data.get("error", "Error al actualizar la credencial."))
                _restore_button()
                return
            if response.status_code == 200:
                try:
                    resp_data = response.json()
                except Exception:
                    resp_data = {}
                updated_fields = {
                    "id": self.credencial_id,
                    "sitio_web": sitio,
                    "login_user": usuario,
                    "password": nueva_pass,  # cadena vacía si el usuario no cambió la contraseña
                    "categoria": categoria_seleccionada,
                    "updated_at": resp_data.get("updated_at")
                }
                logger.info(f"Credencial '{sitio}' (ID: {self.credencial_id}) actualizada vía API.")
                self.on_save_callback(updated_fields)
                self.destroy()
            elif response.status_code == 429:
                self.label_error.configure(text="Has superado el límite de peticiones. Espera un momento.")
                _restore_button()
            else:
                try:
                    data = response.json()
                except Exception:
                    data = {}
                self.label_error.configure(text=data.get("error", "Error al actualizar la credencial."))
                _restore_button()

        def _on_error(err: str):
            if not self.winfo_exists():
                return
            logger.error(f"Error de conexión al actualizar credencial: {err}")
            self.label_error.configure(text="Error de conexión con el servidor.")
            _restore_button()

        def _restore_button():
            if self.winfo_exists():
                self.btn_guardar_cambios.configure(state="normal", text="Guardar Cambios")

        self.btn_guardar_cambios.configure(state="disabled", text="Guardando...")
        threading.Thread(target=_fetch, daemon=True).start()


class DashboardFrame(ctk.CTkFrame):
    """
    Frame principal que representa la bóveda una vez que el usuario inicia sesión.
    Conecta exclusivamente con la API REST en Render.
    """
    def __init__(self, parent: ctk.CTk, username: str, master_password: str, on_logout: Callable[[], None]):
        super().__init__(parent, fg_color="transparent")
        self.parent = parent
        self.username = username
        self.master_password = master_password
        self.on_logout = on_logout
        self._notif_timer = None
        self._mostrar_timers = {}
        self._credenciales_cache: list = []   # Caché local de credenciales descifradas
        self._load_generation: int = 0        # Contador de generación para descartar respuestas obsoletas
        self._categorias_nombres: list = []   # Nombres de categorías disponibles (caché local)
        self._ultima_firma_render = None      # Firma del último resultado renderizado

        self.grid_columnconfigure(0, weight=0, minsize=200)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        self.sidebar_frame = ctk.CTkFrame(
            self,
            width=200,
            fg_color="#0F172A",
            corner_radius=0,
            border_width=0
        )
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_propagate(False)

        self.label_lockbox = ctk.CTkLabel(
            self.sidebar_frame,
            text="LOCKBOX",
            font=ctk.CTkFont(family="Helvetica", size=24, weight="bold"),
            text_color="#6366F1"
        )
        self.label_lockbox.pack(pady=(30, 25), padx=20, anchor="w")

        self.btn_mi_boveda = ctk.CTkButton(
            self.sidebar_frame,
            text="🔑 Mi Bóveda",
            font=ctk.CTkFont(family="Helvetica", size=14, weight="bold"),
            fg_color="#1E293B",
            hover_color="#334155",
            anchor="w",
            height=40
        )
        self.btn_mi_boveda.pack(pady=6, padx=15, fill="x")

        self.btn_generador = ctk.CTkButton(
            self.sidebar_frame,
            text="⚙️ Generador",
            font=ctk.CTkFont(family="Helvetica", size=14),
            fg_color="transparent",
            hover_color="#334155",
            anchor="w",
            height=40,
            command=self.abrir_ventana_generador
        )
        self.btn_generador.pack(pady=6, padx=15, fill="x")

        self.btn_logout = ctk.CTkButton(
            self.sidebar_frame,
            text="Cerrar Sesión",
            font=ctk.CTkFont(family="Helvetica", size=13),
            fg_color="#A51F1F",
            hover_color="#701414",
            height=35,
            command=self.on_logout
        )
        self.btn_logout.pack(side="bottom", pady=25, padx=15, fill="x")

        # Panel de Contenido
        self.content_panel = ctk.CTkFrame(
            self,
            fg_color="transparent",
            border_width=0
        )
        self.content_panel.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        
        self.content_panel.grid_columnconfigure(0, weight=1)
        self.content_panel.grid_rowconfigure(0, weight=0)
        self.content_panel.grid_rowconfigure(1, weight=0)
        self.content_panel.grid_rowconfigure(2, weight=1)

        # Barra de Búsqueda
        self.search_entry = ctk.CTkEntry(
            self.content_panel,
            height=45,
            placeholder_text="🔍 Buscar sitio, usuario o categoría...",
            font=ctk.CTkFont(family="Helvetica", size=14)
        )
        self.search_entry.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        self.search_entry.bind("<KeyRelease>", lambda e: self._buscar_local())

        # Contenedor de Controles
        self.controls_frame = ctk.CTkFrame(self.content_panel, fg_color="transparent", border_width=0)
        self.controls_frame.grid(row=1, column=0, sticky="ew", pady=(0, 15))
        self.controls_frame.grid_columnconfigure(0, weight=0)
        self.controls_frame.grid_columnconfigure(1, weight=0)
        self.controls_frame.grid_columnconfigure(2, weight=1)
        self.controls_frame.grid_columnconfigure(3, weight=0)

        self.categoria_var = tk.StringVar(value="Todas")
        self.categoria_menu = ctk.CTkOptionMenu(
            self.controls_frame,
            variable=self.categoria_var,
            values=["Todas"],
            width=150,
            command=lambda _: self._buscar_local()
        )
        self.categoria_menu.grid(row=0, column=0, sticky="w")
        # Cargar categorías sin bloquear el hilo principal
        self._cargar_categorias_async()

        self.btn_actualizar = ctk.CTkButton(
            self.controls_frame,
            text="🔄 Actualizar",
            font=ctk.CTkFont(family="Helvetica", size=13),
            fg_color="#334155",
            hover_color="#475569",
            width=120,
            command=self.on_actualizar_click
        )
        self.btn_actualizar.grid(row=0, column=1, sticky="w", padx=(10, 0))

        self.label_notificacion = ctk.CTkLabel(
            self.controls_frame,
            text="",
            font=ctk.CTkFont(family="Helvetica", size=13, weight="bold")
        )
        self.label_notificacion.grid(row=0, column=2, padx=10)

        self.btn_agregar = ctk.CTkButton(
            self.controls_frame,
            text="+ Agregar Credencial",
            font=ctk.CTkFont(family="Helvetica", size=13, weight="bold"),
            command=self.abrir_ventana_agregar,
            width=160
        )
        self.btn_agregar.grid(row=0, column=3, sticky="e")

        self.scroll_frame = ctk.CTkScrollableFrame(self.content_panel, fg_color="transparent")
        self.scroll_frame.grid(row=2, column=0, sticky="nsew")

        self.cargar_credenciales()

    def _cargar_categorias_async(self):
        """Carga los nombres de categoría en segundo plano (sin bloquear la UI)
        y actualiza el selector y la caché local cuando terminan."""
        def _worker():
            cats = obtener_categorias_api()
            nombres = [c.get("nombre") for c in cats if c.get("nombre")]
            try:
                self.after(0, lambda: self._on_categorias_cargadas(nombres))
            except Exception:
                pass
        threading.Thread(target=_worker, daemon=True).start()

    def _on_categorias_cargadas(self, nombres):
        if not self.winfo_exists():
            return
        self._categorias_nombres = list(nombres)
        valores = ["Todas"] + [n for n in self._categorias_nombres if n != "Todas"]
        self.categoria_menu.configure(values=valores)
        actual = self.categoria_var.get()
        if actual not in valores:
            self.categoria_var.set("Todas")
            self._buscar_local()

    def on_actualizar_click(self):
        self.btn_actualizar.configure(state="disabled", text="🔄 Actualizando...")
        self.update_idletasks()

        def _on_done(exito: bool, error_msg: str = ""):
            if exito:
                self.mostrar_notificacion_temporal("✓ Bóveda actualizada", es_error=False)
            else:
                self.mostrar_notificacion_temporal(
                    error_msg or "Error al actualizar la bóveda.", es_error=True
                )
            self.btn_actualizar.configure(state="normal", text="🔄 Actualizar")

        self.cargar_credenciales(on_done=_on_done)

    def mostrar_notificacion_temporal(self, mensaje: str, es_error: bool = False):
        color = "#FF3333" if es_error else "#2ECC71"
        self.label_notificacion.configure(text=mensaje, text_color=color)

        if self._notif_timer:
            self.after_cancel(self._notif_timer)

        self._notif_timer = self.after(4000, lambda: self.label_notificacion.configure(text=""))

    def cargar_credenciales(self, on_done=None):
        """Descarga la bóveda completa en un hilo secundario y actualiza la caché local.
        on_done: callable opcional con firma (exito: bool, error_msg: str = '') que se invoca
        en el hilo principal cuando la operación termina."""
        # Cancelar timers de contraseñas visibles
        for timer_id in list(self._mostrar_timers.values()):
            try:
                self.after_cancel(timer_id)
            except Exception:
                pass
        self._mostrar_timers.clear()

        # Incrementar la generación para invalidar cualquier respuesta en vuelo
        self._load_generation += 1
        gen = self._load_generation

        def _fetch():
            try:
                response = self.parent.authenticated_post(
                    f"{API_BASE_URL}/credentials",
                    json={
                        "username": self.username,
                        "master_password": self.master_password
                    },
                    timeout=10
                )
                if gen != self._load_generation:
                    return  # Respuesta obsoleta: se inició una carga más reciente
                try:
                    self.after(0, lambda: _apply(response))
                except Exception:
                    pass  # DashboardFrame destruido durante logout
            except requests.exceptions.RequestException as e:
                if gen != self._load_generation:
                    return
                logger.error(f"Error de conexión al cargar credenciales: {e}")
                try:
                    self.after(0, lambda: _apply_error(SIN_CONEXION_MSG))
                except Exception:
                    pass
            except Exception as e:
                if gen != self._load_generation:
                    return
                logger.error(f"Error inesperado al cargar credenciales: {e}")
                try:
                    self.after(0, lambda: _apply_error(ERROR_GENERICO_MSG))
                except Exception:
                    pass

        def _apply(response):
            # Segunda comprobación de generación (puede haber pasado tiempo desde after())
            if gen != self._load_generation:
                return
            if response.status_code == 200:
                self._credenciales_cache = response.json().get("credenciales", [])
                self._filtrar_y_renderizar()
                if on_done:
                    on_done(True)
            elif response.status_code == 429:
                msg = "Límite de peticiones alcanzado (Rate Limit). Espera un momento."
                self.mostrar_notificacion_temporal(msg, es_error=True)
                if on_done:
                    on_done(False, msg)
            else:
                try:
                    data = response.json()
                except Exception:
                    data = {}
                err_msg = data.get("error", "Error al cargar credenciales.")
                self.mostrar_notificacion_temporal(err_msg, es_error=True)
                if on_done:
                    on_done(False, err_msg)

        def _apply_error(mensaje: str):
            if gen != self._load_generation:
                return
            try:
                if self.scroll_frame.winfo_exists():
                    ctk.CTkLabel(
                        self.scroll_frame,
                        text=mensaje,
                        text_color="#FF3333"
                    ).pack(pady=20)
            except Exception:
                pass
            if on_done:
                on_done(False, mensaje)

        threading.Thread(target=_fetch, daemon=True).start()

    def _filtrar_y_renderizar(self):
        """Filtra la caché local según búsqueda activa y categoría y renderiza las tarjetas.
        Debe ejecutarse siempre en el hilo principal de Tkinter."""
        texto_busqueda = self.search_entry.get().strip().lower()
        categoria_seleccionada = self.categoria_var.get()

        credenciales = list(self._credenciales_cache)

        if categoria_seleccionada != "Todas":
            credenciales = [c for c in credenciales if c.get("categoria") == categoria_seleccionada]

        if texto_busqueda:
            credenciales = [
                c for c in credenciales
                if texto_busqueda in c.get("sitio_web", "").lower()
                or texto_busqueda in c.get("login_user", "").lower()
            ]

        # Firma del resultado visible: si nada cambió respecto al último render,
        # se evita destruir y reconstruir todos los widgets (escritura/categoría rápida).
        firma = tuple(
            (c.get("id"), c.get("sitio_web"), c.get("login_user"),
             c.get("password"), c.get("categoria"))
            for c in credenciales
        )
        if firma == self._ultima_firma_render:
            return
        self._ultima_firma_render = firma

        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        if not credenciales:
            self.mostrar_mensaje_vacio()
            return

        for i, cred in enumerate(credenciales):
            self.crear_tarjeta_credencial(
                credencial_id=cred.get("id"),
                sitio_web=cred.get("sitio_web"),
                login_user=cred.get("login_user"),
                password=cred.get("password"),
                categoria_nombre=cred.get("categoria"),
                index=i
            )

    def _buscar_local(self):
        """Filtra y renderiza desde la caché local. Sin petición HTTP."""
        self._filtrar_y_renderizar()

    def _on_credencial_agregada(self, new_cred: dict):
        """Inserta una credencial recién creada en la caché y re-renderiza. Sin petición HTTP."""
        if new_cred:
            # Invalidar respuestas en vuelo antes de modificar la caché
            self._load_generation += 1
            self._credenciales_cache.append(new_cred)
        self._filtrar_y_renderizar()

    def _on_credencial_editada(self, updated_fields: dict):
        """Actualiza una credencial en la caché y re-renderiza. Sin petición HTTP.
        Solo modifica los campos que el backend confirmó como actualizados."""
        # Invalidar respuestas en vuelo antes de modificar la caché
        self._load_generation += 1
        cred_id = updated_fields.get("id")
        for i, c in enumerate(self._credenciales_cache):
            if c.get("id") == cred_id:
                merged = dict(c)
                merged["sitio_web"] = updated_fields.get("sitio_web", c.get("sitio_web"))
                merged["login_user"] = updated_fields.get("login_user", c.get("login_user"))
                # La contraseña solo se actualiza si el usuario proporcionó una nueva
                nueva_pass = updated_fields.get("password", "")
                if nueva_pass:
                    merged["password"] = nueva_pass
                # La categoría enviada en el payload de edición reemplaza a la original
                if "categoria" in updated_fields:
                    merged["categoria"] = updated_fields.get("categoria")
                if updated_fields.get("updated_at"):
                    merged["updated_at"] = updated_fields["updated_at"]
                self._credenciales_cache[i] = merged
                break
        self._filtrar_y_renderizar()

    def _on_credencial_eliminada(self, cred_id: str, sitio_web: str):
        """Elimina una credencial de la caché y re-renderiza. Sin petición HTTP."""
        # Invalidar respuestas en vuelo antes de modificar la caché
        self._load_generation += 1
        self._credenciales_cache = [c for c in self._credenciales_cache if c.get("id") != cred_id]
        self.mostrar_notificacion_temporal(f"Credencial '{sitio_web}' eliminada.")
        self._filtrar_y_renderizar()

    def mostrar_mensaje_vacio(self):
        self.container_vacio = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        self.container_vacio.pack(expand=True, fill="both", pady=80)
        
        label_vacio = ctk.CTkLabel(
            self.container_vacio,
            text="No tienes ninguna credencial guardada.",
            font=ctk.CTkFont(size=14, slant="italic"),
            text_color="#888888"
        )
        label_vacio.pack(pady=10)
        
        btn_primer_registro = ctk.CTkButton(
            self.container_vacio,
            text="Crea tu primera credencial",
            width=180,
            command=self.abrir_ventana_agregar
        )
        btn_primer_registro.pack(pady=10)

    def crear_tarjeta_credencial(
        self,
        credencial_id: str,
        sitio_web: str,
        login_user: str,
        password: str,
        categoria_nombre: str,
        index: int
    ):
        card = ctk.CTkFrame(
            self.scroll_frame,
            height=100,
            corner_radius=10,
            border_width=1
        )
        card.pack(fill="x", pady=6, padx=5)
        card.pack_propagate(False)

        card.grid_columnconfigure(0, weight=1)
        card.grid_columnconfigure(1, weight=0)
        card.grid_rowconfigure(0, weight=1)

        text_container = ctk.CTkFrame(card, fg_color="transparent", border_width=0)
        text_container.grid(row=0, column=0, sticky="w", padx=25, pady=8)

        label_sitio = ctk.CTkLabel(
            text_container,
            text=sitio_web,
            font=ctk.CTkFont(family="Helvetica", size=16, weight="bold"),
            text_color="#38BDF8",
            anchor="w"
        )
        label_sitio.pack(anchor="w", pady=(0, 2))

        label_user = ctk.CTkLabel(
            text_container,
            text=f"Usuario: {login_user}",
            font=ctk.CTkFont(family="Helvetica", size=13),
            text_color="#94A3B8",
            anchor="w"
        )
        label_user.pack(anchor="w", pady=(0, 2))

        label_pass = ctk.CTkLabel(
            text_container,
            text="••••••••",
            font=ctk.CTkFont(family="Consolas", size=13),
            text_color="#64748B",
            anchor="w"
        )
        label_pass.pack(anchor="w")

        buttons_container = ctk.CTkFrame(card, fg_color="transparent", border_width=0)
        buttons_container.grid(row=0, column=1, sticky="e", padx=15, pady=8)

        btn_mostrar = ctk.CTkButton(
            buttons_container,
            text="Mostrar",
            width=75,
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color="#334155",
            hover_color="#475569"
        )
        btn_mostrar.configure(
            command=lambda p=password, lp=label_pass, bm=btn_mostrar, cid=credencial_id:
                self.toggle_mostrar_contrasena(p, lp, bm, cid)
        )
        btn_mostrar.pack(side="left", padx=4)

        btn_copiar_user = ctk.CTkButton(
            buttons_container,
            text="👤 Usuario",
            width=90,
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color="#334155",
            hover_color="#475569"
        )
        btn_copiar_user.configure(
            command=lambda u=login_user, b=btn_copiar_user:
                self.copiar_usuario(u, b)
        )
        btn_copiar_user.pack(side="left", padx=4)

        btn_copiar_pass = ctk.CTkButton(
            buttons_container,
            text="🔑 Clave",
            width=80,
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color="#334155",
            hover_color="#475569"
        )
        btn_copiar_pass.configure(
            command=lambda p=password, b=btn_copiar_pass:
                self.copiar_contrasena(p, b)
        )
        btn_copiar_pass.pack(side="left", padx=4)

        btn_editar = ctk.CTkButton(
            buttons_container,
            text="Editar",
            width=65,
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color="#334155",
            hover_color="#475569"
        )
        btn_editar.configure(
            command=lambda cid=credencial_id, s=sitio_web, u=login_user, catname=categoria_nombre:
                self.abrir_ventana_editar(cid, s, u, catname)
        )
        btn_editar.pack(side="left", padx=4)

        btn_eliminar = ctk.CTkButton(
            buttons_container,
            text="Eliminar",
            width=75,
            height=32,
            font=ctk.CTkFont(size=12),
            fg_color="#991B1B",
            hover_color="#DC2626"
        )
        btn_eliminar.configure(
            command=lambda cid=credencial_id, s=sitio_web:
                self.eliminar_credencial(cid, s)
        )
        btn_eliminar.pack(side="left", padx=4)

    def copiar_usuario(self, usuario: str, boton: ctk.CTkButton):
        import pyperclip
        try:
            pyperclip.copy(usuario)
            boton.configure(text="¡Copiado!", fg_color="#059669", state="disabled")
            self.after(2000, lambda: boton.configure(text="👤 Usuario", fg_color="#334155", state="normal"))
            self.mostrar_notificacion_temporal("¡Usuario copiado al portapapeles!")
        except Exception as e:
            logger.error(f"Error al copiar usuario: {e}")

    def toggle_mostrar_contrasena(self, password: str, label_pass: ctk.CTkLabel, boton_mostrar: ctk.CTkButton, credencial_id: str):
        if credencial_id in self._mostrar_timers:
            self.after_cancel(self._mostrar_timers[credencial_id])
            del self._mostrar_timers[credencial_id]

        if boton_mostrar.cget("text") == "Mostrar":
            label_pass.configure(text=password, text_color="#2ECC71")
            boton_mostrar.configure(text="Ocultar", fg_color="#475569", hover_color="#64748B")
            
            timer_id = self.after(15000, lambda: self.ocultar_contrasena_auto(label_pass, boton_mostrar, credencial_id))
            self._mostrar_timers[credencial_id] = timer_id
        else:
            label_pass.configure(text="••••••••", text_color="#64748B")
            boton_mostrar.configure(text="Mostrar", fg_color="#334155", hover_color="#475569")

    def ocultar_contrasena_auto(self, label_pass: ctk.CTkLabel, boton_mostrar: ctk.CTkButton, credencial_id: str):
        if label_pass.winfo_exists():
            label_pass.configure(text="••••••••", text_color="#64748B")
        if boton_mostrar.winfo_exists():
            boton_mostrar.configure(text="Mostrar", fg_color="#334155", hover_color="#475569")
        if credencial_id in self._mostrar_timers:
            del self._mostrar_timers[credencial_id]

    def copiar_contrasena(self, password: str, boton: ctk.CTkButton):
        try:
            copiar_contrasena_segura(self.winfo_toplevel(), password)
            boton.configure(text="¡Copiada!", fg_color="#059669", state="disabled")
            self.after(3000, lambda: boton.configure(text="🔑 Clave", fg_color="#334155", state="normal"))
            self.mostrar_notificacion_temporal("¡Contraseña copiada al portapapeles! Se limpiará en 30 segundos.")
        except Exception as e:
            logger.error(f"Error al copiar contraseña: {e}")
            messagebox.showerror("Error", f"No se pudo copiar la contraseña.\nDetalle: {e}")

    def eliminar_credencial(self, credencial_id: str, sitio_web: str):
        confirmar = messagebox.askyesno(
            title="Confirmar eliminación",
            message=f"¿Estás seguro de que deseas eliminar la credencial de '{sitio_web}'?\n\nEsta acción no se puede deshacer."
        )
        if not confirmar:
            return

        def _fetch():
            try:
                response = self.parent.authenticated_post(
                    f"{API_BASE_URL}/credentials/delete",
                    json={
                        "id": credencial_id,
                        "username": self.username,
                        "master_password": self.master_password
                    },
                    timeout=10
                )
                try:
                    self.after(0, lambda: _on_result(response))
                except Exception:
                    pass
            except requests.exceptions.RequestException as e:
                err = str(e)
                try:
                    self.after(0, lambda: _on_error(err))
                except Exception:
                    pass
            except Exception as e:
                err = str(e)
                try:
                    self.after(0, lambda: _on_error(err))
                except Exception:
                    pass

        def _on_result(response):
            if response.status_code == 200:
                logger.info(f"Credencial '{sitio_web}' (ID: {credencial_id}) eliminada vía API.")
                self._on_credencial_eliminada(credencial_id, sitio_web)
            elif response.status_code == 429:
                messagebox.showerror("Límite superado", "Has alcanzado el límite de intentos. Por favor espera un momento.")
            else:
                try:
                    data = response.json()
                except Exception:
                    data = {}
                err_msg = data.get("error", "No se pudo eliminar la credencial.")
                messagebox.showerror("Error", err_msg)

        def _on_error(err: str):
            logger.error(f"Error al eliminar credencial vía API: {err}")
            messagebox.showerror("Error de Conexión", f"No se pudo conectar con el servidor.\nDetalle: {err}")

        threading.Thread(target=_fetch, daemon=True).start()

    def abrir_ventana_editar(self, credencial_id: str, sitio_web: str, login_user: str, categoria_nombre: str):
        EditarCredencialWindow(
            parent=self,
            credencial_id=credencial_id,
            sitio_web_actual=sitio_web,
            login_user_actual=login_user,
            categoria_nombre_actual=categoria_nombre,
            username=self.username,
            master_password=self.master_password,
            on_save_callback=self._on_credencial_editada
        )

    def abrir_ventana_agregar(self):
        AgregarCredencialWindow(
            self,
            username=self.username,
            master_password=self.master_password,
            on_save_callback=self._on_credencial_agregada
        )

    def abrir_ventana_generador(self):
        GenerarContrasenaWindow(self, self.parent)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Gestor de Contraseñas Lockbox")
        self.geometry("450x550")
        self.resizable(False, False)
        self.center_window()

        self.username = None
        self.master_password = None
        self.access_token = None
        self.refresh_token = None
        self.dashboard_frame = None
        self._clipboard_timer = None

        self.setup_login_ui()
        self.check_api_connection()

    def center_window(self):
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def check_api_connection(self):
        """Verifica la conectividad inicial con la API en Render."""
        try:
            response = requests.get(f"{API_BASE_URL}/ping", timeout=5)
            if response.status_code == 200:
                logger.info("Conexión con la API en Render verificada con éxito.")
            else:
                self.show_status("Advertencia: El servidor respondió con un estado inesperado.", is_error=True)
        except requests.exceptions.RequestException as e:
            logger.warning(f"No se pudo conectar con la API en {API_BASE_URL}: {e}")
            self.show_status("API no conectada (Render puede estar iniciando...).", is_error=True)

    def show_status(self, message: str, is_error: bool = False):
        color = "#FF3333" if is_error else "#2ECC71"
        if hasattr(self, 'status_label') and self.status_label.winfo_exists():
            self.status_label.configure(text=message, text_color=color)

    def setup_login_ui(self):
        if self.dashboard_frame:
            self.dashboard_frame.destroy()
            self.dashboard_frame = None

        self.title_label = ctk.CTkLabel(
            self, 
            text="LOCKBOX", 
            font=ctk.CTkFont(family="Helvetica", size=32, weight="bold"),
            text_color="#1F6AA5"
        )
        self.title_label.pack(pady=(40, 10))

        self.subtitle_label = ctk.CTkLabel(
            self, 
            text="Tu gestor de contraseñas seguro en la Nube", 
            font=ctk.CTkFont(family="Helvetica", size=14, slant="italic"),
            text_color="#888888"
        )
        self.subtitle_label.pack(pady=(0, 20))

        self.tabview = ctk.CTkTabview(self, width=380, height=320)
        self.tabview.pack(pady=10)

        self.tabview.add("Iniciar Sesión")
        self.tabview.add("Registrarse")

        self.setup_login_tab()
        self.setup_register_tab()

        self.status_label = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(family="Helvetica", size=13, weight="normal"),
            wraplength=380
        )
        self.status_label.pack(pady=(15, 10))

    def setup_login_tab(self):
        tab = self.tabview.tab("Iniciar Sesión")
        container = ctk.CTkFrame(tab, fg_color="transparent")
        container.pack(expand=True, fill="both", padx=20, pady=10)

        self.login_user_entry = ctk.CTkEntry(container, width=280, placeholder_text="Nombre de usuario")
        self.login_user_entry.pack(pady=12)

        self.login_pass_entry = ctk.CTkEntry(container, width=280, placeholder_text="Contraseña Maestra", show="*")
        self.login_pass_entry.pack(pady=12)

        self.login_button = ctk.CTkButton(container, text="Ingresar", width=280, command=self.handle_login)
        self.login_button.pack(pady=20)

        link_olvido = ctk.CTkLabel(
            master=container,
            text="¿Olvidaste tu usuario o contraseña?",
            text_color="#8b9eb3",
            cursor="hand2",
            font=("Arial", 11, "underline")
        )
        link_olvido.pack(pady=(12, 0))
        link_olvido.bind("<Button-1>", lambda e: self.abrir_ventana_recuperacion())

    def setup_register_tab(self):
        tab = self.tabview.tab("Registrarse")
        container = ctk.CTkFrame(tab, fg_color="transparent")
        container.pack(expand=True, fill="both", padx=20, pady=10)

        self.register_user_entry = ctk.CTkEntry(container, width=280, placeholder_text="Nombre de usuario")
        self.register_user_entry.pack(pady=12)

        self.register_pass_entry = ctk.CTkEntry(container, width=280, placeholder_text="Contraseña Maestra", show="*")
        self.register_pass_entry.pack(pady=12)

        self.register_button = ctk.CTkButton(
            container, 
            text="Registrar Usuario", 
            width=280,
            fg_color="#1F6AA5",
            hover_color="#144870",
            command=self.handle_register
        )
        self.register_button.pack(pady=20)

    def abrir_ventana_recuperacion(self):
        win_recovery = ctk.CTkToplevel(self)
        win_recovery.title("Recuperar Cuenta - Lockbox")
        win_recovery.geometry("420x450")
        win_recovery.resizable(False, False)
        
        win_recovery.transient(self)
        win_recovery.grab_set()
        win_recovery.focus_force()

        win_recovery.update_idletasks()
        parent_x = self.winfo_rootx()
        parent_y = self.winfo_rooty()
        parent_w = self.winfo_width()
        parent_h = self.winfo_height()
        
        w = 420
        h = 450
        x = parent_x + (parent_w - w) // 2
        y = parent_y + (parent_h - h) // 2
        win_recovery.geometry(f"{w}x{h}+{x}+{y}")

        title = ctk.CTkLabel(win_recovery, text="Restablecer Contraseña", font=("Arial", 18, "bold"))
        title.pack(pady=(20, 10))

        warning_box = ctk.CTkTextbox(win_recovery, width=360, height=80, activate_scrollbars=False)
        warning_box.insert("1.0", "⚠️ IMPORTANTE:\nPara restablecer tu acceso necesitas la Clave de Recuperación que se te proporcionó al registrarte. Lockbox no guarda tu contraseña maestra.")
        warning_box.configure(state="disabled", text_color="#ffcc00", fg_color="#2b2b2b")
        warning_box.pack(pady=5)

        user_entry = ctk.CTkEntry(win_recovery, placeholder_text="Nombre de usuario", width=340)
        user_entry.pack(pady=8)

        key_entry = ctk.CTkEntry(win_recovery, placeholder_text="Clave de Recuperación (ej: LOCK-XXXX)", width=340)
        key_entry.pack(pady=8)

        new_pass_entry = ctk.CTkEntry(win_recovery, placeholder_text="Nueva Contraseña Maestra", show="•", width=340)
        new_pass_entry.pack(pady=8)

        def ejecutar_recuperacion():
            usuario = user_entry.get().strip()
            clave_rec = key_entry.get().strip()
            nueva_pass = new_pass_entry.get()

            if not usuario or not clave_rec or not nueva_pass:
                messagebox.showerror("Error", "Por favor completa todos los campos.", parent=win_recovery)
                return

            try:
                response = requests.post(
                    f"{API_BASE_URL}/recover",
                    json={
                        "username": usuario,
                        "recovery_key": clave_rec,
                        "new_master_password": nueva_pass
                    },
                    timeout=10
                )
                if response.status_code == 200:
                    data = response.json()
                    messagebox.showinfo("¡Éxito!", data.get("message", "Contraseña restablecida correctamente."), parent=win_recovery)
                    win_recovery.destroy()
                elif response.status_code == 429:
                    messagebox.showerror("Límite superado", "Has intentado demasiadas veces. Por favor espera un momento.", parent=win_recovery)
                else:
                    data = response.json() if response.headers.get("content-type") == "application/json" else {}
                    err_msg = data.get("error", "No se pudo restablecer la contraseña.")
                    messagebox.showerror("Error de Autenticación", err_msg, parent=win_recovery)
            except requests.exceptions.RequestException as e:
                messagebox.showerror("Error de Conexión", f"No se pudo conectar con el servidor.\nDetalle: {e}", parent=win_recovery)

        btn_restablecer = ctk.CTkButton(
            win_recovery, 
            text="Restablecer Contraseña", 
            fg_color="#3b82f6", 
            hover_color="#2563eb",
            command=ejecutar_recuperacion,
            width=340
        )
        btn_restablecer.pack(pady=20)

    def destroy_login_ui(self):
        self.title_label.destroy()
        self.subtitle_label.destroy()
        self.tabview.destroy()
        self.status_label.destroy()

    def handle_login(self):
        username = self.login_user_entry.get().strip()
        password = self.login_pass_entry.get()

        if not username or not password:
            self.show_status("Por favor, llena todos los campos.", is_error=True)
            return

        self.show_status("Verificando credenciales con la API...")

        try:
            response = requests.post(
                f"{API_BASE_URL}/login",
                json={"username": username, "master_password": password},
                timeout=15
            )

            if response.status_code == 200:
                data = response.json()
                self.username = data.get("username", username)
                self.master_password = password
                self.access_token = data.get("access_token")
                self.refresh_token = data.get("refresh_token")
                logger.info(f"Acceso concedido vía API a la bóveda para el usuario: {username}")
                self.mostrar_dashboard()
            elif response.status_code == 429:
                self.show_status("Has superado el límite de intentos. Por favor, espera un momento.", is_error=True)
            else:
                data = response.json() if response.headers.get("content-type") == "application/json" else {}
                err_msg = data.get("error", "Nombre de usuario o contraseña incorrectos.")
                self.show_status(err_msg, is_error=True)

        except requests.exceptions.RequestException as err:
            logger.error(f"Error de conexión durante login: {err}")
            self.show_status("Error de conexión con el servidor API en Render.", is_error=True)

    def handle_register(self):
        username = self.register_user_entry.get().strip()
        password = self.register_pass_entry.get()

        if not username or not password:
            self.show_status("Por favor, llena todos los campos.", is_error=True)
            return

        if len(password) < 8:
            self.show_status("La contraseña maestra debe tener al menos 8 caracteres.", is_error=True)
            return

        self.show_status("Registrando usuario en la API...")

        try:
            response = requests.post(
                f"{API_BASE_URL}/register",
                json={"username": username, "master_password": password},
                timeout=15
            )

            if response.status_code == 201:
                data = response.json()
                clave_raw = data.get("recovery_key", "")
                self.show_status("¡Usuario registrado con éxito! Ya puedes iniciar sesión.", is_error=False)
                logger.info(f"Usuario '{username}' registrado correctamente vía API.")

                msg = (
                    f"Tu Clave de Recuperación es:\n\n{clave_raw}\n\n"
                    "⚠️ IMPORTANTE:\nAnótala en un papel o lugar seguro. No la podrás volver a ver.\n"
                    "La necesitarás para restablecer tu contraseña maestra si la olvidas."
                )
                messagebox.showinfo("Clave de Recuperación - Lockbox", msg, parent=self)

                self.register_user_entry.delete(0, tk.END)
                self.register_pass_entry.delete(0, tk.END)

                self.tabview.set("Iniciar Sesión")
                self.login_user_entry.delete(0, tk.END)
                self.login_user_entry.insert(0, username)

            elif response.status_code == 429:
                self.show_status("Has superado el límite de registros por minuto. Espera un momento.", is_error=True)
            else:
                data = response.json() if response.headers.get("content-type") == "application/json" else {}
                err_msg = data.get("error", "Error al registrar el usuario.")
                self.show_status(err_msg, is_error=True)

        except requests.exceptions.RequestException as err:
            logger.error(f"Error de conexión en registro: {err}")
            self.show_status("Error de conexión con el servidor API en Render.", is_error=True)

    def authenticated_post(self, url, json=None, timeout=10):
        headers = {"Authorization": f"Bearer {self.access_token}"}

        response = requests.post(url, json=json, headers=headers, timeout=timeout)

        if response.status_code != 401:
            return response

        if self.refresh_token is None:
            return response

        refresh_response = requests.post(
            f"{API_BASE_URL}/auth/refresh",
            json={"refresh_token": self.refresh_token},
            timeout=timeout
        )

        if refresh_response.status_code == 200:
            tokens = refresh_response.json()
            self.access_token = tokens.get("access_token")
            self.refresh_token = tokens.get("refresh_token")

            headers = {"Authorization": f"Bearer {self.access_token}"}
            return requests.post(url, json=json, headers=headers, timeout=timeout)

        self.access_token = None
        self.refresh_token = None
        self.master_password = None
        try:
            self.after(0, self.handle_logout)
        except Exception:
            pass
        return response

    def mostrar_dashboard(self):
        self.destroy_login_ui()
        self.geometry("950x650")
        self.resizable(True, True)
        self.center_window()

        self.dashboard_frame = DashboardFrame(
            self,
            username=self.username,
            master_password=self.master_password,
            on_logout=self.handle_logout
        )
        self.dashboard_frame.pack(fill="both", expand=True)

    def handle_logout(self):
        self.limpiar_portapapeles()
        # Limpiar explícitamente la caché de credenciales antes de destruir el dashboard
        if self.dashboard_frame and hasattr(self.dashboard_frame, '_credenciales_cache'):
            self.dashboard_frame._credenciales_cache = []
        self.username = None
        self.master_password = None
        self.access_token = None
        self.refresh_token = None

        self.geometry("450x550")
        self.resizable(False, False)
        self.center_window()

        self.setup_login_ui()
        self.show_status("Sesión cerrada correctamente.", is_error=False)

    def copiar_al_portapapeles(self, texto: str):
        import pyperclip

        if self._clipboard_timer:
            self.after_cancel(self._clipboard_timer)
            self._clipboard_timer = None

        try:
            pyperclip.copy(texto)
            logger.info("Contraseña copiada al portapapeles.")
        except Exception as e:
            logger.error(f"Error al escribir en el portapapeles con pyperclip: {e}")

        self._clipboard_timer = self.after(30000, lambda: self.limpiar_portapapeles(texto))

    def limpiar_portapapeles(self, texto_copiado: str = None):
        import pyperclip
        try:
            if texto_copiado is None or pyperclip.paste() == texto_copiado:
                pyperclip.copy("")
                logger.info("Portapapeles efímero limpiado automáticamente.")
            else:
                logger.info("El portapapeles fue modificado externamente; se omitió la limpieza.")
        except Exception as e:
            logger.error(f"Error al limpiar el portapapeles: {e}")

        self._clipboard_timer = None


if __name__ == "__main__":
    app = App()
    app.mainloop()
