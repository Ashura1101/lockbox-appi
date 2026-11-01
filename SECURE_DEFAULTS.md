# Seguro por defecto en Lockbox

Cumple el control **DIS-03 · P1** del checklist de seguridad: *la configuración inicial debe ser la más segura (bloqueo automático activado, autorrelleno manual, permisos mínimos)*.

- **Versión:** 1.0 · 1 de noviembre de 2026
- **Código analizado:** rama `main` en el commit `fe973f2` (`PRIVILEGE_REVIEW.md`)
- **Relación con otros documentos:** usa las amenazas de `THREAT_MODEL.md` (T-xx) y las brechas de `PRIVILEGE_REVIEW.md` (F-x).
- **Regla aplicada:** si falta una opción, o su valor no es válido, se aplica la alternativa **más restrictiva**, nunca la más cómoda.

---

## 1. Qué cambia

| Componente | Antes (por defecto) | Ahora (por defecto) | Amenaza |
|---|---|---|---|
| **Móvil**: arranque con sesión guardada | Sin biometría activada (el valor por defecto), la bóveda se abría **sin pedir nada** | Siempre arranca bloqueada; se pide huella/Face ID (si la activó) o la contraseña maestra | T-09 |
| **Móvil**: pantalla de bloqueo | Con la biometría desactivada, `authenticateWithBiometrics()` devolvía `true` | Devuelve `false` si la biometría no está activada, no está disponible o falla (falla cerrado) | T-09 |
| **Escritorio**: inactividad | La sesión no caducaba | Cierra la sesión a los **5 min** sin actividad. Se puede ajustar de 1 a 60 min con `LOCKBOX_AUTOBLOQUEO_MIN`; **no se puede desactivar** | T-11 |
| **Extensión**: inactividad | La sesión duraba hasta cerrar el navegador | Cierra la sesión a los **5 min** sin actividad. Una sesión sin marca de actividad válida se considera caducada | T-10, T-11 |
| **Extensión**: contraseñas en el popup | Se mostraban en claro | Aparecen ocultas (`••••••••`); el botón 👁️ las muestra **15 s** y se vuelven a ocultar | T-10 |
| **Extensión**: editar credencial | El cuadro se precargaba con la contraseña actual en claro | Se abre vacío; vacío significa «no cambiarla» | T-10 |
| **API**: CORS sin `ALLOWED_ORIGINS` | Aceptaba cuatro orígenes `localhost` / `127.0.0.1` también en producción | Lista **vacía** salvo en modo debug (`FLASK_DEBUG=true`) | F5 |
| **API**: modo debug | Se calculaba solo dentro de `__main__` | Solo es `true` si `FLASK_DEBUG` vale literalmente `true`; cualquier otro valor es producción | — |
| **API**: cabeceras | `nosniff`, `X-Frame-Options`, CSP | Además `Cache-Control: no-store`, `Pragma: no-cache` y HSTS (solo sobre HTTPS) | T-08 |
| **Base de datos**: TLS | Si la URL no indicaba `sslmode`, `psycopg2` usaba `prefer` y podía caer a texto plano | Con servidor remoto y sin `sslmode`, se fuerza `sslmode=require` | T-04, T-08 |

El código nuevo está en `config_segura.py` (funciones puras de la API y del escritorio) y `Lockbox_Extension/session_policy.js` (política de la extensión).

---

## 2. Qué revisar al desplegar

Estos cambios alteran el comportamiento en producción. Conviene mirarlos antes de publicar.

1. **`ALLOWED_ORIGINS` en Render.** Si no está definida, ya no se acepta ningún origen web. La extensión no lo necesita (usa `host_permissions`) y los clientes nativos (escritorio y móvil) no pasan por CORS. Si algún sitio web propio llama a la API desde un navegador, añádelo explícitamente. `EXTENSION_ID`, si existe, se sigue añadiendo.
2. **`DATABASE_URL`.** Supabase y Render admiten TLS, así que no debería haber cambio. Si el proveedor no lo admite, las conexiones a la base de datos **fallarán** en lugar de hacerse sin cifrar; la salida segura es corregir el proveedor, no desactivar TLS. Una URL con `sslmode` explícito se respeta tal cual.
3. **HSTS.** `max-age=31536000` (un año) sin `includeSubDomains`. `ProxyFix` ya está configurado en `app_api.py`, así que `request.is_secure` refleja `X-Forwarded-Proto` de Render y la cabecera sí se envía.
4. **Sesiones que ya estaban abiertas.** Los usuarios de la extensión con la sesión iniciada antes de actualizar no tienen marca de actividad y tendrán que volver a iniciar sesión una vez (es el comportamiento de fallar cerrado).

---

## 3. Qué ya cumplía (sin cambios)

| Elemento | Estado |
|---|---|
| Móvil: auto-lock al volver de segundo plano tras más de 15 s | Conforme |
| Móvil: `allowBackup=false` en Android, permisos mínimos | Conforme |
| Extensión: autorrelleno solo con clic del usuario, sin `content_scripts` ni `<all_urls>` | Conforme |
| Escritorio: contraseña visible 15 s, portapapeles limpiado a los 30 s | Conforme |
| API: `FLASK_DEBUG` desactivado salvo petición expresa | Conforme |

---

## 4. Verificación

| Comprobación | Resultado |
|---|---|
| `python -m unittest test_dis03_defaults -v` | **19 pruebas pasan**. El grupo `TestAutobloqueoEscritorio` (cableado en `app_gui.py`) se **omite** si falta `bcrypt`; en el entorno donde se escribió esto no se pudo instalar. Ejecútalo en tu máquina tras `pip install -r requirements.txt` |
| `node --test tests_js/session_policy.test.js tests_js/popup_behavior.test.js` | **15 de 15 pasan** (política de sesión, ocultar/mostrar contraseña, edición, cierre de sesión) |
| `python -m py_compile` sobre `app_api.py`, `app_db.py`, `app_gui.py`, `config_segura.py` y `node --check` sobre `popup.js` y `session_policy.js` | Sin errores de sintaxis |
| Cambios de Flutter (`auth_controller.dart`, `biometric_lock_screen.dart`) | **Revisados leyendo el código; no ejecutados** (no había SDK de Flutter). Ejecuta `flutter test` y prueba a mano: abrir la app con la biometría desactivada debe pedir la contraseña maestra |
| `app_api.py` y `app_db.py` | Solo comprobada la sintaxis. **No** se arrancó el servidor ni se conectó a una base de datos real |

---

## 5. Brechas que quedan abiertas

Se vieron al revisar, pero pertenecen a otros controles:

- La extensión sigue autorrellenando en el primer campo de contraseña **sin comprobar que el dominio coincide** (T-10, GP-41).
- CORS conserva `supports_credentials=True` y los métodos `PUT`/`DELETE` que la API no usa (F5 de `PRIVILEGE_REVIEW.md`).
- `repomix-output.xml` sigue versionado (T-06) y `api.py` sigue en el repositorio (T-14).
- Móvil: la contraseña maestra en claro sigue guardada en el almacén seguro y `lockbox_offline.db` sigue sin cifrar (T-09). La biometría continúa siendo solo una compuerta de interfaz.
- El autobloqueo de escritorio y de la extensión **cierra la sesión** (hay que volver a escribir la contraseña maestra); no existe un bloqueo ligero con PIN.

---

## 6. Criterio de cierre de DIS-03

DIS-03 se marca como completado cuando:

1. Esta rama está revisada y mezclada en `main`.
2. Las pruebas de la sección 4 pasan en tu máquina, incluido el grupo omitido y `flutter test`.
3. Se ha comprobado a mano en un entorno de pruebas: arranque del móvil con la biometría desactivada, caducidad de sesión en escritorio y extensión, y arranque de la API sin `ALLOWED_ORIGINS`.
4. Se han revisado en Render los puntos de la sección 2.

---

## Historial

| Fecha | Cambio |
|---|---|
| 2026-11-01 | Versión 1.0: primera revisión y aplicación de valores por defecto seguros sobre `main` en `fe973f2` |
