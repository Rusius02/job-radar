const LEGACY_STORAGE_KEY = "job-radar-profile";
const form = document.querySelector("#profile-form");
const status = document.querySelector("#form-status");

function splitValues(value) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function populateForm(profile) {
  const preferences = profile.preferences || {};
  form.elements.titles.value = (preferences.desired_titles || []).join(", ");
  form.elements.skills.value = (profile.skills || []).map((skill) => skill.name).join(", ");
  form.elements.locations.value = (preferences.desired_locations || []).join(", ");
  form.elements.keywords.value = (preferences.keywords || []).join(", ");
  form.elements.remoteOnly.checked = preferences.remote_only === true;
}

async function loadProfile() {
  try {
    const response = await fetch("/api/profile", { headers: { Accept: "application/json" } });
    if (!response.ok) throw new Error(`Le serveur a répondu ${response.status}.`);
    const profile = await response.json();
    const legacy = localStorage.getItem(LEGACY_STORAGE_KEY);
    if (legacy) {
      const oldProfile = JSON.parse(legacy);
      const preferences = profile.preferences || {};
      if (!preferences.desired_titles.length && Array.isArray(oldProfile.desired_titles)) {
        preferences.desired_titles = oldProfile.desired_titles;
      }
      if (!profile.skills.length && Array.isArray(oldProfile.skills)) {
        profile.skills = oldProfile.skills.map((name) => ({ name }));
      }
      if (!preferences.desired_locations.length && Array.isArray(oldProfile.locations)) {
        preferences.desired_locations = oldProfile.locations;
      }
      if (!preferences.keywords.length && Array.isArray(oldProfile.keywords)) {
        preferences.keywords = oldProfile.keywords;
      }
      if (oldProfile.remote_only === true) preferences.remote_only = true;
      profile.preferences = preferences;
      const saved = await fetch("/api/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(profile),
      });
      if (!saved.ok) throw new Error(`Migration du profil impossible (${saved.status}).`);
      localStorage.removeItem(LEGACY_STORAGE_KEY);
      status.textContent = "Votre ancien profil a été transféré dans la base locale.";
      populateForm(await saved.json());
      return;
    }
    populateForm(profile);
  } catch (error) {
    status.textContent = `Chargement du profil impossible : ${error.message}`;
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const response = await fetch("/api/profile");
    if (!response.ok) throw new Error(`Le serveur a répondu ${response.status}.`);
    const profile = await response.json();
    profile.preferences = {
      ...profile.preferences,
      desired_titles: splitValues(form.elements.titles.value),
      desired_locations: splitValues(form.elements.locations.value),
      keywords: splitValues(form.elements.keywords.value),
      remote_only: form.elements.remoteOnly.checked ? true : null,
    };
    const oldSkills = profile.skills || [];
    const enteredSkills = splitValues(form.elements.skills.value);
    profile.skills = enteredSkills.map((name) => {
      const existing = oldSkills.find((skill) => skill.name.toLocaleLowerCase() === name.toLocaleLowerCase());
      return existing || { name, proficiency: "", years_experience: null };
    });
    const saved = await fetch("/api/profile", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(profile),
    });
    if (!saved.ok) {
      const result = await saved.json();
      throw new Error(result.error || `Le serveur a répondu ${saved.status}.`);
    }
    status.textContent = "Profil enregistré dans la base locale.";
  } catch (error) {
    status.textContent = `Enregistrement impossible : ${error.message}`;
  }
});

loadProfile();
