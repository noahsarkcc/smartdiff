const API = "";

const state = {
  config: null,
  mode: "local",       // "local" | "revision" | "browse" | "overview" | "merge"
  files: [],
  modifiedFiles: [],
  selectedFile: null,
  filterText: "",
  showOnlyModified: false,
  diff: null,
  activeSheet: null,
  loading: false,
  // revision mode
  revLog: [],
  revOld: null,
  revNew: null,
  // overview mode
  overviewLog: [],
  overviewFiles: null,
  overviewFilter: "all",  // "all" | "data-only"
  overviewExpanded: {},
  modifiedClassify: {},
  // merge mode
  mergeData: null,
  mergeTheirsRev: "HEAD",
  mergeFromSvnConflict: false,
  mergeOnlyConflicts: false,         // 工具栏过滤：只看待解决
  mergeExpandMode: "smart",          // "smart"（按需）| "all" | "none"
  mergeRowExpanded: {},              // 单行手动展开覆盖：{ "sheet:rowKey": true|false }
};

let _lastMtime = 0;
let _scrollHintUpdaters = [];
let _scrollHintElements = [];
function _refreshScrollHints() { _scrollHintUpdaters.forEach(fn => fn()); }
function _cleanupScrollHints() {
  _scrollHintElements.forEach(el => el.remove());
  _scrollHintElements = [];
  _scrollHintUpdaters = [];
}

function _fixScrollableHeight() {
  const content = document.getElementById("content");
  if (!content) return;
  const targets = content.querySelectorAll(".diff-container, .overview-files");
  targets.forEach(el => {
    if (el.closest(".ov-file-detail")) return;
    el.style.maxHeight = "";
    const contentRect = content.getBoundingClientRect();
    const elRect = el.getBoundingClientRect();
    const avail = contentRect.bottom - elRect.top;
    if (avail > 50) el.style.maxHeight = avail + "px";
  });
  content.querySelectorAll(".ov-file-detail .diff-container").forEach(dc => {
    dc.style.maxHeight = "";
    const top = dc.getBoundingClientRect().top;
    const avail = window.innerHeight - top - 20;
    const h = Math.max(200, Math.min(avail, 600));
    dc.style.maxHeight = h + "px";
  });
  requestAnimationFrame(_refreshScrollHints);
}
window.addEventListener("resize", () => { _fixScrollableHeight(); });

// ── API helpers ──

async function api(url, opts) {
  const res = await fetch(API + url, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || res.statusText);
  }
  return res.json();
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1024 / 1024).toFixed(1) + " MB";
}

// ── Init ──

async function init() {
  try {
    state.config = await api("/api/config");
    renderHeader();
    await loadFiles();
    if (state.config.svn_available) {
      loadModifiedFiles();
      loadModifiedClassify();
      startRemoteVersionCheck();
    }
  } catch (e) {
    document.querySelector(".main").innerHTML =
      `<div class="placeholder"><div class="icon">!</div><div class="text">连接失败: ${e.message}</div></div>`;
  }
}

async function loadFiles() {
  try {
    const data = await api("/api/files");
    state.files = data.files || [];
    renderFileList();
  } catch (e) {
    state.files = [];
    renderFileList();
  }
}

async function loadModifiedFiles() {
  const data = await api("/api/svn/modified");
  state.modifiedFiles = data.files;
  renderFileList();
}

async function loadModifiedClassify() {
  try {
    const data = await api("/api/svn/modified-classify");
    state.modifiedClassify = data.classify || {};
    renderFileList();
  } catch (_) { /* non-critical */ }
}

// ── Render: Header ──

function renderHeader() {
  const cfg = state.config;
  const badge = document.getElementById("svnBadge");
  if (cfg.svn_available) {
    badge.textContent = `SVN ${cfg.svn_version}`;
    badge.className = "svn-badge";
  } else {
    badge.textContent = "SVN 未连接";
    badge.className = "svn-badge offline";
  }
  renderWorkspaceSelect();
}

function renderWorkspaceSelect() {
  const sel = document.getElementById("workspaceSelect");
  const cfg = state.config;
  if (!cfg.workspaces) return;
  sel.innerHTML = cfg.workspaces.map((ws, i) =>
    `<option value="${i}" ${i === cfg.active_workspace ? "selected" : ""}>${ws.name} — ${ws.path}</option>`
  ).join("");
}

async function switchWorkspace(idx) {
  try {
    await api("/api/workspaces/switch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ index: idx }),
    });
    state.selectedFile = null;
    state.diff = null;
    state.activeSheet = null;
    state.overviewFiles = null;
    state.overviewLog = [];
    state.revLog = [];
    state.modifiedClassify = {};
    document.getElementById("updateBanner").style.display = "none";
    _bannerDismissed = false;
    state.config = await api("/api/config");
    renderHeader();
    await loadFiles();
    if (state.config.svn_available) {
      loadModifiedFiles();
      loadModifiedClassify();
      startRemoteVersionCheck();
    }
    if (state.mode === "overview") {
      loadOverviewLog();
    }
    renderToolbar();
    renderContent();
  } catch (e) {
    alert("\u5207\u6362\u5de5\u4f5c\u533a\u5931\u8d25: " + e.message);
  }
}

async function addWorkspace() {
  try {
    const resp = await fetch("/api/pick-dir", { method: "POST" });
    if (resp.ok) {
      const data = await resp.json();
      if (data.path) await _doAddWorkspace(data.path);
      return;
    }
    if (resp.status === 501) { showDirBrowser(); return; }
  } catch (_) { /* network error */ }
  showDirBrowser();
}

async function _doAddWorkspace(path) {
  try {
    await api("/api/workspaces/add", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    state.selectedFile = null;
    state.diff = null;
    state.config = await api("/api/config");
    renderHeader();
    renderToolbar();
    renderContent();
    await loadFiles();
    if (state.config.svn_available) {
      loadModifiedFiles();
      startRemoteVersionCheck();
    }
  } catch (e) {
    alert("\u6dfb\u52a0\u5de5\u4f5c\u533a\u5931\u8d25: " + e.message);
  }
}

async function showDirBrowser() {
  const overlay = document.createElement("div");
  overlay.className = "update-modal-overlay";
  overlay.id = "dirBrowserOverlay";

  overlay.innerHTML = `<div class="update-modal dir-browser-modal">
    <h3>\u9009\u62e9\u5de5\u4f5c\u533a\u76ee\u5f55</h3>
    <div class="dir-path-bar">
      <button class="dir-up-btn" onclick="dirBrowserUp()" title="\u8fd4\u56de\u4e0a\u7ea7\u76ee\u5f55">\u2191</button>
      <input type="text" id="dirPathInput" placeholder="\u8f93\u5165\u8def\u5f84..." onkeydown="if(event.key==='Enter')dirBrowserGo()" />
      <button onclick="dirBrowserGo()">\u524d\u5f80</button>
    </div>
    <div class="dir-breadcrumb" id="dirBreadcrumb"></div>
    <div class="dir-list" id="dirList"><div class="loading">\u52a0\u8f7d\u4e2d...</div></div>
    <div class="modal-footer">
      <button class="primary" onclick="dirBrowserSelect()">\u9009\u62e9\u6b64\u76ee\u5f55</button>
      <button onclick="closeDirBrowser()">\u53d6\u6d88</button>
    </div>
  </div>`;

  document.body.appendChild(overlay);
  await dirBrowserNavigate("");
}

let _dirBrowserPath = "";

function _dirNorm(p) { return p.replace(/\\/g, "/"); }

function _dirParent(p) {
  const norm = _dirNorm(p).replace(/\/+$/, "");
  if (/^[A-Za-z]:$/.test(norm)) return "";
  const idx = norm.lastIndexOf("/");
  if (idx <= 0) return norm.match(/^[A-Za-z]:/) ? norm.slice(0, 2) : "";
  return norm.slice(0, idx);
}

async function dirBrowserNavigate(path) {
  _dirBrowserPath = path;
  const listEl = document.getElementById("dirList");
  const inputEl = document.getElementById("dirPathInput");
  const breadEl = document.getElementById("dirBreadcrumb");
  if (!listEl) return;

  listEl.innerHTML = `<div style="padding:10px;color:var(--text-dim)">\u52a0\u8f7d\u4e2d...</div>`;
  try {
    const data = await api(`/api/browse-dir?path=${encodeURIComponent(path)}`);
    _dirBrowserPath = data.path || "";
    if (inputEl) inputEl.value = _dirBrowserPath;

    if (breadEl) {
      if (data.is_root) {
        breadEl.innerHTML = `<span class="crumb active">\u6211\u7684\u7535\u8111</span>`;
      } else {
        const norm = _dirNorm(_dirBrowserPath);
        const parts = norm.split("/").filter(Boolean);
        let crumbs = `<span class="crumb" onclick="dirBrowserNavigate('')">\u6211\u7684\u7535\u8111</span>`;
        for (let i = 0; i < parts.length; i++) {
          const seg = parts.slice(0, i + 1).join("/");
          const isLast = i === parts.length - 1;
          crumbs += ` <span class="sep">\u203a</span> <span class="crumb${isLast ? " active" : ""}" onclick="dirBrowserNavigate('${seg.replace(/'/g, "\\'")}')">${parts[i]}</span>`;
        }
        breadEl.innerHTML = crumbs;
      }
    }

    let html = "";
    if (!data.is_root && _dirBrowserPath) {
      const parent = _dirParent(_dirBrowserPath);
      html += `<div class="dir-item dir-item-up" onclick="dirBrowserNavigate('${_dirNorm(parent).replace(/'/g, "\\'")}')">\ud83d\udcc1 ..</div>`;
    }
    if (data.dirs.length === 0 && !html) {
      listEl.innerHTML = `<div style="padding:10px;color:var(--text-dim)">\u6ca1\u6709\u5b50\u76ee\u5f55</div>`;
    } else {
      for (const d of data.dirs) {
        const name = _dirNorm(d).split("/").filter(Boolean).pop() || d;
        const dSafe = _dirNorm(d).replace(/'/g, "\\'");
        html += `<div class="dir-item" onclick="dirBrowserHighlight(this)" ondblclick="dirBrowserNavigate('${dSafe}')">\ud83d\udcc2 ${name}</div>`;
      }
      listEl.innerHTML = html;
    }
  } catch (e) {
    listEl.innerHTML = `<div style="padding:10px;color:var(--red)">\u52a0\u8f7d\u5931\u8d25: ${e.message}</div>`;
  }
}

function dirBrowserHighlight(el) {
  document.querySelectorAll(".dir-item.selected").forEach(e => e.classList.remove("selected"));
  el.classList.add("selected");
}

function dirBrowserUp() {
  if (!_dirBrowserPath) return;
  dirBrowserNavigate(_dirParent(_dirBrowserPath));
}

function dirBrowserGo() {
  const input = document.getElementById("dirPathInput");
  if (input && input.value.trim()) {
    dirBrowserNavigate(input.value.trim());
  }
}

async function dirBrowserSelect() {
  const selected = document.querySelector(".dir-item.selected");
  let path = _dirBrowserPath;
  if (selected) {
    const text = selected.textContent.replace(/^\ud83d\udcc2\s*/, "").trim();
    if (text && text !== "..") {
      const dirs = await api(`/api/browse-dir?path=${encodeURIComponent(_dirBrowserPath)}`).catch(() => null);
      if (dirs) {
        const match = dirs.dirs.find(d => _dirNorm(d).split("/").filter(Boolean).pop() === text);
        if (match) path = match;
      }
    }
  }
  if (!path) {
    alert("\u8bf7\u5148\u9009\u62e9\u4e00\u4e2a\u76ee\u5f55");
    return;
  }
  closeDirBrowser();
  await _doAddWorkspace(path);
}

function closeDirBrowser() {
  const overlay = document.getElementById("dirBrowserOverlay");
  if (overlay) overlay.remove();
}

async function openWorkspaceDir() {
  try {
    await api("/api/open-dir", { method: "POST" });
  } catch (e) {
    alert("\u6253\u5f00\u76ee\u5f55\u5931\u8d25: " + e.message);
  }
}

async function removeWorkspace() {
  const cfg = state.config;
  if (!cfg.workspaces || cfg.workspaces.length <= 1) {
    alert("至少保留一个工作区");
    return;
  }
  const idx = cfg.active_workspace;
  const ws = cfg.workspaces[idx];
  if (!confirm(`确定删除工作区 "${ws.name}" (${ws.path})？`)) return;
  try {
    const res = await api("/api/workspaces/remove", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ index: idx }),
    });
    state.selectedFile = null;
    state.diff = null;
    state.config = await api("/api/config");
    renderHeader();
    await loadFiles();
    if (state.config.svn_available) loadModifiedFiles();
    renderToolbar();
    renderContent();
  } catch (e) {
    alert("删除工作区失败: " + e.message);
  }
}

// ── SVN Remote Version Check & Update ──

let _remoteCheckTimer = null;
let _bannerDismissed = false;

function startRemoteVersionCheck() {
  if (_remoteCheckTimer) clearInterval(_remoteCheckTimer);
  _remoteCheckTimer = setInterval(checkRemoteVersion, 30000);
  checkRemoteVersion();
}

async function checkRemoteVersion() {
  if (!state.config || !state.config.svn_available) return;
  if (_bannerDismissed) return;
  try {
    const data = await api("/api/svn/remote-revision");
    const banner = document.getElementById("updateBanner");
    if (data.has_update) {
      const diff = data.remote_revision - data.local_revision;
      banner.innerHTML = `\u6709 ${diff} \u4e2a\u65b0\u7248\u672c\u53ef\u7528 (r${data.local_revision} \u2192 r${data.remote_revision}) ` +
        `<button class="btn-update" onclick="doSvnUpdate()">\u66f4\u65b0</button>` +
        `<button class="btn-dismiss" onclick="dismissBanner()">\u5ffd\u7565</button>`;
      banner.style.display = "flex";
    } else {
      banner.style.display = "none";
    }
  } catch (_) {}
}

function dismissBanner() {
  document.getElementById("updateBanner").style.display = "none";
  _bannerDismissed = true;
  setTimeout(() => { _bannerDismissed = false; }, 300000);
}

async function doSvnUpdate() {
  const banner = document.getElementById("updateBanner");
  banner.innerHTML = `\u68c0\u67e5\u51b2\u7a81\u4e2d...`;

  try {
    const checkData = await api("/api/svn/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ check_only: true }),
    });

    if (checkData.conflicts && checkData.conflicts.length > 0) {
      showUpdateConflictModal(checkData);
    } else {
      const result = await api("/api/svn/update", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      banner.innerHTML = `\u66f4\u65b0\u5b8c\u6210\uff01\u5df2\u66f4\u65b0 ${result.updated || 0} \u4e2a\u6587\u4ef6`;
      setTimeout(() => { banner.style.display = "none"; }, 3000);
      await reloadAfterUpdate();
    }
  } catch (e) {
    banner.innerHTML = `\u66f4\u65b0\u5931\u8d25: ${e.message} <button class="btn-dismiss" onclick="dismissBanner()">\u5173\u95ed</button>`;
  }
}

function showUpdateConflictModal(checkData) {
  const overlay = document.createElement("div");
  overlay.className = "update-modal-overlay";
  overlay.id = "updateModalOverlay";

  const conflicts = checkData.conflicts;
  const safeCount = checkData.safe_updates;

  let conflictHtml = "";
  for (const fname of conflicts) {
    const isXml = fname.toLowerCase().endsWith(".xml");
    const semBtn = isXml
      ? `<button onclick="openMergeFromConflict('${fname.replace(/'/g, "\\'")}')" title="\u5355\u5143\u683c\u7ea7\u8bed\u4e49\u5408\u5e76" class="btn-merge">\u8bed\u4e49\u5408\u5e76</button>`
      : "";
    conflictHtml += `<div class="conflict-item" data-file="${fname}">
      <span class="fname">${fname}</span>
      <div class="actions">
        <button onclick="setConflictChoice(this,'mine')" title="\u4fdd\u7559\u672c\u5730\u4fee\u6539">\u4fdd\u7559\u6211\u7684</button>
        <button onclick="setConflictChoice(this,'theirs')" title="\u7528\u670d\u52a1\u5668\u7248\u672c\u8986\u76d6">\u7528\u6700\u65b0</button>
        <button onclick="setConflictChoice(this,'skip')" title="\u8df3\u8fc7\u4e0d\u66f4\u65b0">\u8df3\u8fc7</button>
        ${semBtn}
      </div>
    </div>`;
  }

  overlay.innerHTML = `<div class="update-modal">
    <h3>\u53d1\u73b0\u51b2\u7a81\u6587\u4ef6</h3>
    <p class="safe-info">\u65e0\u51b2\u7a81\u6587\u4ef6 ${safeCount} \u4e2a\u5c06\u81ea\u52a8\u66f4\u65b0</p>
    <div class="conflict-list">${conflictHtml}</div>
    <div class="modal-footer">
      <button onclick="skipAllConflicts()">\u5168\u90e8\u8df3\u8fc7\u51b2\u7a81\u6587\u4ef6</button>
      <button class="primary" onclick="executeUpdate()">\u786e\u8ba4\u66f4\u65b0</button>
      <button onclick="closeUpdateModal()">\u53d6\u6d88</button>
    </div>
  </div>`;

  document.body.appendChild(overlay);
}

function setConflictChoice(btn, choice) {
  const item = btn.closest(".conflict-item");
  item.querySelectorAll("button").forEach(b => {
    b.className = "";
  });
  btn.className = choice === "theirs" ? "selected-theirs" :
                  choice === "mine" ? "selected-mine" : "selected-skip";
  item.dataset.choice = choice;
}

function skipAllConflicts() {
  document.querySelectorAll(".conflict-item").forEach(item => {
    item.dataset.choice = "skip";
    item.querySelectorAll("button").forEach(b => b.className = "");
    const skipBtn = item.querySelector("button:last-child");
    if (skipBtn) skipBtn.className = "selected-skip";
  });
  executeUpdate();
}

async function executeUpdate() {
  const items = document.querySelectorAll(".conflict-item");
  const skip_files = [];
  const theirs_files = [];
  const mine_files = [];

  items.forEach(item => {
    const fname = item.dataset.file;
    const choice = item.dataset.choice || "skip";
    if (choice === "skip") skip_files.push(fname);
    else if (choice === "theirs") theirs_files.push(fname);
    else if (choice === "mine") mine_files.push(fname);
  });

  closeUpdateModal();
  const banner = document.getElementById("updateBanner");
  banner.innerHTML = `\u6b63\u5728\u66f4\u65b0...`;
  banner.style.display = "flex";

  try {
    const result = await api("/api/svn/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ skip_files, theirs_files, mine_files }),
    });
    const parts = [];
    if (result.updated) parts.push(`\u66f4\u65b0 ${result.updated} \u4e2a\u6587\u4ef6`);
    if (result.skipped.length) parts.push(`\u8df3\u8fc7 ${result.skipped.length} \u4e2a`);
    if (result.theirs.length) parts.push(`\u7528\u6700\u65b0\u7248 ${result.theirs.length} \u4e2a`);
    if (result.mine.length) parts.push(`\u4fdd\u7559\u672c\u5730 ${result.mine.length} \u4e2a`);
    if (result.errors.length) parts.push(`\u9519\u8bef ${result.errors.length}`);
    banner.innerHTML = `\u66f4\u65b0\u5b8c\u6210: ${parts.join(", ")}`;
    setTimeout(() => { banner.style.display = "none"; }, 5000);
    await reloadAfterUpdate();
  } catch (e) {
    banner.innerHTML = `\u66f4\u65b0\u5931\u8d25: ${e.message} <button class="btn-dismiss" onclick="dismissBanner()">\u5173\u95ed</button>`;
  }
}

function closeUpdateModal() {
  const overlay = document.getElementById("updateModalOverlay");
  if (overlay) overlay.remove();
}

async function reloadAfterUpdate() {
  state.config = await api("/api/config");
  renderHeader();
  await loadFiles();
  if (state.config.svn_available) loadModifiedFiles();
  if (state.selectedFile && state.mode === "local") {
    doDiffLocal();
  }
}

// ── Render: File list ──

function renderFileList() {
  const list = document.getElementById("fileList");
  const modMap = {};
  state.modifiedFiles.forEach(f => { modMap[f.name] = f.status; });

  let files = state.files;
  if (state.mode === "merge") {
    files = files.filter(f => f.name.toLowerCase().endsWith(".xml"));
  }
  if (state.filterText) {
    const ft = state.filterText.toLowerCase();
    files = files.filter(f => f.name.toLowerCase().includes(ft));
  }
  if (state.showOnlyModified) {
    files = files.filter(f => modMap[f.name]);
  }

  list.innerHTML = files.map(f => {
    const status = modMap[f.name] || "";
    const active = state.selectedFile === f.name ? " active" : "";
    let dotClass = "";
    if (status === "added") dotClass = " added";
    else if (status === "deleted") dotClass = " deleted";
    else if (status) {
      const cls = state.modifiedClassify[f.name];
      dotClass = cls === "meta" ? " meta-change" : " data-change";
    }
    const lowName = f.name.toLowerCase();
    const typeBadge = lowName.endsWith(".xlsx") ? '<span class="type-badge xlsx">XLSX</span>'
                    : lowName.endsWith(".xls") ? '<span class="type-badge xls">XLS</span>' : '';
    const slashIdx = f.name.lastIndexOf("/");
    const displayName = slashIdx >= 0 ? f.name.substring(slashIdx + 1) : f.name;
    const dirBadge = slashIdx >= 0 ? `<span class="type-badge dir">${f.name.substring(0, slashIdx)}</span>` : '';
    const safeName = f.name.replace(/&/g,"&amp;").replace(/'/g,"&#39;").replace(/"/g,"&quot;");
    return `<div class="file-item${active}" onclick="selectFile('${safeName}')">
      <span class="status-dot${dotClass}"></span>
      <span class="name" title="${f.name}">${displayName}</span>
      ${typeBadge}${dirBadge}
      <span class="size">${formatSize(f.size)}</span>
    </div>`;
  }).join("");
}

// ── Mode switching ──

function setMode(mode) {
  state.mode = mode;
  document.querySelectorAll(".mode-tab").forEach(t => {
    t.classList.toggle("active", t.dataset.mode === mode);
  });
  state.diff = null;
  state.activeSheet = null;
  state.mergeData = null;

  const sidebar = document.querySelector(".sidebar");
  const app = document.querySelector(".app");
  if (mode === "overview") {
    sidebar.style.display = "none";
    app.style.gridTemplateColumns = "1fr";
    state.overviewFiles = null;
    state.overviewExpanded = {};
    loadOverviewLog();
  } else {
    sidebar.style.display = "";
    app.style.gridTemplateColumns = "320px 1fr";
  }

  renderFileList();
  renderToolbar();
  renderContent();
  if (state.selectedFile) {
    if (mode === "local") doDiffLocal();
    else if (mode === "revision") loadRevLog();
    else if (mode === "browse") doBrowse();
    else if (mode === "merge") doMergePreview();
  }
}

// ── File selection ──

async function selectFile(name) {
  _lastMtime = 0;
  state.selectedFile = name;
  state.diff = null;
  state.activeSheet = null;
  state.mergeData = null;
  renderFileList();
  renderToolbar();

  if (state.mode === "local") {
    await doDiffLocal();
  } else if (state.mode === "revision") {
    await loadRevLog();
  } else if (state.mode === "browse") {
    await doBrowse();
  } else if (state.mode === "merge") {
    await doMergePreview();
  }
}

// ── Toolbar ──

function renderToolbar() {
  const tb = document.getElementById("toolbar");

  if (state.mode === "overview") {
    if (state.overviewLog.length > 0) renderOverviewToolbar();
    else tb.innerHTML = `<span style="color:var(--text-dim)">加载版本历史中...</span>`;
    return;
  }

  if (!state.selectedFile) {
    tb.innerHTML = "";
    return;
  }

  if (state.mode === "local") {
    tb.innerHTML = `
      <span style="font-size:13px;color:var(--text-bright)">${state.selectedFile}</span>
      <div class="spacer" style="flex:1"></div>
      <button class="btn" onclick="doDiffLocal()" title="\u624b\u52a8\u5237\u65b0">&#8635; \u5237\u65b0</button>`;
  } else if (state.mode === "revision") {
    if (state.revLog.length === 0) {
      tb.innerHTML = `
        <span style="font-size:13px;color:var(--text-bright)">${state.selectedFile}</span>
        <span style="margin-left:12px;color:var(--text-dim)">暂无 SVN 版本记录</span>`;
    } else if (state.revLog.length === 1) {
      const e = state.revLog[0];
      tb.innerHTML = `
        <span style="font-size:13px;color:var(--text-bright)">${state.selectedFile}</span>
        <span style="margin-left:12px;font-size:12px;color:var(--text-dim);padding:4px 8px;border:1px solid var(--border);border-radius:var(--radius);background:var(--bg)">r${e.revision} - ${e.author}</span>
        <span style="font-size:11px;color:var(--text-dim);margin-left:8px">仅有 1 个版本，无法进行版本间对比</span>`;
    } else {
      const opts = state.revLog.map(e =>
        `<option value="${e.revision}">r${e.revision} - ${e.author} - ${e.message.substring(0, 30)}</option>`
      ).join("");
      tb.innerHTML = `
        <span style="font-size:13px;color:var(--text-bright)">${state.selectedFile}</span>
        <label>旧版本:</label>
        <select id="revOld">${opts}</select>
        <label>新版本:</label>
        <select id="revNew">${opts}</select>
        <button class="btn primary" onclick="doDiffRevision()">对比版本</button>`;
      document.getElementById("revOld").value = state.revLog[1].revision;
      document.getElementById("revNew").value = state.revLog[0].revision;
    }
  } else if (state.mode === "browse") {
    tb.innerHTML = `
      <span style="font-size:13px;color:var(--text-bright)">${state.selectedFile}</span>
      <div style="flex:1"></div>
      <span style="font-size:12px;color:var(--text-dim)">浏览模式 - 查看文件内容</span>`;
  } else if (state.mode === "merge") {
    renderMergeToolbar();
  }
}

function renderMergeToolbar() {
  const tb = document.getElementById("toolbar");
  const md = state.mergeData;

  let stats = "";
  let progress = "";
  let applyBtnDisabled = "";
  let extras = "";
  if (md && md.summary) {
    const s = md.summary;
    const remaining = countRemainingConflicts();
    const total = (s.conflicts || 0);
    const resolved = total - remaining;
    const pct = total > 0 ? Math.round((resolved / total) * 100) : 100;
    const cls = remaining > 0 ? "merge-stat-pending" : "merge-stat-ok";
    stats = `<span class="merge-stats ${cls}">自动 ${s.auto_resolved} · 冲突 ${total}${remaining > 0 ? ` · 待解决 ${remaining}` : "（全部解决）"}</span>`;
    progress = total > 0
      ? `<div class="merge-progress" title="${resolved}/${total} 已解决">
           <div class="merge-progress-bar ${remaining === 0 ? "done" : ""}" style="width:${pct}%"></div>
           <span class="merge-progress-text">${pct}%</span>
         </div>`
      : "";
    if (remaining > 0) applyBtnDisabled = "disabled";

    const filterActive = state.mergeOnlyConflicts ? " active" : "";
    const expandLabel = state.mergeExpandMode === "all" ? "全部折叠"
      : state.mergeExpandMode === "none" ? "智能展开"
      : "全部展开";
    extras = `
      <button class="btn merge-toolbar-toggle${filterActive}" onclick="toggleMergeFilter()" title="只显示需要手动处理的项">
        ${state.mergeOnlyConflicts ? "✓ " : ""}只看待解决${remaining > 0 ? ` (${remaining})` : ""}
      </button>
      <button class="btn merge-toolbar-toggle" onclick="cycleMergeExpandMode()" title="切换 智能/全展开/全折叠">
        ${expandLabel}
      </button>`;
  }

  const fname = state.selectedFile
    ? `<span style="font-size:13px;color:var(--text-bright)">${state.selectedFile}</span>`
    : `<span style="font-size:13px;color:var(--text-dim)">未选择文件</span>`;

  tb.innerHTML = `
    ${fname}
    <label>对比版本:</label>
    <input type="text" id="mergeTheirsRev" value="${state.mergeTheirsRev}" style="width:80px" title="HEAD 或具体版本号" />
    <button class="btn" onclick="doMergePreview()">刷新</button>
    ${stats}
    ${progress}
    ${extras}
    <div style="flex:1"></div>
    <button class="btn primary" id="applyMergeBtn" onclick="applyMerge()" ${applyBtnDisabled}>应用合并并保存</button>`;

  const revInput = document.getElementById("mergeTheirsRev");
  if (revInput) {
    revInput.addEventListener("change", () => {
      state.mergeTheirsRev = revInput.value.trim() || "HEAD";
    });
  }
}

function toggleMergeFilter() {
  state.mergeOnlyConflicts = !state.mergeOnlyConflicts;
  renderMergeToolbar();
  renderMergeView(document.getElementById("content"));
}

function cycleMergeExpandMode() {
  const order = { smart: "all", all: "none", none: "smart" };
  state.mergeExpandMode = order[state.mergeExpandMode] || "smart";
  state.mergeRowExpanded = {};
  renderMergeToolbar();
  renderMergeView(document.getElementById("content"));
}

function rowNeedsAttention(row) {
  if (row.is_row_conflict && row.row_decision === null) return true;
  if (rowKeepsCells(row)) {
    for (const col in row.cells) {
      const c = row.cells[col];
      if (c.status === "conflict" && c.resolved === null) return true;
    }
  }
  return false;
}

function isRowExpanded(sheetName, row) {
  const key = `${sheetName}:${row.row_key}`;
  if (state.mergeRowExpanded[key] !== undefined) return state.mergeRowExpanded[key];
  if (state.mergeExpandMode === "all") return true;
  if (state.mergeExpandMode === "none") return false;
  return rowNeedsAttention(row);
}

function toggleRowExpanded(sheetName, rowKey) {
  const md = state.mergeData;
  if (!md) return;
  const sheet = md.sheets[sheetName];
  if (!sheet) return;
  const row = sheet.rows.find(r => r.row_key === rowKey);
  if (!row) return;
  const key = `${sheetName}:${rowKey}`;
  const current = isRowExpanded(sheetName, row);
  state.mergeRowExpanded[key] = !current;
  renderMergeView(document.getElementById("content"));
}

function countRemainingConflicts() {
  const md = state.mergeData;
  if (!md || !md.sheets) return 0;
  let n = 0;
  for (const sheetName in md.sheets) {
    const sheet = md.sheets[sheetName];
    for (const row of sheet.rows) {
      if (row.is_row_conflict && row.row_decision === null) n++;
      else if (rowKeepsCells(row)) {
        for (const col in row.cells) {
          const c = row.cells[col];
          if (c.status === "conflict" && c.resolved === null) n++;
        }
      }
    }
  }
  return n;
}

function rowKeepsCells(row) {
  const s = row.status;
  if (s === "modified") return true;
  if (s === "added_both_diff") return row.row_decision === "merge";
  return false;
}

function renderOverviewToolbar() {
  const tb = document.getElementById("toolbar");
  const opts = state.overviewLog.map(e =>
    `<option value="${e.revision}">r${e.revision} - ${e.author} - ${e.message.substring(0, 40)}</option>`
  ).join("");
  tb.innerHTML = `
    <label>旧版本:</label>
    <select id="ovRevOld">${opts}</select>
    <label>新版本:</label>
    <select id="ovRevNew">${opts}</select>
    <button class="btn primary" onclick="doOverview()">对比版本</button>
    <div style="flex:1"></div>
    <button class="btn ${state.overviewFilter === 'all' ? 'primary' : ''}" onclick="setOverviewFilter('all')">全部文件</button>
    <button class="btn ${state.overviewFilter === 'data-only' ? 'primary' : ''}" onclick="setOverviewFilter('data-only')">仅数据变更</button>`;
  if (state.overviewLog.length >= 2) {
    document.getElementById("ovRevOld").value = state.overviewLog[1].revision;
    document.getElementById("ovRevNew").value = state.overviewLog[0].revision;
  }
}

// ── Actions ──

async function doDiffLocal() {
  if (!state.selectedFile) return;
  state.loading = true;
  renderContent();
  try {
    state.diff = await api("/api/diff/local", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file: state.selectedFile }),
    });
    if (state.diff.sheets) {
      const names = Object.keys(state.diff.sheets);
      state.activeSheet = names[0] || null;
    }
  } catch (e) {
    state.diff = { error: e.message };
  }
  state.loading = false;
  renderContent();
}

async function loadRevLog() {
  if (!state.selectedFile) return;
  try {
    const data = await api(`/api/svn/log?file=${encodeURIComponent(state.selectedFile)}&limit=30`);
    state.revLog = data.entries;
    renderToolbar();
  } catch (e) {
    state.revLog = [];
    renderToolbar();
  }
}

async function doDiffRevision() {
  if (!state.selectedFile) return;
  const revOldEl = document.getElementById("revOld");
  const revNewEl = document.getElementById("revNew");
  const revOld = revOldEl ? revOldEl.value : (state.revLog.length >= 2 ? String(state.revLog[state.revLog.length - 1].revision) : "");
  const revNew = revNewEl ? revNewEl.value : (state.revLog.length ? String(state.revLog[0].revision) : "");
  state.loading = true;
  renderContent();
  try {
    state.diff = await api("/api/diff/revisions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        file: state.selectedFile,
        rev_old: revOld,
        rev_new: revNew,
      }),
    });
    if (state.diff.sheets) {
      const names = Object.keys(state.diff.sheets);
      state.activeSheet = names[0] || null;
    }
  } catch (e) {
    state.diff = { error: e.message };
  }
  state.loading = false;
  renderContent();
}

async function doBrowse() {
  if (!state.selectedFile) return;
  state.loading = true;
  renderContent();
  try {
    const data = await api(`/api/parse?file=${encodeURIComponent(state.selectedFile)}`);
    state.diff = { browse: true, parsed: data };
    if (data.sheets) {
      const names = Object.keys(data.sheets);
      state.activeSheet = names[0] || null;
    }
  } catch (e) {
    state.diff = { error: e.message };
  }
  state.loading = false;
  renderContent();
}

// ── Render: Main content ──

function renderContent() {
  _cleanupScrollHints();
  const main = document.getElementById("content");

  if (state.loading) {
    main.innerHTML = `<div class="loading"><img class="icon-img pixel-bounce" src="/static/img/miku.svg" alt="" />\u52a0\u8f7d\u4e2d...</div>`;
    return;
  }

  if (state.mode === "overview") {
    if (!state.overviewFiles) {
      main.innerHTML = `<div class="placeholder">
        <img class="icon-img" src="/static/img/miku.svg" alt="" />
        <div class="text">\u9009\u62e9\u4e24\u4e2a\u7248\u672c\u540e\u70b9\u51fb"\u5bf9\u6bd4\u7248\u672c"</div>
        <div class="hint">类似 GitHub 的版本间文件变更总览</div>
      </div>`;
      return;
    }
    renderOverviewView(main);
    return;
  }

  if (state.mode === "merge") {
    if (!state.selectedFile) {
      main.innerHTML = `<div class="placeholder">
        <img class="icon-img" src="/static/img/miku.svg" alt="" />
        <div class="text">\u9009\u62e9\u4e00\u4e2a .xml \u6587\u4ef6\u5f00\u59cb\u4e09\u65b9\u8bed\u4e49\u5408\u5e76</div>
        <div class="hint">BASE (\u7248\u672c\u5e93\u539f\u59cb) / MINE (\u672c\u5730\u4fee\u6539) / THEIRS (\u8fdc\u7a0b HEAD)</div>
      </div>`;
      return;
    }
    if (!state.mergeData) {
      main.innerHTML = `<div class="placeholder">
        <img class="icon-img" src="/static/img/miku.svg" alt="" />
        <div class="text">\u52a0\u8f7d\u4e09\u65b9\u5408\u5e76\u9884\u89c8</div>
      </div>`;
      return;
    }
    if (state.mergeData.error) {
      main.innerHTML = `<div class="placeholder"><div class="icon">&#9888;</div><div class="text">${state.mergeData.error}</div></div>`;
      return;
    }
    renderMergeView(main);
    return;
  }

  if (!state.selectedFile) {
    main.innerHTML = `<div class="placeholder">
      <img class="icon-img" src="/static/img/miku.svg" alt="" />
      <div class="text">\u9009\u62e9\u5de6\u4fa7\u6587\u4ef6\u5f00\u59cb\u5bf9\u6bd4</div>
      <div class="hint">支持 本地变更 / 版本对比 / 浏览 三种模式</div>
    </div>`;
    return;
  }

  if (!state.diff) {
    main.innerHTML = `<div class="placeholder">
      <img class="icon-img" src="/static/img/miku.svg" alt="" />
      <div class="text">\u70b9\u51fb\u5de5\u5177\u680f\u6309\u94ae\u5f00\u59cb</div>
    </div>`;
    return;
  }

  if (state.diff.error) {
    main.innerHTML = `<div class="placeholder">
      <div class="icon">&#9888;</div>
      <div class="text">${state.diff.error}</div>
    </div>`;
    return;
  }

  if (state.diff.browse) {
    renderBrowseView(main);
    return;
  }

  renderDiffView(main);
}

function getDiffBlocksHtml(adds, dels, mods) {
  const total = adds + dels + mods;
  if (total === 0) return `<span class="diff-blocks"><span class="block empty"></span><span class="block empty"></span><span class="block empty"></span><span class="block empty"></span><span class="block empty"></span></span>`;
  let addB = Math.round((adds / total) * 5);
  let delB = Math.round((dels / total) * 5);
  let modB = Math.round((mods / total) * 5);
  
  while (addB + delB + modB > 5) {
    if (addB >= delB && addB >= modB) addB--;
    else if (delB >= addB && delB >= modB) delB--;
    else modB--;
  }
  
  let emptyB = 5 - (addB + delB + modB);
  let html = `<span class="diff-blocks" title="${adds} 新增, ${dels} 删除, ${mods} 修改">`;
  for(let i=0; i<addB; i++) html += `<span class="block add"></span>`;
  for(let i=0; i<delB; i++) html += `<span class="block del"></span>`;
  for(let i=0; i<modB; i++) html += `<span class="block mod"></span>`;
  for(let i=0; i<emptyB; i++) html += `<span class="block empty"></span>`;
  html += `</span>`;
  return html;
}

function renderDiffView(container) {
  const diff = state.diff;
  const summary = diff.summary;

  let html = "";

  // Sheet tabs
  const sheetNames = Object.keys(diff.sheets);
  html += `<div class="sheet-tabs">`;
  for (const name of sheetNames) {
    const sd = diff.sheets[name];
    const active = state.activeSheet === name ? " active" : "";
    let badge = "";
    if (sd.status === "added") badge = `<span class="badge added">新增</span>`;
    else if (sd.status === "removed") badge = `<span class="badge removed">删除</span>`;
    else if (sd.status === "modified") {
      const parts = [];
      if (sd.modified_cells.length > 0) parts.push(`<span class="badge changed">~${sd.modified_cells.length}</span>`);
      if (sd.added_rows.length > 0) parts.push(`<span class="badge added">+${sd.added_rows.length}</span>`);
      if (sd.removed_rows.length > 0) parts.push(`<span class="badge removed">-${sd.removed_rows.length}</span>`);
      badge = parts.join("");
    }
    html += `<button class="sheet-tab${active}" onclick="setActiveSheet('${name.replace(/'/g, "\\'")}')">${name}${badge}</button>`;
  }
  html += `</div>`;

  // Stats panel
  html += `<div class="diff-stats">`;
  html += `<span class="diff-stats-label">${diff.old_label || "旧"} → ${diff.new_label || "新"}</span>`;
  if (summary.has_changes) {
    html += `<span class="diff-stats-counts">`;
    if (summary.total_added_rows > 0)
      html += `<span class="stat-added">+${summary.total_added_rows} 行</span>`;
    if (summary.total_removed_rows > 0)
      html += `<span class="stat-removed">-${summary.total_removed_rows} 行</span>`;
    if (summary.total_modified_cells > 0)
      html += `<span class="stat-modified">~${summary.total_modified_cells} 格</span>`;
    
    html += getDiffBlocksHtml(summary.total_added_rows, summary.total_removed_rows, summary.total_modified_cells);
    const total = summary.total_added_rows + summary.total_removed_rows + summary.total_modified_cells;
    html += `<span class="stat-total">${total} 处变更</span>`;
    html += `</span>`;
  } else {
    html += `<span class="no-changes">无数据变更（仅元数据差异）</span>`;
  }
  html += `</div>`;

  // Diff table
  if (state.activeSheet && diff.sheets[state.activeSheet]) {
    html += renderDiffTable(diff.sheets[state.activeSheet]);
  }

  container.innerHTML = html;
  requestAnimationFrame(() => { attachScrollHints(container, true); _fixScrollableHeight(); });
}

function attachScrollHints(root, clearAll) {
  if (clearAll) _cleanupScrollHints();
  const containers = root.querySelectorAll(".diff-container");
  containers.forEach(container => {
    const modCells = container.querySelectorAll("td.cell-modified");
    if (modCells.length === 0) return;

    const leftHint = document.createElement("div");
    leftHint.className = "scroll-hint scroll-hint-left";
    leftHint.style.display = "none";
    document.body.appendChild(leftHint);
    _scrollHintElements.push(leftHint);

    const rightHint = document.createElement("div");
    rightHint.className = "scroll-hint scroll-hint-right";
    rightHint.style.display = "none";
    document.body.appendChild(rightHint);
    _scrollHintElements.push(rightHint);

    function updateHints() {
      if (!container.isConnected) {
        leftHint.style.display = "none";
        rightHint.style.display = "none";
        return;
      }
      const cr = container.getBoundingClientRect();
      if (cr.width < 50 || cr.height < 30 || cr.bottom < 0 || cr.top > window.innerHeight) {
        leftHint.style.display = "none";
        rightHint.style.display = "none";
        return;
      }

      let leftCount = 0, rightCount = 0;
      let nearestLeftOffset = 0, nearestRightOffset = Infinity;
      modCells.forEach(cell => {
        const r = cell.getBoundingClientRect();
        if (r.right < cr.left + 2) {
          leftCount++;
          const off = cell.offsetLeft;
          if (off > nearestLeftOffset) nearestLeftOffset = off;
        } else if (r.left > cr.right - 2) {
          rightCount++;
          const off = cell.offsetLeft;
          if (off < nearestRightOffset) nearestRightOffset = off;
        }
      });

      const centerY = cr.top + cr.height / 2;
      if (leftCount > 0) {
        leftHint.textContent = `\u2190 \u5de6\u4fa7 ${leftCount} \u5904\u53d8\u66f4`;
        leftHint.style.display = "block";
        leftHint.style.top = centerY + "px";
        leftHint.style.left = (cr.left + 8) + "px";
        leftHint.style.right = "";
        leftHint.onclick = () => {
          container.scrollTo({ left: Math.max(0, nearestLeftOffset - 40), behavior: "smooth" });
        };
      } else {
        leftHint.style.display = "none";
      }
      if (rightCount > 0) {
        rightHint.textContent = `\u53f3\u4fa7 ${rightCount} \u5904\u53d8\u66f4 \u2192`;
        rightHint.style.display = "block";
        rightHint.style.top = centerY + "px";
        rightHint.style.left = "";
        rightHint.style.right = (window.innerWidth - cr.right + 8) + "px";
        rightHint.onclick = () => {
          container.scrollTo({ left: Math.max(0, nearestRightOffset - 40), behavior: "smooth" });
        };
      } else {
        rightHint.style.display = "none";
      }
    }

    container.addEventListener("scroll", updateHints);
    _scrollHintUpdaters.push(updateHints);
  });
  requestAnimationFrame(_refreshScrollHints);
}


const BATCH_SIZE = 150;
let _tableIdCounter = 0;

function _colLetters(count) {
  const letters = [];
  for (let i = 0; i < count; i++) {
    let n = i + 1, s = "";
    while (n > 0) { n--; s = String.fromCharCode(65 + n % 26) + s; n = Math.floor(n / 26); }
    letters.push(s);
  }
  return letters;
}

/**
 * Character-level inline diff using LCS (Longest Common Subsequence).
 * Returns HTML with <del> for removed and <ins> for added segments.
 * For strings > 200 chars, tokenizes by common delimiters first.
 */
function inlineDiff(oldStr, newStr) {
  if (oldStr === newStr) return escHtml(newStr);
  if (!oldStr) return `<ins>${escHtml(newStr)}</ins>`;
  if (!newStr) return `<del>${escHtml(oldStr)}</del>`;

  const CHAR_THRESHOLD = 200;
  let oldToks, newToks;
  if (oldStr.length <= CHAR_THRESHOLD && newStr.length <= CHAR_THRESHOLD) {
    oldToks = Array.from(oldStr);
    newToks = Array.from(newStr);
  } else {
    const split = s => {
      const toks = [];
      let buf = "";
      for (const ch of s) {
        if (",;{}() \t".includes(ch)) {
          if (buf) { toks.push(buf); buf = ""; }
          toks.push(ch);
        } else {
          buf += ch;
        }
      }
      if (buf) toks.push(buf);
      return toks;
    };
    oldToks = split(oldStr);
    newToks = split(newStr);
  }

  const m = oldToks.length, n = newToks.length;
  const dp = [];
  for (let i = 0; i <= m; i++) {
    dp[i] = new Uint16Array(n + 1);
  }
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (oldToks[i - 1] === newToks[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1] + 1;
      } else {
        dp[i][j] = dp[i][j - 1] > dp[i - 1][j] ? dp[i][j - 1] : dp[i - 1][j];
      }
    }
  }

  const ops = [];
  let i = m, j = n;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && oldToks[i - 1] === newToks[j - 1]) {
      ops.push({ type: "eq", val: oldToks[i - 1] });
      i--; j--;
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      ops.push({ type: "ins", val: newToks[j - 1] });
      j--;
    } else {
      ops.push({ type: "del", val: oldToks[i - 1] });
      i--;
    }
  }
  ops.reverse();

  let html = "";
  let delBuf = "", insBuf = "";
  const flush = () => {
    if (delBuf) { html += `<del>${escHtml(delBuf)}</del>`; delBuf = ""; }
    if (insBuf) { html += `<ins>${escHtml(insBuf)}</ins>`; insBuf = ""; }
  };
  for (const op of ops) {
    if (op.type === "eq") {
      flush();
      html += escHtml(op.val);
    } else if (op.type === "del") {
      if (insBuf) flush();
      delBuf += op.val;
    } else {
      insBuf += op.val;
    }
  }
  flush();
  return html;
}

function _rowHtml(row, colLetters, headers) {
  const st = row._status;
  let h;
  if (st === "added") h = `<tr class=" row-added">`;
  else if (st === "removed") h = `<tr class=" row-removed">`;
  else h = `<tr>`;
  h += `<td class="row-num">${row._row}</td>`;

  if (st === "modified" && row.changes) {
    const changes = row.changes;
    for (let i = 0; i < colLetters.length; i++) {
      const col = colLetters[i];
      const ch = changes[col];
      if (ch) {
        const diffHtml = inlineDiff(ch.old, ch.new);
        h += `<td class="cell-modified" title="${col}${row._row}"><div class="inline-diff">${diffHtml}</div></td>`;
      } else {
        h += `<td>${escHtml(row.cells[col] || "")}</td>`;
      }
    }
  } else {
    const cells = row.cells;
    for (let i = 0; i < colLetters.length; i++) {
      h += `<td>${escHtml(cells[colLetters[i]] || "")}</td>`;
    }
  }
  h += `</tr>`;
  return h;
}

function _appendRowsBatch(tbodyId, rows, colLetters, headers, start) {
  const tbody = document.getElementById(tbodyId);
  if (!tbody) return;
  const end = Math.min(start + BATCH_SIZE, rows.length);
  let html = "";
  for (let i = start; i < end; i++) html += _rowHtml(rows[i], colLetters, headers);
  tbody.insertAdjacentHTML("beforeend", html);
  if (end < rows.length) {
    requestAnimationFrame(() => _appendRowsBatch(tbodyId, rows, colLetters, headers, end));
  }
}

function renderDiffTable(sheetDiff) {
  const headers = sheetDiff.new_headers.length > 0 ? sheetDiff.new_headers : sheetDiff.old_headers;
  if (headers.length === 0) return `<div class="placeholder"><div class="text">该 Sheet 无数据</div></div>`;

  const allRows = [];
  const seenRows = new Set();
  (sheetDiff.removed_rows || []).forEach(r => { allRows.push({ ...r, _status: "removed" }); seenRows.add(r._row); });
  (sheetDiff.added_rows || []).forEach(r => { allRows.push({ ...r, _status: "added" }); seenRows.add(r._row); });
  (sheetDiff.modified_rows || []).forEach(mr => {
    if (!seenRows.has(mr._row)) {
      allRows.push({ _row: mr._row, cells: mr.cells, old_cells: mr.old_cells, changes: mr.changes, _status: "modified" });
      seenRows.add(mr._row);
    }
  });
  allRows.sort((a, b) => a._row - b._row);

  if (allRows.length === 0) {
    return `<div class="summary-bar"><span class="no-changes">该 Sheet 无变更</span></div>`;
  }

  const tid = `dtb_${++_tableIdCounter}`;
  const colLetters = _colLetters(headers.length);
  let headHtml = `<div class="diff-container"><table class="diff-table"><thead><tr><th class="row-num">#</th>`;
  for (let i = 0; i < headers.length; i++) headHtml += `<th title="${colLetters[i]}">${headers[i] || colLetters[i]}</th>`;
  headHtml += `</tr></thead><tbody id="${tid}">`;

  const firstBatch = allRows.slice(0, BATCH_SIZE);
  let bodyHtml = "";
  for (const row of firstBatch) bodyHtml += _rowHtml(row, colLetters, headers);
  headHtml += bodyHtml + `</tbody></table></div>`;

  if (allRows.length > BATCH_SIZE) {
    requestAnimationFrame(() => _appendRowsBatch(tid, allRows, colLetters, headers, BATCH_SIZE));
  }
  return headHtml;
}

function renderBrowseView(container) {
  const parsed = state.diff.parsed;
  const sheetNames = Object.keys(parsed.sheets);

  let html = `<div class="sheet-tabs">`;
  for (const name of sheetNames) {
    const sd = parsed.sheets[name];
    const active = state.activeSheet === name ? " active" : "";
    html += `<button class="sheet-tab${active}" onclick="setActiveSheet('${name.replace(/'/g, "\\'")}')">${name} <span class="badge" style="border:1px solid var(--border);color:var(--text-dim)">${sd.row_count}</span></button>`;
  }
  html += `</div>`;

  html += `<div class="summary-bar"><span>浏览模式 · 解析耗时 ${parsed._parse_ms}ms</span></div>`;

  if (state.activeSheet && parsed.sheets[state.activeSheet]) {
    const sheet = parsed.sheets[state.activeSheet];
    const headers = sheet.headers;
    const colLetters = _colLetters(headers.length);
    const dataRows = sheet.rows.slice(1);

    const browseTid = `btb_${++_tableIdCounter}`;
    html += `<div class="diff-container"><table class="diff-table"><thead><tr>`;
    html += `<th class="row-num">#</th>`;
    for (let i = 0; i < headers.length; i++) html += `<th title="${colLetters[i]}">${headers[i] || colLetters[i]}</th>`;
    html += `</tr></thead><tbody id="${browseTid}">`;

    const firstBatch = dataRows.slice(0, BATCH_SIZE);
    for (const row of firstBatch) {
      html += `<tr><td class="row-num">${row._row}</td>`;
      for (const col of colLetters) html += `<td>${escHtml(row.cells[col] || "")}</td>`;
      html += `</tr>`;
    }
    html += `</tbody></table></div>`;

    if (dataRows.length > BATCH_SIZE) {
      requestAnimationFrame(() => _appendBrowseRowsBatch(browseTid, dataRows, colLetters, BATCH_SIZE));
    }
  }

  container.innerHTML = html;
  requestAnimationFrame(_fixScrollableHeight);
}

function _appendBrowseRowsBatch(tbodyId, rows, colLetters, start) {
  const tbody = document.getElementById(tbodyId);
  if (!tbody) return;
  const end = Math.min(start + BATCH_SIZE, rows.length);
  let html = "";
  for (let i = start; i < end; i++) {
    const row = rows[i];
    html += `<tr><td class="row-num">${row._row}</td>`;
    for (const col of colLetters) html += `<td>${escHtml(row.cells[col] || "")}</td>`;
    html += `</tr>`;
  }
  tbody.insertAdjacentHTML("beforeend", html);
  if (end < rows.length) {
    requestAnimationFrame(() => _appendBrowseRowsBatch(tbodyId, rows, colLetters, end));
  }
}

function setActiveSheet(name) {
  state.activeSheet = name;
  renderContent();
}

// ── Overview mode ──

async function loadOverviewLog() {
  try {
    const data = await api("/api/svn/dir-log?limit=50");
    state.overviewLog = data.entries;
    renderOverviewToolbar();
  } catch (e) {
    state.overviewLog = [];
  }
}

function setOverviewFilter(filter) {
  state.overviewFilter = filter;
  renderContent();
  const btns = document.querySelectorAll("#toolbar .btn:not(.primary)");
  document.querySelectorAll("#toolbar .btn").forEach(b => {
    if (b.textContent === "全部文件" || b.textContent === "仅数据变更") {
      b.classList.toggle("primary",
        (b.textContent === "全部文件" && filter === "all") ||
        (b.textContent === "仅数据变更" && filter === "data-only"));
    }
  });
}

function toggleOverviewFile(fname) {
  state.overviewExpanded[fname] = !state.overviewExpanded[fname];
  const card = document.querySelector(`.ov-file-card[data-file="${fname}"]`);
  if (!card) { renderContent(); return; }

  const expanded = state.overviewExpanded[fname];
  card.classList.toggle("expanded", expanded);

  const arrow = card.querySelector(".ov-expand");
  if (arrow) arrow.textContent = expanded ? "\u25BC" : "\u25B6";

  const existingDetail = card.querySelector(".ov-file-detail");
  if (expanded) {
    if (!existingDetail) {
      const f = (state.overviewFiles.files || []).find(x => x.file === fname);
      if (f && f.diff) {
        const detailHtml = renderOverviewFileDetail(f);
        card.insertAdjacentHTML("beforeend", detailHtml);
        const dc = card.querySelector(".diff-container");
        if (dc) {
          dc.offsetHeight;
          const top = dc.getBoundingClientRect().top;
          const avail = window.innerHeight - top - 20;
          dc.style.maxHeight = Math.max(200, Math.min(avail, 600)) + "px";
        }
        requestAnimationFrame(() => attachScrollHints(card));
      }
    }
  } else {
    if (existingDetail) existingDetail.remove();
  }
}

function setOverviewSheet(fname, sheetName) {
  const key = `_sheet_${fname}`;
  state.overviewExpanded[key] = sheetName;
  const card = document.querySelector(`.ov-file-card[data-file="${fname}"]`);
  if (!card) { renderContent(); return; }

  const existingDetail = card.querySelector(".ov-file-detail");
  if (existingDetail) existingDetail.remove();

  const f = (state.overviewFiles.files || []).find(x => x.file === fname);
  if (f && f.diff) {
    const detailHtml = renderOverviewFileDetail(f);
    card.insertAdjacentHTML("beforeend", detailHtml);
    const dc = card.querySelector(".diff-container");
    if (dc) {
      dc.offsetHeight;
      const top = dc.getBoundingClientRect().top;
      const avail = window.innerHeight - top - 20;
      dc.style.maxHeight = Math.max(200, Math.min(avail, 600)) + "px";
    }
    requestAnimationFrame(() => attachScrollHints(card));
  }
}

async function doOverview() {
  const revOld = document.getElementById("ovRevOld").value;
  const revNew = document.getElementById("ovRevNew").value;
  state.loading = true;
  state.overviewExpanded = {};
  renderContent();
  try {
    state.overviewFiles = await api("/api/diff/overview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rev_old: revOld, rev_new: revNew }),
    });
  } catch (e) {
    state.overviewFiles = { error: e.message };
  }
  state.loading = false;
  renderContent();
}

function renderOverviewView(container) {
  const ov = state.overviewFiles;
  if (ov.error) {
    container.innerHTML = `<div class="placeholder"><div class="icon">&#9888;</div><div class="text">${ov.error}</div></div>`;
    return;
  }

  let files = ov.files || [];
  if (state.overviewFilter === "data-only") {
    files = files.filter(f => {
      const s = f.summary || {};
      return (s.total_modified_cells || 0) + (s.total_added_rows || 0) + (s.total_removed_rows || 0) > 0;
    });
  }

  let html = `<div class="overview-summary">`;
  html += `<span>r${ov.rev_old} \u2192 r${ov.rev_new}</span>`;
  html += `<span class="stat">\u5171 ${ov.total_files} \u4e2a\u6587\u4ef6\u53d8\u66f4</span>`;
  html += `<span class="stat">\u5176\u4e2d ${ov.data_changed_files} \u4e2a\u6709\u6570\u636e\u53d8\u66f4</span>`;
  if (state.overviewFilter === "data-only") {
    html += `<span class="stat">\u5f53\u524d\u663e\u793a ${files.length} \u4e2a</span>`;
  }
  html += `</div>`;

  if (files.length === 0) {
    html += `<div class="placeholder"><div class="text">\u65e0\u5339\u914d\u7684\u6587\u4ef6</div></div>`;
    container.innerHTML = html;
    return;
  }

  html += `<div class="overview-files">`;
  for (const f of files) {
    const expanded = state.overviewExpanded[f.file] || false;
    const statusClass = f.status === "added" ? "file-added" : f.status === "deleted" ? "file-deleted" : "";
    const statusIcon = f.status === "added" ? "+" : f.status === "deleted" ? "\u2212" : "\u2022";
    const statusColor = f.status === "added" ? "var(--green)" : f.status === "deleted" ? "var(--red)" : "var(--yellow)";
    const s = f.summary || {};

    let changeSummary = "";
    if (f.status === "deleted") {
      changeSummary = `<span class="ov-badge del">\u5df2\u5220\u9664</span>`;
    } else if (f.status === "added") {
      changeSummary = `<span class="ov-badge add">\u65b0\u589e</span>`;
    } else if (f.status === "error") {
      changeSummary = `<span class="ov-badge err">\u9519\u8bef: ${escHtml(f.error || "")}</span>`;
    } else if (!s.has_changes) {
      changeSummary = `<span class="ov-badge meta">\u4ec5\u5143\u6570\u636e</span>`;
    } else {
      const parts = [];
      if (s.total_added_rows > 0) parts.push(`<span class="ov-badge add">+${s.total_added_rows}</span>`);
      if (s.total_removed_rows > 0) parts.push(`<span class="ov-badge del">-${s.total_removed_rows}</span>`);
      if (s.total_modified_cells > 0) parts.push(`<span class="ov-badge mod">~${s.total_modified_cells}</span>`);
      changeSummary = parts.join(" ");
    }

    html += `<div class="ov-file-card ${statusClass}${expanded ? " expanded" : ""}" data-file="${f.file}">`;
    html += `<div class="ov-file-header" onclick="toggleOverviewFile('${f.file}')">`;
    html += `<span class="ov-expand">${expanded ? "\u25BC" : "\u25B6"}</span>`;
    html += `<span class="ov-status" style="color:${statusColor}">${statusIcon}</span>`;
    html += `<span class="ov-filename">${f.file}</span>`;
    html += `<div class="ov-badges">${changeSummary}</div>`;
    html += `</div>`;

    if (expanded && f.diff) {
      html += renderOverviewFileDetail(f);
    }
    html += `</div>`;
  }
  html += `</div>`;

  container.innerHTML = html;
  requestAnimationFrame(_fixScrollableHeight);
}

function renderOverviewFileDetail(f) {
  const diff = f.diff;
  if (!diff || !diff.sheets) return "";

  const sheetNames = Object.keys(diff.sheets);
  const activeSheetKey = `_sheet_${f.file}`;
  let activeSheet = state.overviewExpanded[activeSheetKey] || sheetNames[0];
  if (!diff.sheets[activeSheet]) activeSheet = sheetNames[0];

  let html = `<div class="ov-file-detail">`;

  if (sheetNames.length > 1) {
    html += `<div class="sheet-tabs">`;
    for (const name of sheetNames) {
      const sd = diff.sheets[name];
      const active = activeSheet === name ? " active" : "";
      let badge = "";
      if (sd.status === "added") badge = `<span class="badge added">\u65b0\u589e</span>`;
      else if (sd.status === "removed") badge = `<span class="badge removed">\u5220\u9664</span>`;
      else if (sd.status === "modified") {
        const parts = [];
        if (sd.modified_cells.length > 0) parts.push(`<span class="badge changed">~${sd.modified_cells.length}</span>`);
        if (sd.added_rows.length > 0) parts.push(`<span class="badge added">+${sd.added_rows.length}</span>`);
        if (sd.removed_rows.length > 0) parts.push(`<span class="badge removed">-${sd.removed_rows.length}</span>`);
        badge = parts.join("");
      }
      html += `<button class="sheet-tab${active}" onclick="event.stopPropagation();setOverviewSheet('${f.file}','${name.replace(/'/g, "\\'")}')">${name}${badge}</button>`;
    }
    html += `</div>`;
  }

  if (activeSheet && diff.sheets[activeSheet]) {
    html += renderDiffTable(diff.sheets[activeSheet]);
  }

  html += `</div>`;
  return html;
}

function escHtml(s) {
  if (!s) return "";
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ── Merge mode ──

async function doMergePreview() {
  if (!state.selectedFile) return;
  if (!state.selectedFile.toLowerCase().endsWith(".xml")) {
    state.mergeData = { error: "语义合并仅支持 .xml (SpreadsheetML 2003) 文件" };
    renderToolbar();
    renderContent();
    return;
  }
  state.loading = true;
  renderContent();
  try {
    state.mergeData = await api("/api/merge/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        file: state.selectedFile,
        theirs_rev: state.mergeTheirsRev || "HEAD",
      }),
    });
    if (state.mergeData.sheets) {
      const names = Object.keys(state.mergeData.sheets);
      state.activeSheet = names[0] || null;
    }
  } catch (e) {
    state.mergeData = { error: e.message };
  }
  state.loading = false;
  renderToolbar();
  renderContent();
}

async function applyMerge() {
  if (!state.mergeData || !state.selectedFile) return;
  if (countRemainingConflicts() > 0) {
    alert("还有未解决的冲突，请先全部决议");
    return;
  }

  const resolutions = collectResolutions();
  const fromSvn = !!state.mergeFromSvnConflict;

  try {
    const result = await api("/api/merge/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        file: state.selectedFile,
        theirs_rev: state.mergeData.theirs_revision || state.mergeTheirsRev || "HEAD",
        resolutions: resolutions,
        mark_resolved: fromSvn,
      }),
    });
    const msg = `合并完成，已写回 ${result.applied} 项决议${result.svn_resolved ? "；SVN 冲突已标记为已解决" : ""}`;
    state.mergeFromSvnConflict = false;
    alert(msg);
    setMode("local");
    loadFiles();
    loadModifiedFiles();
    loadModifiedClassify();
  } catch (e) {
    alert("应用合并失败: " + e.message);
  }
}

function collectResolutions() {
  const md = state.mergeData;
  const out = [];
  if (!md || !md.sheets) return out;
  for (const sheetName in md.sheets) {
    const sheet = md.sheets[sheetName];
    for (const row of sheet.rows) {
      if (row.is_row_conflict) {
        out.push({
          sheet: sheetName,
          row_key: row.row_key,
          choice: row.row_decision,
        });
      } else if (row.row_decision && row.row_decision !== "merge" && row.row_decision !== "keep") {
        out.push({
          sheet: sheetName,
          row_key: row.row_key,
          choice: row.row_decision,
        });
      }
      if (rowKeepsCells(row)) {
        for (const col in row.cells) {
          const c = row.cells[col];
          if (c.status === "conflict" && c.resolved !== null) {
            let choice = "custom";
            let value = c.resolved;
            if (c.resolved === c.mine) choice = "mine";
            else if (c.resolved === c.theirs) choice = "theirs";
            else if (c.resolved === c.base) choice = "base";
            out.push({
              sheet: sheetName, row_key: row.row_key, col: col,
              choice: choice, value: value,
            });
          }
        }
      }
    }
  }
  return out;
}

function setCellChoice(sheetName, rowKey, col, choice, customValue) {
  const md = state.mergeData;
  if (!md) return;
  const sheet = md.sheets[sheetName];
  if (!sheet) return;
  const row = sheet.rows.find(r => r.row_key === rowKey);
  if (!row) return;
  const cell = row.cells[col];
  if (!cell) return;

  if (choice === "mine") cell.resolved = cell.mine;
  else if (choice === "theirs") cell.resolved = cell.theirs;
  else if (choice === "base") cell.resolved = cell.base;
  else if (choice === "custom") {
    const v = customValue !== undefined ? customValue
      : prompt(`输入自定义值 (${col}${row.row_num_mine || row.row_num_theirs || ""}):`, cell.resolved || cell.mine || cell.theirs);
    if (v === null) return;
    cell.resolved = v;
  }
  renderToolbar();
  renderMergeView(document.getElementById("content"));
}

function setRowChoice(sheetName, rowKey, choice) {
  const md = state.mergeData;
  if (!md) return;
  const sheet = md.sheets[sheetName];
  if (!sheet) return;
  const row = sheet.rows.find(r => r.row_key === rowKey);
  if (!row) return;
  row.row_decision = choice;
  renderToolbar();
  renderMergeView(document.getElementById("content"));
}

const ROW_STATUS_LABELS = {
  modified: "修改",
  added_mine: "新增（仅我）",
  added_theirs: "新增（仅远程）",
  added_both_same: "双方新增 · 相同",
  added_both_diff: "双方新增 · 不同",
  removed_mine: "我已删除",
  removed_theirs: "远程已删除",
  removed_both: "双方删除",
  mine_del_theirs_mod: "⚠ 我删除 / 远程修改",
  mine_mod_theirs_del: "⚠ 我修改 / 远程删除",
};

const CELL_STATUS_LABELS = {
  unchanged: "未变",
  auto_mine: "自动 · 取本地",
  auto_theirs: "自动 · 取远程",
  auto_both: "自动 · 双方同改",
  conflict: "⚠ 冲突",
};

function renderMergeView(container) {
  const md = state.mergeData;
  if (!md.sheets) {
    container.innerHTML = `<div class="placeholder"><div class="text">无可合并内容</div></div>`;
    return;
  }
  const sheetNames = Object.keys(md.sheets);
  if (sheetNames.length === 0) {
    container.innerHTML = `<div class="placeholder"><div class="text">该文件无 Sheet</div></div>`;
    return;
  }
  if (!state.activeSheet || !md.sheets[state.activeSheet]) {
    state.activeSheet = sheetNames[0];
  }

  let html = `<div class="merge-sticky-top">`;
  html += `<div class="sheet-tabs">`;
  for (const name of sheetNames) {
    const sd = md.sheets[name];
    const active = state.activeSheet === name ? " active" : "";
    let badge = "";
    if (sd.conflict_count > 0) badge = `<span class="badge changed">${sd.conflict_count}冲突</span>`;
    else if (sd.auto_resolved_count > 0) badge = `<span class="badge added">${sd.auto_resolved_count}自动</span>`;
    html += `<button class="sheet-tab${active}" onclick="setActiveSheet('${name.replace(/'/g, "\\'")}')">${name}${badge}</button>`;
  }
  html += `</div>`;

  html += `<div class="merge-versions-bar">
    <span class="ver base">${escHtml(md.base_label || "BASE")}</span>
    <span class="ver-sep">←</span>
    <span class="ver mine">${escHtml(md.mine_label || "本地")}</span>
    <span class="ver-sep">·</span>
    <span class="ver theirs">${escHtml(md.theirs_label || "远程")}</span>
  </div>`;
  html += `</div>`;

  const sheet = md.sheets[state.activeSheet];
  html += renderMergeSheet(state.activeSheet, sheet);

  container.innerHTML = html;
  requestAnimationFrame(_fixScrollableHeight);
}

function renderMergeSheet(sheetName, sheet) {
  if (sheet.sheet_status === "added_theirs") {
    return `<div class="placeholder"><div class="text">该 Sheet 仅存在于远程，整表新增；请直接更新该文件</div></div>`;
  }
  if (sheet.sheet_status === "mine_only") {
    return `<div class="placeholder"><div class="text">该 Sheet 仅存在于本地，无需合并</div></div>`;
  }
  if (!sheet.rows || sheet.rows.length === 0) {
    return `<div class="merge-empty"><div class="text">该 Sheet 无任何变更</div></div>`;
  }

  let html = `<div class="merge-container">`;
  if (sheet.id_column) {
    html += `<div class="merge-id-hint">ID 列: <code>${sheet.id_column}</code> · 共 ${sheet.rows.length} 行变更</div>`;
  } else {
    html += `<div class="merge-id-hint warn">⚠ 未检测到 ID 列，按行号匹配（精度较低）</div>`;
  }

  let visible = 0;
  let html_rows = "";
  for (const row of sheet.rows) {
    if (state.mergeOnlyConflicts && !rowNeedsAttention(row)) continue;
    html_rows += renderMergeRow(sheetName, sheet, row);
    visible++;
  }

  if (visible === 0 && state.mergeOnlyConflicts) {
    html += `<div class="merge-empty"><div class="text">没有需要手动处理的项 ✓</div><div class="text" style="font-size:11px;color:var(--text-dim);margin-top:6px">取消「只看待解决」可查看自动决议项</div></div>`;
  } else {
    html += html_rows;
  }
  html += `</div>`;
  return html;
}

function renderMergeRow(sheetName, sheet, row) {
  const status = row.status;
  const label = ROW_STATUS_LABELS[status] || status;
  const isConflict = row.is_row_conflict;
  const needsAttn = rowNeedsAttention(row);
  const expanded = isRowExpanded(sheetName, row);
  const rowNum = row.row_num_mine || row.row_num_theirs || row.row_num_base || "?";
  const sk = sheetName.replace(/'/g, "\\'");
  const rk = String(row.row_key).replace(/'/g, "\\'");

  const cls = ["merge-row"];
  if (isConflict) cls.push("row-conflict");
  if (needsAttn) cls.push("needs-attention");
  if (!expanded) cls.push("collapsed");

  let html = `<div class="${cls.join(" ")}" data-status="${status}">`;

  // Header
  html += `<div class="merge-row-header" onclick="toggleRowExpanded('${sk}','${rk}')">
    <span class="row-toggle">${expanded ? "▾" : "▸"}</span>
    <span class="row-key">${escHtml(String(row.row_key))}</span>
    <span class="row-num">#${rowNum}</span>
    <span class="row-status-badge ${isConflict ? "danger" : (needsAttn ? "warn" : "")}">${label}</span>`;

  if (isConflict || ["added_theirs", "removed_theirs", "removed_mine", "removed_both", "added_both_diff", "added_mine"].includes(status)) {
    html += `<div class="row-decision-actions" onclick="event.stopPropagation()">${renderRowDecisionButtonsInner(sheetName, row)}</div>`;
  }
  html += `</div>`;

  // Body: 始终显示完整行表（带表头），无论展开/折叠
  html += renderRowFullTable(sheetName, sheet, row);

  // Body: 展开时显示变更详情
  if (expanded) {
    if (status === "modified" || (status === "added_both_diff" && row.row_decision === "merge")) {
      const changedCells = [];
      for (const col in row.cells) {
        const cell = row.cells[col];
        if (cell.status === "unchanged") continue;
        changedCells.push(renderMergeCell(sheetName, row, col, cell));
      }
      if (changedCells.length > 0) {
        html += `<div class="merge-row-detail">
          <div class="merge-detail-label">变更详情 (${changedCells.length})</div>
          <div class="merge-cells">${changedCells.join("")}</div>
        </div>`;
      }
    } else if (["added_both_diff"].includes(status)) {
      html += `<div class="merge-row-detail">
        <div class="merge-detail-label">候选版本对比</div>
        <div class="row-side-by-side">
          ${renderRowPreviewHorizontal(sheet, row, "mine", "本地版本")}
          ${renderRowPreviewHorizontal(sheet, row, "theirs", "远程版本")}
        </div>
      </div>`;
    }
  }

  html += `</div>`;
  return html;
}

function _resolvedRowSource(row) {
  // 根据当前 row_decision + status 决定行的"有效值来源"
  const status = row.status;
  const dec = row.row_decision;

  // 删除类决定 → 行不会出现在结果中；显示删除前的值 + strike-through
  if (dec === "keep_mine_delete" || dec === "accept_theirs_delete" || dec === "delete") {
    let side = "mine";
    if (status === "removed_mine" || status === "removed_both") side = "base";
    else if (status === "mine_del_theirs_mod") side = "theirs";
    return { side, deleted: true };
  }
  // 接受远程：用 theirs 值
  if (dec === "accept_theirs") return { side: "theirs", deleted: false };
  // 保留本地（已存在）/ keep_mine 新增 → mine
  if (dec === "keep_mine") {
    // 对于 added_theirs + keep_mine = "忽略远程新增"，根本没行；置为虚化
    if (status === "added_theirs") return { side: "theirs", ignored: true };
    return { side: "mine", deleted: false };
  }
  // 行级冲突 + 尚未决议：选择最能说明"当前情况"的一侧
  if (dec === null) {
    if (status === "mine_del_theirs_mod") return { side: "theirs", deleted: false }; // 本地已删，但显示远程修改后的内容供判断
    if (status === "mine_mod_theirs_del") return { side: "mine", deleted: false };   // 本地修改的版本（远程已删除）
    if (status === "added_both_diff") return { side: "mine", deleted: false };       // 默认显示本地版本，下方有 side-by-side 详情
  }
  // merge / null / keep（modified / added_both_same）→ 用 resolved（cell-level）
  return { side: "resolved", deleted: false };
}

function renderRowFullTable(sheetName, sheet, row) {
  const cols = Object.keys(row.cells).sort((a, b) => {
    const f = (s) => s.split("").reduce((acc, ch) => acc * 26 + (ch.charCodeAt(0) - 64), 0);
    return f(a) - f(b);
  });
  if (cols.length === 0) return "";

  const eff = _resolvedRowSource(row);
  const trCls = ["rt-row"];
  if (eff.deleted) trCls.push("deleted");
  if (eff.ignored) trCls.push("ignored");

  const headerCells = cols.map(col => {
    const cell = row.cells[col];
    return `<th class="rt-th"><span class="rt-h">${escHtml(cell.header || "")}</span><span class="rt-l">${col}</span></th>`;
  }).join("");

  const dataCells = cols.map(col => {
    const cell = row.cells[col];
    let v;
    let cellCls = "rt-td";
    let badge = "";
    let titleHint = `本地: ${cell.mine || "（空）"}\n远程: ${cell.theirs || "（空）"}\n基础: ${cell.base || "（空）"}`;

    if (eff.side === "resolved") {
      // 行决议交给单元格层：根据每个 cell 的状态着色 + 加 badge
      v = cell.resolved !== null && cell.resolved !== undefined ? cell.resolved : cell.mine;
      if (cell.status === "unchanged") {
        // 不加 badge
      } else if (cell.status === "auto_mine") {
        cellCls += " val-mine"; badge = `<span class="rt-tag tag-mine" title="自动·取本地">本</span>`;
      } else if (cell.status === "auto_theirs") {
        cellCls += " val-theirs"; badge = `<span class="rt-tag tag-theirs" title="自动·取远程">远</span>`;
      } else if (cell.status === "auto_both") {
        cellCls += " val-both"; badge = `<span class="rt-tag tag-both" title="双方同改">=</span>`;
      } else if (cell.status === "conflict") {
        if (cell.resolved !== null && cell.resolved !== undefined) {
          let src = "?", sCls = "tag-mine";
          if (cell.resolved === cell.mine) { cellCls += " val-mine"; src = "本"; sCls = "tag-mine"; }
          else if (cell.resolved === cell.theirs) { cellCls += " val-theirs"; src = "远"; sCls = "tag-theirs"; }
          else { cellCls += " val-custom"; src = "✎"; sCls = "tag-custom"; }
          badge = `<span class="rt-tag ${sCls}" title="冲突已解决">${src}</span>`;
        } else {
          cellCls += " val-conflict";
          badge = `<span class="rt-tag tag-warn" title="待解决冲突">!</span>`;
        }
      }
    } else {
      // 行级决议直接选择了一侧（mine / theirs / base）：整行统一着色，
      // 仅对"该单元格在两侧实际不同"的列加细微高亮。
      v = cell[eff.side];
      const sideCls = eff.side === "mine" ? "val-mine" : (eff.side === "theirs" ? "val-theirs" : "");
      if (sideCls) cellCls += " " + sideCls;
      // 与 base 对比标识
      if (eff.side === "mine" && cell.mine !== cell.base) {
        badge = `<span class="rt-tag tag-mine" title="本地修改">改</span>`;
      } else if (eff.side === "theirs" && cell.theirs !== cell.base) {
        badge = `<span class="rt-tag tag-theirs" title="远程修改">改</span>`;
      }
    }

    return `<td class="${cellCls}" title="${escHtml(titleHint)}">${badge}<span class="rt-v">${escHtml(v || "—")}</span></td>`;
  }).join("");

  let footnote = "";
  if (eff.deleted) footnote = `<div class="rt-footnote">该行将被删除</div>`;
  else if (eff.ignored) footnote = `<div class="rt-footnote">该行将被忽略（不引入合并结果）</div>`;

  return `<div class="merge-row-table">
    <table class="rt"><thead><tr>${headerCells}</tr></thead><tbody><tr class="${trCls.join(" ")}">${dataCells}</tr></tbody></table>
    ${footnote}
  </div>`;
}

function renderRowDecisionButtonsInner(sheetName, row) {
  const status = row.status;
  const dec = row.row_decision;
  const sk = sheetName.replace(/'/g, "\\'");
  const rk = String(row.row_key).replace(/'/g, "\\'");

  const btn = (choice, label, title, kind) => {
    const active = dec === choice ? " selected" : "";
    const k = kind ? ` btn-${kind}` : "";
    return `<button class="row-decision-btn${active}${k}" title="${title || ""}" onclick="setRowChoice('${sk}','${rk}','${choice}')">${label}</button>`;
  };

  if (status === "added_theirs") return btn("accept_theirs", "接受远程", "引入远程新增的行", "theirs") + btn("keep_mine", "忽略", "不引入远程新增的行", "mine");
  if (status === "added_mine") return btn("keep_mine", "保留新增", "", "mine");
  if (status === "removed_mine") return btn("keep_mine_delete", "保留删除", "", "delete") + btn("accept_theirs", "恢复", "接受远程：恢复此行", "theirs");
  if (status === "removed_theirs") return btn("accept_theirs_delete", "接受删除", "", "delete") + btn("keep_mine", "保留", "保留我的此行", "mine");
  if (status === "removed_both") return btn("delete", "确认删除", "", "delete");
  if (status === "added_both_diff") return btn("keep_mine", "保留我的", "", "mine") + btn("accept_theirs", "用远程", "", "theirs") + btn("merge", "按单元格", "进入逐单元格合并模式", "merge");
  if (status === "mine_del_theirs_mod") return btn("keep_mine_delete", "保留删除", "", "delete") + btn("accept_theirs", "恢复+接受远程", "", "theirs");
  if (status === "mine_mod_theirs_del") return btn("keep_mine", "保留修改", "", "mine") + btn("accept_theirs_delete", "接受删除", "", "delete");
  return "";
}

function renderRowPreviewHorizontal(sheet, row, side, label) {
  const cols = Object.keys(row.cells).sort((a, b) => {
    const f = (s) => s.split("").reduce((acc, ch) => acc * 26 + (ch.charCodeAt(0) - 64), 0);
    return f(a) - f(b);
  });
  const headers = cols.map(col => {
    const cell = row.cells[col];
    return `<th class="rt-th"><span class="rt-h">${escHtml(cell.header || "")}</span><span class="rt-l">${col}</span></th>`;
  }).join("");
  const data = cols.map(col => {
    const cell = row.cells[col];
    const v = cell[side];
    const cls = side === "mine" ? "val-mine" : (side === "theirs" ? "val-theirs" : "");
    return `<td class="rt-td ${cls}" title="${escHtml(v || "")}"><span class="rt-v">${escHtml(v || "—")}</span></td>`;
  }).join("");
  return `<div class="merge-row-preview-inline">
    <div class="preview-label">${label}</div>
    <div class="merge-row-table">
      <table class="rt"><thead><tr>${headers}</tr></thead><tbody><tr>${data}</tr></tbody></table>
    </div>
  </div>`;
}

function renderMergeCell(sheetName, row, col, cell) {
  const sk = sheetName.replace(/'/g, "\\'");
  const rk = String(row.row_key).replace(/'/g, "\\'");
  const isConflict = cell.status === "conflict";
  const isResolved = cell.resolved !== null && cell.resolved !== undefined;
  const statusLabel = CELL_STATUS_LABELS[cell.status] || cell.status;
  const header = cell.header || col;

  let resolvedDisplay = "";
  if (isResolved && (isConflict || cell.status === "auto_mine" || cell.status === "auto_theirs" || cell.status === "auto_both")) {
    let src = "";
    let srcCls = "";
    if (cell.resolved === cell.mine) { src = "本地"; srcCls = "src-mine"; }
    else if (cell.resolved === cell.theirs) { src = "远程"; srcCls = "src-theirs"; }
    else if (cell.resolved === cell.base) { src = "原始"; srcCls = "src-base"; }
    else { src = "自定义"; srcCls = "src-custom"; }
    resolvedDisplay = `<span class="cell-arrow">→</span><span class="cell-resolved ${srcCls}"><strong>${escHtml(cell.resolved || "（空）")}</strong><span class="src">${src}</span></span>`;
  }

  let btns = "";
  if (isConflict) {
    const sel = (choice) => {
      let v = "";
      if (choice === "mine") v = cell.mine;
      else if (choice === "theirs") v = cell.theirs;
      else if (choice === "base") v = cell.base;
      return cell.resolved === v ? " selected" : "";
    };
    const customSel = (cell.resolved !== null && cell.resolved !== cell.mine && cell.resolved !== cell.theirs && cell.resolved !== cell.base) ? " selected" : "";
    btns = `<div class="merge-resolve-btns">
      <button class="btn-mine${sel("mine")}" onclick="setCellChoice('${sk}','${rk}','${col}','mine')" title="保留本地值">保留我的</button>
      <button class="btn-theirs${sel("theirs")}" onclick="setCellChoice('${sk}','${rk}','${col}','theirs')" title="使用远程值">用远程</button>
      <button class="btn-custom${customSel}" onclick="setCellChoice('${sk}','${rk}','${col}','custom')" title="输入自定义值">自定义</button>
    </div>`;
  }

  const cls = ["merge-cell"];
  if (cell.status === "conflict") cls.push("conflict");
  if (cell.status === "auto_mine") cls.push("auto-mine");
  if (cell.status === "auto_theirs") cls.push("auto-theirs");
  if (cell.status === "auto_both") cls.push("auto-both");
  if (isResolved && cell.status === "conflict") cls.push("resolved");

  // 紧凑布局：标题行 + 三方对比内联 + 决议/按钮
  return `<div class="${cls.join(" ")}">
    <div class="merge-cell-header">
      <span class="col-name">${escHtml(header)}</span>
      <span class="col-letter">${col}</span>
      <span class="cell-status">${statusLabel}</span>
      ${resolvedDisplay}
    </div>
    <div class="merge-cell-sides">
      <div class="side base"><span class="side-label">BASE</span><span class="side-value">${escHtml(cell.base || "—")}</span></div>
      <div class="side mine ${cell.mine !== cell.base ? "changed" : ""}"><span class="side-label">本地</span><span class="side-value">${escHtml(cell.mine || "—")}</span></div>
      <div class="side theirs ${cell.theirs !== cell.base ? "changed" : ""}"><span class="side-label">远程</span><span class="side-value">${escHtml(cell.theirs || "—")}</span></div>
    </div>
    ${btns}
  </div>`;
}

function openMergeFromConflict(fname) {
  closeUpdateModal();
  state.mergeFromSvnConflict = true;
  setMode("merge");
  selectFile(fname);
}

// ── Event bindings ──

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".mode-tab").forEach(t => {
    t.addEventListener("click", () => setMode(t.dataset.mode));
  });

  document.getElementById("searchInput").addEventListener("input", (e) => {
    state.filterText = e.target.value;
    renderFileList();
  });

  document.getElementById("filterModified").addEventListener("click", (e) => {
    state.showOnlyModified = !state.showOnlyModified;
    e.target.classList.toggle("active", state.showOnlyModified);
    renderFileList();
  });

  document.getElementById("workspaceSelect").addEventListener("change", (e) => {
    switchWorkspace(parseInt(e.target.value));
  });

  document.getElementById("wsAddBtn").addEventListener("click", addWorkspace);
  document.getElementById("wsRemoveBtn").addEventListener("click", removeWorkspace);
  document.getElementById("wsOpenBtn").addEventListener("click", openWorkspaceDir);

  init();

  let _refreshCycle = 0;
  setInterval(async () => {
    _refreshCycle++;
    if (_refreshCycle % 4 === 0 && state.config && state.config.svn_available && !state.loading) {
      loadModifiedFiles();
    }
    if (_refreshCycle % 10 === 0 && state.config && state.config.svn_available && !state.loading) {
      loadModifiedClassify();
    }
    if (!state.selectedFile || state.loading) return;
    if (state.mode !== "local" && state.mode !== "browse") return;
    try {
      const data = await fetch(`${API}/api/file-mtime?file=${encodeURIComponent(state.selectedFile)}`).then(r => r.json());
      const mtime = data.mtime || 0;
      if (_lastMtime && mtime && mtime !== _lastMtime) {
        if (state.mode === "local") doDiffLocal();
        else if (state.mode === "browse") doBrowse();
        loadFiles();
        loadModifiedFiles();
      }
      _lastMtime = mtime;
    } catch (_) {}
  }, 3000);
});
