// Pruebas de comportamiento del popup de la extensión (DIS-03), sin navegador ni dependencias.
//
// Ejecutan el popup.js REAL dentro de un contexto de Node con un DOM mínimo falso, un reloj
// falso y un `chrome.storage.session` en memoria. Comprueban:
//   - las contraseñas salen ocultas y solo se revelan 15 s al pedirlo;
//   - la sesión se cierra por inactividad (al abrir el popup y con el popup abierto);
//   - una sesión sin marca de actividad (anterior a esta política) se cierra: falla cerrado;
//   - al editar no se precarga la contraseña actual en el cuadro de diálogo.
//
// Ejecutar desde la raíz del repositorio:  node --test "tests_js/*.test.js"
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const EXT = path.join(__dirname, "..", "Lockbox_Extension");
const HTML = fs.readFileSync(path.join(EXT, "popup.html"), "utf8");
const IDS = [...HTML.matchAll(/id="([^"]+)"/g)].map((m) => m[1]);

const SECRETO = "S3cret!-no-debe-verse";
const MASK = "••••••••";
const flush = () => new Promise((r) => setImmediate(r));

// ---------- DOM falso mínimo ----------
class ClassList {
  constructor() { this.set = new Set(); }
  add(...c) { c.forEach((x) => this.set.add(x)); }
  remove(...c) { c.forEach((x) => this.set.delete(x)); }
  contains(c) { return this.set.has(c); }
}
class Txt {
  constructor(data) { this.data = String(data); }
  allText() { return this.data; }
}
class El {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.listeners = {};
    this.classList = new ClassList();
    this.style = {};
    this.value = "";
    this.title = "";
    this.className = "";
    this.disabled = false;
    this.type = "";
    this._text = "";
  }
  get textContent() { return this._text; }
  set textContent(v) { this._text = String(v); this.children = []; }
  appendChild(c) { this.children.push(c); return c; }
  addEventListener(ev, fn) { (this.listeners[ev] = this.listeners[ev] || []).push(fn); }
  async click() { for (const fn of this.listeners.click || []) await fn({ preventDefault() {}, target: this }); }
  querySelector() { this._qs = this._qs || new El("button"); return this._qs; }
  allText() { return this._text + this.children.map((c) => c.allText()).join(""); }
  find(pred, out = []) {
    this.children.forEach((c) => { if (c instanceof El) { if (pred(c)) out.push(c); c.find(pred, out); } });
    return out;
  }
}

// ---------- Reloj falso ----------
function makeClock() {
  let now = 1_700_000_000_000;
  let seq = 1;
  const timers = new Map();
  return {
    get now() { return now; },
    setTimeout(fn, ms) { const id = seq++; timers.set(id, { fn, at: now + ms, every: null }); return id; },
    setInterval(fn, ms) { const id = seq++; timers.set(id, { fn, at: now + ms, every: ms }); return id; },
    clear(id) { timers.delete(id); },
    async advance(ms) {
      const end = now + ms;
      for (;;) {
        let nextId = null;
        let nextAt = Infinity;
        for (const [id, t] of timers) if (t.at <= end && t.at < nextAt) { nextAt = t.at; nextId = id; }
        if (nextId === null) break;
        const t = timers.get(nextId);
        now = nextAt;
        if (t.every) t.at += t.every; else timers.delete(nextId);
        await t.fn();
        await flush();
      }
      now = end;
    },
  };
}

// ---------- Entorno completo del popup ----------
async function abrirPopup({ sesion, promptRespuestas = [] } = {}) {
  const clock = makeClock();
  const store = sesion ? { ...sesion(clock.now) } : {};
  const fetchCalls = [];
  const promptCalls = [];

  const els = {};
  IDS.forEach((id) => { els[id] = new El("div"); });
  els["view-main"].classList.add("hidden");
  els["btn-logout"].classList.add("hidden");

  const docListeners = {};
  const document = {
    addEventListener(ev, fn) { (docListeners[ev] = docListeners[ev] || []).push(fn); },
    getElementById(id) { return els[id]; },
    createElement(tag) { return new El(tag); },
    createTextNode(d) { return new Txt(d); },
    querySelector() { return null; },
    async dispatch(ev) { for (const fn of docListeners[ev] || []) await fn({}); },
  };

  const session = {
    get(keys, cb) {
      const ks = Array.isArray(keys) ? keys : typeof keys === "string" ? [keys] : Object.keys(keys || {});
      const out = {};
      ks.forEach((k) => { if (k in store) out[k] = store[k]; });
      // Como en Chrome, los callbacks se ejecutan de forma asíncrona.
      if (cb) { Promise.resolve().then(() => cb(out)); return undefined; }
      return Promise.resolve(out);
    },
    set(obj, cb) {
      Object.assign(store, obj);
      if (cb) { Promise.resolve().then(() => cb()); return undefined; }
      return Promise.resolve();
    },
    remove(keys, cb) {
      [].concat(keys).forEach((k) => delete store[k]);
      if (cb) { Promise.resolve().then(() => cb()); return undefined; }
      return Promise.resolve();
    },
  };

  const respuesta = (status, body) => ({ ok: status >= 200 && status < 300, status, json: async () => body });
  const fakeFetch = async (url, opts) => {
    fetchCalls.push({ url, body: opts && opts.body ? JSON.parse(opts.body) : null });
    if (url.endsWith("/credentials")) {
      return respuesta(200, { credenciales: [{ id: "1", sitio_web: "example.com", login_user: "ana", password: SECRETO }] });
    }
    if (url.endsWith("/credentials/update")) return respuesta(200, { message: "ok" });
    return respuesta(404, {});
  };

  class FakeDate extends Date {
    static now() { return clock.now; }
    constructor(...a) { if (a.length) super(...a); else super(clock.now); }
  }

  const respuestasPrompt = [...promptRespuestas];
  const sandbox = {
    document,
    chrome: {
      storage: { session },
      tabs: { query: (_q, cb) => cb([]) },
      scripting: { executeScript() {} },
    },
    fetch: fakeFetch,
    Headers,
    TextEncoder,
    TextDecoder,
    URL,
    console,
    navigator: {},
    prompt: (msg, def) => { promptCalls.push({ msg, def }); return respuestasPrompt.shift(); },
    confirm: () => true,
    setTimeout: clock.setTimeout,
    clearTimeout: clock.clear,
    setInterval: clock.setInterval,
    clearInterval: clock.clear,
    Date: FakeDate,
  };
  const ctx = vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(EXT, "session_policy.js"), "utf8"), ctx, { filename: "session_policy.js" });
  vm.runInContext(fs.readFileSync(path.join(EXT, "popup.js"), "utf8"), ctx, { filename: "popup.js" });
  await document.dispatch("DOMContentLoaded");
  await flush();
  await flush();

  return { els, store, clock, document, fetchCalls, promptCalls };
}

const sesionActiva = (now) => ({ currentUser: "ana", masterPassword: "maestra", accessToken: "a", refreshToken: "r", lastActive: now });
const sesionVista = (env) => !env.els["view-main"].classList.contains("hidden");
const tarjetaPassword = (env) => env.els["results-container"].find((e) => e.tag === "code")[0];
const botonPorClase = (env, clase) => env.els["results-container"].find((e) => e.className === clase)[0];

// ---------- Contraseñas ocultas por defecto ----------
test("la contraseña se muestra oculta por defecto y no aparece en ningún lugar de la tarjeta", async () => {
  const env = await abrirPopup({ sesion: sesionActiva });
  assert.ok(sesionVista(env), "la sesión activa debe mostrar la vista principal");
  assert.equal(tarjetaPassword(env).textContent, MASK);
  assert.ok(!env.els["results-container"].allText().includes(SECRETO), "la contraseña no debe estar en el texto de la tarjeta");
});

test("«mostrar» revela la contraseña y se vuelve a ocultar sola a los 15 s", async () => {
  const env = await abrirPopup({ sesion: sesionActiva });
  await botonPorClase(env, "btn-reveal-item").click();
  assert.equal(tarjetaPassword(env).textContent, SECRETO);

  await env.clock.advance(14_000);
  assert.equal(tarjetaPassword(env).textContent, SECRETO, "aún visible a los 14 s");
  await env.clock.advance(1_000);
  assert.equal(tarjetaPassword(env).textContent, MASK, "oculta de nuevo a los 15 s");
});

test("pulsar «mostrar» dos veces vuelve a ocultar la contraseña", async () => {
  const env = await abrirPopup({ sesion: sesionActiva });
  const boton = botonPorClase(env, "btn-reveal-item");
  await boton.click();
  await boton.click();
  assert.equal(tarjetaPassword(env).textContent, MASK);
});

// ---------- Inactividad ----------
test("una sesión con actividad reciente se mantiene al abrir el popup", async () => {
  const env = await abrirPopup({ sesion: sesionActiva });
  assert.ok(sesionVista(env));
  assert.equal(env.store.currentUser, "ana");
});

test("una sesión caducada por inactividad se cierra al abrir el popup y se borran los datos", async () => {
  const env = await abrirPopup({ sesion: (now) => sesionActiva(now - 5 * 60 * 1000 - 1) });
  assert.ok(!sesionVista(env), "no debe mostrar la bóveda");
  assert.ok(!env.els["view-login"].classList.contains("hidden"), "debe mostrar el login");
  for (const clave of ["currentUser", "masterPassword", "accessToken", "refreshToken", "lastActive"]) {
    assert.ok(!(clave in env.store), `${clave} debe haberse borrado`);
  }
  assert.match(env.els["status-message"].textContent, /inactividad/);
});

test("falla cerrado: una sesión sin marca de actividad (anterior a esta política) se cierra", async () => {
  const env = await abrirPopup({
    sesion: () => ({ currentUser: "ana", masterPassword: "maestra", accessToken: "a", refreshToken: "r" }),
  });
  assert.ok(!sesionVista(env));
  assert.ok(!("masterPassword" in env.store));
});

test("con el popup abierto, la sesión se cierra tras 5 min sin actividad", async () => {
  const env = await abrirPopup({ sesion: sesionActiva });
  await env.clock.advance(4 * 60 * 1000);
  assert.ok(sesionVista(env), "a los 4 min sigue abierta");
  await env.clock.advance(61 * 1000);
  assert.ok(!sesionVista(env), "pasados los 5 min se cierra");
  assert.ok(!("masterPassword" in env.store));
});

test("la actividad del usuario reinicia el contador de inactividad", async () => {
  const env = await abrirPopup({ sesion: sesionActiva });
  await env.clock.advance(4 * 60 * 1000);
  await env.document.dispatch("click"); // el usuario hace clic
  await env.clock.advance(4 * 60 * 1000);
  assert.ok(sesionVista(env), "8 min en total, pero solo 4 desde el último clic");
  await env.clock.advance(70 * 1000);
  assert.ok(!sesionVista(env), "5 min desde el último clic: se cierra");
});

test("«Cerrar sesión» borra tokens, usuario, contraseña maestra y marca de actividad", async () => {
  const env = await abrirPopup({ sesion: sesionActiva });
  await env.els["btn-logout"].click();
  assert.ok(!sesionVista(env));
  for (const clave of ["currentUser", "masterPassword", "accessToken", "refreshToken", "lastActive"]) {
    assert.ok(!(clave in env.store), `${clave} debe haberse borrado`);
  }
});

// ---------- Editar ----------
test("al editar, el cuadro de contraseña no se precarga con la contraseña actual y vacío = no cambiarla", async () => {
  const env = await abrirPopup({ sesion: sesionActiva, promptRespuestas: ["example.com", "ana", ""] });
  await botonPorClase(env, "btn-edit-item").click();
  await flush();
  await flush();

  assert.equal(env.promptCalls.length, 3);
  for (const p of env.promptCalls) {
    assert.notEqual(p.def, SECRETO, "ningún cuadro debe mostrar la contraseña en claro");
  }
  assert.equal(env.promptCalls[2].def, "");

  const actualizacion = env.fetchCalls.find((c) => c.url.endsWith("/credentials/update"));
  assert.ok(actualizacion, "debe haberse llamado a /credentials/update");
  assert.ok(!("password" in actualizacion.body), "sin contraseña nueva no se envía el campo password");
});

test("al editar con una contraseña nueva, esta sí se envía", async () => {
  const env = await abrirPopup({ sesion: sesionActiva, promptRespuestas: ["example.com", "ana", "NuevaClave#1"] });
  await botonPorClase(env, "btn-edit-item").click();
  await flush();
  await flush();

  const actualizacion = env.fetchCalls.find((c) => c.url.endsWith("/credentials/update"));
  assert.equal(actualizacion.body.password, "NuevaClave#1");
});
