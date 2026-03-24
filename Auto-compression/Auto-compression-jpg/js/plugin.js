'use strict';

const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const fsp = fs.promises;

const PLUGIN_ID = 'auto-compression-jpg';
const DEFAULT_APP_PATH = '/Applications/图压.app';
const DEFAULT_INTERVAL_MINUTES = 5;
const FILE_STABILITY_DELAY_MS = 400;
const MANUAL_CONFIRMATION_DELAY_MS = 1200;
const MANUAL_CONFIRMATION_MAX_ATTEMPTS = 5;
const WRITE_RETRY_DELAY_MS = 5000;
const TAG_RETRY_DELAY_MS = 15000;
const OPEN_RETRY_DELAY_MS = 30000;
const WAITING_FOR_WRITE_REASON = 'waiting_for_write';

const DEFAULT_STATE = {
  pendingItems: {},
  lastIssue: null,
  repairStats: {
    date: null,
    healedCount: 0,
    lastIssue: null
  }
};

let timerId = null;
let config = {
  enabled: false,
  intervalMinutes: DEFAULT_INTERVAL_MINUTES,
  appPath: DEFAULT_APP_PATH
};
let state = normalizeState(DEFAULT_STATE);
let lastRunTime = null;
let nextRunTime = null;
let countdownId = null;
let selectedCountWatcherId = null;
let selectedCountRefreshInFlight = false;
let pendingSelectedCountRefresh = false;
let compressionJobInProgress = false;
let pendingValidationTimerId = null;
let pendingValidationRunInProgress = false;

let cachedStorageDir = null;

function getStorageDir() {
  if (cachedStorageDir) return cachedStorageDir;
  try {
    const userData = eagle.app.userDataPath || process.env.HOME + '/Library/Application Support/Eagle';
    cachedStorageDir = path.join(userData, 'plugins', PLUGIN_ID);
  } catch (err) {
    cachedStorageDir = path.join(process.env.HOME, 'Library/Application Support/Eagle/plugins', PLUGIN_ID);
  }
  return cachedStorageDir;
}

function getConfigPath() {
  return path.join(getStorageDir(), 'config.json');
}

function getProcessedPath() {
  return path.join(getStorageDir(), 'processed.json');
}

function getStatePath() {
  return path.join(getStorageDir(), 'state.json');
}

function ensureStorageDir() {
  const dir = getStorageDir();
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  return dir;
}

function normalizePendingItem(raw, itemId) {
  if (!raw || typeof raw !== 'object') return null;
  return {
    itemId: String(raw.itemId || itemId || '').trim(),
    itemName: String(raw.itemName || '').trim(),
    filePath: String(raw.filePath || '').trim(),
    snapshot: raw.snapshot && typeof raw.snapshot === 'object' ? raw.snapshot : null,
    attempts: Number.isFinite(raw.attempts) ? raw.attempts : 0,
    nextRetryAt: raw.nextRetryAt || null,
    lastReason: String(raw.lastReason || '').trim(),
    openedAt: raw.openedAt || null,
    status: String(raw.status || 'pending').trim() || 'pending',
    updatedAt: raw.updatedAt || null
  };
}

function normalizeState(raw) {
  const merged = {
    ...DEFAULT_STATE,
    ...(raw && typeof raw === 'object' ? raw : {})
  };
  const pendingItems = {};
  Object.entries(merged.pendingItems || {}).forEach(([itemId, entry]) => {
    const normalized = normalizePendingItem(entry, itemId);
    if (normalized && normalized.itemId) {
      pendingItems[normalized.itemId] = normalized;
    }
  });

  const lastIssue = merged.lastIssue && typeof merged.lastIssue === 'object'
    ? {
        at: merged.lastIssue.at || null,
        itemId: merged.lastIssue.itemId || null,
        itemName: merged.lastIssue.itemName || '',
        message: String(merged.lastIssue.message || '').trim()
      }
    : null;

  const repairStatsRaw = merged.repairStats && typeof merged.repairStats === 'object'
    ? merged.repairStats
    : {};

  const repairLastIssue = repairStatsRaw.lastIssue && typeof repairStatsRaw.lastIssue === 'object'
    ? {
        at: repairStatsRaw.lastIssue.at || null,
        itemId: repairStatsRaw.lastIssue.itemId || null,
        itemName: repairStatsRaw.lastIssue.itemName || '',
        message: String(repairStatsRaw.lastIssue.message || '').trim()
      }
    : null;

  const repairStats = {
    date: repairStatsRaw.date || null,
    healedCount: Number.isFinite(repairStatsRaw.healedCount) ? repairStatsRaw.healedCount : 0,
    lastIssue: repairLastIssue && repairLastIssue.message ? repairLastIssue : null
  };

  return {
    pendingItems,
    lastIssue: lastIssue && lastIssue.message ? lastIssue : null,
    repairStats
  };
}

function loadConfig() {
  try {
    ensureStorageDir();
    const configPath = getConfigPath();
    if (fs.existsSync(configPath)) {
      const data = JSON.parse(fs.readFileSync(configPath, 'utf8'));
      config = { ...config, ...data };
    }
  } catch (err) {
    console.warn('[Auto-compression] Failed to load config:', err);
  }
  return config;
}

function saveConfig() {
  try {
    ensureStorageDir();
    fs.writeFileSync(getConfigPath(), JSON.stringify(config, null, 2), 'utf8');
  } catch (err) {
    console.error('[Auto-compression] Failed to save config:', err);
  }
}

function loadProcessed() {
  try {
    const processedPath = getProcessedPath();
    if (fs.existsSync(processedPath)) {
      const data = JSON.parse(fs.readFileSync(processedPath, 'utf8'));
      const today = getTodayStr();
      if (data.lastDate === today) {
        return new Set(data.processedIds || []);
      }
    }
  } catch (err) {
    console.warn('[Auto-compression] Failed to load processed:', err);
  }
  return new Set();
}

function saveProcessed(processedIds) {
  try {
    ensureStorageDir();
    const processedPath = getProcessedPath();
    const data = {
      lastDate: getTodayStr(),
      processedIds: Array.from(processedIds)
    };
    fs.writeFileSync(processedPath, JSON.stringify(data, null, 2), 'utf8');
  } catch (err) {
    console.error('[Auto-compression] Failed to save processed:', err);
  }
}

function loadState() {
  try {
    ensureStorageDir();
    const statePath = getStatePath();
    if (fs.existsSync(statePath)) {
      state = normalizeState(JSON.parse(fs.readFileSync(statePath, 'utf8')));
    } else {
      state = normalizeState(DEFAULT_STATE);
    }
  } catch (err) {
    console.warn('[Auto-compression] Failed to load state:', err);
    state = normalizeState(DEFAULT_STATE);
  }
  return state;
}

function saveState() {
  try {
    ensureStorageDir();
    fs.writeFileSync(getStatePath(), JSON.stringify(state, null, 2), 'utf8');
  } catch (err) {
    console.error('[Auto-compression] Failed to save state:', err);
  }
}

function getTodayStr() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

function isToday(timestamp) {
  if (!timestamp) return false;
  const ts = typeof timestamp === 'number' ? timestamp : parseInt(timestamp, 10);
  const itemDate = new Date(ts);
  const today = new Date();
  return itemDate.getFullYear() === today.getFullYear() &&
    itemDate.getMonth() === today.getMonth() &&
    itemDate.getDate() === today.getDate();
}

function wait(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function getMimeTypeForPath(filePath) {
  const ext = String(path.extname(filePath || '')).toLowerCase().replace(/^\./, '');
  if (ext === 'jpg' || ext === 'jpeg') return 'image/jpeg';
  if (ext === 'png') return 'image/png';
  if (ext === 'webp') return 'image/webp';
  if (ext === 'gif') return 'image/gif';
  if (ext === 'avif') return 'image/avif';
  return 'application/octet-stream';
}

function getHealthReasonMessage(reason) {
  switch (reason) {
    case 'file_missing':
      return '原图文件不存在';
    case 'file_not_readable':
      return '原图文件暂时不可读';
    case 'file_not_stable':
      return '文件仍在同步或写入中，稍后自动重试';
    case 'decode_failed':
      return '图片暂时无法解码';
    case 'invalid_dimensions':
      return '图片尺寸异常（<= 1x1）';
    case 'open_failed':
      return '无法打开图压应用';
    case WAITING_FOR_WRITE_REASON:
      return '等待图压写回文件，稍后自动重试';
    case 'item_missing':
      return '素材已不存在';
    case 'tag_failed':
      return '写入压缩标签失败';
    default:
      return reason || '等待重试';
  }
}

function createFileSnapshot(stats, width, height) {
  return {
    size: stats.size,
    mtimeMs: Math.round(stats.mtimeMs),
    width,
    height
  };
}

function areSnapshotsEqual(a, b) {
  if (!a || !b) return false;
  return Number(a.size) === Number(b.size) &&
    Math.round(Number(a.mtimeMs || 0)) === Math.round(Number(b.mtimeMs || 0));
}

function hasFileWriteAfterOpen(entry, snapshot) {
  if (!entry || !entry.openedAt || !snapshot || !Number.isFinite(Number(snapshot.mtimeMs))) {
    return false;
  }
  const openedAtMs = new Date(entry.openedAt).getTime();
  if (!Number.isFinite(openedAtMs)) return false;
  return Number(snapshot.mtimeMs) > openedAtMs + 250;
}

function hasPendingValidation(itemId) {
  return Boolean(state.pendingItems && state.pendingItems[itemId]);
}

function getPendingCount() {
  return Object.keys(state.pendingItems || {}).length;
}

function getPendingCountForIds(itemIds) {
  if (!itemIds) return getPendingCount();
  const idSet = itemIds instanceof Set ? itemIds : new Set(itemIds);
  return Object.values(state.pendingItems || {}).filter(entry => idSet.has(entry.itemId)).length;
}

function getRetryDelayMs(reason = '') {
  switch (reason) {
    case WAITING_FOR_WRITE_REASON:
    case 'file_not_stable':
      return WRITE_RETRY_DELAY_MS;
    case 'tag_failed':
      return TAG_RETRY_DELAY_MS;
    case 'open_failed':
      return OPEN_RETRY_DELAY_MS;
    default:
      return Math.max(60000, config.intervalMinutes * 60 * 1000);
  }
}

function setLastIssue(message, item) {
  state.lastIssue = {
    at: new Date().toISOString(),
    itemId: item && (item.id || item.itemId) ? (item.id || item.itemId) : null,
    itemName: item && (item.name || item.itemName) ? (item.name || item.itemName) : '',
    message: String(message || '').trim()
  };
  saveState();
}

function ensureRepairStatsForToday() {
  const today = getTodayStr();
  if (!state.repairStats || typeof state.repairStats !== 'object') {
    state.repairStats = {
      date: today,
      healedCount: 0,
      lastIssue: null
    };
    return;
  }

  if (state.repairStats.date !== today) {
    state.repairStats = {
      date: today,
      healedCount: 0,
      lastIssue: state.repairStats.lastIssue || null
    };
  } else if (!Number.isFinite(state.repairStats.healedCount)) {
    state.repairStats.healedCount = 0;
  }
}

function incrementRepairCount(count = 1) {
  ensureRepairStatsForToday();
  state.repairStats.healedCount += count;
  saveState();
}

function setRepairIssue(message, item) {
  ensureRepairStatsForToday();
  state.repairStats.lastIssue = {
    at: new Date().toISOString(),
    itemId: item && (item.id || item.itemId) ? (item.id || item.itemId) : null,
    itemName: item && (item.name || item.itemName) ? (item.name || item.itemName) : '',
    message: String(message || '').trim()
  };
  saveState();
}

function getTodayRepairCount() {
  ensureRepairStatsForToday();
  return state.repairStats.healedCount || 0;
}

function getNextPendingRetryDelay() {
  const entries = Object.values(state.pendingItems || {});
  if (!entries.length) return null;

  const now = Date.now();
  let minDelay = Infinity;
  for (const entry of entries) {
    if (!entry.nextRetryAt || entry.nextRetryAt <= now) {
      return 0;
    }
    minDelay = Math.min(minDelay, Math.max(0, entry.nextRetryAt - now));
  }
  return Number.isFinite(minDelay) ? minDelay : null;
}

function stopPendingValidationTimer() {
  if (pendingValidationTimerId) {
    clearTimeout(pendingValidationTimerId);
    pendingValidationTimerId = null;
  }
}

function schedulePendingValidationTimer(delayMs = null) {
  stopPendingValidationTimer();
  const nextDelay = delayMs === null ? getNextPendingRetryDelay() : delayMs;
  if (nextDelay === null) return;

  pendingValidationTimerId = setTimeout(() => {
    pendingValidationTimerId = null;
    runPendingValidationTask();
  }, Math.max(0, nextDelay));
}

function removePendingItem(itemId) {
  if (state.pendingItems[itemId]) {
    delete state.pendingItems[itemId];
    saveState();
  }
}

function rememberPendingItem(item, updates = {}) {
  const itemId = item && item.id ? item.id : updates.itemId;
  if (!itemId) return null;
  const existing = state.pendingItems[itemId] || {};
  const snapshot = Object.prototype.hasOwnProperty.call(updates, 'snapshot')
    ? updates.snapshot
    : (existing.snapshot || null);
  const pending = {
    itemId,
    itemName: item && item.name ? item.name : (updates.itemName || existing.itemName || itemId),
    filePath: item && item.filePath ? item.filePath : (updates.filePath || existing.filePath || ''),
    snapshot,
    attempts: Number.isFinite(updates.attempts) ? updates.attempts : (existing.attempts || 0),
    nextRetryAt: Object.prototype.hasOwnProperty.call(updates, 'nextRetryAt') ? updates.nextRetryAt : (existing.nextRetryAt || null),
    lastReason: Object.prototype.hasOwnProperty.call(updates, 'lastReason') ? updates.lastReason : (existing.lastReason || ''),
    openedAt: Object.prototype.hasOwnProperty.call(updates, 'openedAt') ? updates.openedAt : (existing.openedAt || null),
    status: updates.status || existing.status || 'pending',
    updatedAt: new Date().toISOString()
  };
  state.pendingItems[itemId] = pending;
  saveState();
  return pending;
}

function queuePendingRetry(item, reason, snapshot, existing, extraMessage, status = 'pending') {
  const attempts = (existing && existing.attempts ? existing.attempts : 0) + 1;
  const entry = rememberPendingItem(item, {
    snapshot: snapshot || (existing ? existing.snapshot : null),
    attempts,
    nextRetryAt: Date.now() + getRetryDelayMs(reason),
    lastReason: reason,
    status
  });
  const message = extraMessage ? `${getHealthReasonMessage(reason)}：${extraMessage}` : getHealthReasonMessage(reason);
  setLastIssue(message, item || entry);
  schedulePendingValidationTimer();
  return entry;
}

function beginCompressionJob(source) {
  if (compressionJobInProgress) {
    console.log(`[Auto-compression] Skip ${source}, another job is still running`);
    if (source !== 'auto') {
      eagle.notification.show('上一轮压缩尚未结束', 'info');
    }
    return false;
  }
  compressionJobInProgress = true;
  return true;
}

function endCompressionJob() {
  compressionJobInProgress = false;
}

function openWithApp(filePath, appPath) {
  return new Promise((resolve, reject) => {
    if (!eagle.app.isMac) {
      reject(new Error('macOS only'));
      return;
    }
    const quotedFile = filePath.replace(/'/g, "'\\''");
    const quotedApp = appPath.replace(/'/g, "'\\''");
    exec(`open -a '${quotedApp}' '${quotedFile}'`, err => {
      if (err) {
        console.error('[Auto-compression] open failed:', err);
        reject(err);
        return;
      }
      resolve();
    });
  });
}

const COMPRESSION_TAG = '已图压压缩';

async function updateItemViaHTTP(itemId, fields) {
  const payload = { id: itemId, ...fields };
  const response = await fetch('http://localhost:41595/api/item/update', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Eagle API error: ${response.status} ${response.statusText}`);
  }
  const result = await response.json();
  if (result.status !== 'success') {
    throw new Error(result.message || `Eagle API returned ${result.status}`);
  }
  return result.data;
}

async function addCompressionTag(itemOrId) {
  const item = typeof itemOrId === 'string'
    ? await eagle.item.getById(itemOrId)
    : itemOrId;
  if (!item) {
    throw new Error('素材不存在');
  }
  const currentTags = item.tags || [];
  if (currentTags.includes(COMPRESSION_TAG)) {
    console.log(`[Auto-compression] Tag already exists for ${item.id}`);
    return;
  }
  const newTags = [...currentTags, COMPRESSION_TAG];
  await updateItemViaHTTP(item.id, { tags: newTags });
  console.log(`[Auto-compression] ✓ Added tag to ${item.id}`);
}

function hasCompressionTag(item) {
  return Boolean(item && item.tags && item.tags.includes(COMPRESSION_TAG));
}

function isJpegItem(item) {
  const ext = String(item.ext || '').toLowerCase();
  return ext === 'jpg' || ext === 'jpeg';
}

function isWithinDays(timestamp, days) {
  if (!timestamp) return false;
  if (days === null) return true;

  const now = Date.now();
  const itemDate = new Date(timestamp).getTime();
  const dayMs = days * 24 * 60 * 60 * 1000;
  return (now - itemDate) <= dayMs;
}

async function inspectImageHealth(filePath) {
  try {
    await fsp.access(filePath, fs.constants.R_OK);
  } catch (err) {
    return {
      ok: false,
      reason: err && err.code === 'ENOENT' ? 'file_missing' : 'file_not_readable'
    };
  }

  let firstStat;
  let secondStat;
  try {
    firstStat = await fsp.stat(filePath);
    await wait(FILE_STABILITY_DELAY_MS);
    secondStat = await fsp.stat(filePath);
  } catch (err) {
    return {
      ok: false,
      reason: err && err.code === 'ENOENT' ? 'file_missing' : 'file_not_readable'
    };
  }

  if (!firstStat.isFile() || !secondStat.isFile()) {
    return { ok: false, reason: 'file_missing' };
  }

  if (firstStat.size <= 0 || secondStat.size <= 0 || !areSnapshotsEqual(firstStat, secondStat)) {
    return {
      ok: false,
      reason: 'file_not_stable',
      snapshot: createFileSnapshot(secondStat, null, null)
    };
  }

  let buffer;
  try {
    buffer = await fsp.readFile(filePath);
  } catch (err) {
    return { ok: false, reason: 'file_not_readable' };
  }

  const blob = new Blob([buffer], { type: getMimeTypeForPath(filePath) });
  let bitmap;
  try {
    bitmap = await createImageBitmap(blob);
  } catch (err) {
    return {
      ok: false,
      reason: 'decode_failed',
      snapshot: createFileSnapshot(secondStat, null, null)
    };
  }

  const width = bitmap.width;
  const height = bitmap.height;
  if (typeof bitmap.close === 'function') bitmap.close();

  if (width <= 1 || height <= 1) {
    return {
      ok: false,
      reason: 'invalid_dimensions',
      snapshot: createFileSnapshot(secondStat, width, height)
    };
  }

  return {
    ok: true,
    snapshot: createFileSnapshot(secondStat, width, height)
  };
}

async function getAllJpgItems() {
  const [jpgItems, jpegItems] = await Promise.all([
    eagle.item.get({ ext: 'jpg' }),
    eagle.item.get({ ext: 'jpeg' })
  ]);
  return [].concat(jpgItems || [], jpegItems || []);
}

async function refreshSelectedButtonCount() {
  const selectedBtn = document.getElementById('btnBatchSelected');
  if (!selectedBtn) return;

  if (selectedCountRefreshInFlight) {
    pendingSelectedCountRefresh = true;
    return;
  }

  selectedCountRefreshInFlight = true;
  try {
    let selectedCount = 0;
    try {
      loadState();
      const selectedItems = await eagle.item.getSelected();
      selectedCount = (selectedItems || []).filter(item => {
        if (!item || !item.filePath) return false;
        if (!isJpegItem(item)) return false;
        return !hasCompressionTag(item) && !hasPendingValidation(item.id);
      }).length;
    } catch (err) {
      console.warn('[Auto-compression] Failed to load selected items count:', err);
    }
    selectedBtn.textContent = `我选中的项目 (${selectedCount})`;
  } finally {
    selectedCountRefreshInFlight = false;
    if (pendingSelectedCountRefresh) {
      pendingSelectedCountRefresh = false;
      setTimeout(() => {
        refreshSelectedButtonCount();
      }, 0);
    }
  }
}

function startSelectedCountWatcher() {
  stopSelectedCountWatcher();
  refreshSelectedButtonCount();
  selectedCountWatcherId = setInterval(() => {
    refreshSelectedButtonCount();
  }, 2000);
}

function stopSelectedCountWatcher() {
  if (selectedCountWatcherId) {
    clearInterval(selectedCountWatcherId);
    selectedCountWatcherId = null;
  }
}

async function refreshBatchButtonCounts() {
  loadState();
  const items = await getAllJpgItems();
  const RANGES = [
    [7, 'btnBatch7'],
    [14, 'btnBatch14'],
    [30, 'btnBatch30'],
    [60, 'btnBatch60'],
    [90, 'btnBatch90'],
    [null, 'btnBatchAll']
  ];
  for (const [days, btnId] of RANGES) {
    const count = items.filter(item => {
      if (!item.filePath) return false;
      const ts = item.importedAt || item.modifiedAt;
      if (!ts) return false;
      return isWithinDays(ts, days) && !hasCompressionTag(item) && !hasPendingValidation(item.id);
    }).length;
    const btn = document.getElementById(btnId);
    if (btn) {
      const label = days === null ? '所有图片' : `最近 ${days} 天`;
      btn.textContent = `${label} (${count})`;
    }
  }
  await refreshSelectedButtonCount();
}

async function queueCompressionAttempt(item) {
  const existing = state.pendingItems[item.id] || null;
  const health = await inspectImageHealth(item.filePath);
  if (!health.ok) {
    queuePendingRetry(item, health.reason, health.snapshot || (existing && existing.snapshot) || null, existing, '', 'awaiting_open');
    return { status: 'retry', reason: health.reason };
  }

  try {
    await openWithApp(item.filePath, config.appPath);
  } catch (err) {
    queuePendingRetry(item, 'open_failed', health.snapshot, existing, err.message, 'awaiting_open');
    return { status: 'retry', reason: 'open_failed' };
  }

  const attempts = (existing && existing.attempts ? existing.attempts : 0) + 1;
  rememberPendingItem(item, {
    snapshot: health.snapshot,
    attempts,
    nextRetryAt: Date.now() + getRetryDelayMs(WAITING_FOR_WRITE_REASON),
    lastReason: WAITING_FOR_WRITE_REASON,
    openedAt: new Date().toISOString(),
    status: 'pending'
  });
  schedulePendingValidationTimer();
  return { status: 'queued' };
}

async function processPendingItems(processed, options = {}) {
  loadState();
  const itemIds = options.itemIds ? (options.itemIds instanceof Set ? options.itemIds : new Set(options.itemIds)) : null;
  const ignoreRetryAt = Boolean(options.ignoreRetryAt);
  const dueEntries = Object.values(state.pendingItems || {}).filter(entry => {
    if (itemIds && !itemIds.has(entry.itemId)) return false;
    return ignoreRetryAt || !entry.nextRetryAt || entry.nextRetryAt <= Date.now();
  });
  if (!dueEntries.length) {
    return {
      confirmed: 0,
      pending: getPendingCount(),
      targetedPending: getPendingCountForIds(itemIds)
    };
  }

  let confirmed = 0;
  for (const entry of dueEntries) {
    let item;
    try {
      item = await eagle.item.getById(entry.itemId);
    } catch (err) {
      item = null;
    }

    if (!item || !item.filePath) {
      removePendingItem(entry.itemId);
      setLastIssue(getHealthReasonMessage('item_missing'), entry);
      continue;
    }

    if (hasCompressionTag(item)) {
      processed.add(item.id);
      removePendingItem(item.id);
      confirmed += 1;
      continue;
    }

    if (entry.status === 'awaiting_open') {
      await queueCompressionAttempt(item);
      continue;
    }

    const health = await inspectImageHealth(item.filePath);
    if (!health.ok) {
      queuePendingRetry(item, health.reason, health.snapshot || entry.snapshot || null, entry);
      continue;
    }

    const fileWasWrittenAfterOpen = hasFileWriteAfterOpen(entry, health.snapshot);
    if (entry.snapshot && areSnapshotsEqual(entry.snapshot, health.snapshot) && !fileWasWrittenAfterOpen) {
      rememberPendingItem(item, {
        snapshot: entry.snapshot,
        attempts: (entry.attempts || 0) + 1,
        nextRetryAt: Date.now() + getRetryDelayMs(WAITING_FOR_WRITE_REASON),
        lastReason: WAITING_FOR_WRITE_REASON,
        openedAt: entry.openedAt || null,
        status: 'pending'
      });
      continue;
    }

    try {
      await addCompressionTag(item.id);
      processed.add(item.id);
      removePendingItem(item.id);
      confirmed += 1;
    } catch (err) {
      queuePendingRetry(item, 'tag_failed', health.snapshot, entry, err.message);
    }
  }

  if (confirmed > 0) {
    saveProcessed(processed);
  }
  schedulePendingValidationTimer();
  return {
    confirmed,
    pending: getPendingCount(),
    targetedPending: getPendingCountForIds(itemIds)
  };
}

async function healProcessedTagDrift(processed) {
  loadState();
  const processedIds = Array.from(processed || []);
  if (!processedIds.length) {
    return { healed: 0, failed: 0 };
  }

  let healed = 0;
  let failed = 0;
  for (const itemId of processedIds) {
    if (hasPendingValidation(itemId)) continue;

    let item;
    try {
      item = await eagle.item.getById(itemId);
    } catch (err) {
      item = null;
    }

    if (!item || !item.filePath) {
      failed += 1;
      setRepairIssue(getHealthReasonMessage('item_missing'), { itemId });
      continue;
    }

    if (hasCompressionTag(item)) continue;

    const health = await inspectImageHealth(item.filePath);
    if (!health.ok) {
      failed += 1;
      setRepairIssue(`漏标签自愈失败：${getHealthReasonMessage(health.reason)}`, item);
      continue;
    }

    try {
      await addCompressionTag(item.id);
      healed += 1;
      incrementRepairCount(1);
    } catch (err) {
      failed += 1;
      setRepairIssue(`漏标签自愈失败：${err.message}`, item);
    }
  }

  return { healed, failed };
}

async function confirmPendingItemsNow(itemIds) {
  const targets = Array.from(new Set((itemIds || []).filter(Boolean)));
  if (!targets.length) {
    return { confirmed: 0, pending: 0, totalPending: getPendingCount() };
  }

  const processed = loadProcessed();
  let totalConfirmed = 0;
  let pending = getPendingCountForIds(targets);

  for (let attempt = 0; attempt < MANUAL_CONFIRMATION_MAX_ATTEMPTS && pending > 0; attempt++) {
    if (attempt > 0) {
      await wait(MANUAL_CONFIRMATION_DELAY_MS);
    }
    const result = await processPendingItems(processed, {
      itemIds: targets,
      ignoreRetryAt: true
    });
    totalConfirmed += result.confirmed;
    pending = result.targetedPending;
  }

  schedulePendingValidationTimer();
  return {
    confirmed: totalConfirmed,
    pending,
    totalPending: getPendingCount()
  };
}

async function runPendingValidationTask() {
  if (pendingValidationRunInProgress) return;
  if (compressionJobInProgress) {
    schedulePendingValidationTimer(1000);
    return;
  }

  pendingValidationRunInProgress = true;
  try {
    const processed = loadProcessed();
    const result = await processPendingItems(processed);
    if (result.confirmed > 0) {
      console.log(`[Auto-compression] Confirmed ${result.confirmed} pending item(s)`);
    }
    updateStatusUI();
    await refreshBatchButtonCounts();
  } catch (err) {
    console.error('[Auto-compression] Pending validation error:', err);
    setLastIssue(err.message || '待验证检查失败');
  } finally {
    pendingValidationRunInProgress = false;
    schedulePendingValidationTimer();
  }
}

function summarizeQueueResult(summary, result) {
  if (result.status === 'queued') {
    summary.queued += 1;
    summary.queuedItemIds.push(result.itemId);
  } else if (result.status === 'retry') {
    summary.retry += 1;
  } else {
    summary.skipped += 1;
  }
  return summary;
}

async function queueCompressionItems(items, progressLabel) {
  loadState();
  const summary = { queued: 0, retry: 0, skipped: 0, queuedItemIds: [] };
  for (let i = 0; i < items.length; i++) {
    const result = await queueCompressionAttempt(items[i]);
    if (!result.itemId) result.itemId = items[i].id;
    summarizeQueueResult(summary, result);
    if ((i + 1) % 10 === 0) {
      console.log(`[Auto-compression] ${progressLabel}: ${i + 1}/${items.length}`);
    }
  }
  return summary;
}

function getManualSummaryMessage(summary) {
  const parts = [];
  if (summary.queued > 0) parts.push(`已提交 ${summary.queued} 个文件到图压`);
  if (summary.confirmed > 0) parts.push(`已确认打标 ${summary.confirmed} 个`);
  if (summary.retry > 0) parts.push(`待重试 ${summary.retry} 个`);
  if (summary.pendingAfterConfirm > 0) parts.push(`仍待验证 ${summary.pendingAfterConfirm} 个`);
  if (!parts.length) parts.push('没有新的文件被提交');
  if (summary.pendingAfterConfirm > 0 || summary.retry > 0) {
    parts.push('未打标前请勿手动同步');
  }
  parts.push(`当前待验证 ${summary.totalPending} 项`);
  return parts.join('，');
}

async function batchCompress(days) {
  if (!beginCompressionJob('manual-batch')) return;

  try {
    const daysLabel = days === null ? '所有' : `最近${days}天`;
    console.log(`[Auto-compression] Starting batch compression: ${daysLabel}`);

    const items = await getAllJpgItems();
    const filtered = items.filter(item => {
      if (!item.filePath) return false;
      const ts = item.importedAt || item.modifiedAt;
      if (!ts) return false;
      return isWithinDays(ts, days);
    });
    loadState();
    const toProcess = filtered.filter(item => !hasCompressionTag(item) && !hasPendingValidation(item.id));

    console.log(`[Auto-compression] Found ${filtered.length} items, ${toProcess.length} need processing`);

    if (toProcess.length === 0) {
      eagle.notification.show(`${daysLabel}没有需要压缩的图片`, 'info');
      return;
    }

    const confirmMsg = `找到 ${toProcess.length} 个${daysLabel}的 JPG 图片需要压缩，是否继续？`;
    const confirmed = confirm(confirmMsg);
    if (!confirmed) {
      console.log('[Auto-compression] Batch compression cancelled by user');
      return;
    }

    eagle.notification.show(`开始处理 ${toProcess.length} 个文件...`, 'info');
    const summary = await queueCompressionItems(toProcess, 'Batch progress');
    const confirmation = await confirmPendingItemsNow(summary.queuedItemIds);
    summary.confirmed = confirmation.confirmed;
    summary.pendingAfterConfirm = confirmation.pending;
    summary.totalPending = confirmation.totalPending;
    eagle.notification.show(
      getManualSummaryMessage(summary),
      summary.retry > 0 || summary.pendingAfterConfirm > 0 ? 'info' : 'success'
    );
    console.log(`[Auto-compression] Batch compression queued: ${JSON.stringify(summary)}`);
    updateStatusUI();
    await refreshBatchButtonCounts();
  } catch (err) {
    console.error('[Auto-compression] Batch compression error:', err);
    eagle.notification.show('批量压缩失败', 'error');
  } finally {
    endCompressionJob();
  }
}

async function batchCompressSelected() {
  if (!beginCompressionJob('manual-selected')) return;

  try {
    loadState();
    const selectedItems = await eagle.item.getSelected();
    const selectable = (selectedItems || []).filter(item => {
      if (!item || !item.filePath) return false;
      return isJpegItem(item);
    });
    const toProcess = selectable.filter(item => !hasCompressionTag(item) && !hasPendingValidation(item.id));

    if (selectable.length === 0) {
      eagle.notification.show('当前未选中可压缩的 JPG 图片', 'info');
      await refreshBatchButtonCounts();
      return;
    }

    if (toProcess.length === 0) {
      eagle.notification.show('选中图片均已压缩或正在等待验证', 'info');
      await refreshBatchButtonCounts();
      return;
    }

    const confirmed = confirm(`选中 ${selectable.length} 个 JPG 图片，其中 ${toProcess.length} 个需要压缩，是否继续？`);
    if (!confirmed) {
      console.log('[Auto-compression] Selected compression cancelled by user');
      return;
    }

    eagle.notification.show(`开始处理选中的 ${toProcess.length} 个文件...`, 'info');
    const summary = await queueCompressionItems(toProcess, 'Selected progress');
    const confirmation = await confirmPendingItemsNow(summary.queuedItemIds);
    summary.confirmed = confirmation.confirmed;
    summary.pendingAfterConfirm = confirmation.pending;
    summary.totalPending = confirmation.totalPending;
    eagle.notification.show(
      getManualSummaryMessage(summary),
      summary.retry > 0 || summary.pendingAfterConfirm > 0 ? 'info' : 'success'
    );
    console.log(`[Auto-compression] Selected compression queued: ${JSON.stringify(summary)}`);
    updateStatusUI();
    await refreshBatchButtonCounts();
  } catch (err) {
    console.error('[Auto-compression] Selected compression error:', err);
    eagle.notification.show('选中项压缩失败', 'error');
  } finally {
    endCompressionJob();
  }
}

async function runTask() {
  if (!config.enabled) {
    console.log('[Auto-compression] Task skipped: disabled');
    return;
  }
  if (!beginCompressionJob('auto')) return;

  try {
    console.log('[Auto-compression] Running task...');
    loadState();
    const processed = loadProcessed();

    const pendingResult = await processPendingItems(processed);
    const repairResult = await healProcessedTagDrift(processed);
    const items = await getAllJpgItems();
    console.log(`[Auto-compression] Found ${items.length} JPG/JPEG items in total`);

    const toProcess = [];
    for (const item of items) {
      if (!item.filePath) continue;
      const ts = item.importedAt || item.modifiedAt;
      if (!ts) continue;
      if (!isToday(ts)) continue;
      if (processed.has(item.id)) continue;
      if (hasCompressionTag(item)) continue;
      if (hasPendingValidation(item.id)) continue;
      toProcess.push(item);
    }

    console.log(`[Auto-compression] Found ${toProcess.length} new JPG/JPEG file(s) added today`);

    const summary = await queueCompressionItems(toProcess, 'Auto progress');
    if (summary.queued > 0) {
      console.log(`[Auto-compression] Queued ${summary.queued} file(s) for 图压`);
    }

    lastRunTime = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    updateStatusUI();
    console.log(`[Auto-compression] Task completed (confirmed=${pendingResult.confirmed}, repaired=${repairResult.healed}, queued=${summary.queued}, retry=${summary.retry})`);
  } catch (err) {
    console.error('[Auto-compression] runTask error:', err);
    setLastIssue(err.message || '自动压缩执行失败');
  } finally {
    updateStatusUI();
    endCompressionJob();
  }
}

function getTodayProcessedCount() {
  try {
    const processedPath = getProcessedPath();
    if (fs.existsSync(processedPath)) {
      const data = JSON.parse(fs.readFileSync(processedPath, 'utf8'));
      if (data.lastDate === getTodayStr()) {
        return (data.processedIds || []).length;
      }
    }
  } catch (err) { /* ignore */ }
  return 0;
}

function formatIssue(issue) {
  if (!issue || !issue.message) return '—';
  const prefix = issue.at ? new Date(issue.at).toLocaleTimeString('zh-CN', { hour12: false }) : '';
  const itemName = issue.itemName ? `${issue.itemName} · ` : '';
  return [prefix, `${itemName}${issue.message}`].filter(Boolean).join(' · ');
}

function formatRepairIssue(issue) {
  if (!issue || !issue.message) return '—';
  const prefix = issue.at ? new Date(issue.at).toLocaleTimeString('zh-CN', { hour12: false }) : '';
  const itemName = issue.itemName ? `${issue.itemName} · ` : '';
  return [prefix, `${itemName}${issue.message}`].filter(Boolean).join(' · ');
}

function updateStatusUI() {
  const lastEl = document.getElementById('statusLastRun');
  const countEl = document.getElementById('statusProcessedCount');
  const repairedEl = document.getElementById('statusRepairedCount');
  const pendingEl = document.getElementById('statusPendingCount');
  const issueEl = document.getElementById('statusLastIssue');
  const repairIssueEl = document.getElementById('statusLastRepairIssue');
  ensureRepairStatsForToday();
  if (lastEl) lastEl.textContent = lastRunTime || '—';
  if (countEl) countEl.textContent = String(getTodayProcessedCount());
  if (repairedEl) repairedEl.textContent = String(getTodayRepairCount());
  if (pendingEl) pendingEl.textContent = String(getPendingCount());
  if (issueEl) issueEl.textContent = formatIssue(state.lastIssue);
  if (repairIssueEl) repairIssueEl.textContent = formatRepairIssue(state.repairStats.lastIssue);
}

function formatCountdown(ms) {
  if (ms <= 0) return '即将运行…';
  const totalSec = Math.ceil(ms / 1000);
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  return `${String(min).padStart(2, '0')} 分 ${String(sec).padStart(2, '0')} 秒`;
}

function updateCountdownUI() {
  const el = document.getElementById('statusCountdown');
  if (!el) return;
  if (!config.enabled) {
    el.textContent = '已暂停';
    return;
  }
  if (!nextRunTime) {
    el.textContent = '—';
    return;
  }
  el.textContent = formatCountdown(nextRunTime - Date.now());
}

function startCountdown() {
  stopCountdown();
  updateCountdownUI();
  countdownId = setInterval(updateCountdownUI, 1000);
}

function stopCountdown() {
  if (countdownId) {
    clearInterval(countdownId);
    countdownId = null;
  }
}

function startTimer() {
  stopTimer();
  if (!config.enabled) {
    nextRunTime = null;
    updateCountdownUI();
    return;
  }
  const intervalMs = Math.max(60000, config.intervalMinutes * 60 * 1000);
  nextRunTime = Date.now() + intervalMs;
  runTask();
  timerId = setInterval(() => {
    nextRunTime = Date.now() + intervalMs;
    runTask();
  }, intervalMs);
  console.log(`[Auto-compression] Timer started, interval: ${config.intervalMinutes} min`);
}

function stopTimer() {
  if (timerId) {
    clearInterval(timerId);
    timerId = null;
  }
}

function applySettingsFromUI() {
  const enabledEl = document.getElementById('settingEnabled');
  const intervalEl = document.getElementById('settingInterval');
  const appPathEl = document.getElementById('settingAppPath');
  if (enabledEl) config.enabled = enabledEl.checked;
  if (intervalEl) {
    const val = parseInt(intervalEl.value, 10);
    config.intervalMinutes = isNaN(val) ? DEFAULT_INTERVAL_MINUTES : Math.max(1, Math.min(60, val));
  }
  if (appPathEl) config.appPath = appPathEl.value.trim() || DEFAULT_APP_PATH;
  saveConfig();
  startTimer();
}

function bindUI() {
  const enabledEl = document.getElementById('settingEnabled');
  const intervalEl = document.getElementById('settingInterval');
  const appPathEl = document.getElementById('settingAppPath');
  const saveBtn = document.getElementById('btnSave');

  if (enabledEl) enabledEl.checked = config.enabled;
  if (intervalEl) intervalEl.value = config.intervalMinutes;
  if (appPathEl) appPathEl.value = config.appPath;

  if (saveBtn) {
    saveBtn.onclick = () => {
      applySettingsFromUI();
      if (typeof eagle !== 'undefined' && eagle.notification) {
        eagle.notification.show('设置已保存', 'success');
      }
    };
  }

  updateStatusUI();
  refreshBatchButtonCounts();
}

eagle.onPluginCreate(async () => {
  console.log('[Auto-compression] Plugin created');
  setTimeout(() => {
    loadConfig();
    loadState();
    startTimer();
    schedulePendingValidationTimer();
  }, 1000);
});

eagle.onPluginRun(() => {
  console.log('[Auto-compression] Plugin run');
});

eagle.onPluginShow(() => {
  console.log('[Auto-compression] Plugin show');
  loadConfig();
  loadState();
  bindUI();
  startSelectedCountWatcher();
  startCountdown();
  schedulePendingValidationTimer();
});

eagle.onPluginHide(() => {
  console.log('[Auto-compression] Plugin hide');
  stopSelectedCountWatcher();
  stopCountdown();
});

eagle.onLibraryChanged && eagle.onLibraryChanged(() => {
  loadProcessed();
  loadState();
  updateStatusUI();
  refreshBatchButtonCounts();
  schedulePendingValidationTimer();
});
