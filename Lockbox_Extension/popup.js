const API_URL = "http://127.0.0.1:5000/api";
const DEFAULT_USER = "usuario_demo";

document.addEventListener("DOMContentLoaded", () => {
    // Pestañas
    const tabSearch = document.getElementById("tab-search");
    const tabAdd = document.getElementById("tab-add");
    const viewSearch = document.getElementById("view-search");
    const viewAdd = document.getElementById("view-add");

    // Inputs Búsqueda
    const masterPasswordInput = document.getElementById("master-password");
    const toggleMasterVisibilityBtn = document.getElementById("toggle-master-visibility");
    const searchSiteInput = document.getElementById("search-site");
    const btnSearch = document.getElementById("btn-search");
    const resultsContainer = document.getElementById("results-container");
    const statusMessage = document.getElementById("status-message");

    // Inputs Formulario Añadir
    const addCredentialForm = document.getElementById("add-credential-form");
    const addSiteInput = document.getElementById("add-site");
    const addUserInput = document.getElementById("add-user");
    const addPassInput = document.getElementById("add-pass");

    // Generador
    const genLengthInput = document.getElementById("gen-length");
    const lengthValLabel = document.getElementById("length-val");
    const genPasswordInput = document.getElementById("gen-password");
    const btnGenPassword = document.getElementById("btn-gen-password");
    const btnCopyGenPassword = document.getElementById("btn-copy-gen-password");
    const btnClearClipboard = document.getElementById("btn-clear-clipboard");

    // ==========================================
    // 0. RECUPERAR SESIÓN ACTIVA (STORAGE.SESSION)
    // ==========================================
    if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.session) {
        chrome.storage.session.get(["masterPasswordSession"], (result) => {
            if (result.masterPasswordSession) {
                masterPasswordInput.value = result.masterPasswordSession;
            }
        });
    }

    // ==========================================
    // 0.1 AUTO-DETECCIÓN DE PESTAÑA ACTIVA
    // ==========================================
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

    // ==========================================
    // 1. MANEJO DE PESTAÑAS (TABS)
    // ==========================================
    tabSearch.addEventListener("click", () => {
        tabSearch.classList.add("active");
        tabAdd.classList.remove("active");
        viewSearch.classList.remove("d-none");
        viewAdd.classList.add("d-none");
        ocultarMensaje();
    });

    tabAdd.addEventListener("click", () => {
        tabAdd.classList.add("active");
        tabSearch.classList.remove("active");
        viewAdd.classList.remove("d-none");
        viewSearch.classList.add("d-none");
        ocultarMensaje();
    });

    toggleMasterVisibilityBtn.addEventListener("click", () => {
        masterPasswordInput.type = masterPasswordInput.type === "password" ? "text" : "password";
    });

    // ==========================================
    // 2. CONSULTAR CREDENCIALES
    // ==========================================
    btnSearch.addEventListener("click", async () => {
        const masterPassword = masterPasswordInput.value.trim();
        const querySite = searchSiteInput.value.trim().toLowerCase();

        if (!masterPassword) {
            mostrarMensaje("Introduce tu contraseña maestra.", "error");
            return;
        }

        mostrarMensaje("Consultando y descifrando...", "info");

        try {
            const response = await fetch(`${API_URL}/credentials`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username: DEFAULT_USER, master_password: masterPassword })
            });

            const data = await response.json();

            if (response.ok) {
                // Guardar contraseña en la sesión del navegador
                if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.session) {
                    chrome.storage.session.set({ masterPasswordSession: masterPassword });
                }

                ocultarMensaje();
                let credenciales = data.credenciales || [];
                if (querySite) {
                    credenciales = credenciales.filter(c =>
                        c.sitio_web.toLowerCase().includes(querySite) ||
                        c.login_user.toLowerCase().includes(querySite)
                    );
                }
                renderizarResultados(credenciales);
            } else {
                mostrarMensaje(data.error || "Contraseña maestra incorrecta", "error");
            }
        } catch (err) {
            mostrarMensaje("Error al conectar con la API Python.", "error");
        }
    });

    // ==========================================
    // 3. GUARDAR NUEVA CREDENCIAL
    // ==========================================
    addCredentialForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const masterPassword = masterPasswordInput.value.trim();

        if (!masterPassword) {
            mostrarMensaje("Debes ingresar la Contraseña Maestra arriba antes de guardar.", "error");
            return;
        }

        const sitioWeb = addSiteInput.value.trim();
        const loginUser = addUserInput.value.trim();
        const password = addPassInput.value.trim();

        mostrarMensaje("Cifrando y guardando en Supabase...", "info");

        try {
            const response = await fetch(`${API_URL}/credentials/add`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    username: DEFAULT_USER,
                    master_password: masterPassword,
                    sitio_web: sitioWeb,
                    login_user: loginUser,
                    password: password
                })
            });

            const data = await response.json();

            if (response.ok) {
                // Guardar contraseña en la sesión del navegador
                if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.session) {
                    chrome.storage.session.set({ masterPasswordSession: masterPassword });
                }

                mostrarMensaje(`¡'${sitioWeb}' cifrado y guardado con éxito!`, "success");
                addCredentialForm.reset();
            } else {
                mostrarMensaje(data.error || "Error al guardar", "error");
            }
        } catch (err) {
            mostrarMensaje("Error de conexión con el servidor.", "error");
        }
    });

    // ==========================================
    // 4. RENDERIZADO Y AUTO-LLENADO
    // ==========================================
    function renderizarResultados(lista) {
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
                mostrarMensaje("¡Contraseña copiada!", "success");
                setTimeout(ocultarMensaje, 2000);
            });

            // Evento: Auto-llenar
            card.querySelector(".btn-autofill").addEventListener("click", () => {
                autofillCredentials(c.login_user, c.password);
                mostrarMensaje("¡Credenciales inyectadas!", "success");
                setTimeout(ocultarMensaje, 2000);
            });

            // Evento: Eliminar
            card.querySelector(".btn-delete-item").addEventListener("click", async () => {
                const masterPassword = masterPasswordInput.value.trim();
                if (!confirm(`¿Estás seguro de borrar las credenciales de '${c.sitio_web}'?`)) return;

                try {
                    const res = await fetch(`${API_URL}/credentials/delete`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            id: c.id,
                            username: DEFAULT_USER,
                            master_password: masterPassword
                        })
                    });

                    if (res.ok) {
                        mostrarMensaje("Credencial eliminada correctamente", "success");
                        btnSearch.click(); // Recargar la lista
                    } else {
                        const data = await res.json();
                        mostrarMensaje(data.error || "Error al eliminar", "error");
                    }
                } catch (e) {
                    mostrarMensaje("Error de conexión al eliminar", "error");
                }
            });

            // Evento: Editar
            card.querySelector(".btn-edit-item").addEventListener("click", async () => {
                const nuevoUsuario = prompt("Editar usuario/email:", c.login_user);
                if (nuevoUsuario === null) return;

                const nuevaPassword = prompt("Editar contraseña (déjalo igual si no quieres cambiarla):", c.password);
                if (nuevaPassword === null) return;

                const masterPassword = masterPasswordInput.value.trim();

                try {
                    const res = await fetch(`${API_URL}/credentials/update`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            id: c.id,
                            username: DEFAULT_USER,
                            master_password: masterPassword,
                            sitio_web: c.sitio_web,
                            login_user: nuevoUsuario,
                            password: nuevaPassword
                        })
                    });

                    if (res.ok) {
                        mostrarMensaje("Credencial actualizada con éxito", "success");
                        btnSearch.click(); // Recargar la lista
                    } else {
                        const data = await res.json();
                        mostrarMensaje(data.error || "Error al actualizar", "error");
                    }
                } catch (e) {
                    mostrarMensaje("Error de conexión al actualizar", "error");
                }
            });

            resultsContainer.appendChild(card);
        });
    }

    // ==========================================
    // 5. GENERADOR Y AUXILIARES
    // ==========================================
    genLengthInput.addEventListener("input", (e) => {
        lengthValLabel.textContent = `Longitud: ${e.target.value} caracteres`;
    });

    btnGenPassword.addEventListener("click", () => {
        const length = parseInt(genLengthInput.value);
        const chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()_+-=[]{}|;:,.<>?";
        let password = "";
        const array = new Uint32Array(length);
        window.crypto.getRandomValues(array);
        for (let i = 0; i < length; i++) password += chars[array[i] % chars.length];
        genPasswordInput.value = password;
    });

    btnCopyGenPassword.addEventListener("click", () => {
        if (!genPasswordInput.value) return;
        navigator.clipboard.writeText(genPasswordInput.value);
        mostrarMensaje("¡Contraseña generada copiada!", "success");
        setTimeout(ocultarMensaje, 2000);
    });

    btnClearClipboard.addEventListener("click", () => {
        navigator.clipboard.writeText("");
        mostrarMensaje("Portapapeles limpiado.", "info");
        setTimeout(ocultarMensaje, 2000);
    });

    function mostrarMensaje(texto, tipo) {
        statusMessage.textContent = texto;
        statusMessage.classList.remove("d-none");
        statusMessage.style.cssText = `
      padding: 8px 12px; margin-top: 10px; border-radius: 6px; font-size: 12px; font-weight: 500; text-align: center;
      background: ${tipo === "error" ? "rgba(239, 68, 68, 0.2)" : tipo === "success" ? "rgba(34, 197, 94, 0.2)" : "rgba(59, 130, 246, 0.2)"};
      color: ${tipo === "error" ? "#fca5a5" : tipo === "success" ? "#86efac" : "#93c5fd"};
      border: 1px solid ${tipo === "error" ? "rgba(239, 68, 68, 0.4)" : tipo === "success" ? "rgba(34, 197, 94, 0.4)" : "rgba(59, 130, 246, 0.4)"};
    `;
    }

    function ocultarMensaje() { statusMessage.classList.add("d-none"); }
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