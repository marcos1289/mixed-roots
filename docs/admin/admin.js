// Admin for the Mixed Roots site. Edits content/*.json in the GitHub repo and
// commits uploaded photos to content/photos/; a GitHub Action rebuilds the site.
const OWNER = "marcos1289";
const REPO = "mixed-roots";
const BRANCH = "main";
const API = `https://api.github.com/repos/${OWNER}/${REPO}`;
const FILES = { shows: "content/shows.json", gallery: "content/gallery.json", site: "content/site.json" };
const KEY_STORE = "mixedroots-admin-key";
const MAX_EDGE = 2400;

const $ = (sel, root = document) => root.querySelector(sel);
const state = { key: "", data: {}, original: {}, uploads: new Map(), library: [], showAllPast: false };

function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, "");
    else if (v !== false && v != null) el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid != null) el.append(kid);
  return el;
}

async function gh(path, opts = {}) {
  const res = await fetch(path.startsWith("http") ? path : API + path, {
    ...opts,
    headers: { Authorization: `Bearer ${state.key}`, Accept: "application/vnd.github+json", ...(opts.headers || {}) },
  });
  if (!res.ok) {
    const err = new Error(`GitHub ${res.status}: ${(await res.json().catch(() => ({}))).message || res.statusText}`);
    err.status = res.status;
    throw err;
  }
  return res.status === 204 ? null : res.json();
}

function decode(b64) {
  const bytes = Uint8Array.from(atob(b64.replace(/\n/g, "")), (c) => c.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

const today = () => new Date().toLocaleDateString("en-CA");

function prettyDate(s) {
  if (s.dateLabel) return s.dateLabel;
  const d = new Date(s.date + "T12:00:00");
  return isNaN(d) ? s.date : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function slugName(name) {
  return name.toLowerCase().replace(/\.[^.]+$/, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40) || "photo";
}

function thumbFor(file) {
  if (state.uploads.has(file)) return state.uploads.get(file).url;
  const hit = state.library.find((l) => l.file === file);
  return hit ? "../" + hit.thumb : "";
}

/* ---------- sign in / load ---------- */

async function load() {
  const [lib, ...contents] = await Promise.all([
    fetch("library.json", { cache: "no-store" }).then((r) => (r.ok ? r.json() : [])).catch(() => []),
    ...Object.values(FILES).map((f) => gh(`/contents/${f}?ref=${BRANCH}`)),
  ]);
  state.library = lib;
  Object.keys(FILES).forEach((k, i) => {
    const text = decode(contents[i].content);
    state.original[k] = JSON.stringify(JSON.parse(text));
    state.data[k] = JSON.parse(text);
  });
}

async function signIn(key) {
  state.key = key;
  await gh("");
  await load();
  try { localStorage.setItem(KEY_STORE, key); } catch {}
  $("#login").hidden = true;
  $("#app").hidden = false;
  $("#publish-bar").hidden = false;
  $("#logout").hidden = false;
  renderAll();
}

$("#login-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  $("#login-error").textContent = "";
  try {
    await signIn($("#key").value.trim());
  } catch (err) {
    $("#login-error").textContent = err.status === 401
      ? "That key didn't work. Check it was pasted in full, or ask Mark for a new one."
      : "Couldn't load the site content (" + err.message + "). Tell Mark.";
  }
});

$("#logout").addEventListener("click", () => {
  if (isDirty() && !confirm("You have unpublished changes. Log out anyway?")) return;
  try { localStorage.removeItem(KEY_STORE); } catch {}
  location.reload();
});

/* ---------- tabs ---------- */

document.querySelectorAll("[data-tab]").forEach((tab) =>
  tab.addEventListener("click", () => {
    document.querySelectorAll("[data-tab]").forEach((t) => t.setAttribute("aria-selected", t === tab));
    document.querySelectorAll("[data-panel]").forEach((p) => (p.hidden = p.dataset.panel !== tab.dataset.tab));
  }),
);

/* ---------- shows ---------- */

function renderShows() {
  const shows = state.data.shows.map((s, i) => ({ s, i }));
  const t = today();
  const upcoming = shows.filter(({ s }) => s.date >= t).sort((a, b) => a.s.date.localeCompare(b.s.date));
  const past = shows.filter(({ s }) => s.date < t).sort((a, b) => b.s.date.localeCompare(a.s.date));
  const row = ({ s, i }) =>
    h("li", {},
      h("span", { class: "when" }, prettyDate(s)),
      h("span", { class: "what" }, h("strong", {}, s.title || "(untitled)"), h("span", {}, s.place || "")),
      h("button", { type: "button", onclick: () => openShow(i) }, "Edit"));
  $("#upcoming").replaceChildren(...(upcoming.length ? upcoming.map(row) : [h("li", { class: "empty" }, "No upcoming shows. Tap “Add show” to post one.")]));
  const visible = state.showAllPast ? past : past.slice(0, 8);
  $("#past").replaceChildren(...visible.map(row));
  $("#more-past").hidden = state.showAllPast || past.length <= 8;
}
$("#more-past").addEventListener("click", () => { state.showAllPast = true; renderShows(); });

let editing = null; // { index, draft }

function openShow(index) {
  const src = index == null ? { date: "", title: "", place: "" } : state.data.shows[index];
  editing = { index, draft: structuredClone(src) };
  const f = $("#show-form");
  for (const name of ["date", "dateLabel", "time", "title", "place", "text"]) f.elements[name].value = editing.draft[name] || "";
  $("#vague-date").checked = !!editing.draft.dateLabel;
  $("#date-label-field").hidden = !editing.draft.dateLabel;
  $("#show-dialog-title").textContent = index == null ? "Add a show" : "Edit show";
  $("#delete-show").hidden = index == null;
  $("#show-error").textContent = "";
  renderShowLinks();
  renderShowPhotos();
  $("#show-dialog").showModal();
}

function renderShowLinks() {
  const links = (editing.draft.links ||= []);
  $("#show-links").replaceChildren(...links.map((l, i) =>
    h("div", { class: "link-row" },
      h("input", { placeholder: "Label, e.g. Tickets", value: l.label || "", oninput: (e) => (l.label = e.target.value) }),
      h("input", { type: "url", placeholder: "https://…", value: l.url || "", oninput: (e) => (l.url = e.target.value) }),
      h("button", { type: "button", class: "icon", "aria-label": "Remove link", onclick: () => { links.splice(i, 1); renderShowLinks(); } }, "✕"))));
}
$("#vague-date").addEventListener("change", (e) => {
  $("#date-label-field").hidden = !e.target.checked;
  if (!e.target.checked) $("#show-form").elements.dateLabel.value = "";
});
$("#add-link").addEventListener("click", () => { editing.draft.links.push({ label: "", url: "" }); renderShowLinks(); });

function renderShowPhotos() {
  const photos = (editing.draft.photos ||= []);
  $("#show-photos").replaceChildren(...photos.map((file, i) =>
    h("figure", {},
      h("img", { src: thumbFor(file), alt: "" }),
      h("button", { type: "button", "aria-label": "Remove photo", onclick: () => { photos.splice(i, 1); renderShowPhotos(); } }, "✕"))));
}

$("#show-upload").addEventListener("change", async (ev) => {
  const files = await addUploads(ev.target.files);
  editing.draft.photos.push(...files);
  ev.target.value = "";
  renderShowPhotos();
});
$("#show-library").addEventListener("click", () => pickFromLibrary((files) => { editing.draft.photos.push(...files); renderShowPhotos(); }));
$("#cancel-show").addEventListener("click", () => $("#show-dialog").close());

$("#delete-show").addEventListener("click", () => {
  if (!confirm(`Delete “${editing.draft.title}”?`)) return;
  state.data.shows.splice(editing.index, 1);
  $("#show-dialog").close();
  changed();
});

$("#show-form").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const f = ev.target;
  const d = editing.draft;
  for (const name of ["date", "dateLabel", "time", "title", "place", "text"]) {
    const v = f.elements[name].value.trim();
    if (v) d[name] = v; else delete d[name];
  }
  d.links = (d.links || []).filter((l) => l.url && l.url.trim()).map((l) => ({ label: (l.label || "").trim() || "More info", url: l.url.trim() }));
  if (!d.links.length) delete d.links;
  if (!d.photos?.length) delete d.photos;
  const bad = d.links?.find((l) => !/^https?:\/\//.test(l.url));
  if (!d.date || !d.title) return ($("#show-error").textContent = "A show needs at least a date and a title.");
  if (bad) return ($("#show-error").textContent = `Links must start with https:// (check “${bad.label}”).`);
  if (editing.index == null) state.data.shows.push(d); else state.data.shows[editing.index] = d;
  state.data.shows.sort((a, b) => b.date.localeCompare(a.date));
  $("#show-dialog").close();
  changed();
});
$("#add-show").addEventListener("click", () => openShow(null));

/* ---------- photos ---------- */

function renderGallery() {
  const g = state.data.gallery;
  const move = (i, by) => { const [x] = g.splice(i, 1); g.splice(i + by, 0, x); changed(); };
  $("#gallery").replaceChildren(...g.map((item, i) =>
    h("li", {},
      h("img", { src: thumbFor(item.file), alt: "" }),
      h("label", {}, "Caption", h("input", { value: item.caption || "", oninput: (e) => { item.caption = e.target.value; changed(false); } })),
      h("div", { class: "moves" },
        h("button", { type: "button", class: "icon", "aria-label": "Move up", disabled: i === 0, onclick: () => move(i, -1) }, "↑"),
        h("button", { type: "button", class: "icon", "aria-label": "Move down", disabled: i === g.length - 1, onclick: () => move(i, 1) }, "↓"),
        h("button", { type: "button", class: "icon danger", "aria-label": "Remove from gallery", onclick: () => { g.splice(i, 1); changed(); } }, "✕")))));
}

$("#gallery-upload").addEventListener("change", async (ev) => {
  const files = await addUploads(ev.target.files);
  state.data.gallery.unshift(...files.map((file) => ({ file, caption: "" })));
  ev.target.value = "";
  changed();
});
$("#gallery-library").addEventListener("click", () =>
  pickFromLibrary((files) => { state.data.gallery.unshift(...files.map((file) => ({ file, caption: "" }))); changed(); }));

async function addUploads(fileList) {
  const added = [];
  for (const file of fileList) {
    try {
      const blob = await shrink(file);
      const name = `uploads/${today()}-${slugName(file.name)}-${Math.random().toString(36).slice(2, 7)}.jpg`;
      const b64 = await new Promise((res) => { const r = new FileReader(); r.onload = () => res(r.result.split(",")[1]); r.readAsDataURL(blob); });
      state.uploads.set(name, { b64, url: URL.createObjectURL(blob) });
      added.push(name);
    } catch {
      alert(`Couldn't read ${file.name}. Try a JPEG or PNG.`);
    }
  }
  return added;
}

// Resizing in the browser keeps uploads small and drops location data from phone photos.
async function shrink(file) {
  const bmp = await createImageBitmap(file, { imageOrientation: "from-image" });
  const scale = Math.min(1, MAX_EDGE / Math.max(bmp.width, bmp.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bmp.width * scale);
  canvas.height = Math.round(bmp.height * scale);
  canvas.getContext("2d").drawImage(bmp, 0, 0, canvas.width, canvas.height);
  return new Promise((res, rej) => canvas.toBlob((b) => (b ? res(b) : rej()), "image/jpeg", 0.86));
}

function pickFromLibrary(onDone) {
  const picked = new Set();
  const all = [...[...state.uploads.keys()].map((file) => ({ file })), ...state.library];
  $("#library").replaceChildren(...all.map(({ file }) =>
    h("button", { type: "button", "aria-pressed": "false", onclick: (e) => {
      const b = e.currentTarget;
      picked.has(file) ? picked.delete(file) : picked.add(file);
      b.classList.toggle("picked", picked.has(file));
      b.setAttribute("aria-pressed", picked.has(file));
    } }, h("img", { src: thumbFor(file), alt: file, loading: "lazy" }))));
  const dlg = $("#library-dialog");
  $("#library-close").onclick = () => { dlg.close(); if (picked.size) onDone([...picked]); };
  $("#library-close").textContent = "Add selected";
  dlg.showModal();
}

/* ---------- band info ---------- */

function renderBand() {
  const s = state.data.site;
  const field = (label, key, multi) =>
    h("label", {}, label, h(multi ? "textarea" : "input", { rows: multi ? 5 : null, value: multi ? null : s[key] || "",
      oninput: (e) => { s[key] = e.target.value; changed(false); } }, multi ? s[key] || "" : null));
  const lineup = s.lineup;
  const move = (i, by) => { const [x] = lineup.splice(i, 1); lineup.splice(i + by, 0, x); changed(); };
  const members = lineup.map((m, i) =>
    h("div", { class: "member" },
      h("label", {}, "Name", h("input", { value: m.name, oninput: (e) => { m.name = e.target.value; changed(false); } })),
      h("label", {}, "Instrument / role", h("input", { value: m.role, oninput: (e) => { m.role = e.target.value; changed(false); } })),
      h("label", {}, "Short bio", h("textarea", { rows: 2, oninput: (e) => { m.bio = e.target.value; changed(false); } }, m.bio || "")),
      h("div", { class: "moves" },
        h("button", { type: "button", class: "icon", disabled: i === 0, onclick: () => move(i, -1) }, "↑"),
        h("button", { type: "button", class: "icon", disabled: i === lineup.length - 1, onclick: () => move(i, 1) }, "↓"),
        h("button", { type: "button", class: "danger", onclick: () => { if (confirm(`Remove ${m.name || "this member"}?`)) { lineup.splice(i, 1); changed(); } } }, "Remove"))));
  const links = s.links.map((l, i) =>
    h("div", { class: "link-row" },
      h("input", { placeholder: "Label, e.g. Instagram", value: l.label, oninput: (e) => { l.label = e.target.value; changed(false); } }),
      h("input", { type: "url", placeholder: "https://…", value: l.url, oninput: (e) => { l.url = e.target.value; changed(false); } }),
      h("button", { type: "button", class: "icon", "aria-label": "Remove link", onclick: () => { s.links.splice(i, 1); changed(); } }, "✕")));
  $("#band-form").replaceChildren(
    field("Tagline (under the band name at the top)", "tagline"),
    field("Band section heading", "bandHeading"),
    field("Intro line", "bandLead"),
    field("About the band (blank line between paragraphs)", "bandText", true),
    field("Motto", "motto"),
    h("fieldset", {}, h("legend", {}, "Lineup"), ...members,
      h("button", { type: "button", class: "link", onclick: () => { lineup.push({ name: "", role: "", bio: "" }); changed(); } }, "+ Add member")),
    field("Booking text", "bookingText", true),
    field("Booking email", "email"),
    h("fieldset", {}, h("legend", {}, "Social and music links"), ...links,
      h("button", { type: "button", class: "link", onclick: () => { s.links.push({ label: "", url: "" }); changed(); } }, "+ Add link")),
  );
}

/* ---------- dirty tracking and publishing ---------- */

const changedFiles = () => Object.keys(FILES).filter((k) => JSON.stringify(state.data[k]) !== state.original[k]);
const usedUploads = () => {
  const used = new Set([...state.data.shows.flatMap((s) => s.photos || []), ...state.data.gallery.map((g) => g.file)]);
  return [...state.uploads.keys()].filter((f) => used.has(f) && !state.uploads.get(f).published);
};
const isDirty = () => changedFiles().length > 0 || usedUploads().length > 0;

function changed(rerender = true) {
  if (rerender) renderAll();
  else updateBar();
}

function updateBar(message) {
  const dirty = isDirty();
  $("#publish-bar").classList.toggle("dirty", dirty);
  $("#publish").disabled = !dirty;
  $("#publish-status").textContent = message || (dirty ? "Unpublished changes" : "Everything is published");
}

function renderAll() {
  renderShows();
  renderGallery();
  renderBand();
  updateBar();
}

function problems() {
  const s = state.data.site;
  const out = [];
  for (const l of s.links) if (!/^https?:\/\//.test(l.url || "")) out.push(`Link “${l.label || l.url}” must start with https://`);
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(s.email || "")) out.push("Booking email doesn't look like an email address");
  for (const m of s.lineup) if (!m.name.trim()) out.push("Every lineup member needs a name");
  return out;
}

$("#publish").addEventListener("click", publish);

async function publish() {
  const issues = problems();
  if (issues.length) return alert(issues.join("\n"));
  const btn = $("#publish");
  btn.disabled = true;
  try {
    updateBar("Saving…");
    const ref = await gh(`/git/ref/heads/${BRANCH}`);
    const head = await gh(`/git/commits/${ref.object.sha}`);
    for (const k of changedFiles()) {
      const remote = await gh(`/contents/${FILES[k]}?ref=${ref.object.sha}`);
      if (JSON.stringify(JSON.parse(decode(remote.content))) !== state.original[k])
        throw new Error("Someone else published changes since you opened this page. Reload the page and make your edits again.");
    }
    const tree = [];
    for (const k of changedFiles())
      tree.push({ path: FILES[k], mode: "100644", type: "blob", content: JSON.stringify(state.data[k], null, 2) + "\n" });
    const uploads = usedUploads();
    for (const f of uploads) {
      const blob = await gh("/git/blobs", { method: "POST", body: JSON.stringify({ content: state.uploads.get(f).b64, encoding: "base64" }) });
      tree.push({ path: "content/photos/" + f.slice("uploads/".length), mode: "100644", type: "blob", sha: blob.sha });
    }
    const newTree = await gh("/git/trees", { method: "POST", body: JSON.stringify({ base_tree: head.tree.sha, tree }) });
    const what = [...changedFiles().map((k) => ({ shows: "shows", gallery: "gallery", site: "band info" })[k]),
      ...(uploads.length ? [`${uploads.length} photo${uploads.length > 1 ? "s" : ""}`] : [])].join(", ");
    const commit = await gh("/git/commits", { method: "POST", body: JSON.stringify({
      message: `Update ${what} from the admin page`, tree: newTree.sha, parents: [head.sha] }) });
    await gh(`/git/refs/heads/${BRANCH}`, { method: "PATCH", body: JSON.stringify({ sha: commit.sha }) });
    for (const k of Object.keys(FILES)) state.original[k] = JSON.stringify(state.data[k]);
    for (const f of uploads) state.uploads.get(f).published = true;
    updateBar("Published. Updating the live site…");
    watchBuild(commit.sha);
  } catch (err) {
    updateBar();
    alert("Couldn't publish: " + err.message);
  }
}

async function watchBuild(sha) {
  for (let i = 0; i < 60; i++) {
    await new Promise((r) => setTimeout(r, 10000));
    if (isDirty()) return updateBar();
    try {
      const { workflow_runs: runs } = await gh(`/actions/runs?head_sha=${sha}&per_page=1`);
      const run = runs[0];
      if (run?.status === "completed") {
        return updateBar(run.conclusion === "success"
          ? "Live now. If the site still looks old, refresh it (Ctrl+F5 on a computer) or wait a few minutes."
          : "The site update failed. Your changes are saved; tell Mark so he can take a look.");
      }
    } catch {
      return updateBar("Published. The live site updates in about 2 minutes.");
    }
  }
}

window.addEventListener("beforeunload", (e) => { if (isDirty()) e.preventDefault(); });

(async () => {
  let saved = "";
  try { saved = localStorage.getItem(KEY_STORE) || ""; } catch {}
  if (saved) {
    try { return await signIn(saved); } catch { try { localStorage.removeItem(KEY_STORE); } catch {} }
  }
  $("#login").hidden = false;
})();
