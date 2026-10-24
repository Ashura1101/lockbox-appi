# Revisión de mínimo privilegio de Lockbox

Cumple la parte de análisis del control **DIS-02 · P1** del checklist de seguridad: *cada usuario, servicio, token y componente accede solo a lo que necesita*.

- **Versión:** 1.0 · 22 de octubre de 2026
- **Código analizado:** rama `main` tras el commit `35d6699` (`THREAT_MODEL.md`)
- **Relación con DIS-01:** usa los adversarios y las amenazas de `THREAT_MODEL.md` (T-xx).
- **Alcance:** solo privilegios y accesos. Los demás riesgos siguen en `THREAT_MODEL.md` y se tratan en sus propios controles.

**Leyenda de estado:** `Conforme` = ya cumple. `Exceso` = tiene más acceso del necesario. `Sin verificar` = no se puede comprobar leyendo el código; hay que mirarlo en una consola.

---

## 1. Matriz de privilegios

### 1.1 Usuario final

| Qué puede hacer hoy | Qué necesita | Estado |
|---|---|---|
| Leer, buscar, editar y borrar solo sus credenciales: las consultas filtran por `usuario_id` en `/credentials`, `/search`, `/update` y `/delete` | Lo mismo | **Conforme** |
| Crear categorías que quedan **globales**: `Categoria(nombre=...)` se inserta sin dueño en `/add` y `/update` | Categorías propias o una lista fija | **Exceso** (F3) |
| Cualquier persona, sin cuenta, lee todas las categorías con `GET /api/categories` | Solo usuarios autenticados, y solo las suyas | **Exceso** (F3) |

### 1.2 Servicio: API Flask hacia la base de datos

| Qué puede hacer hoy | Qué necesita | Estado |
|---|---|---|
| Un único `DATABASE_URL` para todo. `init_db()` ejecuta `ALTER TABLE` en cada arranque, así que la cuenta tiene permisos de **DDL** (y en Supabase suele ser el rol propietario o `postgres`) | Un rol de aplicación con `SELECT/INSERT/UPDATE/DELETE` solo sobre `usuarios`, `categorias`, `credenciales` y `revoked_tokens`, sin DDL | **Exceso probable** (F1). El rol real **no se ve en el código**: confírmalo en la consola de la base de datos |
| No hay separación entre la cuenta que migra el esquema y la que sirve peticiones | Dos cuentas: migraciones (uso puntual) y ejecución (mínimos permisos) | **Exceso** (F1) |

### 1.3 Tokens

| Elemento | Qué hace hoy | Estado |
|---|---|---|
| Access token | Vida de 15 min, claim `type=access`, `jti` revocable, tipo verificado en `token_requerido` | **Conforme** |
| Refresh token | Vida de 7 días, claim `type=refresh`, rotación obligatoria con revocación del anterior, solo sirve en `/api/auth/refresh` | **Conforme** |
| Alcance del token | Sin `scope`, `aud` ni distinción de cliente: un access token vale igual para escritorio, móvil y extensión | Sin diferencia de privilegios (F2) |
| Efecto del token | Los endpoints de credenciales usan `token_opcional_log` (modo «soft launch»): aceptan la petición sin token. Quien autoriza de verdad es `usuario + contraseña maestra` en el cuerpo. El token no limita nada | **Exceso** (F2) |

### 1.4 Clientes

| Componente | Privilegios hoy | Estado |
|---|---|---|
| Escritorio | Habla solo con la API; no lleva credenciales de la base de datos | **Conforme** |
| Móvil (Android) | `INTERNET`, `USE_BIOMETRIC`, `USE_FINGERPRINT`: los tres se usan (red y huella). `allowBackup=false`. `MainActivity` exportada solo por ser el lanzador | **Conforme** |
| Móvil (iOS) | `Info.plist` sin permisos innecesarios | **Conforme** |
| Extensión de Chrome | `storage`, `clipboardWrite`, `activeTab`, `scripting`: todos se usan (sesión, copiar, autorrelleno al hacer clic). Sin `content_scripts` ni `<all_urls>` | **Conforme** |
| Extensión de Chrome, hosts | `host_permissions` incluye `http://localhost/*` y `http://127.0.0.1/*`, pero `API_URL` está fijada a Render. No se usan en producción | **Exceso** (F4) |

### 1.5 Red y CORS

| Qué hay hoy | Qué se necesita | Estado |
|---|---|---|
| `supports_credentials=True`, aunque la API usa cabecera `Authorization` y no cookies | `False` | **Exceso** (F5) |
| Métodos permitidos `GET, POST, PUT, DELETE, OPTIONS`; el código solo usa `GET`, `POST` y `OPTIONS` | `GET, POST, OPTIONS` | **Exceso** (F5) |
| Si falta `ALLOWED_ORIGINS`, se aceptan por defecto cuatro orígenes `localhost`/`127.0.0.1` | En producción, lista explícita y sin valores locales por defecto | **Exceso** (F5) |

### 1.6 Operación y cuentas

| Cuenta | Qué conviene comprobar | Estado |
|---|---|---|
| Render | Quién tiene acceso y con qué rol; variables `JWT_SECRET_KEY` y `DATABASE_URL` visibles solo para quien despliega | Sin verificar (F6) |
| Base de datos (Supabase u otra) | Rol de la API, quién puede entrar a la consola, si hay acceso público directo | Sin verificar (F6) |
| GitHub | Colaboradores y permisos; el conector con el que trabajo aquí es de **solo lectura** | Sin verificar (F6) |
| Chrome Web Store | Propietarios de la cuenta de publicación | Sin verificar (F6) |

---

## 2. Brechas de DIS-02

Ninguna está corregida. Todas figuran como **Pendiente**.

| ID | Brecha | Gravedad | Acción propuesta | Estado |
|---|---|---|---|---|
| F1 | La API usa una cuenta de base de datos con permisos de DDL, probablemente propietaria (T-04, T-05) | Alta | Crear el rol `lockbox_app` del apéndice, sustituir `DATABASE_URL` en Render y dejar las migraciones para un paso aparte con el rol propietario | Pendiente |
| F2 | El token no limita nada: se acepta la petición sin él (T-03) | Alta | Sustituir `token_opcional_log` por `token_requerido` en los endpoints de credenciales y exigir que `sub` del token coincida con el usuario del cuerpo. Su valor real depende de la decisión de arquitectura (DIS-12, GP-01): mientras la contraseña maestra viaje en cada petición, el token solo añade una segunda comprobación | Pendiente |
| F3 | Categorías globales creadas por cualquier usuario y listadas sin autenticar | Media | Exigir autenticación en `/api/categories` y, o bien una lista fija de categorías, o bien categorías con dueño | Pendiente |
| F4 | `host_permissions` con `localhost` y `127.0.0.1` en el manifiesto de producción | Baja | Quitar esas dos líneas del manifiesto que se publica (dejar un manifiesto aparte para desarrollo) | Pendiente |
| F5 | CORS más permisivo de lo que usa la API | Baja | `supports_credentials=False`, métodos `GET, POST, OPTIONS`, y sin orígenes locales por defecto fuera de desarrollo | Pendiente |
| F6 | Roles y accesos de Render, base de datos, GitHub y Chrome Web Store sin comprobar | Media | Revisar cada consola y anotar quién tiene acceso, con qué rol y si tiene MFA | Pendiente |

### Se ve en esta revisión pero pertenece a otros controles

- La lista de credenciales devuelve **todas** las contraseñas descifradas aunque la pantalla solo necesite sitio y usuario, y la extensión filtra por sitio en el cliente: **DIS-05** (minimizar datos) y API-03.
- `api.py` expone endpoints sin autenticación: **DIS-08** y API-01.
- `Info.plist` no declara `NSFaceIDUsageDescription`, la clave que iOS exige para usar Face ID: es un fallo funcional, no un exceso de privilegio.

---

## 3. Criterio de cierre de DIS-02

DIS-02 se marca como completado cuando:

1. F1 y F3 están corregidos y verificados.
2. F4 y F5 están corregidos.
3. F2 está corregido, o aceptado por escrito (OPS-10) hasta decidir el modelo de confianza de `THREAT_MODEL.md` sección 3.
4. F6 está revisado y los resultados anotados en este documento.

---

## Apéndice A. Borrador del rol de aplicación (F1)

Probar primero en un entorno de pruebas. Ejecutar con el rol propietario. Ajustar el nombre de la base de datos y, si el código borra tokens caducados, añadir `DELETE` sobre `revoked_tokens`.

```sql
CREATE ROLE lockbox_app LOGIN PASSWORD '<contraseña larga, aleatoria y única>';

GRANT CONNECT ON DATABASE <nombre_de_la_base> TO lockbox_app;
GRANT USAGE ON SCHEMA public TO lockbox_app;

GRANT SELECT, INSERT, UPDATE         ON usuarios       TO lockbox_app;
GRANT SELECT, INSERT                 ON categorias     TO lockbox_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON credenciales   TO lockbox_app;
GRANT SELECT, INSERT                 ON revoked_tokens TO lockbox_app;

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO lockbox_app;
```

Después de cambiar `DATABASE_URL` en Render, confirmar que login, alta, edición y borrado funcionan. `init_db()` seguirá intentando sus `ALTER TABLE` y los registrará como advertencia sin romper el arranque, porque ya están dentro de bloques `try/except`.

---

## Historial

| Fecha | Cambio |
|---|---|
| 2026-10-22 | Versión 1.0: primera revisión a partir del código en `main` tras `35d6699` |
