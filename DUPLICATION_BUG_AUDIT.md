## Confirmación empírica

> Nota: el archivo `DUPLICATION_BUG_AUDIT.md` no existía en el repositorio al inicio
> de esta auditoría (verificado con `git ls-files` y búsqueda glob). Se crea con la
> sección requerida. No se reescribió ningún contenido previo porque no lo había.

### 1) Puntos de llamada a `loadCredentials()` y ausencia de guard/debounce — CONFIRMADO EN CÓDIGO

`loadCredentials()` (`lib/controllers/auth_controller.dart:257`) ejecuta
`await _readLocalCredentials()` y luego `unawaited(_syncWithServer())`
(`auth_controller.dart:259`). Por tanto, **cada** llamada a `loadCredentials()`
dispara una sincronización con el servidor sin control alguno.

Puntos de invocación confirmados leyendo el código actual:

| # | Ubicación | Referencia |
|---|-----------|------------|
| 1 | `VaultScreen` `initState()` (post-frame callback) | `lib/screens/vault_screen.dart:35-37` |
| 2 | `RefreshIndicator` `onRefresh` | `lib/screens/vault_screen.dart:199-200` |
| 3 | `AuthController.addCredential()` tras insertar localmente | `lib/controllers/auth_controller.dart:320` |
| 4 | `AuthController.updateCredential()` tras actualizar en API | `lib/controllers/auth_controller.dart:344` |
| 5 | `AuthController.deleteCredential()` tras eliminar en API | `lib/controllers/auth_controller.dart:358` |

Observación: la hipótesis describía "4 puntos (initState, RefreshIndicator y tras
add/update/delete)". En realidad hay **5** sitios de llamada (initState + refresh + 3
mutaciones), agrupables en las mismas 3 categorías. La descripción coincide en esencia.

**No existe ningún guard ni debounce** en `_syncWithServer()`
(`auth_controller.dart:277-294`): no hay flag `_isSyncing`, no hay lock, no hay
comprobación de ejecución en curso. Cada `loadCredentials()` lanza una `_syncWithServer()`
independiente y concurrente (vía `unawaited`).

`upsertVaultItem()` (`lib/services/local_database_service.dart:61-99`) es un
**SELECT-then-INSERT/UPDATE no atómico**: hace `db.query(... remote_id = ? ...)`
(`:68-73`) y, según el resultado, `update` (`:77-88`) o `insert` (`:90-97`). Entre el
SELECT y la escritura hay `await` que ceden al event loop, permitiendo intercalado de
dos syncs concurrentes.

El esquema de `vault_items` (`local_database_service.dart:27-39`) declara
`remote_id TEXT` **sin** restricción `UNIQUE`. Confirmado: es posible insertar dos filas
con el mismo `remote_id`.

### 2) Consulta a SQLite del dispositivo/emulador — NO VERIFICABLE (sin dispositivo conectado)

No fue posible ejecutar la consulta:

```sql
SELECT id, remote_id, title, is_synced, updated_at FROM vault_items WHERE title = 'Spotify' ORDER BY id;
```

Motivo:

- `adb devices` → `List of devices attached` **vacía** (no hay dispositivo físico ni
  emulador Android conectado).
- `flutter emulators` → `No emulators available`.
- `flutter devices` solo detecta Windows desktop / Chrome / Edge (no soportan `sqflite`).

Por tanto, este punto queda **pendiente de confirmación manual** del usuario (ejecutar la
consulta con `adb shell` + inspector de DB, o extraer `lockbox_offline.db` del dispositivo).

### 3) Fila de "Spotify" en PostgreSQL (`credenciales`) — PREMISA REFUTADA: hay 36 filas, no una

Se consultó directamente la base PostgreSQL (Supabase) usando el `DATABASE_URL` del `.env`
(pooler `aws-0-us-east-1.pooler.supabase.com:6543`), en modo solo lectura (solo `SELECT`).

```sql
SELECT id, usuario_id, sitio_web, login_user, fecha_actualizacion
FROM credenciales WHERE LOWER(sitio_web) LIKE '%spotify%'
ORDER BY fecha_actualizacion;
```

Resultado: **36 filas**, no una. Todas pertenecen al mismo usuario
(`usuario_id = a9eaaad8-69a0-40c0-bd9a-eaad06586c5d`, `username = 'MOD'`), con
`sitio_web = 'spotify.com'` y `login_user = 'shina'`. Cada fila tiene un `id` (UUID)
**distinto**.

Conteo agregado del usuario `MOD` (41 credenciales totales):

| sitio_web | login_user | n |
|-----------|------------|---|
| spotify.com | shina | **36** |
| (resto) | — | 5 |

Distribución temporal de las 36 filas (UTC): desde `2026-09-29 00:41:27` hasta
`2026-09-29 00:53:55`, con intervalos frecuentes de ~2-4 segundos entre filas
(ej. `00:49:15`, `00:49:27`, `00:49:31`, `00:49:34`, `00:49:41`, `00:49:44`,
`00:49:48`, `00:49:51`, `00:49:59`, `00:50:03`, `00:50:06` …).

UUIDs de las 36 filas (en orden de `fecha_actualizacion`):
`eb8823ba-143b-4816-a483-3fdd113e0d64`, `a145c349-ea1a-41f6-ac94-bc3bfb42f654`,
`0df9b103-feab-4697-990d-0c7fd940885d`, `39d71753-a1ac-427e-90d5-61f1f4860103`,
`4df53c54-3f59-4a5a-bbec-73f611db7b0c`, `e8029831-7d66-410f-b31c-b94df32b8a79`,
`2b462ba5-fc2e-4220-9fa1-6c1a0eb5dd4e`, `74326a41-a3fe-4ebc-87c1-dd37fc9a225d`,
`4405090b-3967-45f1-a2a6-184ec56618ab`, `925c3c17-3425-4f13-9ac4-63789b9eac8f`,
`f9cb82cc-1135-4e7c-a365-7dc3bc8877f9`, `7e1d3f46-fbce-4efc-b46e-de43e48df60b`,
`c0040dd0-1c3e-47fa-b997-012c10a9856b`, `6137b19f-5fc4-4a60-a3bb-e09661bc06a0`,
`3c43f233-add8-4ea7-98e5-9c2c38a8cefe`, `ca6f2a70-e7c6-4263-98f2-07c51cf87cbb`,
`efb59c07-f0b9-413a-9be8-594e3b8efb83`, `c0b48161-344a-482e-a0d8-bfa45854a0ff`,
`db0c08fe-5d34-45e2-bd50-4c026f54f7c6`, `4a724121-8d76-481c-975e-c25ead8d9d26`,
`838c1df8-ee19-46e8-b07d-477f1b5bafc0`, `13aff7ef-282b-4f12-bc0d-62a65ba55b1e`,
`bfca0fe1-3e6e-49bf-8b5e-2f197b274346`, `961efd2c-d028-436a-bff4-23b5af6fa93f`,
`61762241-39ca-4b4f-ad8d-5de55b11d864`, `595e5ffa-96f7-4a0e-8555-6b5ac908d638`,
`71666a8c-030b-4ba0-ad23-e86a1f30d744`, `f91a53b7-0e52-4bf3-b466-6071cc050490`,
`55f0ffb0-e382-456d-86b9-d98934444997`, `906b9fc7-d03a-4294-8eba-806b7cfea36c`,
`e410f5db-4d3b-44ba-838c-3cb18a8d294b`, `b4988feb-407d-4d78-ab3c-6a471309006c`,
`87635395-25af-4a9e-a133-a1b2262af730`, `8bf8d246-5dcc-46e3-8a3c-381815f46357`,
`2665e376-f572-4ca9-8346-cee5244a9f85`, `dd2bb751-16b1-4dfe-84c3-83826f847966`.

**Implicación para la hipótesis:** la premisa de que en PostgreSQL existe "una sola fila"
para `Spotify` **es falsa**. La duplicación ya está materializada en el servidor (36 filas
con UUIDs distintos). Un race condition en `upsertVaultItem()` (que opera sobre un único
`remote_id`) no puede explicar 36 filas con UUIDs distintos en PostgreSQL; en todo caso, el
cliente reflejaría localmente esas 36 filas (cada una con su propio `remote_id` único) al
sincronizar.

Dato adicional (observación, sin aplicar correcciones):
- El esquema de `credenciales` (`app_db.py:151-196`) no tiene restricción `UNIQUE` sobre
  `(usuario_id, sitio_web, login_user)`, por lo que el servidor permite duplicados.
- En el flujo de alta del móvil, `AuthController.addCredential()` llama a
  `vault.addVaultItem()` (`auth_controller.dart:314`), que hace POST a `/api/vault`
  (`vault_repository.dart:60`), pero **no existe** ruta `/vault` en `app_api.py`.
  `ApiService.addCredential()` (POST `/api/credentials/add`) existe pero **no se invoca**
  desde el móvil. La extensión (`Lockbox_Extension/popup.js:348`) sí hace POST a
  `/api/credentials/add`. Esto sugiere que las 36 filas de Spotify en el servidor provienen
  de una ruta distinta al race de SQLite.

### 4) Reproducción con dos llamadas casi simultáneas y captura de logs — NO VERIFICABLE (sin emulador)

No fue posible forzar dos llamadas a `loadCredentials()` ni capturar `debugPrint` de dos
`_syncWithServer()` solapadas, porque no hay dispositivo Android ni emulador disponible
(puntos 2). Este punto queda **pendiente** de verificación en un entorno con emulador.

---

### Resumen de estado de confirmación

| # | Punto | Estado |
|---|-------|--------|
| 1 | 5 puntos de llamada + sin guard/debounce + upsert no atómico sin UNIQUE | **CONFIRMADO** (código) |
| 2 | SELECT sobre `vault_items` en SQLite del dispositivo | **PENDIENTE** (sin dispositivo) |
| 3 | Una sola fila "Spotify" en PostgreSQL | **REFUTADO** (hay 36 filas) |
| 4 | Reproducción de sync concurrente + logs | **PENDIENTE** (sin emulador) |