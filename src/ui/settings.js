const siteForm = document.querySelector("#site-form");
const siteList = document.querySelector("#site-list");
const siteCount = document.querySelector("#site-count");
const formStatus = document.querySelector("#site-form-status");
const listStatus = document.querySelector("#site-list-status");

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

loadSites();
