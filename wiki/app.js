const state = { tables: [], facets: { categories: {}, entity_types: {} }, pageSize: 50 };
const content = document.querySelector("#content");
const breadcrumbs = document.querySelector("#breadcrumbs");

const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[character]);
const label = (value) => String(value ?? "").replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
const short = (value, max = 145) => {
  const text = String(value ?? "").trim();
  return text.length > max ? `${text.slice(0, max).trimEnd()}…` : text;
};
const pathFor = (kind, id) => `/${kind}/${encodeURIComponent(id)}`;
const imageURL = (path) => {
  path = String(path || "");
  if (!path.startsWith("images/")) return "";
  const filename = path.slice("images/".length);
  if (!filename || filename.includes("/")) return "";
  return `/database-images/${encodeURIComponent(filename)}`;
};
const entityLink = (entity, text = entity.title || entity.name || entity.id) => `<a class="row-title" data-route href="${pathFor("entity", entity.id)}">${esc(text)}</a>`;
const eventLink = (event, text = event.title) => `<a class="row-title" data-route href="${pathFor("timeline", event.id)}">${esc(text)}</a>`;
const fmtNumber = (value) => Number(value || 0).toLocaleString();

async function api(path) {
  const response = await fetch(`/api/${path}`);
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
  return payload;
}

function setCrumbs(items) {
  breadcrumbs.innerHTML = items.map((item, index) => `${index ? '<span class="crumb-separator">/</span>' : ""}${item.href ? `<a data-route href="${esc(item.href)}">${esc(item.text)}</a>` : `<span>${esc(item.text)}</span>`}`).join("");
}

function setActiveNav(name) {
  document.querySelectorAll("[data-nav]").forEach((link) => link.classList.toggle("active", link.dataset.nav === name));
  document.querySelectorAll("[data-table-nav]").forEach((link) => link.classList.toggle("active", link.dataset.tableNav === name));
}

async function initialize() {
  const [tableData, facets] = await Promise.all([api("tables"), api("facets")]);
  state.tables = tableData.tables;
  state.facets = facets;
  document.querySelector("#record-total").textContent = fmtNumber(state.tables.find((table) => table.name === "entities")?.count);
  document.querySelector("#table-nav").innerHTML = state.tables.map((table) => `<a class="table-link" data-route data-table-nav="${esc(table.name)}" href="/table/${encodeURIComponent(table.name)}"><span class="table-icon">▤</span>${esc(label(table.name))}<span class="table-count">${fmtNumber(table.count)}</span></a>`).join("");
  await renderRoute();
}

async function renderRoute() {
  content.innerHTML = '<div class="loading">Opening archive…</div>';
  content.classList.remove("fade-in");
  const parts = location.pathname.split("/").filter(Boolean).map((part) => decodeURIComponent(part));
  const params = new URLSearchParams(location.search);
  try {
    if (!parts.length) return await renderHome();
    if (parts[0] === "entities") return await renderEntities(params.get("q") || "", params.get("category") || "", Number(params.get("offset") || 0));
    if (parts[0] === "entity" && parts[1]) return await renderEntity(parts.slice(1).join("/"));
    if (parts[0] === "timeline" && parts[1]) return await renderEvent(parts.slice(1).join("/"));
    if (parts[0] === "timeline") return await renderTimeline();
    if (parts[0] === "table" && parts[1]) return await renderTable(parts[1], params.get("q") || "", Number(params.get("offset") || 0));
    if (parts[0] === "search") return await renderEntities(params.get("q") || "", "", Number(params.get("offset") || 0));
    content.innerHTML = '<div class="error-state">That archive page was not found.</div>';
    setCrumbs([{ text: "Not found" }]);
  } catch (error) {
    content.innerHTML = `<div class="error-state">${esc(error.message)}</div>`;
  }
  content.classList.add("fade-in");
}

async function renderHome() {
  setActiveNav("home");
  setCrumbs([{ text: "Overview" }]);
  const timeline = await api("timeline");
  const entityCount = state.tables.find((table) => table.name === "entities")?.count || 0;
  const events = timeline.events;
  const categories = Object.entries(state.facets.categories).sort((a, b) => b[1] - a[1]);
  content.innerHTML = `
    <section class="hero-band">
      <div class="hero-copy"><div class="eyebrow">A living reference snapshotted from the pokeemerald source</div><h1>Emerald Archive</h1><p>A connected guide to the people, places, objects and events across Pokémon Emerald, extracted from the game source.</p></div>
      <div class="hero-stat"><strong>${fmtNumber(entityCount)}</strong><span>indexed entries</span></div>
    </section>
    <div class="stats-grid">${state.tables.map((table) => `<div class="stat-tile"><span>${esc(label(table.name))}</span><strong>${fmtNumber(table.count)}</strong></div>`).join("")}</div>
    <div class="section-heading"><h2>Story timeline</h2><a class="text-link" data-route href="/timeline">View timeline →</a></div>
    <div class="timeline-strip">${events.map((event) => `<a class="timeline-card" data-route href="${pathFor("timeline", event.id)}"><span class="event-year">${esc(yearLabel(event.year))}</span><strong>${esc(event.title)}</strong><small>${esc(event.tagline || label(event.type))}</small></a>`).join("")}</div>
    <div class="section-heading"><h2>Browse by category</h2><a class="text-link" data-route href="/entities">All entities →</a></div>
    <div class="stats-grid">${categories.slice(0, 8).map(([category, count]) => `<a class="stat-tile" data-route href="/entities?category=${encodeURIComponent(category)}"><span>${esc(label(category))}</span><strong>${fmtNumber(count)}</strong></a>`).join("")}</div>`;
}

function yearLabel(value) {
  const year = Number(value);
  return Number.isFinite(year) ? `Chapter ${year}` : "Chapter ?";
}

async function renderEntities(search = "", category = "", offset = 0) {
  setActiveNav("entities");
  setCrumbs([{ text: "Entities" }, ...(category ? [{ text: label(category) }] : []), ...(search ? [{ text: `Search: ${search}` }] : [])]);
  const query = new URLSearchParams({ limit: state.pageSize, offset });
  if (search) query.set("q", search);
  if (category) query.set("category", category);
  const data = await api(`entities?${query}`);
  const categoryOptions = Object.keys(state.facets.categories).sort().map((value) => `<option value="${esc(value)}" ${value === category ? "selected" : ""}>${esc(label(value))}</option>`).join("");
  content.innerHTML = `<div class="page-heading"><div><div class="eyebrow">Database index</div><h1>${search ? "Search results" : category ? label(category) : "Entities"}</h1><p class="page-subtitle">Entries discovered from the current CSV schema.</p></div><span class="heading-count">${fmtNumber(data.total)} entries</span></div>
    <div class="list-tools"><input id="entity-search" type="search" value="${esc(search)}" placeholder="Search names, descriptions, fields…"><select id="category-filter" class="filter-select"><option value="">All categories</option>${categoryOptions}</select></div>
    ${renderEntityTable(data.rows)}${renderPagination(data.total, offset, "entities", { q: search, category })}`;
  document.querySelector("#entity-search").addEventListener("keydown", (event) => { if (event.key === "Enter") navigate(`/entities?q=${encodeURIComponent(event.currentTarget.value)}&category=${encodeURIComponent(document.querySelector("#category-filter").value)}`); });
  document.querySelector("#category-filter").addEventListener("change", (event) => navigate(`/entities?category=${encodeURIComponent(event.currentTarget.value)}&q=${encodeURIComponent(search)}`));
}

function renderEntityTable(rows) {
  if (!rows.length) return '<div class="empty-state">No entries match this search.</div>';
  return `<div class="table-wrap"><table><thead><tr><th>Name</th><th>Category</th><th>Type</th><th>Description</th></tr></thead><tbody>${rows.map((row) => `<tr><td>${entityLink(row)}</td><td><span class="pill">${esc(label(row.category))}</span></td><td>${esc(label(row.entity_type || "—"))}</td><td>${esc(short(row.description, 115))}</td></tr>`).join("")}</tbody></table></div>`;
}

async function renderEntity(id) {
  setActiveNav("entities");
  const data = await api(`entity/${encodeURIComponent(id)}`);
  const entity = data.entity;
  setCrumbs([{ text: "Entities", href: "/entities" }, { text: label(entity.category) }, { text: entity.title || entity.name || entity.id }]);
  const excluded = new Set(["id", "title", "name", "description", "history"]);
  const wikiFields = Object.entries(entity).filter(([key, value]) => key.startsWith("wiki_") && value);
  wikiFields.forEach(([key]) => excluded.add(key));
  const properties = Object.entries(entity).filter(([key, value]) => !excluded.has(key) && value).map(([key, value]) => `<div class="property"><dt>${esc(label(key))}</dt><dd>${esc(value)}</dd></div>`).join("");
  const wikiContent = wikiFields.length ? `<section class="detail-section"><h2>Wiki content</h2><div class="wiki-content-list">${wikiFields.map(([key, value]) => `<details class="wiki-content"><summary>${esc(label(key))}<span>${esc(short(value, 150))}</span></summary><div class="wiki-content-text">${esc(value)}</div></details>`).join("")}</div></section>` : "";
  const related = data.related.length ? data.related.map((item) => `<a class="aside-link" data-route href="${pathFor("entity", item.entity.id)}"><strong>${esc(item.entity.title || item.entity.name || item.entity.id)}</strong><small>${esc(label(item.relationship))} · ${esc(label(item.entity.category))}</small></a>`).join("") : '<div class="muted-cell">No linked entries.</div>';
  const appearances = data.events.length ? data.events.map((item) => `<a class="aside-link" data-route href="${pathFor("timeline", item.event.id)}"><strong>${esc(item.event.title)}</strong><small>${esc(yearLabel(item.event.year))} · ${esc(label(item.relationship))}</small></a>`).join("") : '<div class="muted-cell">No linked story events.</div>';
  const metadata = data.metadata.length ? data.metadata.map((item) => `<div class="metadata-row"><strong>${esc(label(item.field))}</strong><span>${item.related_entity_id ? entityLink({ id: item.related_entity_id, title: item.value }, item.value || item.related_entity_id) : esc(item.value)}</span></div>`).join("") : '<div class="muted-cell">No metadata.</div>';
  const images = data.images || (entity.image_path ? [{ path: entity.image_path }] : []);
  const imageGallery = images.map((item) => imageURL(item.path)).filter(Boolean).map((url, index) => `<img class="entity-image" src="${esc(url)}" alt="${esc(entity.title || entity.name || "Database entry")}${images.length > 1 ? `, image ${index + 1}` : ""}" loading="lazy">`).join("");
  content.innerHTML = `<div class="entity-layout fade-in"><article class="entity-main"><div class="entity-heading"><div class="eyebrow">${esc(label(entity.entity_type || entity.category))}</div><h1>${esc(entity.title || entity.name || entity.id)}</h1><div class="entity-tags"><span class="pill">${esc(label(entity.category))}</span>${entity.collection ? `<span class="pill accent">${esc(label(entity.collection))}</span>` : ""}</div></div>
    ${imageGallery ? `<div class="entity-images">${imageGallery}</div>` : ""}${entity.description ? `<p class="entity-description">${esc(entity.description)}</p>` : ""}${entity.history ? `<blockquote class="entity-history">${esc(entity.history)}</blockquote>` : ""}
    <section class="detail-section"><h2>Record details</h2><dl class="property-list">${properties || '<div class="property"><dd>No populated fields.</dd></div>'}</dl></section>${wikiContent}
    <section class="detail-section"><h2>Database ID</h2><div class="event-detail"><code>${esc(entity.id)}</code></div></section></article>
    <aside class="entity-aside"><section class="aside-panel"><h3>Timeline appearances</h3>${appearances}</section><section class="aside-panel"><h3>Connected entries</h3>${related}</section><section class="aside-panel"><h3>Metadata</h3><div class="metadata-list">${metadata}</div></section></aside></div>`;
}

async function renderTimeline() {
  setActiveNav("timeline");
  setCrumbs([{ text: "Story timeline" }]);
  const { events } = await api("timeline");
  content.innerHTML = `<div class="page-heading"><div><div class="eyebrow">Lore chronology</div><h1>Story timeline</h1><p class="page-subtitle">Events are ordered by their sequence in the database.</p></div><span class="heading-count">${events.length} events</span></div>
    <div class="table-wrap"><table><thead><tr><th>Order</th><th>Event</th><th>Chapter</th><th>Badges</th><th>Era</th><th>Summary</th></tr></thead><tbody>${events.map((event) => `<tr><td>${esc(event.sequence)}</td><td>${eventLink(event)}</td><td>${esc(yearLabel(event.year))}</td><td>${esc(event.release_year || "—")}</td><td><span class="pill">${esc(label(event.era))}</span></td><td>${esc(short(event.tagline || event.description, 125))}</td></tr>`).join("")}</tbody></table></div>`;
}

async function renderEvent(id) {
  setActiveNav("timeline");
  const data = await api(`timeline/${encodeURIComponent(id)}`);
  const event = data.event;
  setCrumbs([{ text: "Story timeline", href: "/timeline" }, { text: event.title }]);
  const previous = event.previous_event_id ? `<a class="text-link" data-route href="${pathFor("timeline", event.previous_event_id)}">← Previous event</a>` : "";
  const members = data.entities.map((item) => `<a class="aside-link" data-route href="${pathFor("entity", item.entity.id)}"><strong>${esc(item.entity.title || item.entity.name || item.entity.id)}</strong><small>${esc(label(item.entity.category))} · ${esc(label(item.relationship))}</small></a>`).join("");
  content.innerHTML = `<div class="page-heading"><div><div class="eyebrow">Timeline event · ${esc(event.sequence)}</div><h1>${esc(event.title)}</h1><p class="page-subtitle">${esc(yearLabel(event.year))} · ${esc(event.release_year || "0")} badges</p></div>${previous}</div>
    <article class="event-detail"><div class="event-meta">${esc(label(event.type))} / ${esc(label(event.era))} / ${esc(event.canon || "")}</div><h2>${esc(event.tagline || event.title)}</h2><p class="event-copy">${esc(event.description || "")}</p><div class="event-grid"><section><h3>In the lore</h3><p class="event-copy">${esc(event.lore || "No lore notes have been added.")}</p></section><section><h3>Connected database entries <span class="muted-cell">(${fmtNumber(data.entities.length)})</span></h3>${members || '<div class="muted-cell">No entities are linked to this event.</div>'}</section></div></article>`;
}

async function renderTable(name, search = "", offset = 0) {
  setActiveNav(name);
  setCrumbs([{ text: "Database tables" }, { text: label(name) }]);
  const query = new URLSearchParams({ limit: state.pageSize, offset });
  if (search) query.set("q", search);
  const data = await api(`table/${encodeURIComponent(name)}?${query}`);
  const preferred = ["title", "name", "id", "event_id", "entity_id", "relationship", "field", "year", "sequence", "category", "source_id", "target_id"];
  const columns = [...data.columns].sort((a, b) => {
    const ai = preferred.indexOf(a), bi = preferred.indexOf(b);
    return (ai < 0 ? 100 : ai) - (bi < 0 ? 100 : bi);
  }).slice(0, 7);
  content.innerHTML = `<div class="page-heading"><div><div class="eyebrow">Dynamic CSV view</div><h1>${esc(label(name))}</h1><p class="page-subtitle">${data.columns.length} columns detected from ${esc(name)}.csv</p></div><span class="heading-count">${fmtNumber(data.total)} rows</span></div>
    <div class="list-tools"><input id="table-search" type="search" value="${esc(search)}" placeholder="Filter rows by any field…"><span class="muted-cell">${data.columns.map(esc).join(" · ")}</span></div>
    ${renderGenericTable(data.rows, columns, name)}${renderPagination(data.total, offset, `table/${name}`, { q: search })}`;
  document.querySelector("#table-search").addEventListener("keydown", (event) => { if (event.key === "Enter") navigate(`/table/${encodeURIComponent(name)}?q=${encodeURIComponent(event.currentTarget.value)}`); });
}

function renderGenericTable(rows, columns, tableName) {
  if (!rows.length) return '<div class="empty-state">No rows found.</div>';
  const headers = columns.map((column) => `<th>${esc(label(column))}</th>`).join("");
  const cells = rows.map((row) => `<tr>${columns.map((column) => `<td>${renderCell(row[column], column, tableName, row)}</td>`).join("")}</tr>`).join("");
  return `<div class="table-wrap"><table><thead><tr>${headers}</tr></thead><tbody>${cells}</tbody></table></div>`;
}

function renderCell(value, column, tableName, row) {
  if (!value) return '<span class="muted-cell">—</span>';
  if (tableName === "entities" && column === "id") return entityLink({ id: value, title: row.title || row.name || value }, row.title || row.name || value);
  if (tableName === "timeline_events" && column === "id") return eventLink({ id: value, title: row.title || value }, row.title || value);
  if (["entity_id", "source_id", "target_id", "related_entity_id"].includes(column)) return entityLink({ id: value }, short(value, 50));
  if (column === "event_id") return eventLink({ id: value, title: value }, value);
  return esc(short(value, 100));
}

function renderPagination(total, offset, route, filters = {}) {
  const start = total ? offset + 1 : 0;
  const end = Math.min(offset + state.pageSize, total);
  const params = new URLSearchParams({ ...filters });
  const go = (nextOffset) => {
    params.set("offset", nextOffset);
    navigate(`/${route}?${params}`);
  };
  return `<div class="pagination"><span>${start}–${end} of ${fmtNumber(total)}</span><button data-page="${Math.max(0, offset - state.pageSize)}" ${offset <= 0 ? "disabled" : ""}>Previous</button><button data-page="${offset + state.pageSize}" ${offset + state.pageSize >= total ? "disabled" : ""}>Next</button></div>`;
}

function navigate(path) {
  history.pushState({}, "", path);
  renderRoute();
}

document.addEventListener("click", (event) => {
  const pagination = event.target.closest("button[data-page]");
  if (pagination) {
    const routeParts = location.pathname.split("/").filter(Boolean);
    const params = new URLSearchParams(location.search);
    params.set("offset", pagination.dataset.page);
    navigate(`/${routeParts.join("/")}?${params}`);
    return;
  }
  const link = event.target.closest("a[data-route]");
  if (link && !event.metaKey && !event.ctrlKey && !event.shiftKey && event.button === 0) {
    event.preventDefault();
    navigate(link.getAttribute("href"));
  }
});

window.addEventListener("popstate", renderRoute);
document.querySelector("#search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const query = document.querySelector("#global-search").value.trim();
  navigate(query ? `/search?q=${encodeURIComponent(query)}` : "/entities");
});
document.querySelector("#global-search").addEventListener("keydown", (event) => {
  if (event.key === "Escape") event.currentTarget.value = "";
});

initialize().catch((error) => {
  content.innerHTML = `<div class="error-state">Could not load the database: ${esc(error.message)}. Start the local server from the wiki folder and reload.</div>`;
});
