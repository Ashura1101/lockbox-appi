const API_URL = "https://lockbox-appi.onrender.com/api";

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
      resultsContainer.innerHTML = "";

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
    resultsContainer.innerHTML = "";
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
    resultsContainer.innerHTML = "";
    if (lista.length === 0) {
      resultsContainer.innerHTML = `<div style="padding: 12px; text-align: center; color: #a0aec0; font-size: 13px;">No se encontraron credenciales.</div>`;
      return;
    }

    lista.forEach(c => {
      const card = document.createElement("div");
      card.style.cssText = `
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 8px; padding: 12px; margin-top: 10px;
      `;
      card.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
          <div style="font-weight: 700; color: #6366f1; font-size: 14px;">🌐 ${escapeHTML(c.sitio_web)}</div>
          <div>
            <button type="button" class="btn-edit-item" style="background:none; border:none; cursor:pointer; font-size:14px;" title="Editar">✏️</button>
            <button type="button" class="btn-delete-item" style="background:none; border:none; cursor:pointer; font-size:14px; margin-left:6px;" title="Eliminar">🗑️</button>
          </div>
        </div>
        <div style="font-size: 12px; color: #cbd5e1; margin-bottom: 4px;">👤 <b>Usuario:</b> ${escapeHTML(c.login_user)}</div>
        <div style="font-size: 12px; color: #cbd5e1; display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
          <span>🔑 <b>Password:</b> <code style="background: #0f172a; padding: 2px 6px; border-radius: 4px; color: #38bdf8;">${escapeHTML(c.password)}</code></span>
          <button type="button" class="btn-copy-item" style="background:none; border:none; cursor:pointer;" title="Copiar contraseña">📋</button>
        </div>
        <button type="button" class="btn-autofill" style="width: 100%; background: #4f46e5; color: #fff; border: none; border-radius: 6px; padding: 6px; font-size: 12px; font-weight: 600; cursor: pointer;">
          ⚡ Auto-llenar en el sitio
        </button>
      `;

      // Evento: Copiar
      card.querySelector(".btn-copy-item").addEventListener("click", () => {
        navigator.clipboard.writeText(c.password);
        showStatus("¡Contraseña copiada!", "success");
        setTimeout(() => showStatus("", "hidden"), 2000);
      });

      // Evento: Auto-llenar
      card.querySelector(".btn-autofill").addEventListener("click", () => {
        autofillCredentials(c.login_user, c.password);
        showStatus("¡Credenciales inyectadas!", "success");
        setTimeout(() => showStatus("", "hidden"), 2000);
      });

      // Evento: Eliminar
      card.querySelector(".btn-delete-item").addEventListener("click", async () => {
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
      card.querySelector(".btn-edit-item").addEventListener("click", async () => {
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

  function escapeHTML(str) { return str.replace(/[&<>'"]/g, tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)); }
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