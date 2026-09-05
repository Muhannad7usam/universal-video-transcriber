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
    time: "Time",
    cached: "instant cache",
    copied: "Copied ✓",
    analyzing: "Analyzing link…",
    queued: "Queued",
    checking_cache: "Checking previous result",
    checking_captions: "Checking captions",
    downloading_captions: "Downloading captions",
    cleaning_captions: "Cleaning captions",
    downloading_audio: "Downloading audio",
    loading_model: "Loading transcription model",
    transcribing: "Transcribing speech",
    formatting: "Formatting transcript",
    saving: "Saving result",
    caching: "Optimizing next run",
    completed: "Completed",
    failed: "Failed"
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
    time: "الوقت",
    cached: "نتيجة محفوظة فوراً",
    copied: "اتنسخ ✓",
    analyzing: "بنفحص اللينك…",
    queued: "في الانتظار",
    checking_cache: "بنفحص نتيجة سابقة",
    checking_captions: "بنفحص الـ Captions",
    downloading_captions: "بنحمّل الـ Captions",
    cleaning_captions: "بننضّف الـ Captions",
    downloading_audio: "بنحمّل الصوت",
    loading_model: "بنجهز موديل التفريغ",
    transcribing: "بنفّرغ الكلام",
    formatting: "بنرتب الـ Transcript",
    saving: "بنحفظ النتيجة",
    caching: "بنسرّع التشغيل الجاي",
    completed: "اكتمل",
    failed: "فشل"
  }
};

let lang = localStorage.getItem("uvt-ui-language") || "en";
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
  return h
    ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
    : `${m}:${String(s).padStart(2, "0")}`;
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

function stageLabel(state) {
  return i18n[lang][state] || String(state || "").replaceAll("_", " ");
}

function applyUiLanguage(next) {
  lang = next === "ar" ? "ar" : "en";
  localStorage.setItem("uvt-ui-language", lang);
  document.documentElement.lang = lang;
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
    // Keep the built-in options if the endpoint is temporarily unavailable.
  }
  if ([...languageSelect.options].some(o => o.value === saved)) {
    languageSelect.value = saved;
  }
}

languageSelect?.addEventListener("change", () => {
  localStorage.setItem("uvt-transcription-language", languageSelect.value);
});

document.querySelectorAll("[data-lang]").forEach(button => {
  button.addEventListener("click", () => applyUiLanguage(button.dataset.lang));
});

async function startTranscription() {
  const url = $("#url").value.trim();
  if (!url) return;

  const start = $("#start");
  start.disabled = true;
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
  } finally {
    start.disabled = false;
  }
}

$("#start")?.addEventListener("click", startTranscription);
$("#url")?.addEventListener("keydown", e => {
  if (e.key === "Enter") startTranscription();
});

function renderJobProgress(j) {
  const status = $("#status");
  const bar = $("#bar");
  if (status) status.textContent = `${stageLabel(j.state)} · ${j.progress}%`;
  if (bar) bar.style.width = `${Math.max(0, Math.min(100, j.progress || 0))}%`;
}

function watch(id) {
  content.innerHTML = `<div class="card"><div id="status">${esc(i18n[lang].analyzing)}</div><div class="progress"><div id="bar" class="bar" style="width:0%"></div></div><div id="result"></div></div>`;

  let finished = false;
  let fallbackStarted = false;
  const source = new EventSource(`/api/jobs/${encodeURIComponent(id)}/events`);

  const handle = async j => {
    if (finished) return;
    renderJobProgress(j);
    if (j.state === "completed") {
      finished = true;
      source.close();
      await renderResult(j);
    } else if (j.state === "failed") {
      finished = true;
      source.close();
      const host = $("#result");
      if (host) host.innerHTML = `<p class="error">${esc(j.error || "Transcription failed")}</p>`;
    }
  };

  source.onmessage = event => {
    try { handle(JSON.parse(event.data)); } catch (_) {}
  };

  source.onerror = () => {
    source.close();
    if (!finished && !fallbackStarted) {
      fallbackStarted = true;
      pollJob(id, handle);
    }
  };
}

async function pollJob(id, handle) {
  try {
    const j = await api(`/api/jobs/${id}`);
    await handle(j);
    if (!["completed", "failed"].includes(j.state)) {
      setTimeout(() => pollJob(id, handle), 900);
    }
  } catch (e) {
    const host = $("#result");
    if (host) host.innerHTML = `<p class="error">${esc(e.message)}</p>`;
  }
}

function renderPlaylist(j) {
  currentPlaylist = j;
  playMode = "selected";
  content.innerHTML = `<div class="card">
    <div class="toolbar"><div><h2>${esc(j.title)}</h2><p class="muted">${j.count} videos</p></div></div>
    <div class="actions">
      <button class="chip" type="button" data-mode="one">${esc(i18n[lang].one)}</button>
      <button class="chip active" type="button" data-mode="selected">${esc(i18n[lang].selected)}</button>
      <button class="chip" type="button" data-mode="range">${esc(i18n[lang].range)}</button>
      <button class="chip" type="button" data-mode="all">${esc(i18n[lang].all)}</button>
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
    <button id="go" class="primary" type="button" style="margin-top:18px;height:46px">${esc(i18n[lang].go)}</button>
  </div>`;
}

function selectMode(mode) {
  playMode = mode;
  document.querySelectorAll("[data-mode]").forEach(b => b.classList.toggle("active", b.dataset.mode === mode));
  const checks = [...document.querySelectorAll("#list input")];
  if (mode === "all") checks.forEach(x => { x.checked = true; });
  if (mode === "one") {
    let kept = false;
    checks.forEach(x => {
      if (x.checked && !kept) kept = true;
      else x.checked = false;
    });
  }
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

  const go = $("#go");
  if (go) go.disabled = true;
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
    if (go) go.disabled = false;
  }
}

function paintGroup(g) {
  const host = $("#group");
  if (!host) return;
  host.innerHTML = g.jobs.map(x => `<button class="item" type="button" data-job-id="${esc(x.id)}" style="width:100%;margin:8px 0;text-align:left">
    <span>${esc(x.item_index)}. ${esc(x.title)}</span>
    <span class="muted">${esc(stageLabel(x.state))} ${esc(x.progress)}%</span>
  </button>`).join("");
}

function renderGroup(gid) {
  content.innerHTML = `<div class="split"><aside class="card"><h2>${esc(i18n[lang].playlist)}</h2><div id="group"></div></aside><section class="card"><div id="groupResult" class="muted">${esc(i18n[lang].selectCompleted)}</div></section></div>`;

  let fallbackStarted = false;
  const source = new EventSource(`/api/groups/${encodeURIComponent(gid)}/events`);
  source.onmessage = event => {
    try {
      const g = JSON.parse(event.data);
      paintGroup(g);
      if (g.jobs.length && g.jobs.every(x => ["completed", "failed"].includes(x.state))) {
        source.close();
      }
    } catch (_) {}
  };
  source.onerror = () => {
    source.close();
    if (!fallbackStarted) {
      fallbackStarted = true;
      pollGroup(gid);
    }
  };
}

async function pollGroup(gid) {
  try {
    const g = await api(`/api/groups/${gid}`);
    paintGroup(g);
    if (!g.jobs.every(x => ["completed", "failed"].includes(x.state))) {
      setTimeout(() => pollGroup(gid), 1200);
    }
  } catch (_) {}
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
  const extra = [];
  if (r.processing_seconds != null) extra.push(`<span class="status-pill">${esc(i18n[lang].time)}: ${esc(Number(r.processing_seconds).toFixed(1))}s</span>`);
  if (r.cache_hit) extra.push(`<span class="status-pill">${esc(i18n[lang].cached)}</span>`);

  return `<div class="toolbar"><div><h2>${esc(r.title || j.title)}</h2><div class="result-meta">
    <span class="status-pill">${esc(i18n[lang].language)}: ${esc(r.language || "Unknown")}</span>
    <span class="status-pill">${esc(i18n[lang].method)}: ${esc(r.method || "")}</span>
    <span class="status-pill">${esc(i18n[lang].coverage)}: ${esc(i18n[lang].fullVideo)}</span>
    ${extra.join("")}
  </div></div></div>
  <div class="actions">
    <button class="chip active" type="button" data-result-action="clean">${esc(i18n[lang].clean)}</button>
    <button class="chip" type="button" data-result-action="timestamped">${esc(i18n[lang].timestamped)}</button>
    <button class="chip" type="button" data-result-action="copy">${esc(i18n[lang].copy)}</button>
    <button class="chip" type="button" data-result-action="copy-ts">${esc(i18n[lang].copyTimestamps)}</button>
    <button class="chip" type="button" data-result-action="prev">${esc(i18n[lang].previous)}</button>
    <button class="chip" type="button" data-result-action="next">${esc(i18n[lang].next)}</button>
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

  const escaped = q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const re = new RegExp(escaped, "gi");
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
  const old = button.textContent;
  button.textContent = i18n[lang].copied;
  setTimeout(() => { button.textContent = old; }, 1200);
}

document.addEventListener("click", event => {
  const mode = event.target.closest("[data-mode]");
  if (mode) {
    selectMode(mode.dataset.mode);
    return;
  }

  if (event.target.closest("#go")) {
    submitPlaylist();
    return;
  }

  const job = event.target.closest("[data-job-id]");
  if (job) {
    openGroupJob(job.dataset.jobId);
    return;
  }

  const actionButton = event.target.closest("[data-result-action]");
  if (!actionButton) return;
  const action = actionButton.dataset.resultAction;
  if (action === "clean") showTranscript();
  else if (action === "timestamped") showTimestamped();
  else if (action === "copy") copyValue(rawTranscript, actionButton);
  else if (action === "copy-ts") copyValue(rawTimestamped, actionButton);
  else if (action === "prev") focusMatch(-1);
  else if (action === "next") focusMatch(1);
});

document.addEventListener("input", event => {
  if (event.target?.id === "search") searchText(event.target);
});

document.addEventListener("change", event => {
  if (playMode !== "one" || !event.target.matches("#list input[type='checkbox']") || !event.target.checked) return;
  document.querySelectorAll("#list input[type='checkbox']").forEach(x => {
    if (x !== event.target) x.checked = false;
  });
});

applyUiLanguage(lang);
loadLanguages();
