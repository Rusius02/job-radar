const offerList = document.querySelector("#offer-list");
const offerCount = document.querySelector("#offer-count");

function formatDate(value) {
  if (!value) return "Date non précisée";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date non précisée";
  return new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short", year: "numeric" }).format(date);
}

function safeApplicationUrl(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

function renderOffer(offer) {
  const card = document.createElement("a");
  const applicationUrl = safeApplicationUrl(offer.application_url || offer.url);
  card.className = "offer-card";
  card.href = applicationUrl || "#";
  if (applicationUrl) {
    card.target = "_blank";
    card.rel = "noopener noreferrer";
    card.setAttribute("aria-label", `Postuler à ${offer.title || "cette offre"}`);
  } else {
    card.addEventListener("click", (event) => event.preventDefault());
    card.setAttribute("aria-disabled", "true");
  }

  const main = document.createElement("div");
  main.className = "offer-main";
  const title = document.createElement("h3");
  title.className = "offer-title";
  title.textContent = offer.title || "Poste sans intitulé";
  const company = document.createElement("p");
  company.className = "offer-company";
  company.textContent = [offer.organization || offer.company, ...(Array.isArray(offer.locations) ? offer.locations : [])]
    .filter(Boolean)
    .join(" · ") || "Entreprise non précisée";
  const meta = document.createElement("div");
  meta.className = "offer-meta";
  const score = Number(offer.score);
  if (Number.isFinite(score) && score >= 0) {
    meta.append(makeTag(`${Math.min(score, 100)} % de pertinence`, "match"));
  }
  if (offer.is_remote) meta.append(makeTag("Télétravail"));
  for (const type of Array.isArray(offer.employment_type) ? offer.employment_type.slice(0, 2) : []) {
    meta.append(makeTag(type));
  }
  main.append(title, company, meta);

  const right = document.createElement("div");
  right.className = "offer-right";
  const date = document.createElement("time");
  date.className = "offer-date";
  date.textContent = formatDate(offer.date_found || offer.date_posted);
  if (offer.date_found || offer.date_posted) date.dateTime = offer.date_found || offer.date_posted;
  const arrow = document.createElement("span");
  arrow.className = "offer-arrow";
  arrow.setAttribute("aria-hidden", "true");
  arrow.textContent = "↗";
  right.append(date, arrow);
  card.append(main, right);
  return card;
}

function makeTag(text, extraClass = "") {
  const tag = document.createElement("span");
  tag.className = `offer-tag ${extraClass}`.trim();
  tag.textContent = text;
  return tag;
}

function renderEmpty(message, detail = "") {
  const state = document.createElement("div");
  state.className = "state-card";
  const title = document.createElement("strong");
  title.textContent = message;
  state.append(title);
  if (detail) {
    const text = document.createElement("p");
    text.textContent = detail;
    state.append(text);
  }
  offerList.replaceChildren(state);
}

async function loadOffers() {
  try {
    const response = await fetch("/api/offers", { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`Le serveur a répondu ${response.status}.`);
    const offers = await response.json();
    if (!Array.isArray(offers)) throw new Error("Le format des offres reçu est invalide.");
    offerCount.textContent = `${offers.length} offre${offers.length === 1 ? "" : "s"}`;
    if (offers.length === 0) {
      renderEmpty("Votre veille démarre ici.", "Aucune annonce enregistrée pour le moment. Les nouvelles offres apparaîtront ici dès qu’elles seront ajoutées à votre veille.");
      return;
    }
    offerList.replaceChildren(...offers.slice(0, 5).map(renderOffer));
  } catch (error) {
    offerCount.textContent = "indisponible";
    renderEmpty("Impossible de charger les annonces.", error.message || "Vérifiez que le serveur Job Radar est en cours d’exécution.");
  }
}

loadOffers();
