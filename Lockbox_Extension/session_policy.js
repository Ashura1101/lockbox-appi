// Política de sesión de la extensión (control DIS-03: seguro por defecto).
//
// Se carga como script clásico antes de popup.js, así que estas constantes y
// funciones quedan disponibles para él. El bloque final permite probarlas con
// Node (ver tests_js/session_policy.test.js) sin necesidad de un navegador.

// Tiempo máximo sin actividad antes de cerrar la sesión (5 minutos).
const SESSION_IDLE_LIMIT_MS = 5 * 60 * 1000;

// Tiempo que una contraseña permanece visible tras pulsar «mostrar» (15 s).
const REVEAL_PASSWORD_MS = 15 * 1000;

// Texto que sustituye a la contraseña mientras está oculta.
const PASSWORD_MASK = "••••••••";

// ¿Expiró la sesión por inactividad?
// Si no hay marca de actividad válida (sesión anterior a esta política, valor
// corrupto o inexistente) se considera expirada: se falla cerrado.
function isSessionExpired(lastActive, now) {
  if (typeof lastActive !== "number" || !isFinite(lastActive)) return true;
  if (typeof now !== "number" || !isFinite(now)) return true;
  return now - lastActive >= SESSION_IDLE_LIMIT_MS;
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = { SESSION_IDLE_LIMIT_MS, REVEAL_PASSWORD_MS, PASSWORD_MASK, isSessionExpired };
}
