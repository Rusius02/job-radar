const STORAGE_KEY = "job-radar-profile";
const form = document.querySelector("#profile-form");
const status = document.querySelector("#form-status");

function splitValues(value) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function loadProfile() {
  try {
    const profile = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    for (const [field, values] of Object.entries({
      titles: profile.desired_titles,
      skills: profile.skills,
      locations: profile.locations,
      keywords: profile.keywords,
    })) {
      if (Array.isArray(values)) form.elements[field].value = values.join(", ");
    }
    form.elements.remoteOnly.checked = profile.remote_only === true;
  } catch {
    status.textContent = "Le profil enregistré n’a pas pu être lu.";
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const profile = {
    desired_titles: splitValues(form.elements.titles.value),
    skills: splitValues(form.elements.skills.value),
    locations: splitValues(form.elements.locations.value),
    keywords: splitValues(form.elements.keywords.value),
    remote_only: form.elements.remoteOnly.checked,
  };
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(profile));
    status.textContent = "Profil enregistré dans ce navigateur.";
  } catch (error) {
    status.textContent = `Enregistrement impossible : ${error.message}`;
  }
});

loadProfile();
