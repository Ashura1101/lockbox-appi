// Pruebas de la política de sesión de la extensión (DIS-03).
// Ejecutar desde la raíz del repositorio:  node --test "tests_js/*.test.js"
const test = require("node:test");
const assert = require("node:assert/strict");
const {
  SESSION_IDLE_LIMIT_MS,
  REVEAL_PASSWORD_MS,
  PASSWORD_MASK,
  isSessionExpired,
} = require("../Lockbox_Extension/session_policy.js");

test("los valores por defecto son los acordados (5 min de sesión, 15 s de contraseña visible)", () => {
  assert.equal(SESSION_IDLE_LIMIT_MS, 5 * 60 * 1000);
  assert.equal(REVEAL_PASSWORD_MS, 15 * 1000);
  assert.ok(PASSWORD_MASK.length > 0);
});

test("una sesión con actividad reciente no expira", () => {
  const now = 1_000_000;
  assert.equal(isSessionExpired(now, now), false);
  assert.equal(isSessionExpired(now - (SESSION_IDLE_LIMIT_MS - 1), now), false);
});

test("expira justo al cumplirse el límite de inactividad", () => {
  const now = 1_000_000;
  assert.equal(isSessionExpired(now - SESSION_IDLE_LIMIT_MS, now), true);
  assert.equal(isSessionExpired(now - SESSION_IDLE_LIMIT_MS - 1, now), true);
});

test("falla cerrado: sin marca de actividad válida, la sesión se considera expirada", () => {
  const now = 1_000_000;
  for (const invalido of [undefined, null, "123", NaN, Infinity, {}, []]) {
    assert.equal(isSessionExpired(invalido, now), true, `lastActive=${String(invalido)}`);
  }
  assert.equal(isSessionExpired(now, undefined), true);
  assert.equal(isSessionExpired(now, NaN), true);
});
