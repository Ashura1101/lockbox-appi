const API_URL = "https://lockbox-appi.onrender.com/api";

// ==========================================
// MÓDULO CRIPTOGRÁFICO NATIVO (Zero-Knowledge)
// ==========================================

const encoder = new TextEncoder();
const decoder = new TextDecoder();

// Convertidores auxiliares Hexadecimal <-> Uint8Array
function bytesToHex(bytes) {
  return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
}

function hexToBytes(hex) {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.substr(i, 2), 16);
  }
  return bytes;
}

/**
 * Deriva dos claves a partir de la contraseña maestra:
 * 1. aesKey: Clave local para cifrar/descifrar (NUNCA SE ENVÍA).
 * 2. authHashHex: Token que se envía al servidor para iniciar sesión.
 */
async function deriveKeys(masterPassword, saltHex) {
  const salt = hexToBytes(saltHex);
  const keyMaterial = await crypto.subtle.importKey(
    "raw",
    encoder.encode(masterPassword),
    "PBKDF2",
    false,
    ["deriveBits", "deriveKey"]
  );

  // Clave local para Cifrado/Descifrado (AES-GCM 256-bit)
  const aesKey = await crypto.subtle.deriveKey(
    {
      name: "PBKDF2",
      salt: salt,
      iterations: 600000, // Recomendación OWASP
      hash: "SHA-256"
    },
    keyMaterial,
    { name: "AES-GCM", length: 256 },
    false,
    ["encrypt", "decrypt"]
  );

  // Hash de autenticación para el servidor
  const authBits = await crypto.subtle.deriveBits(
    {
      name: "PBKDF2",
      salt: encoder.encode("auth_" + saltHex),
      iterations: 100000,
      hash: "SHA-256"
    },
    keyMaterial,
    256
  );

  return {
    aesKey: aesKey,
    authHashHex: bytesToHex(new Uint8Array(authBits))
  };
}

/**
 * Cifra un texto plano en el navegador usando AES-GCM
 */
async function encryptLocal(plainText, aesKey) {
  const iv = crypto.getRandomValues(new Uint8Array(12)); // Vector de inicialización único
  const encryptedBuffer = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: iv },
    aesKey,
    encoder.encode(plainText)
  );

  return {
    ciphertextHex: bytesToHex(new Uint8Array(encryptedBuffer)),
    ivHex: bytesToHex(iv)
  };
}

/**
 * Descifra un texto cifrado en el navegador usando AES-GCM
 */
async function decryptLocal(ciphertextHex, ivHex, aesKey) {
  const ciphertext = hexToBytes(ciphertextHex);
  const iv = hexToBytes(ivHex);

  const decryptedBuffer = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: iv },
    aesKey,
    ciphertext
  );

  return decoder.decode(decryptedBuffer);
}

// Clave AES en memoria volátil de la sesión
let currentAesKey = null;

document.addEventListener("DOMContentLoaded", async () => {
  // Elementos de la interfaz
  const viewLogin = document.getElementById("view-login");
  const viewMain = document.getElementById("view-main");
  const formLogin = document.getElementById("form-login");
  const btnLogout = document.getElementById("btn-logout");
  const activeUserDisplay = document.getElementById("active-user-display");
  const statusMessage = document.getElementById("status-message");

  // Pestañas
  const tabSearch = document.getElementById("tab-search");
  const tabAdd = document.getElementById("tab-add");
  const viewSearch = document.getElementById("view-search");
  const viewAdd = document.getElementById("add-credential-form");

  // Inputs
  const searchSiteInput = document.getElementById("search-site");
  const btnSearch = document.getElementById("btn-search");
  const resultsContainer = document.getElementById("results-container");

  // Inputs Formulario Añadir
  const addSiteInput = document.getElementById("add-site");
  const addUserInput = document.getElementById("add-user");
  const addPassInput = document.getElementById("add-pass");

  // Estado del Servidor (Nube o Local)
  const apiStatusBadge = document.getElementById("api-status");
  if (apiStatusBadge) {
    if (API_URL.includes("onrender.com")) {
      apiStatusBadge.textContent = "Nube";
      apiStatusBadge.style.background = "rgba(16, 185, 129, 0.15)";
      apiStatusBadge.style.color = "#34d399";
      apiStatusBadge.style.borderColor = "rgba(16, 185, 129, 0.3)";
    } else {
      apiStatusBadge.textContent = "Local";
      apiStatusBadge.style.background = "rgba(99, 102, 241, 0.15)";
      apiStatusBadge.style.color = "#818cf8";
      apiStatusBadge.style.borderColor = "rgba(99, 102, 241, 0.3)";
    }
  }

  // AUTO-DETECCIÓN DE PESTAÑA ACTIVA
  if (typeof chrome !== "undefined" && chrome.tabs) {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0] && tabs[0].url) {
        try {
          const urlObj = new URL(tabs[0].url);
          let domain = urlObj.hostname.replace(/^www\./, "");
          if (domain && !domain.includes("chrome://") && !domain.includes("newtab")) {
            searchSiteInput.value = domain;
            if (addSiteInput) addSiteInput.value = domain;
          }
        } catch (e) {
          console.log("No se pudo obtener el dominio:", e);
        }
      }
    });
  }

  // 1. Comprobar si ya hay una sesión activa guardada
  chrome.storage.local.get(["currentUser", "masterPassword"], (data) => {
    if (data.currentUser && data.masterPassword) {
      showMainView(data.currentUser);
    } else {
      showLoginView();
    }
  });

  // 2. Evento del Login (Valida contra la API antes de guardar)
  formLogin.addEventListener("submit", async (e) => {
    e.preventDefault();
    const username = document.getElementById("login-username").value.trim();
    const masterPassword = document.getElementById("login-password").value;

    if (!username || !masterPassword) return;

    showStatus("Iniciando sesión...", "info");

    try {
      const response = await fetch(`${API_URL}/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, master_password: masterPassword })
      });

      const resData = await response.json();

      if (response.ok) {
        showStatus("", "hidden");
        // Almacenar tokens en memoria volátil de sesión (se borra automáticamente al cerrar el navegador)
        if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.session) {
          chrome.storage.session.set({
            accessToken: resData.access_token,
            refreshToken: resData.refresh_token
          });
        }
        chrome.storage.local.set({ currentUser: username, masterPassword: masterPassword }, () => {
          showMainView(username);
        });
      } else {
        showStatus(resData.error || "Usuario o contraseña incorrectos", "error");
      }
    } catch (err) {
      showStatus("Error al conectar con la API Python.", "error");
    }
  });

  // 3. Evento de Cerrar Sesión
  btnLogout.addEventListener("click", () => {
    if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.session) {
      chrome.storage.session.remove(["accessToken", "refreshToken"]);
    }
    chrome.storage.local.remove(["currentUser", "masterPassword"], () => {
      showLoginView();
    });
  });

  // Cambiar entre pestañas
  tabSearch.addEventListener("click", () => {
    tabSearch.classList.add("active");
    tabAdd.classList.remove("active");
    viewSearch.classList.remove("hidden");
    viewAdd.classList.add("hidden");
  });

  tabAdd.addEventListener("click", () => {
    tabAdd.classList.add("active");
    tabSearch.classList.remove("active");
    viewAdd.classList.remove("hidden");
    viewSearch.classList.add("hidden");
  });

  // 4. Buscar Credenciales usando el usuario activo
  btnSearch.addEventListener("click", async () => {
    const querySite = searchSiteInput.value.trim().toLowerCase();
    
    chrome.storage.local.get(["currentUser", "masterPassword"], async (data) => {
      if (!data.currentUser) return showStatus("Por favor inicia sesión", "error");

      showStatus("Consultando y descifrando...", "info");
      resultsContainer.textContent = "";

      try {
        const payload = {
          username: data.currentUser,
          master_password: data.masterPassword
        };
        if (querySite) payload.query = querySite;

        const res = await fetch(`${API_URL}/credentials`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });

        // Siempre leer el JSON primero (sea error o éxito)
        const result = await res.json();

        // 🚨 Rate limit superado — mostrar mensaje personalizado de Flask
        if (res.status === 429) {
          showStatus(result.error || "Has superado el límite de intentos. Espera un momento.", "error");
          return;
        }

        if (res.ok) {
          showStatus("", "hidden");
          let credenciales = result.credenciales || [];
          if (querySite) {
            credenciales = filterCredentialsForCurrentSite(credenciales, querySite);
          }
          renderResults(credenciales);
        } else {
          showStatus(result.error || "Error al obtener credenciales", "error");
        }
      } catch (err) {
        showStatus("Error al conectar con la API Python.", "error");
      }
    });
  });

  // 5. Guardar nueva credencial
  viewAdd.addEventListener("submit", async (e) => {
    e.preventDefault();
    
    chrome.storage.local.get(["currentUser", "masterPassword"], async (data) => {
      if (!data.currentUser || !data.masterPassword) {
        showStatus("Debes iniciar sesión primero.", "error");
        return;
      }

      const sitioWeb = normalizeDomain(addSiteInput.value);
      const loginUser = addUserInput.value.trim();
      const password = addPassInput.value.trim();

      showStatus("Cifrando y guardando...", "info");

      try {
        const response = await fetch(`${API_URL}/credentials/add`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            username: data.currentUser,
            master_password: data.masterPassword,
            sitio_web: sitioWeb,
            login_user: loginUser,
            password: password
          })
        });

        const resData = await response.json();

        if (response.ok) {
          showStatus(`¡'${sitioWeb}' cifrado y guardado con éxito!`, "success");
          viewAdd.reset();
        } else {
          showStatus(resData.error || "Error al guardar", "error");
        }
      } catch (err) {
        showStatus("Error de conexión con el servidor.", "error");
      }
    });
  });

  /**
   * Copia texto al portapapeles y programa autolimpieza en 30 segundos.
   */
  function copiarAlPortapapeles(texto) {
    if (!navigator.clipboard) return;
    navigator.clipboard.writeText(texto).then(() => {
      showStatus("¡Contraseña copiada! Se limpiará en 30s.", "success");
      setTimeout(async () => {
        try {
          const textoActual = await navigator.clipboard.readText();
          if (textoActual === texto) {
            await navigator.clipboard.writeText("");
            console.log("Portapapeles efímero limpiado automáticamente por seguridad.");
          }
        } catch (e) {
          // Si el documento perdió foco o permisos de lectura
        }
      }, 30000);
    });
  }

  /**
   * Normaliza cualquier entrada de sitio web a un dominio o URL estándar.
   * Ejemplos: "youtube" -> "youtube.com", "http://www.youtube.com" -> "youtube.com"
   */
  function normalizeDomain(input) {
    if (!input || typeof input !== "string") return "";
    let trimmed = input.trim().toLowerCase();

    if (trimmed.startsWith("localhost") || trimmed.startsWith("127.0.0.1")) {
      return trimmed.split("/")[0];
    }

    if (!trimmed.includes(".") && !trimmed.includes("://") && !trimmed.includes(":")) {
      return `${trimmed}.com`;
    }

    try {
      let urlToParse = trimmed;
      if (!urlToParse.startsWith("http://") && !urlToParse.startsWith("https://")) {
        urlToParse = "https://" + urlToParse;
      }
      const parsed = new URL(urlToParse);
      return parsed.hostname.replace(/^www\./, "");
    } catch (e) {
      return trimmed.replace(/^www\./, "");
    }
  }

  /**
   * Extrae las variantes de un término/URL para realizar una búsqueda inclusiva.
   * Ejemplo: "https://www.youtube.com/watch?v=..." -> { hostname: "youtube.com", domainBase: "youtube" }
   */
  function getSearchTermsFromUrl(urlString) {
    try {
      const urlObj = new URL(urlString);
      let hostname = urlObj.hostname.toLowerCase().replace(/^www\./, "");
      let domainBase = hostname.split(".")[0];
      return { hostname, domainBase };
    } catch (e) {
      let clean = urlString.toLowerCase().replace(/^https?:\/\//, "").replace(/^www\./, "").split("/")[0];
      let domainBase = clean.split(".")[0];
      return { hostname: clean, domainBase };
    }
  }

  /**
   * Lógica de filtrado en el cliente/popup con coincidencia fuerte y por nombre base
   */
  function filterCredentialsForCurrentSite(allCredentials, currentUrlOrDomain) {
    if (!currentUrlOrDomain) return allCredentials;

    const { hostname, domainBase } = getSearchTermsFromUrl(currentUrlOrDomain);
    const rawQuery = currentUrlOrDomain.toLowerCase().trim();

    return allCredentials.filter(cred => {
      if (!cred) return false;

      const site = (cred.sitio_web || "").toLowerCase().trim();
      const user = (cred.login_user || "").toLowerCase().trim();

      // Coincidencia por usuario
      if (user && user.includes(rawQuery)) return true;

      if (!site) return false;

      // Coincidencia 1: Exacta o parcial por FQDN ("youtube.com") o término directo
      const matchesHostname = site.includes(hostname) || hostname.includes(site) || site.includes(rawQuery) || rawQuery.includes(site);

      // Coincidencia 2: Coincidencia por nombre base ("youtube")
      const matchesBase = (domainBase && domainBase.length > 2) && (site.includes(domainBase) || domainBase.includes(site));

      return matchesHostname || matchesBase;
    });
  }

  // Funciones Auxiliares
  function showMainView(username) {
    viewLogin.classList.add("hidden");
    viewMain.classList.remove("hidden");
    btnLogout.classList.remove("hidden");
    activeUserDisplay.textContent = username;
    btnSearch.click(); // Autoconsultar al iniciar sesión
  }

  function showLoginView() {
    viewLogin.classList.remove("hidden");
    viewMain.classList.add("hidden");
    btnLogout.classList.add("hidden");
    document.getElementById("login-password").value = "";
    resultsContainer.textContent = "";
  }

  function showStatus(msg, type) {
    if (type === "hidden") {
      statusMessage.classList.add("hidden");
      return;
    }
    statusMessage.textContent = msg;
    statusMessage.className = `status-msg ${type}`;
    statusMessage.classList.remove("hidden");

    // Estilos dinámicos para mensajes de estado basados en el tipo
    statusMessage.style.cssText = `
      padding: 8px 12px; margin-top: 10px; border-radius: 6px; font-size: 12px; font-weight: 500; text-align: center;
      background: ${type === "error" ? "rgba(239, 68, 68, 0.2)" : type === "success" ? "rgba(34, 197, 94, 0.2)" : "rgba(59, 130, 246, 0.2)"};
      color: ${type === "error" ? "#fca5a5" : type === "success" ? "#86efac" : "#93c5fd"};
      border: 1px solid ${type === "error" ? "rgba(239, 68, 68, 0.4)" : type === "success" ? "rgba(34, 197, 94, 0.4)" : "rgba(59, 130, 246, 0.4)"};
    `;
  }

  function renderResults(lista) {
    resultsContainer.textContent = "";
    if (lista.length === 0) {
      const emptyDiv = document.createElement("div");
      emptyDiv.style.cssText = "padding: 12px; text-align: center; color: #a0aec0; font-size: 13px;";
      emptyDiv.textContent = "No se encontraron credenciales.";
      resultsContainer.appendChild(emptyDiv);
      return;
    }

    lista.forEach(c => {
      const card = document.createElement("div");
      card.style.cssText = `
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px; padding: 12px; margin-top: 10px;
      `;

      // 1. Fila de Encabezado (Sitio Web + Botones de Acción)
      const headerRow = document.createElement("div");
      headerRow.style.cssText = "display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;";

      const siteTitle = document.createElement("div");
      siteTitle.style.cssText = "font-weight: 700; color: #6366f1; font-size: 14px;";
      siteTitle.textContent = `🌐 ${c.sitio_web || ""}`;

      const actionButtons = document.createElement("div");

      const btnEdit = document.createElement("button");
      btnEdit.type = "button";
      btnEdit.className = "btn-edit-item";
      btnEdit.style.cssText = "background:none; border:none; cursor:pointer; font-size:14px;";
      btnEdit.title = "Editar";
      btnEdit.textContent = "✏️";

      const btnDelete = document.createElement("button");
      btnDelete.type = "button";
      btnDelete.className = "btn-delete-item";
      btnDelete.style.cssText = "background:none; border:none; cursor:pointer; font-size:14px; margin-left:6px;";
      btnDelete.title = "Eliminar";
      btnDelete.textContent = "🗑️";

      actionButtons.appendChild(btnEdit);
      actionButtons.appendChild(btnDelete);
      headerRow.appendChild(siteTitle);
      headerRow.appendChild(actionButtons);

      // 2. Fila de Usuario
      const userRow = document.createElement("div");
      userRow.style.cssText = "font-size: 12px; color: #cbd5e1; margin-bottom: 4px;";
      userRow.appendChild(document.createTextNode("👤 "));
      const userLabel = document.createElement("b");
      userLabel.textContent = "Usuario: ";
      userRow.appendChild(userLabel);
      userRow.appendChild(document.createTextNode(c.login_user || ""));

      // 3. Fila de Contraseña con Botón Copiar
      const passRow = document.createElement("div");
      passRow.style.cssText = "font-size: 12px; color: #cbd5e1; display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;";

      const passLabelSpan = document.createElement("span");
      passLabelSpan.appendChild(document.createTextNode("🔑 "));
      const passBold = document.createElement("b");
      passBold.textContent = "Password: ";
      passLabelSpan.appendChild(passBold);

      const passCode = document.createElement("code");
      passCode.style.cssText = "background: #0f172a; padding: 2px 6px; border-radius: 4px; color: #38bdf8;";
      passCode.textContent = c.password || "";
      passLabelSpan.appendChild(passCode);

      const btnCopy = document.createElement("button");
      btnCopy.type = "button";
      btnCopy.className = "btn-copy-item";
      btnCopy.style.cssText = "background:none; border:none; cursor:pointer;";
      btnCopy.title = "Copiar contraseña";
      btnCopy.textContent = "📋";

      passRow.appendChild(passLabelSpan);
      passRow.appendChild(btnCopy);

      // 4. Botón de Auto-llenado
      const btnAutofill = document.createElement("button");
      btnAutofill.type = "button";
      btnAutofill.className = "btn-autofill";
      btnAutofill.style.cssText = "width: 100%; background: #4f46e5; color: #fff; border: none; border-radius: 6px; padding: 6px; font-size: 12px; font-weight: 600; cursor: pointer;";
      btnAutofill.textContent = "⚡ Auto-llenar en el sitio";

      // Ensamblar tarjeta
      card.appendChild(headerRow);
      card.appendChild(userRow);
      card.appendChild(passRow);
      card.appendChild(btnAutofill);

      // Evento: Copiar con autolimpieza efímera en 30 segundos
      btnCopy.addEventListener("click", () => {
        copiarAlPortapapeles(c.password);
      });

      // Evento: Auto-llenar
      btnAutofill.addEventListener("click", () => {
        autofillCredentials(c.login_user, c.password);
        showStatus("¡Credenciales inyectadas!", "success");
        setTimeout(() => showStatus("", "hidden"), 2000);
      });

      // Evento: Eliminar
      btnDelete.addEventListener("click", async () => {
        chrome.storage.local.get(["currentUser", "masterPassword"], async (data) => {
          if (!data.currentUser || !data.masterPassword) return;
          if (!confirm(`¿Estás seguro de borrar las credenciales de '${c.sitio_web}'?`)) return;

          try {
            const res = await fetch(`${API_URL}/credentials/delete`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                id: c.id,
                username: data.currentUser,
                master_password: data.masterPassword
              })
            });

            if (res.ok) {
              showStatus("Credencial eliminada correctamente", "success");
              btnSearch.click(); // Recargar la lista
            } else {
              const resData = await res.json();
              showStatus(resData.error || "Error al eliminar", "error");
            }
          } catch (e) {
            showStatus("Error de conexión al eliminar", "error");
          }
        });
      });

      // Evento: Editar
      btnEdit.addEventListener("click", async () => {
        const nuevoSitio = prompt("Editar sitio web:", c.sitio_web);
        if (nuevoSitio === null) return;
        const sitioNormalizado = normalizeDomain(nuevoSitio);

        const nuevoUsuario = prompt("Editar usuario/email:", c.login_user);
        if (nuevoUsuario === null) return;

        const nuevaPassword = prompt("Editar contraseña (déjalo igual si no quieres cambiarla):", c.password);
        if (nuevaPassword === null) return;

        chrome.storage.local.get(["currentUser", "masterPassword"], async (data) => {
          if (!data.currentUser || !data.masterPassword) return;

          try {
            const res = await fetch(`${API_URL}/credentials/update`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                id: c.id,
                username: data.currentUser,
                master_password: data.masterPassword,
                sitio_web: sitioNormalizado,
                login_user: nuevoUsuario,
                password: nuevaPassword
              })
            });

            if (res.ok) {
              showStatus("Credencial actualizada con éxito", "success");
              btnSearch.click(); // Recargar la lista
            } else {
              const resData = await res.json();
              showStatus(resData.error || "Error al actualizar", "error");
            }
          } catch (e) {
            showStatus("Error de conexión al actualizar", "error");
          }
        });
      });

      resultsContainer.appendChild(card);
    });
  }
});

// ==========================================
// FUNCIÓN INYECTORA (Scripting)
// ==========================================
async function autofillCredentials(user, password) {
  if (typeof chrome === "undefined" || !chrome.tabs) return;

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !tab.id) return;

  chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: (userInput, passwordInput) => {
      const passField = document.querySelector('input[type="password"]');
      const userField = document.querySelector('input[type="text"], input[type="email"], input[name*="user"], input[name*="email"], input[name*="login"]');

      if (userField && userInput) {
        userField.value = userInput;
        userField.dispatchEvent(new Event('input', { bubbles: true }));
        userField.dispatchEvent(new Event('change', { bubbles: true }));
      }

      if (passField && passwordInput) {
        passField.value = passwordInput;
        passField.dispatchEvent(new Event('input', { bubbles: true }));
        passField.dispatchEvent(new Event('change', { bubbles: true }));
      }
    },
    args: [user, password]
  });
}