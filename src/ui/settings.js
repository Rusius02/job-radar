const siteForm = document.querySelector("#site-form");
const siteList = document.querySelector("#site-list");
const siteCount = document.querySelector("#site-count");
const formStatus = document.querySelector("#site-form-status");
const listStatus = document.querySelector("#site-list-status");
const integrationForm = document.querySelector("#integration-form");
const integrationList = document.querySelector("#integration-list");
const integrationCount = document.querySelector("#integration-count");
const integrationFormStatus = document.querySelector("#integration-form-status");
const integrationListStatus = document.querySelector("#integration-list-status");
const integrationSubmit = document.querySelector("#integration-submit");
const integrationCancel = document.querySelector("#integration-cancel");
let editingIntegrationId = null;

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error(`Le serveur a répondu ${response.status} avec une réponse invalide.`);
  }
  if (!response.ok) throw new Error(payload.error || `Le serveur a répondu ${response.status}.`);
  return payload;
}

function makeBadge(text, extraClass = "") {
  const badge = document.createElement("span");
  badge.className = `site-badge ${extraClass}`.trim();
  badge.textContent = text;
  return badge;
}

function makeAction(label, extraClass, onClick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `site-action ${extraClass}`.trim();
  button.textContent = label;
  button.addEventListener("click", onClick);
  return button;
}

function renderSite(site) {
  const card = document.createElement("article");
  card.className = "site-card";

  const main = document.createElement("div");
  main.className = "site-card-main";
  const name = document.createElement("h3");
  name.className = "site-card-name";
  name.textContent = site.name;
  const link = document.createElement("a");
  link.className = "site-card-url";
  link.href = site.url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = site.url;
  const badges = document.createElement("div");
  badges.className = "site-badges";
  badges.append(makeBadge(site.is_enabled ? "Actif" : "En pause", site.is_enabled ? "enabled" : ""));
  badges.append(makeBadge(site.terms_reviewed ? "Règles consultées" : "Règles à vérifier"));
  main.append(name, link, badges);

  const actions = document.createElement("div");
  actions.className = "site-actions";
  actions.append(makeAction(site.is_enabled ? "Mettre en pause" : "Activer", "", async () => {
    await changeEnabled(site.id, !site.is_enabled);
  }));
  actions.append(makeAction("Retirer", "remove", async () => {
    if (!window.confirm(`Retirer « ${site.name} » de votre liste ?`)) return;
    await removeSite(site.id);
  }));
  card.append(main, actions);
  return card;
}

function renderEmpty(message) {
  const state = document.createElement("p");
  state.className = "state-card";
  state.textContent = message;
  siteList.replaceChildren(state);
}

async function loadSites() {
  try {
    const sites = await requestJson("/api/sites");
    if (!Array.isArray(sites)) throw new Error("Le format de la liste de sites est invalide.");
    siteCount.textContent = `${sites.length} site${sites.length === 1 ? "" : "s"}`;
    if (sites.length === 0) {
      renderEmpty("Votre liste est vide. Ajoutez un site pour commencer à organiser vos sources.");
      return;
    }
    siteList.replaceChildren(...sites.map(renderSite));
  } catch (error) {
    siteCount.textContent = "indisponible";
    renderEmpty(`Impossible de charger la liste : ${error.message}`);
  }
}

async function changeEnabled(siteId, isEnabled) {
  listStatus.textContent = "";
  try {
    await requestJson(`/api/sites/${siteId}`, {
      method: "PATCH",
      body: JSON.stringify({ is_enabled: isEnabled }),
    });
    await loadSites();
  } catch (error) {
    listStatus.textContent = `Modification impossible : ${error.message}`;
  }
}

async function removeSite(siteId) {
  listStatus.textContent = "";
  try {
    await requestJson(`/api/sites/${siteId}`, { method: "DELETE" });
    await loadSites();
  } catch (error) {
    listStatus.textContent = `Suppression impossible : ${error.message}`;
  }
}

function parseJsonObject(field, label) {
  let value;
  try {
    value = JSON.parse(field.value || "{}");
  } catch {
    throw new Error(`${label} contiene un JSON non valido.`);
  }
  if (!value || Array.isArray(value) || typeof value !== "object") {
    throw new Error(`${label} deve essere un oggetto JSON.`);
  }
  return value;
}

function renderIntegration(integration) {
  const card = document.createElement("article");
  card.className = "site-card";

  const main = document.createElement("div");
  main.className = "site-card-main";
  const name = document.createElement("h3");
  name.className = "site-card-name";
  name.textContent = integration.name;
  const link = document.createElement("a");
  link.className = "site-card-url";
  link.href = integration.url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = integration.url;
  const badges = document.createElement("div");
  badges.className = "site-badges";
  badges.append(makeBadge(integration.method));
  badges.append(makeBadge(integration.is_enabled ? "Actif" : "En pause", integration.is_enabled ? "enabled" : ""));
  badges.append(makeBadge(`${integration.header_names.length} en-tête${integration.header_names.length === 1 ? "" : "s"}`));
  main.append(name, link, badges);

  const actions = document.createElement("div");
  actions.className = "site-actions";
  actions.append(makeAction("Modifier", "", () => editIntegration(integration)));
  actions.append(makeAction(integration.is_enabled ? "Mettre en pause" : "Activer", "", async () => {
    await changeIntegrationEnabled(integration.id, !integration.is_enabled);
  }));
  actions.append(makeAction("Retirer", "remove", async () => {
    if (!window.confirm(`Retirer l’API « ${integration.name} » de votre liste ?`)) return;
    await removeIntegration(integration.id);
  }));
  card.append(main, actions);
  return card;
}

function renderEmptyIntegrations(message) {
  const state = document.createElement("p");
  state.className = "state-card";
  state.textContent = message;
  integrationList.replaceChildren(state);
}

async function loadIntegrations() {
  try {
    const integrations = await requestJson("/api/integrations");
    if (!Array.isArray(integrations)) throw new Error("Le format de la liste d’APIs est invalide.");
    integrationCount.textContent = `${integrations.length} API${integrations.length === 1 ? "" : "s"}`;
    if (integrations.length === 0) {
      renderEmptyIntegrations("Aucune API configurée pour le moment.");
      return;
    }
    integrationList.replaceChildren(...integrations.map(renderIntegration));
  } catch (error) {
    integrationCount.textContent = "indisponible";
    renderEmptyIntegrations(`Impossible de charger les APIs : ${error.message}`);
  }
}

function editIntegration(integration) {
  editingIntegrationId = integration.id;
  integrationForm.elements.name.value = integration.name;
  integrationForm.elements.url.value = integration.url;
  integrationForm.elements.method.value = integration.method;
  integrationForm.elements.query_params.value = JSON.stringify(integration.query_params, null, 2);
  integrationForm.elements.headers.value = "";
  integrationForm.elements.clear_headers.checked = false;
  integrationForm.elements.body.value = JSON.stringify(integration.body, null, 2);
  integrationForm.elements.is_enabled.checked = integration.is_enabled;
  integrationSubmit.textContent = "Enregistrer les modifications";
  integrationCancel.hidden = false;
  integrationFormStatus.textContent = "En-têtes existants masqués ; laissez le champ vide pour les conserver.";
  integrationForm.scrollIntoView({ behavior: "smooth", block: "start" });
}

function resetIntegrationForm() {
  editingIntegrationId = null;
  integrationForm.reset();
  integrationForm.elements.query_params.value = "{}";
  integrationForm.elements.body.value = "{}";
  integrationSubmit.textContent = "Enregistrer l’API";
  integrationCancel.hidden = true;
  integrationFormStatus.textContent = "";
}

async function changeIntegrationEnabled(integrationId, isEnabled) {
  integrationListStatus.textContent = "";
  try {
    await requestJson(`/api/integrations/${integrationId}`, {
      method: "PATCH",
      body: JSON.stringify({ is_enabled: isEnabled }),
    });
    await loadIntegrations();
  } catch (error) {
    integrationListStatus.textContent = `Modification impossible : ${error.message}`;
  }
}

async function removeIntegration(integrationId) {
  integrationListStatus.textContent = "";
  try {
    await requestJson(`/api/integrations/${integrationId}`, { method: "DELETE" });
    if (editingIntegrationId === integrationId) resetIntegrationForm();
    await loadIntegrations();
  } catch (error) {
    integrationListStatus.textContent = `Suppression impossible : ${error.message}`;
  }
}

siteForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  formStatus.textContent = "";
  const payload = {
    name: siteForm.elements.name.value.trim(),
    url: siteForm.elements.url.value.trim(),
    is_enabled: siteForm.elements.is_enabled.checked,
    terms_reviewed: siteForm.elements.terms_reviewed.checked,
  };
  try {
    await requestJson("/api/sites", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    siteForm.reset();
    siteForm.elements.is_enabled.checked = true;
    formStatus.textContent = "Site ajouté à votre liste.";
    await loadSites();
  } catch (error) {
    formStatus.textContent = `Ajout impossible : ${error.message}`;
  }
});

integrationForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  integrationFormStatus.textContent = "";
  try {
    const payload = {
      name: integrationForm.elements.name.value.trim(),
      url: integrationForm.elements.url.value.trim(),
      method: integrationForm.elements.method.value,
      query_params: parseJsonObject(integrationForm.elements.query_params, "Les paramètres"),
      body: parseJsonObject(integrationForm.elements.body, "Le corps"),
      is_enabled: integrationForm.elements.is_enabled.checked,
    };
    const enteredHeaders = integrationForm.elements.headers.value.trim();
    if (!editingIntegrationId || integrationForm.elements.clear_headers.checked) {
      payload.headers = enteredHeaders
        ? parseJsonObject(integrationForm.elements.headers, "Les en-têtes")
        : {};
    } else if (enteredHeaders) {
      payload.headers = parseJsonObject(integrationForm.elements.headers, "Les en-têtes");
    }

    await requestJson(
      editingIntegrationId
        ? `/api/integrations/${editingIntegrationId}`
        : "/api/integrations",
      {
        method: editingIntegrationId ? "PUT" : "POST",
        body: JSON.stringify(payload),
      },
    );
    resetIntegrationForm();
    integrationFormStatus.textContent = "Configuration d’API enregistrée localement.";
    await loadIntegrations();
  } catch (error) {
    integrationFormStatus.textContent = `Enregistrement impossible : ${error.message}`;
  }
});

integrationCancel.addEventListener("click", resetIntegrationForm);

loadSites();
loadIntegrations();
