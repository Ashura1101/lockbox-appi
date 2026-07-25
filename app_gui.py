import logging
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from typing import Callable
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("lockbox_theme.json")

# Importaciones del backend
from app_db import Usuario, Credencial, Categoria, get_db_session, init_db
from seguridad import (
    generar_hash_maestro,
    verificar_hash_maestro,
    generar_salt_derivacion,
    derivar_clave_fernet,
    cifrar_contrasena,
    descifrar_contrasena,
    generar_contrasena_segura
)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import or_

# Configuración del logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger("app_gui")

# Configuración visual de CustomTkinter
ctk.set_appearance_mode("dark")
# Tema cargado globalmente desde lockbox_theme.json



class AgregarCredencialWindow(ctk.CTkToplevel):
    """
    Ventana emergente (modal) para agregar una nueva credencial a la base de datos.
    """
    def __init__(self, parent: ctk.CTkFrame, usuario_id: str, clave_derivada: bytes, on_save_callback: Callable[[], None]):
        super().__init__(parent)
        self.usuario_id = usuario_id
        self.clave_derivada = clave_derivada
        self.on_save_callback = on_save_callback

        # Configuración de ventana
        self.title("Agregar Nueva Credencial")
        self.geometry("440x590")  # Ligeramente más ancho y alto para dar aire a los elementos
        self.resizable(False, False)
        self.configure(fg_color="#0B0F19")  # Fondo unificado con la paleta "Cool Space"

        # Comportamiento modal (hacer foco en esta ventana y bloquear la principal)
        self.transient(parent)
        self.grab_set()
        self.focus_force()

        # Centrar la ventana secundaria con respecto a la principal
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
        self.longitud_pass = 16  # Valor inicial

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
            number_of_steps=22,          # pasos enteros: 8, 9, 10, ... 30
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

        # Recuperar categorías disponibles de PostgreSQL para el menú desplegable
        self.categorias_map = {}
        categorias_valores = ["Sin Categoría"]
        try:
            with get_db_session() as session:
                cats = session.query(Categoria).order_by(Categoria.nombre).all()
                for c in cats:
                    self.categorias_map[c.nombre] = c.id
                    categorias_valores.append(c.nombre)
        except Exception as e:
            logger.error(f"Error al cargar categorías en el formulario: {e}")

        # Menú desplegable para seleccionar categoría
        self.option_categoria = ctk.CTkOptionMenu(
            self,
            width=360,
            values=categorias_valores
        )
        self.option_categoria.set("Sin Categoría")
        self.option_categoria.pack(pady=(0, 14))

        # Mensaje de error interno
        self.label_error = ctk.CTkLabel(
            self,
            text="",
            text_color="#FF5555",
            font=ctk.CTkFont(size=12)
        )
        self.label_error.pack(pady=(0, 4))

        # Botón de guardar — color de acento índigo de la app
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
        """Actualiza la etiqueta y el estado interno al mover el slider de longitud."""
        self.longitud_pass = int(valor)
        self.label_longitud.configure(text=f"Longitud: {self.longitud_pass} caracteres")

    def toggle_password_visibility(self):
        """Muestra u oculta los caracteres del campo de contraseña."""
        if self.show_pass_var.get() == "on":
            self.entry_password.configure(show="")
        else:
            self.entry_password.configure(show="*")

    def generar_y_rellenar(self):
        """Genera una contraseña segura usando la longitud del slider e inserta el resultado en el campo."""
        nueva_pass = generar_contrasena_segura(self.longitud_pass)
        self.entry_password.configure(show="")   # revelar para que el usuario confirme
        self.entry_password.delete(0, tk.END)
        self.entry_password.insert(0, nueva_pass)
        # Activar el checkbox "Mostrar" para que el usuario vea la contraseña generada
        self.show_pass_var.set("on")
        self.check_show_pass.select()

    def guardar_credencial(self):
        """Valida y guarda la credencial cifrada en la base de datos asignando su categoría."""
        sitio = self.entry_sitio.get().strip()
        usuario = self.entry_usuario.get().strip()
        password = self.entry_password.get()

        if not sitio or not usuario or not password:
            self.label_error.configure(text="Por favor, completa todos los campos.")
            return

        try:
            # Obtener el ID de la categoría seleccionada (será un entero o None si es "Sin Categoría")
            cat_seleccionada = self.option_categoria.get()
            cat_id = self.categorias_map.get(cat_seleccionada)

            # Cifrar la contraseña usando la clave derivada del usuario
            password_cifrada = cifrar_contrasena(password, self.clave_derivada)

            with get_db_session() as session:
                nueva_cred = Credencial(
                    usuario_id=self.usuario_id,
                    categoria_id=cat_id,
                    sitio_web=sitio,
                    login_user=usuario,
                    password_cifrada=password_cifrada
                )
                session.add(nueva_cred)
            
            logger.info(f"Credencial para '{sitio}' guardada con éxito.")
            # Ejecutar el callback de recarga y destruir ventana
            self.on_save_callback()
            self.destroy()

        except SQLAlchemyError as e:
            logger.error(f"Error al guardar credencial en base de datos: {e}")
            self.label_error.configure(text="Error de base de datos al guardar.")
        except Exception as e:
            logger.error(f"Error inesperado al cifrar/guardar: {e}")
            self.label_error.configure(text="Ocurrió un error inesperado.")


class GenerarContrasenaWindow(ctk.CTkToplevel):
    """
    Ventana emergente (modal) que actúa como generador seguro de contraseñas.
    """
    def __init__(self, parent: ctk.CTkFrame, app_root: ctk.CTk):
        super().__init__(parent)
        self.app_root = app_root

        # Configuración de ventana
        self.title("Generador Seguro de Contraseñas")
        self.geometry("420x380")
        self.resizable(False, False)

        # Comportamiento modal
        self.transient(parent)
        self.grab_set()
        self.focus_force()

        # Centrar ventana
        self.center_toplevel(parent)

        # Longitud por defecto
        self.longitud = 16

        # Encabezado
        self.label_titulo = ctk.CTkLabel(
            self,
            text="Generador de Contraseñas",
            font=ctk.CTkFont(family="Helvetica", size=20, weight="bold")
        )
        self.label_titulo.pack(pady=(20, 15))

        # Campo de visualización de contraseña (solo lectura)
        self.entry_pass = ctk.CTkEntry(
            self,
            width=320,
            height=40,
            font=ctk.CTkFont(family="Consolas", size=16, weight="bold"),
            justify="center"
        )
        self.entry_pass.pack(pady=10)

        # Etiqueta e indicador de longitud
        self.label_longitud = ctk.CTkLabel(
            self,
            text=f"Longitud: {self.longitud} caracteres",
            font=ctk.CTkFont(family="Helvetica", size=13)
        )
        self.label_longitud.pack(pady=(10, 0))

        # Slider de longitud (de 8 a 32 caracteres)
        self.slider = ctk.CTkSlider(
            self,
            from_=8,
            to=32,
            number_of_steps=24,
            command=self.on_slider_move
        )
        self.slider.set(self.longitud)
        self.slider.pack(pady=10, padx=40, fill="x")

        # Fila de botones de control (Regenerar, Copiar)
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

        # Label de notificación interna
        self.label_info = ctk.CTkLabel(
            self,
            text="",
            font=ctk.CTkFont(size=12)
        )
        self.label_info.pack(pady=5)

        # Generar primera contraseña por defecto
        self.regenerar_password()

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

    def on_slider_move(self, val):
        """Maneja el deslizamiento del slider de longitud."""
        self.longitud = int(val)
        self.label_longitud.configure(text=f"Longitud: {self.longitud} caracteres")
        self.regenerar_password()

    def regenerar_password(self):
        """Genera una nueva contraseña y la escribe en el entry."""
        self.password_actual = generar_contrasena_segura(self.longitud)
        self.entry_pass.configure(state="normal")
        self.entry_pass.delete(0, tk.END)
        self.entry_pass.insert(0, self.password_actual)
        self.entry_pass.configure(state="readonly")

    def copiar_resultado(self):
        """Copia la contraseña al portapapeles y alerta al usuario."""
        self.app_root.copiar_al_portapapeles(self.password_actual)
        
        # Efecto visual temporal en el botón
        self.btn_copiar.configure(text="¡Copiada!", fg_color="#2ECC71", state="disabled")
        self.after(3000, lambda: self.btn_copiar.configure(text="Copiar", fg_color="#1F6AA5", state="normal"))

        # Mostrar mensaje de advertencia
        self.label_info.configure(text="Contraseña copiada. Portapapeles se limpiará en 10 segundos.", text_color="#2ECC71")
        self.after(4000, lambda: self.label_info.configure(text=""))


class EditarCredencialWindow(ctk.CTkToplevel):
    """
    Ventana modal para editar una credencial existente.
    Carga los datos actuales pre-rellenados y realiza un UPDATE en la BD.
    """
    def __init__(
        self,
        parent: ctk.CTkFrame,
        credencial_id: str,
        sitio_web_actual: str,
        login_user_actual: str,
        categoria_id_actual,
        clave_derivada: bytes,
        on_save_callback: Callable[[], None]
    ):
        super().__init__(parent)
        self.credencial_id = credencial_id
        self.clave_derivada = clave_derivada
        self.on_save_callback = on_save_callback

        self.title("Editar Credencial")
        self.geometry("400x560")
        self.resizable(False, False)

        self.transient(parent)
        self.grab_set()
        self.focus_force()
        self.center_toplevel(parent)

        # Encabezado
        ctk.CTkLabel(
            self,
            text="Editar Credencial",
            font=ctk.CTkFont(family="Helvetica", size=20, weight="bold")
        ).pack(pady=(20, 15))

        # Campo: Sitio Web (pre-rellenado)
        self.entry_sitio = ctk.CTkEntry(self, width=300, placeholder_text="Sitio Web / Aplicación")
        self.entry_sitio.insert(0, sitio_web_actual)
        self.entry_sitio.pack(pady=8)

        # Campo: Usuario (pre-rellenado)
        self.entry_usuario = ctk.CTkEntry(self, width=300, placeholder_text="Usuario / Correo Electrónico")
        self.entry_usuario.insert(0, login_user_actual)
        self.entry_usuario.pack(pady=8)

        # Fila de contraseña + botón Generar en línea
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

        # Fila del Slider de longitud + etiqueta dinámica
        self.longitud_pass = 16  # Valor inicial

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
            number_of_steps=22,          # pasos enteros: 8, 9, 10, ... 30
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
            font=ctk.CTkFont(size=12)
        )
        self.check_show_pass.pack(pady=(5, 10))

        # Selector de categoría (con la actual pre-seleccionada)
        self.categorias_map = {}
        categorias_valores = ["Sin Categoría"]
        nombre_cat_actual = "Sin Categoría"
        try:
            with get_db_session() as session:
                cats = session.query(Categoria).order_by(Categoria.nombre).all()
                for c in cats:
                    self.categorias_map[c.nombre] = c.id
                    categorias_valores.append(c.nombre)
                    if c.id == categoria_id_actual:
                        nombre_cat_actual = c.nombre
        except Exception as e:
            logger.error(f"Error al cargar categorías en ventana de edición: {e}")

        self.option_categoria = ctk.CTkOptionMenu(self, width=300, values=categorias_valores)
        self.option_categoria.set(nombre_cat_actual)
        self.option_categoria.pack(pady=8)

        # Mensaje de error
        self.label_error = ctk.CTkLabel(self, text="", text_color="#FF3333", font=ctk.CTkFont(size=12))
        self.label_error.pack(pady=4)

        # Botón Guardar
        ctk.CTkButton(
            self,
            text="Guardar Cambios",
            width=200,
            fg_color="#1F6AA5",
            hover_color="#144870",
            command=self.guardar_cambios
        ).pack(pady=(5, 15))

    def center_toplevel(self, parent):
        """Centra la ventana sobre su padre."""
        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _on_slider_move(self, valor):
        """Actualiza la etiqueta y el estado interno al mover el slider de longitud."""
        self.longitud_pass = int(valor)
        self.label_longitud.configure(text=f"Longitud: {self.longitud_pass} caracteres")

    def generar_y_rellenar(self):
        """Genera una contraseña segura usando la longitud del slider e inserta el resultado en el campo."""
        nueva_pass = generar_contrasena_segura(self.longitud_pass)
        self.entry_password.configure(show="")   # revelar para que el usuario confirme
        self.entry_password.delete(0, tk.END)
        self.entry_password.insert(0, nueva_pass)
        # Activar el checkbox "Mostrar" para que el usuario vea la contraseña generada
        self.show_pass_var.set("on")
        self.check_show_pass.select()

    def toggle_password_visibility(self):
        self.entry_password.configure(show="" if self.show_pass_var.get() == "on" else "*")

    def guardar_cambios(self):
        """Valida y realiza el UPDATE en la base de datos."""
        sitio = self.entry_sitio.get().strip()
        usuario = self.entry_usuario.get().strip()
        nueva_pass = self.entry_password.get()

        if not sitio or not usuario:
            self.label_error.configure(text="Sitio web y usuario no pueden estar vacíos.")
            return

        cat_seleccionada = self.option_categoria.get()
        cat_id = self.categorias_map.get(cat_seleccionada)

        try:
            with get_db_session() as session:
                cred = session.query(Credencial).filter(Credencial.id == self.credencial_id).first()
                if not cred:
                    self.label_error.configure(text="Error: credencial no encontrada en la base de datos.")
                    return

                cred.sitio_web = sitio
                cred.login_user = usuario
                cred.categoria_id = cat_id

                # Solo re-cifra si el usuario escribió una nueva contraseña
                if nueva_pass:
                    cred.password_cifrada = cifrar_contrasena(nueva_pass, self.clave_derivada)

            logger.info(f"Credencial '{sitio}' (ID: {self.credencial_id}) actualizada correctamente.")
            self.on_save_callback()
            self.destroy()

        except SQLAlchemyError as e:
            logger.error(f"Error al actualizar credencial: {e}")
            self.label_error.configure(text="Error de base de datos al guardar.")
        except Exception as e:
            logger.error(f"Error inesperado al editar credencial: {e}")
            self.label_error.configure(text="Ocurrió un error inesperado.")


class DashboardFrame(ctk.CTkFrame):
    """
    Frame principal que representa la bóveda una vez que el usuario inicia sesión.
    """
    def __init__(self, parent: ctk.CTk, usuario_id: str, clave_derivada: bytes, usuario_nombre: str, on_logout: Callable[[], None]):
        super().__init__(parent, fg_color="transparent")
        self.parent = parent
        self.usuario_id = usuario_id
        self.clave_derivada = clave_derivada
        self.usuario_nombre = usuario_nombre
        self.on_logout = on_logout
        self._notif_timer = None
        self._mostrar_timers = {}  # Rastrear temporizadores activos para mostrar contraseñas

        # 1. Estructura de Ventana Principal: Grid Layout de 2 columnas
        # Columna 0: Sidebar (200px ancho)
        # Columna 1: Panel de Contenido (Resto del espacio, expandible)
        self.grid_columnconfigure(0, weight=0, minsize=200)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # 1.1. Barra Lateral / Sidebar (Columna 0)
        self.sidebar_frame = ctk.CTkFrame(
            self,
            width=200,
            fg_color="#0F172A",
            corner_radius=0,
            border_width=0
        )
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_propagate(False)

        # Título "LOCKBOX" en negrita e índigo (#6366F1)
        self.label_lockbox = ctk.CTkLabel(
            self.sidebar_frame,
            text="LOCKBOX",
            font=ctk.CTkFont(family="Helvetica", size=24, weight="bold"),
            text_color="#6366F1"
        )
        self.label_lockbox.pack(pady=(30, 25), padx=20, anchor="w")

        # Botones de navegación
        self.btn_mi_boveda = ctk.CTkButton(
            self.sidebar_frame,
            text="🔑 Mi Bóveda",
            font=ctk.CTkFont(family="Helvetica", size=14, weight="bold"),
            fg_color="#1E293B",  # Botón activo/seleccionado
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

        # Botón Cerrar Sesión en la parte inferior
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

        # 1.2. Panel de Contenido (Columna 1)
        self.content_panel = ctk.CTkFrame(
            self,
            fg_color="transparent",
            border_width=0
        )
        self.content_panel.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        
        self.content_panel.grid_columnconfigure(0, weight=1)
        self.content_panel.grid_rowconfigure(0, weight=0)  # Barra de Búsqueda
        self.content_panel.grid_rowconfigure(1, weight=0)  # Controles de filtro y adición
        self.content_panel.grid_rowconfigure(2, weight=1)  # Bóveda / ScrollableFrame

        # Barra de Búsqueda (ancho completo)
        self.search_entry = ctk.CTkEntry(
            self.content_panel,
            height=45,
            placeholder_text="🔍 Buscar sitio, usuario o categoría...",
            font=ctk.CTkFont(family="Helvetica", size=14)
        )
        self.search_entry.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        self.search_entry.bind("<KeyRelease>", lambda e: self.cargar_credenciales())

        # Contenedor de Controles (Dropdown, Notificaciones, Botón Agregar)
        self.controls_frame = ctk.CTkFrame(self.content_panel, fg_color="transparent", border_width=0)
        self.controls_frame.grid(row=1, column=0, sticky="ew", pady=(0, 15))
        self.controls_frame.grid_columnconfigure(0, weight=0) # Dropdown
        self.controls_frame.grid_columnconfigure(1, weight=1) # Notificación
        self.controls_frame.grid_columnconfigure(2, weight=0) # Botón Agregar

        # Variable y menú de categorías
        self.categoria_var = tk.StringVar(value="Todas")
        self.categorias_map = {}
        category_values = ["Todas"]
        try:
            with get_db_session() as session:
                cats = session.query(Categoria).order_by(Categoria.nombre).all()
                for c in cats:
                    self.categorias_map[c.nombre] = c.id
                    category_values.append(c.nombre)
        except Exception as e:
            logger.error(f"Error al cargar categorías para filtro: {e}")

        self.categoria_menu = ctk.CTkOptionMenu(
            self.controls_frame,
            variable=self.categoria_var,
            values=category_values,
            width=150,
            command=lambda _: self.cargar_credenciales()
        )
        self.categoria_menu.grid(row=0, column=0, sticky="w")

        # Label para avisos temporales
        self.label_notificacion = ctk.CTkLabel(
            self.controls_frame,
            text="",
            font=ctk.CTkFont(family="Helvetica", size=13, weight="bold")
        )
        self.label_notificacion.grid(row=0, column=1, padx=10)

        # Botón Agregar Credencial
        self.btn_agregar = ctk.CTkButton(
            self.controls_frame,
            text="+ Agregar Credencial",
            font=ctk.CTkFont(family="Helvetica", size=13, weight="bold"),
            command=self.abrir_ventana_agregar,
            width=160
        )
        self.btn_agregar.grid(row=0, column=2, sticky="e")

        # Contenedor con scroll para las tarjetas de credenciales
        self.scroll_frame = ctk.CTkScrollableFrame(self.content_panel, fg_color="transparent")
        self.scroll_frame.grid(row=2, column=0, sticky="nsew")

        # Cargar las credenciales inicialmente
        self.cargar_credenciales()

    def mostrar_notificacion_temporal(self, mensaje: str, es_error: bool = False):
        """Muestra una notificación visual en la parte superior central de la bóveda."""
        color = "#FF3333" if es_error else "#2ECC71"
        self.label_notificacion.configure(text=mensaje, text_color=color)

        if self._notif_timer:
            self.after_cancel(self._notif_timer)

        # Limpiar el mensaje a los 4 segundos
        self._notif_timer = self.after(4000, lambda: self.label_notificacion.configure(text=""))

    def cargar_credenciales(self):
        """Consulta la base de datos y dibuja la lista de credenciales según filtros de búsqueda y categoría."""
        # Cancelar todos los temporizadores de Mostrar activos antes de reconstruir la UI
        for timer_id in list(self._mostrar_timers.values()):
            try:
                self.after_cancel(timer_id)
            except Exception:
                pass
        self._mostrar_timers.clear()

        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        # Obtener filtros de la UI
        texto_busqueda = self.search_entry.get().strip()
        categoria_seleccionada = self.categoria_var.get()

        try:
            with get_db_session() as session:
                query = session.query(Credencial).filter(Credencial.usuario_id == self.usuario_id)

                # Filtro por categoría
                if categoria_seleccionada != "Todas":
                    cat_id = self.categorias_map.get(categoria_seleccionada)
                    if cat_id:
                        query = query.filter(Credencial.categoria_id == cat_id)

                # Filtro por texto (sitio o usuario) usando ILIKE
                if texto_busqueda:
                    pattern = f"%{texto_busqueda}%"
                    query = query.filter(or_(Credencial.sitio_web.ilike(pattern),
                                             Credencial.login_user.ilike(pattern)))

                credenciales = query.order_by(Credencial.sitio_web).all()

                if not credenciales:
                    self.mostrar_mensaje_vacio()
                    return

                for i, cred in enumerate(credenciales):
                    pass_cifrada_bytes = bytes(cred.password_cifrada)
                    self.crear_tarjeta_credencial(
                        credencial_id=str(cred.id),
                        sitio_web=cred.sitio_web,
                        login_user=cred.login_user,
                        password_cifrada=pass_cifrada_bytes,
                        categoria_id=cred.categoria_id,
                        index=i
                    )
        
        except SQLAlchemyError as e:
            logger.error(f"Error al cargar las credenciales de la BD: {e}")
            label_error = ctk.CTkLabel(
                self.scroll_frame,
                text="Error al conectar con la base de datos para cargar las credenciales.",
                text_color="#FF3333"
            )
            label_error.pack(pady=20)

    def mostrar_mensaje_vacio(self):
        """Muestra un mensaje informativo si no hay credenciales registradas."""
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
        password_cifrada: bytes,
        categoria_id,
        index: int
    ):
        """Dibuja una tarjeta individual con botones Mostrar, Copiar Usuario, Copiar Contraseña, Editar y Eliminar."""
        # 3. Tarjeta de Credenciales con bordes redondeados y borde
        card = ctk.CTkFrame(
            self.scroll_frame,
            height=100,
            corner_radius=10,
            border_width=1
        )
        card.pack(fill="x", pady=6, padx=5)
        card.pack_propagate(False)

        card.grid_columnconfigure(0, weight=1)   # Contenedor de texto
        card.grid_columnconfigure(1, weight=0)   # Contenedor de botones
        card.grid_rowconfigure(0, weight=1)

        # Contenedor de texto (Sitio, Usuario y Password oculta) - border_width=0 to float text
        text_container = ctk.CTkFrame(card, fg_color="transparent", border_width=0)
        text_container.grid(row=0, column=0, sticky="w", padx=25, pady=8)

        # Título del sitio en celeste (#38BDF8)
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

        # Contenedor de botones alineados a la derecha - border_width=0
        buttons_container = ctk.CTkFrame(card, fg_color="transparent", border_width=0)
        buttons_container.grid(row=0, column=1, sticky="e", padx=15, pady=8)

        # Botón Mostrar
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
            command=lambda p=password_cifrada, lp=label_pass, bm=btn_mostrar, cid=credencial_id:
                self.toggle_mostrar_contrasena(p, lp, bm, cid)
        )
        btn_mostrar.pack(side="left", padx=4)

        # Botón Copiar Usuario ("👤 Usuario")
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

        # Botón Copiar Contraseña ("🔑 Clave")
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
            command=lambda p=password_cifrada, b=btn_copiar_pass, s=sitio_web, u=login_user:
                self.copiar_contrasena(p, b, s, u)
        )
        btn_copiar_pass.pack(side="left", padx=4)

        # Botón Editar
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
            command=lambda cid=credencial_id, s=sitio_web, u=login_user, catid=categoria_id:
                self.abrir_ventana_editar(cid, s, u, catid)
        )
        btn_editar.pack(side="left", padx=4)

        # Botón Eliminar (Rojo desaturado/elegante)
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
        """Copia el usuario al portapapeles y da retroalimentación visual."""
        import pyperclip
        try:
            pyperclip.copy(usuario)
            logger.info("Usuario copiado al portapapeles.")
            
            # Retroalimentación visual temporal (green feedback, then reset to slate)
            boton.configure(text="¡Copiado!", fg_color="#059669", state="disabled")
            self.after(2000, lambda: boton.configure(text="👤 Usuario", fg_color="#334155", state="normal"))
            
            self.mostrar_notificacion_temporal("¡Usuario copiado al portapapeles!")
        except Exception as e:
            logger.error(f"Error al copiar usuario: {e}")

    def toggle_mostrar_contrasena(self, password_cifrada: bytes, label_pass: ctk.CTkLabel, boton_mostrar: ctk.CTkButton, credencial_id: str):
        """Alterna entre mostrar y ocultar la contraseña en texto plano con un timeout de 15 segundos."""
        # Cancelar cualquier temporizador activo para esta credencial
        if credencial_id in self._mostrar_timers:
            self.after_cancel(self._mostrar_timers[credencial_id])
            del self._mostrar_timers[credencial_id]

        if boton_mostrar.cget("text") == "Mostrar":
            try:
                datos_bytes = bytes(password_cifrada)
                pass_plana = descifrar_contrasena(datos_bytes, self.clave_derivada)
                
                # Actualizar UI
                label_pass.configure(text=pass_plana, text_color="#2ECC71")
                boton_mostrar.configure(text="Ocultar", fg_color="#475569", hover_color="#64748B")
                
                # Programar ocultación automática tras 15 segundos
                timer_id = self.after(15000, lambda: self.ocultar_contrasena_auto(label_pass, boton_mostrar, credencial_id))
                self._mostrar_timers[credencial_id] = timer_id
                
            except Exception as e:
                print(f"Error detallado al descifrar para mostrar: {e}")
                logger.error(f"Error al descifrar para mostrar: {e}")
                messagebox.showerror("Error", f"No se pudo descifrar la contraseña.\nDetalle: {e}")
        else:
            # Ocultar manualmente
            label_pass.configure(text="••••••••", text_color="#64748B")
            boton_mostrar.configure(text="Mostrar", fg_color="#334155", hover_color="#475569")

    def ocultar_contrasena_auto(self, label_pass: ctk.CTkLabel, boton_mostrar: ctk.CTkButton, credencial_id: str):
        """Oculta la contraseña automáticamente al expirar el temporizador de 15 segundos."""
        if label_pass.winfo_exists():
            label_pass.configure(text="••••••••", text_color="#64748B")
        if boton_mostrar.winfo_exists():
            boton_mostrar.configure(text="Mostrar", fg_color="#334155", hover_color="#475569")
        if credencial_id in self._mostrar_timers:
            del self._mostrar_timers[credencial_id]

    def copiar_contrasena(self, password_cifrada: bytes, boton: ctk.CTkButton, sitio: str, usuario: str):
        """Descifra la contraseña, la copia al portapapeles e inicia el temporizador de 30s."""
        try:
            # Asegurar conversión explícita a bytes antes de descifrar (resuelve memoryview en drivers como psycopg2)
            datos_bytes = bytes(password_cifrada)
            pass_plana = descifrar_contrasena(datos_bytes, self.clave_derivada)
            
            # Utilizar función centralizada de copia en el objeto App raíz
            self.parent.copiar_al_portapapeles(pass_plana)

            # Efecto visual en el botón de la tarjeta
            boton.configure(text="¡Copiada!", fg_color="#059669", state="disabled")
            self.after(3000, lambda: boton.configure(text="🔑 Clave", fg_color="#334155", state="normal"))

            # Mostrar mensaje de notificación
            self.mostrar_notificacion_temporal("¡Contraseña copiada al portapapeles! Se limpiará en 30 segundos.")
            
        except Exception as e:
            # Imprimir el error original detallado en la consola de Python para depuración
            print(f"Error detallado: {e}")
            logger.error(f"Error al descifrar o copiar contraseña de '{sitio}' para el usuario '{usuario}': {e}")
            messagebox.showerror("Error", f"No se pudo descifrar la contraseña.\nDetalle: {e}")

    def eliminar_credencial(self, credencial_id: str, sitio_web: str):
        """Pide confirmación y elimina la credencial de la base de datos."""
        confirmar = messagebox.askyesno(
            title="Confirmar eliminación",
            message=f"¿Estás seguro de que deseas eliminar la credencial de '{sitio_web}'?\n\nEsta acción no se puede deshacer."
        )
        if not confirmar:
            return

        try:
            with get_db_session() as session:
                cred = session.query(Credencial).filter(Credencial.id == credencial_id).first()
                if cred:
                    session.delete(cred)
            logger.info(f"Credencial '{sitio_web}' (ID: {credencial_id}) eliminada correctamente.")
            self.mostrar_notificacion_temporal(f"Credencial '{sitio_web}' eliminada.")
            self.cargar_credenciales()
        except SQLAlchemyError as e:
            logger.error(f"Error al eliminar credencial: {e}")
            messagebox.showerror("Error", f"No se pudo eliminar la credencial.\nDetalle: {e}")

    def abrir_ventana_editar(self, credencial_id: str, sitio_web: str, login_user: str, categoria_id):
        """Abre la ventana modal para editar una credencial existente."""
        EditarCredencialWindow(
            parent=self,
            credencial_id=credencial_id,
            sitio_web_actual=sitio_web,
            login_user_actual=login_user,
            categoria_id_actual=categoria_id,
            clave_derivada=self.clave_derivada,
            on_save_callback=self.cargar_credenciales
        )

    def abrir_ventana_agregar(self):
        """Abre la ventana modal para registrar una nueva credencial."""
        AgregarCredencialWindow(
            self, 
            usuario_id=self.usuario_id, 
            clave_derivada=self.clave_derivada, 
            on_save_callback=self.cargar_credenciales
        )

    def abrir_ventana_generador(self):
        """Abre la ventana modal del generador de contraseñas."""
        GenerarContrasenaWindow(self, self.parent)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Configuración básica de la ventana de login
        self.title("Gestor de Contraseñas Local - Acceso")
        self.geometry("450x550")
        self.resizable(False, False)

        # Centrar la ventana en la pantalla al iniciar
        self.center_window()

        # Variables de sesión y estado
        self.usuario_id = None
        self.clave_derivada = None
        self.usuario_nombre = None
        self.dashboard_frame = None
        self._clipboard_timer = None  # Identificador para limpiar el portapapeles

        # Construir la interfaz de login inicial
        self.setup_login_ui()

        # Asegurar que las tablas estén inicializadas
        self.check_database_connection()

    def center_window(self):
        """Centra la ventana en la pantalla del usuario."""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def check_database_connection(self):
        """Verifica que la base de datos esté activa e inicializa las tablas."""
        try:
            success = init_db()
            if not success:
                self.show_status("Error: No se pudo inicializar la base de datos. Verifica el archivo .env", is_error=True)
                messagebox.showerror(
                    "Error de Base de Datos",
                    "No se pudo conectar a la base de datos PostgreSQL.\n"
                    "Por favor, asegúrate de que el servicio de PostgreSQL esté iniciado y "
                    "las credenciales en el archivo .env sean correctas."
                )
        except Exception as e:
            logger.error(f"Excepción en la conexión de base de datos inicial: {e}")
            self.show_status("Error de conexión con la base de datos.", is_error=True)

    def show_status(self, message: str, is_error: bool = False):
        """Muestra un mensaje de estado en la parte inferior de la ventana de login."""
        color = "#FF3333" if is_error else "#2ECC71"
        if hasattr(self, 'status_label') and self.status_label.winfo_exists():
            self.status_label.configure(text=message, text_color=color)

    def setup_login_ui(self):
        """Crea todos los widgets correspondientes al Login/Registro."""
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
            text="Tu gestor de contraseñas local seguro", 
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

    def destroy_login_ui(self):
        """Destruye y limpia todos los widgets del formulario de login."""
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

        self.show_status("Verificando credenciales...")
        
        try:
            with get_db_session() as session:
                usuario = session.query(Usuario).filter_by(username=username).first()
                
                if not usuario:
                    self.show_status("Nombre de usuario o contraseña incorrectos.", is_error=True)
                    return
                
                es_valido = verificar_hash_maestro(password, usuario.master_hash)
                
                if es_valido:
                    self.usuario_id = usuario.id
                    self.usuario_nombre = usuario.username
                    self.clave_derivada = derivar_clave_fernet(password, usuario.salt_derivacion)
                    
                    logger.info(f"Acceso concedido a la bóveda para el usuario: {username}")
                    self.mostrar_dashboard()
                else:
                    self.show_status("Nombre de usuario o contraseña incorrectos.", is_error=True)
                    
        except SQLAlchemyError as db_err:
            logger.error(f"Error de base de datos durante login: {db_err}")
            self.show_status("Error de conexión a la base de datos.", is_error=True)
        except Exception as err:
            logger.error(f"Error inesperado en login: {err}")
            self.show_status("Ocurrió un error inesperado al procesar la solicitud.", is_error=True)

    def handle_register(self):
        username = self.register_user_entry.get().strip()
        password = self.register_pass_entry.get()

        if not username or not password:
            self.show_status("Por favor, llena todos los campos.", is_error=True)
            return

        if len(password) < 8:
            self.show_status("La contraseña maestra debe tener al menos 8 caracteres.", is_error=True)
            return

        self.show_status("Registrando usuario...")

        try:
            with get_db_session() as session:
                usuario_existente = session.query(Usuario).filter_by(username=username).first()
                if usuario_existente:
                    self.show_status("El nombre de usuario ya está registrado.", is_error=True)
                    return

                hash_maestro = generar_hash_maestro(password)
                salt_derivacion = generar_salt_derivacion()

                nuevo_usuario = Usuario(
                    username=username,
                    master_hash=hash_maestro,
                    salt_derivacion=salt_derivacion
                )
                session.add(nuevo_usuario)
                
            self.show_status("¡Usuario registrado con éxito! Ya puedes iniciar sesión.", is_error=False)
            logger.info(f"Usuario '{username}' registrado correctamente.")
            
            self.register_user_entry.delete(0, tk.END)
            self.register_pass_entry.delete(0, tk.END)
            
            self.tabview.set("Iniciar Sesión")
            self.login_user_entry.delete(0, tk.END)
            self.login_user_entry.insert(0, username)
            
        except SQLAlchemyError as db_err:
            logger.error(f"Error de base de datos durante registro: {db_err}")
            self.show_status("Error de conexión a la base de datos.", is_error=True)
        except Exception as err:
            logger.error(f"Error inesperado en registro: {err}")
            self.show_status("Ocurrió un error inesperado al procesar la solicitud.", is_error=True)

    def mostrar_dashboard(self):
        """Transiciona de la vista de login a la vista del Dashboard de la bóveda."""
        self.destroy_login_ui()

        self.geometry("950x650")
        self.resizable(True, True)
        self.center_window()

        self.dashboard_frame = DashboardFrame(
            self,
            usuario_id=self.usuario_id,
            clave_derivada=self.clave_derivada,
            usuario_nombre=self.usuario_nombre,
            on_logout=self.handle_logout
        )
        self.dashboard_frame.pack(fill="both", expand=True)

    def handle_logout(self):
        """Cierra la sesión del usuario actual, limpia memoria y vuelve a la pantalla de login."""
        # Limpiar portapapeles antes de salir por seguridad
        self.limpiar_portapapeles()

        self.usuario_id = None
        self.clave_derivada = None
        self.usuario_nombre = None

        self.geometry("450x550")
        self.resizable(False, False)
        self.center_window()

        self.setup_login_ui()
        self.show_status("Sesión cerrada correctamente.", is_error=False)

    # Lógica centralizada del portapapeles seguro usando pyperclip
    def copiar_al_portapapeles(self, texto: str):
        """
        Copia un texto al portapapeles del sistema usando pyperclip y programa su borrado automático a los 10s.
        Si se llama sucesivamente, reinicia el temporizador de limpieza.
        """
        import pyperclip

        # Cancelar cualquier temporizador de borrado anterior activo
        if self._clipboard_timer:
            self.after_cancel(self._clipboard_timer)
            self._clipboard_timer = None

        try:
            # Copiar usando la librería robusta multiplataforma pyperclip
            pyperclip.copy(texto)
            logger.info("Contraseña copiada al portapapeles.")
        except Exception as e:
            logger.error(f"Error al escribir en el portapapeles con pyperclip: {e}")

        # Programar la limpieza automática a los 30 segundos (30,000 milisegundos)
        self._clipboard_timer = self.after(30000, lambda: self.limpiar_portapapeles(texto))

    def limpiar_portapapeles(self, texto_copiado: str = None):
        """
        Limpia el portapapeles del sistema por seguridad.
        Si se pasa texto_copiado, solo lo limpia si el portapapeles sigue conteniendo esa contraseña exacta
        para evitar sobreescribir datos nuevos copiados externamente por el usuario.
        """
        import pyperclip
        try:
            # Si es limpieza incondicional (logout) o si el portapapeles contiene el mismo valor copiado, procedemos
            if texto_copiado is None or pyperclip.paste() == texto_copiado:
                pyperclip.copy("")
                logger.info("Portapapeles efímero limpiado automáticamente por razones de seguridad.")
            else:
                logger.info("El portapapeles fue modificado externamente por el usuario; se omitió la limpieza automática.")
        except Exception as e:
            logger.error(f"Error al limpiar el portapapeles con pyperclip: {e}")

        self._clipboard_timer = None


if __name__ == "__main__":
    app = App()
    app.mainloop()
