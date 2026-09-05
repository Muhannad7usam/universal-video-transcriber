const $ = s => document.querySelector(s);
const content = $("#content");
const languageSelect = $("#transcription-language");

const i18n = {
  en: {
    headline: "Turn videos into clean transcripts.",
    sub: "Paste a video or playlist link. We handle the rest automatically.",
    start: "Start Transcription",
    privacy: "Generated transcripts are retained for up to 10 days and then deleted automatically.",
    transcriptionLanguage: "Transcription Language",
    languageHelp: "Choose the spoken language for better accuracy, or keep Auto Detect.",
    auto: "Auto Detect",
    one: "One Video",
    selected: "Select Videos",
    range: "Range",
    all: "Entire Playlist",
    go: "Transcribe Selected",
    search: "Search transcript…",
    playlist: "Playlist",
    selectCompleted: "Select a completed video.",
    clean: "Clean Transcript",
    timestamped: "Timestamped Transcript",
    copy: "Copy Transcript",
    copyTimestamps: "Copy With Timestamps",
    previous: "Previous Match",
    next: "Next Match",
    language: "Language",
    method: "Method",
    coverage: "Coverage",
    fullVideo: "Full video",
    copied: "Copied ✓",
    analyzing: "Analyzing link…"
  },
  ar: {
    headline: "حوّل الفيديوهات لـ Transcripts مرتبة.",
    sub: "حط لينك الفيديو أو الـ Playlist هنا، وإحنا هنتولى الباقي أوتوماتيك.",
    start: "ابدأ التفريغ",
    privacy: "الـ Transcripts والنتايج بتفضل محفوظة لمدة أقصاها 10 أيام، وبعدها بتتمسح أوتوماتيك.",
    transcriptionLanguage: "لغة الـ Transcription",
    languageHelp: "اختار لغة الكلام عشان الدقة تبقى أحسن، أو سيبها Auto Detect.",
    auto: "Auto Detect",
    one: "فيديو واحد",
    selected: "اختار فيديوهات",
    range: "من فيديو لفيديو",
    all: "كل الـ Playlist",
    go: "ابدأ التفريغ",
    search: "ابحث في الـ Transcript…",
    playlist: "Playlist",
    selectCompleted: "اختار فيديو خلص عشان تشوف الـ Transcript.",
    clean: "Clean Transcript",
    timestamped: "Timestamped Transcript",
    copy: "انسخ الـ Transcript",
    copyTimestamps: "انسخ بالـ Timestamps",
    previous: "النتيجة اللي قبلها",
    next: "النتيجة اللي بعدها",
    language: "اللغة",
    method: "الطريقة",
    coverage: "التغطية",
    fullVideo: "الفيديو كامل",
    copied: "اتنسخ ✓",
    analyzing: "بنفحص اللينك…"
  }
};

let lang = "en";
let currentView = "clean";
let searchMatches = [];
let searchIndex = 0;
let playMode = "selected";
let currentPlaylist = null;
let rawTranscript = "";
let rawTimestamped = "";

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, m => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }[m]));
}

function fmt(sec) {
  if (sec == null) return "";
  sec = Math.round(sec);
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  return h ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
}

async function api(url, opt) {
  const r = await fetch(url, opt);
  const j = await r.json();
  if (!r.ok) throw Error(j.detail || "Request failed");
  return j;
}

function selectedLanguage() {
  const value = languageSelect?.value || "auto";
  return value === "auto" ? null : value;
}

function applyUiLanguage(next) {
  lang = next;
  document.documentElement.lang = lang === "ar" ? "ar" : "en";
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  document.body.classList.toggle("rtl", lang === "ar");
  document.querySelectorAll("[data-i18n]").forEach(x => {
    const value = i18n[lang][x.dataset.i18n];
    if (value) x.textContent = value;
  });
  const auto = languageSelect?.querySelector('option[value="auto"]');
  if (auto) auto.textContent = i18n[lang].auto;
}

async function loadLanguages() {
  if (!languageSelect) return;
  const saved = localStorage.getItem("uvt-transcription-language") || "auto";
  try {
    const data = await api("/api/languages");
    const important = new Map([["ar", "Arabic — العربية"], ["en", "English"]]);
    languageSelect.innerHTML = `<option value="auto">${esc(i18n[lang].auto)}</option>` + data.languages.map(item => {
      const label = important.get(item.code) || item.name;
      return `<option value="${esc(item.code)}">${esc(label)}</option>`;
    }).join("");
  } catch (_) {
    // Keep the built-in common language options if the optional language endpoint fails.
  }
  if ([...languageSelect.options].some(o => o.value === saved)) languageSelect.value = saved;
}

languageSelect?.addEventListener("change", () => {
  localStorage.setItem("uvt-transcription-language", languageSelect.value);
});

document.querySelectorAll("[data-lang]").forEach(button => {
  button.addEventListener("click", () => applyUiLanguage(button.dataset.lang));
});

$("#start").addEventListener("click", async () => {
  const url = $("#url").value.trim();
  if (!url) return;
  content.innerHTML = `<div class="card"><div class="muted">${esc(i18n[lang].analyzing)}</div></div>`;
  try {
    const j = await api("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, language: selectedLanguage() })
    });
    j.type === "video" ? watch(j.job_id) : renderPlaylist(j);
  } catch (e) {
    content.innerHTML = `<div class="card error">${esc(e.message)}</div>`;
  }
});

function watch(id) {
  content.innerHTML = `<div class="card"><div id="status">${esc(i18n[lang].analyzing)}</div><div class="progress"><div id="bar" class="bar" style="width:0%"></div></div><div id="result"></div></div>`;
  const tick = async () => {
    try {
      const j = await api(`/api/jobs/${id}`);
      $("#status").textContent = `${(j.state || "").replaceAll("_", " ")} ${j.progress}%`;
      $("#bar").style.width = `${j.progress}%`;
      if (j.state === "completed") await renderResult(j);
      else if (j.state === "failed") $("#result").innerHTML = `<p class="error">${esc(j.error)}</p>`;
      else setTimeout(tick, 800);
    } catch (e) {
      $("#result").innerHTML = `<p class="error">${esc(e.message)}</p>`;
    }
  };
  tick();
}

function renderPlaylist(j) {
  currentPlaylist = j;
  playMode = "selected";
  content.innerHTML = `<div class="card">
    <div class="toolbar"><div><h2>${esc(j.title)}</h2><p class="muted">${j.count} videos</p></div></div>
    <div class="actions">
      <button class="chip" data-mode="one">${esc(i18n[lang].one)}</button>
      <button class="chip active" data-mode="selected">${esc(i18n[lang].selected)}</button>
      <button class="chip" data-mode="range">${esc(i18n[lang].range)}</button>
      <button class="chip" data-mode="all">${esc(i18n[lang].all)}</button>
    </div>
    <div id="list" class="playlist-grid">${j.items.map(x => `<label class="item">
      <input type="checkbox" data-index="${x.index}">
      <img src="${esc(x.thumbnail || "")}" alt="">
      <span class="meta"><b>${String(x.index).padStart(2, "0")} — ${esc(x.title)}</b><span class="muted">${esc(fmt(x.duration))}</span></span>
    </label>`).join("")}</div>
    <div id="range" style="display:none;margin-top:18px">
      <input id="from" type="number" min="1" max="${j.count}" value="1">
      <input id="to" type="number" min="1" max="${j.count}" value="${Math.min(5, j.count)}">
    </div>
    <button id="go" class="primary" style="margin-top:18px;height:46px">${esc(i18n[lang].go)}</button>
  </div>`;
}

function selectMode(mode) {
  playMode = mode;
  document.querySelectorAll("[data-mode]").forEach(b => b.classList.toggle("active", b.dataset.mode === mode));
  document.querySelectorAll("#list input").forEach(x => x.checked = mode === "all");
  const range = $("#range");
  if (range) range.style.display = mode === "range" ? "block" : "none";
}

async function submitPlaylist() {
  const j = currentPlaylist;
  if (!j) return;
  let items = [];
  if (playMode === "all") {
    items = j.items.map(x => x.index);
  } else if (playMode === "range") {
    const a = +$("#from").value;
    const b = +$("#to").value;
    if (a < 1 || b < a || b > j.count) return;
    items = Array.from({ length: b - a + 1 }, (_, k) => a + k);
  } else {
    items = [...document.querySelectorAll("#list input:checked")].map(x => +x.dataset.index);
  }
  if (playMode === "one") items = items.slice(0, 1);
  if (!items.length) return;

  try {
    const r = await api("/api/playlist/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        playlist_url: j.url,
        items,
        language: selectedLanguage()
      })
    });
    renderGroup(r.group_id);
  } catch (e) {
    content.insertAdjacentHTML("afterbegin", `<div class="card error">${esc(e.message)}</div>`);
  }
}

async function renderGroup(gid) {
  content.innerHTML = `<div class="split"><aside class="card"><h2>${esc(i18n[lang].playlist)}</h2><div id="group"></div></aside><section class="card"><div id="groupResult" class="muted">${esc(i18n[lang].selectCompleted)}</div></section></div>`;
  const tick = async () => {
    try {
      const g = await api(`/api/groups/${gid}`);
      $("#group").innerHTML = g.jobs.map(x => `<button class="item" type="button" data-job-id="${esc(x.id)}" style="width:100%;margin:8px 0;text-align:left"><span>${esc(x.item_index)}. ${esc(x.title)}</span><span class="muted">${esc(x.state)} ${x.progress}%</span></button>`).join("");
      if (!g.jobs.every(x => ["completed", "failed"].includes(x.state))) setTimeout(tick, 900);
    } catch (_) {}
  };
  tick();
}

async function openGroupJob(id) {
  const j = await api(`/api/jobs/${id}`);
  if (j.state !== "completed") {
    const host = $("#groupResult");
    if (host && j.error) host.innerHTML = `<p class="error">${esc(j.error)}</p>`;
    return;
  }
  const r = await api(`/api/results/${id}`);
  rawTranscript = r.transcript || "";
  rawTimestamped = r.timestamped || "";
  currentView = "clean";
  $("#groupResult").innerHTML = resultMarkup(r, j);
  showTranscript();
}

function resultMarkup(r, j) {
  return `<div class="toolbar"><div><h2>${esc(r.title || j.title)}</h2><div class="result-meta">
    <span class="status-pill">${esc(i18n[lang].language)}: ${esc(r.language || "Unknown")}</span>
    <span class="status-pill">${esc(i18n[lang].method)}: ${esc(r.method || "")}</span>
    <span class="status-pill">${esc(i18n[lang].coverage)}: ${esc(i18n[lang].fullVideo)}</span>
  </div></div></div>
  <div class="actions">
    <button class="chip active" data-result-action="clean">${esc(i18n[lang].clean)}</button>
    <button class="chip" data-result-action="timestamped">${esc(i18n[lang].timestamped)}</button>
    <button class="chip" data-result-action="copy">${esc(i18n[lang].copy)}</button>
    <button class="chip" data-result-action="copy-ts">${esc(i18n[lang].copyTimestamps)}</button>
    <button class="chip" data-result-action="prev">${esc(i18n[lang].previous)}</button>
    <button class="chip" data-result-action="next">${esc(i18n[lang].next)}</button>
  </div>
  <input id="search" class="search" placeholder="${esc(i18n[lang].search)}">
  <div id="matchCount" class="muted"></div>
  <div id="transcript" class="transcript"></div>`;
}

async function renderResult(j) {
  const r = await api(`/api/results/${j.id}`);
  rawTranscript = r.transcript || "";
  rawTimestamped = r.timestamped || "";
  currentView = "clean";
  $("#result").innerHTML = resultMarkup(r, j);
  showTranscript();
}

function currentRaw() {
  return currentView === "timestamped" ? rawTimestamped : rawTranscript;
}

function setActiveResultButton(action) {
  document.querySelectorAll("[data-result-action]").forEach(b => {
    b.classList.toggle("active", b.dataset.resultAction === action);
  });
}

function showTranscript() {
  currentView = "clean";
  setActiveResultButton("clean");
  const t = $("#transcript");
  if (t) t.textContent = rawTranscript;
  searchText($("#search"));
}

function showTimestamped() {
  currentView = "timestamped";
  setActiveResultButton("timestamped");
  const t = $("#transcript");
  if (t) t.textContent = rawTimestamped;
  searchText($("#search"));
}

function searchText(el) {
  const t = $("#transcript");
  const q = el ? el.value.trim() : "";
  const raw = currentRaw();
  if (!t) return;
  if (!q) {
    t.textContent = raw;
    searchMatches = [];
    searchIndex = 0;
    const count = $("#matchCount");
    if (count) count.textContent = "";
    return;
  }
  const re = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
  searchMatches = [];
  let m;
  while ((m = re.exec(raw)) !== null) searchMatches.push(m.index);
  t.innerHTML = esc(raw).replace(re, match => `<mark>${match}</mark>`);
  searchIndex = Math.min(searchIndex, Math.max(0, searchMatches.length - 1));
  const count = $("#matchCount");
  if (count) count.textContent = `${searchMatches.length} match${searchMatches.length === 1 ? "" : "es"}`;
}

function focusMatch(delta) {
  if (!searchMatches.length) return;
  searchIndex = (searchIndex + delta + searchMatches.length) % searchMatches.length;
  document.querySelectorAll("#transcript mark")[searchIndex]?.scrollIntoView({ behavior: "smooth", block: "center" });
}

async function copyValue(value, button) {
  await navigator.clipboard.writeText(value || "");
  if (!button) return;
  const original = button.textContent;
  button.textContent = i18n[lang].copied;
  setTimeout(() => { button.textContent = original; }, 1200);
}

content.addEventListener("click", async event => {
  const mode = event.target.closest("[data-mode]");
  if (mode) {
    selectMode(mode.dataset.mode);
    return;
  }

  if (event.target.closest("#go")) {
    await submitPlaylist();
    return;
  }

  const checkbox = event.target.closest("#list input[type='checkbox']");
  if (checkbox && playMode === "one" && checkbox.checked) {
    document.querySelectorAll("#list input").forEach(x => { if (x !== checkbox) x.checked = false; });
    return;
  }

  const job = event.target.closest("[data-job-id]");
  if (job) {
    await openGroupJob(job.dataset.jobId);
    return;
  }

  const action = event.target.closest("[data-result-action]");
  if (!action) return;
  const key = action.dataset.resultAction;
  if (key === "clean") showTranscript();
  if (key === "timestamped") showTimestamped();
  if (key === "copy") await copyValue(rawTranscript, action);
  if (key === "copy-ts") await copyValue(rawTimestamped, action);
  if (key === "prev") focusMatch(-1);
  if (key === "next") focusMatch(1);
});

content.addEventListener("input", event => {
  if (event.target.id === "search") searchText(event.target);
});

applyUiLanguage("en");
loadLanguages();
