'use strict';

const fs = require('fs');
const path = require('path');

const fsp = fs.promises;

const PLUGIN_ID = 'uibook-sync';
const MAX_LOGS = 500;
const LOG_BATCH_SIZE = 100;
const DEFAULT_TIMEOUT_MS = 60000;
const DEFAULT_COOLDOWN_MS = 60 * 60 * 1000;
const DEFAULT_ENDPOINT = 'https://iefgqzcdpuvsjhwtxsyz.supabase.co/functions/v1/eagle-sync';
const FILE_STABILITY_DELAY_MS = 400;
const INFLIGHT_TTL_MS = 15 * 60 * 1000;

const DEFAULT_CONFIG = {
    endpointUrl: DEFAULT_ENDPOINT,
    syncSecret: '',
    autoEnabled: false,
    intervalMinutes: 5,
    manualAllowedExts: ['jpg', 'jpeg', 'png', 'webp', 'gif', 'avif'],
    autoAllowedExts: ['jpg', 'jpeg'],
    requireUrl: true,
    requiredTags: ['已图压压缩'],
    successTag: '已同步UIBook',
    entityRules: {
        sectionTags: [],
        sectionFolders: ['section', 'sections'],
        websiteTags: [],
        websiteFolders: ['page', 'website', 'websites']
    }
};

const DEFAULT_STATE = {
    logs: [],
    cooldowns: {},
    lastAutoScanAt: null,
    inflightItems: {},
    syncedItems: {}
};

let config = normalizeConfig(DEFAULT_CONFIG);
let state = normalizeState(DEFAULT_STATE);
let autoTimerId = null;
let countdownId = null;
let selectedWatcherId = null;
let nextAutoRunAt = null;
let cachedStorageDir = null;
let syncBatchInProgress = false;
let autoRunInProgress = false;
let uiVisible = false;
let logSearchTerm = '';
let logVisibleCount = LOG_BATCH_SIZE;
let folderCache = {
    loadedAt: 0,
    data: {}
};

function normalizeList(value, fallback) {
    if (Array.isArray(value)) {
        return value
            .map(item => String(item || '').trim())
            .filter(Boolean);
    }
    if (typeof value === 'string') {
        return value
            .split(/[,\n]/)
            .map(item => item.trim())
            .filter(Boolean);
    }
    return fallback.slice();
}

function normalizeConfig(raw) {
    const merged = {
        ...DEFAULT_CONFIG,
        ...raw,
        entityRules: {
            ...DEFAULT_CONFIG.entityRules,
            ...(raw && raw.entityRules ? raw.entityRules : {})
        }
    };

    return {
        endpointUrl: String(merged.endpointUrl || DEFAULT_ENDPOINT).trim() || DEFAULT_ENDPOINT,
        syncSecret: String(merged.syncSecret || '').trim(),
        autoEnabled: Boolean(merged.autoEnabled),
        intervalMinutes: clampNumber(merged.intervalMinutes, 1, 120, DEFAULT_CONFIG.intervalMinutes),
        manualAllowedExts: normalizeList(merged.manualAllowedExts, DEFAULT_CONFIG.manualAllowedExts).map(normalizeExt),
        autoAllowedExts: normalizeList(merged.autoAllowedExts, DEFAULT_CONFIG.autoAllowedExts).map(normalizeExt),
        requireUrl: Boolean(merged.requireUrl),
        requiredTags: normalizeList(merged.requiredTags, DEFAULT_CONFIG.requiredTags),
        successTag: String(merged.successTag || DEFAULT_CONFIG.successTag).trim() || DEFAULT_CONFIG.successTag,
        entityRules: {
            sectionTags: normalizeList(merged.entityRules.sectionTags, DEFAULT_CONFIG.entityRules.sectionTags),
            sectionFolders: normalizeList(merged.entityRules.sectionFolders, DEFAULT_CONFIG.entityRules.sectionFolders),
            websiteTags: normalizeList(merged.entityRules.websiteTags, DEFAULT_CONFIG.entityRules.websiteTags),
            websiteFolders: normalizeList(merged.entityRules.websiteFolders, DEFAULT_CONFIG.entityRules.websiteFolders)
        }
    };
}

function normalizeInflightItems(value) {
    if (!value || typeof value !== 'object') return {};
    const normalized = {};
    Object.entries(value).forEach(([itemId, entry]) => {
        if (!itemId || !entry || typeof entry !== 'object') return;
        normalized[itemId] = {
            startedAt: entry.startedAt || null,
            entityType: entry.entityType || null
        };
    });
    return normalized;
}

function normalizeSyncedItems(value) {
    if (!value || typeof value !== 'object') return {};
    const normalized = {};
    Object.entries(value).forEach(([itemId, entry]) => {
        if (!itemId || !entry || typeof entry !== 'object') return;
        normalized[itemId] = {
            remoteId: entry.remoteId || null,
            entityType: entry.entityType || null,
            syncedAt: entry.syncedAt || null
        };
    });
    return normalized;
}

function normalizeState(raw) {
    const merged = {
        ...DEFAULT_STATE,
        ...raw
    };

    return {
        logs: Array.isArray(merged.logs) ? merged.logs.slice(0, MAX_LOGS) : [],
        cooldowns: merged.cooldowns && typeof merged.cooldowns === 'object' ? merged.cooldowns : {},
        lastAutoScanAt: merged.lastAutoScanAt || null,
        inflightItems: normalizeInflightItems(merged.inflightItems),
        syncedItems: normalizeSyncedItems(merged.syncedItems)
    };
}

function clampNumber(value, min, max, fallback) {
    const parsed = parseInt(value, 10);
    if (Number.isNaN(parsed)) return fallback;
    return Math.min(max, Math.max(min, parsed));
}

function normalizeExt(value) {
    return String(value || '').trim().toLowerCase().replace(/^\./, '');
}

function getStorageDir() {
    if (cachedStorageDir) return cachedStorageDir;
    try {
        const userDataPath = eagle.app.userDataPath || path.join(process.env.HOME, 'Library/Application Support/Eagle');
        cachedStorageDir = path.join(userDataPath, 'plugins', PLUGIN_ID);
    } catch (error) {
        cachedStorageDir = path.join(process.env.HOME, 'Library/Application Support/Eagle/plugins', PLUGIN_ID);
    }
    return cachedStorageDir;
}

function ensureStorageDir() {
    const dir = getStorageDir();
    if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
    }
    return dir;
}

function getConfigPath() {
    return path.join(getStorageDir(), 'config.json');
}

function getStatePath() {
    return path.join(getStorageDir(), 'state.json');
}

function loadConfig() {
    try {
        ensureStorageDir();
        const configPath = getConfigPath();
        if (fs.existsSync(configPath)) {
            config = normalizeConfig(JSON.parse(fs.readFileSync(configPath, 'utf8')));
        } else {
            config = normalizeConfig(DEFAULT_CONFIG);
        }
    } catch (error) {
        console.error('[UIBook Sync] Failed to load config:', error);
        config = normalizeConfig(DEFAULT_CONFIG);
    }
    return config;
}

function saveConfig() {
    ensureStorageDir();
    fs.writeFileSync(getConfigPath(), JSON.stringify(config, null, 2), 'utf8');
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
    } catch (error) {
        console.error('[UIBook Sync] Failed to load state:', error);
        state = normalizeState(DEFAULT_STATE);
    }
    pruneCooldowns();
    pruneInflightItems();
    return state;
}

function saveState() {
    ensureStorageDir();
    pruneCooldowns();
    pruneInflightItems();
    fs.writeFileSync(getStatePath(), JSON.stringify(state, null, 2), 'utf8');
}

function pruneCooldowns() {
    const now = Date.now();
    Object.keys(state.cooldowns || {}).forEach(itemId => {
        const record = state.cooldowns[itemId];
        if (!record || !record.until || record.until <= now) {
            delete state.cooldowns[itemId];
        }
    });
}

function pruneInflightItems() {
    const now = Date.now();
    Object.keys(state.inflightItems || {}).forEach(itemId => {
        const record = state.inflightItems[itemId];
        const startedAt = record && record.startedAt ? new Date(record.startedAt).getTime() : NaN;
        if (!record || Number.isNaN(startedAt) || now - startedAt >= INFLIGHT_TTL_MS) {
            delete state.inflightItems[itemId];
        }
    });
}

function formatListForInput(values) {
    return (values || []).join(', ');
}

function parseListInput(value) {
    return String(value || '')
        .split(/[,\n]/)
        .map(item => item.trim())
        .filter(Boolean);
}

function formatDateTime(dateLike) {
    if (!dateLike) return '—';
    const date = new Date(dateLike);
    if (Number.isNaN(date.getTime())) return '—';
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

function formatTime(dateLike) {
    if (!dateLike) return '—';
    const date = new Date(dateLike);
    if (Number.isNaN(date.getTime())) return '—';
    return date.toLocaleTimeString('zh-CN', { hour12: false });
}

function formatCountdown(ms) {
    if (ms === null || ms === undefined) return '—';
    if (ms <= 0) return '即将开始';
    const totalSec = Math.ceil(ms / 1000);
    const min = Math.floor(totalSec / 60);
    const sec = totalSec % 60;
    return `${String(min).padStart(2, '0')} 分 ${String(sec).padStart(2, '0')} 秒`;
}

function isSameDay(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    return date.getFullYear() === now.getFullYear() &&
        date.getMonth() === now.getMonth() &&
        date.getDate() === now.getDate();
}

function cleanURL(url) {
    if (!url) return '';
    try {
        const urlObj = new URL(url);
        return urlObj.origin + urlObj.pathname + urlObj.hash;
    } catch (error) {
        return String(url).split('?')[0];
    }
}

function parseSyncAnnotationLine(line) {
    const trimmed = String(line || '').trim();
    if (!trimmed.startsWith('- 同步于 ') || !trimmed.includes('(uibook,')) return null;
    const match = trimmed.match(/\(uibook,\s*([^,]+),\s*([^,)]+)(?:,\s*sourceItemId=([^)]+))?\)$/);
    if (!match) return null;
    return {
        entityType: String(match[1] || '').trim() || null,
        remoteId: String(match[2] || '').trim() || null,
        sourceItemId: String(match[3] || '').trim() || null
    };
}

function getSyncAnnotationRecord(item) {
    const lines = String(item && item.annotation ? item.annotation : '')
        .split('\n')
        .map(line => parseSyncAnnotationLine(line))
        .filter(Boolean);
    if (!lines.length) return null;

    const exactMatch = lines.find(record => record.sourceItemId && record.sourceItemId === item.id);
    if (exactMatch) return exactMatch;

    const legacyMatch = lines.find(record => !record.sourceItemId);
    if (legacyMatch) {
        return {
            ...legacyMatch,
            sourceItemId: item.id
        };
    }

    return null;
}

function getInflightRecord(itemId) {
    pruneInflightItems();
    return state.inflightItems[itemId] || null;
}

function getSyncedRecord(itemId) {
    return state.syncedItems[itemId] || null;
}

function markItemInflight(itemId, entityType) {
    state.inflightItems[itemId] = {
        startedAt: new Date().toISOString(),
        entityType: entityType || null
    };
    saveState();
}

function clearItemInflight(itemId) {
    if (state.inflightItems[itemId]) {
        delete state.inflightItems[itemId];
        saveState();
    }
}

function rememberSyncedItem(item, remoteId, entityType, syncedAt) {
    state.syncedItems[item.id] = {
        remoteId: remoteId || null,
        entityType: entityType || null,
        syncedAt: syncedAt || new Date().toISOString()
    };
    if (state.inflightItems[item.id]) {
        delete state.inflightItems[item.id];
    }
    saveState();
}

function maybeBackfillSyncedItem(item) {
    if (!item || !item.id) return false;
    if (getSyncedRecord(item.id)) return false;

    const annotationRecord = getSyncAnnotationRecord(item);
    if (annotationRecord) {
        rememberSyncedItem(item, annotationRecord.remoteId, annotationRecord.entityType, new Date().toISOString());
        return true;
    }

    if (itemHasTag(item, config.successTag)) {
        rememberSyncedItem(item, null, null, new Date().toISOString());
        return true;
    }

    return false;
}

function backfillSyncedItems(items) {
    let changed = false;
    (items || []).forEach(item => {
        changed = maybeBackfillSyncedItem(item) || changed;
    });
    return changed;
}

function escapeHtml(value) {
    return String(value || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function toggleCheckbox(id) {
    const checkbox = document.getElementById(id);
    if (!checkbox) return;
    checkbox.checked = !checkbox.checked;
    if (typeof event !== 'undefined' && event) {
        event.stopPropagation();
    }
}

function showToast(message, type) {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = message;
    toast.className = `toast ${type || 'success'} show`;
    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

function setButtonLoading(buttonId, loading, label) {
    const button = document.getElementById(buttonId);
    if (!button) return;
    button.disabled = loading;
    if (loading) {
        button.innerHTML = `<span class="loading"></span> ${escapeHtml(label || '处理中...')}`;
    } else {
        button.textContent = label || button.textContent;
    }
}

function updateUiFromConfig() {
    const endpointEl = document.getElementById('endpointUrl');
    const secretEl = document.getElementById('syncSecret');
    const autoEl = document.getElementById('autoEnabled');
    const intervalEl = document.getElementById('intervalMinutes');
    const requireUrlEl = document.getElementById('requireUrl');
    const requiredTagsEl = document.getElementById('requiredTags');
    const successTagEl = document.getElementById('successTag');
    const manualExtsEl = document.getElementById('manualAllowedExts');
    const autoExtsEl = document.getElementById('autoAllowedExts');
    const sectionTagsEl = document.getElementById('sectionTags');
    const sectionFoldersEl = document.getElementById('sectionFolders');
    const websiteTagsEl = document.getElementById('websiteTags');
    const websiteFoldersEl = document.getElementById('websiteFolders');

    if (endpointEl) endpointEl.value = config.endpointUrl;
    if (secretEl) secretEl.value = config.syncSecret;
    if (autoEl) autoEl.checked = config.autoEnabled;
    if (intervalEl) intervalEl.value = config.intervalMinutes;
    if (requireUrlEl) requireUrlEl.checked = config.requireUrl;
    if (requiredTagsEl) requiredTagsEl.value = formatListForInput(config.requiredTags);
    if (successTagEl) successTagEl.value = config.successTag;
    if (manualExtsEl) manualExtsEl.value = formatListForInput(config.manualAllowedExts);
    if (autoExtsEl) autoExtsEl.value = formatListForInput(config.autoAllowedExts);
    if (sectionTagsEl) sectionTagsEl.value = formatListForInput(config.entityRules.sectionTags);
    if (sectionFoldersEl) sectionFoldersEl.value = formatListForInput(config.entityRules.sectionFolders);
    if (websiteTagsEl) websiteTagsEl.value = formatListForInput(config.entityRules.websiteTags);
    if (websiteFoldersEl) websiteFoldersEl.value = formatListForInput(config.entityRules.websiteFolders);
}

function updateConfigFromUi() {
    config = normalizeConfig({
        endpointUrl: document.getElementById('endpointUrl').value,
        syncSecret: document.getElementById('syncSecret').value,
        autoEnabled: document.getElementById('autoEnabled').checked,
        intervalMinutes: document.getElementById('intervalMinutes').value,
        requireUrl: document.getElementById('requireUrl').checked,
        requiredTags: parseListInput(document.getElementById('requiredTags').value),
        successTag: document.getElementById('successTag').value,
        manualAllowedExts: parseListInput(document.getElementById('manualAllowedExts').value),
        autoAllowedExts: parseListInput(document.getElementById('autoAllowedExts').value),
        entityRules: {
            sectionTags: parseListInput(document.getElementById('sectionTags').value),
            sectionFolders: parseListInput(document.getElementById('sectionFolders').value),
            websiteTags: parseListInput(document.getElementById('websiteTags').value),
            websiteFolders: parseListInput(document.getElementById('websiteFolders').value)
        }
    });
}

function renderStatusSummary() {
    const todayLogs = state.logs.filter(entry => entry && entry.at && isSameDay(entry.at));
    const successCount = todayLogs.filter(entry => entry.status === 'success').length;
    const skippedCount = todayLogs.filter(entry => entry.status === 'skipped' || entry.status === 'duplicate').length;
    const errorCount = todayLogs.filter(entry => entry.status === 'error').length;

    setText('statusAutoEnabled', config.autoEnabled ? '开启' : '关闭');
    setText('statusNextRun', config.autoEnabled ? formatCountdown(nextAutoRunAt ? nextAutoRunAt - Date.now() : null) : '已暂停');
    setText('statusSuccessCount', String(successCount));
    setText('statusSkippedCount', String(skippedCount));
    setText('statusErrorCount', String(errorCount));
    setText('statusLastAutoScan', state.lastAutoScanAt ? formatDateTime(state.lastAutoScanAt) : '—');
}

function renderSelectionInfo(selectedCount) {
    const message = selectedCount > 0
        ? `当前已选 ${selectedCount} 项。自动同步默认关闭，建议只在家里的常开主设备启用。`
        : '自动同步默认关闭。建议只在常开主设备启用，其他 iCloud 设备保留手动同步。';
    setText('selectionInfoText', message);
}

function getLogSearchText(entry) {
    return [
        entry.itemName,
        entry.message,
        entry.itemId,
        entry.remoteId
    ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
}

function getFilteredLogs() {
    if (!logSearchTerm) return state.logs;
    return state.logs.filter(entry => getLogSearchText(entry).includes(logSearchTerm));
}

function getLogTitle(entry) {
    if (entry.itemName) return entry.itemName;
    if (entry.title) return entry.title;
    if (entry.mode === 'auto' && entry.message && entry.message.startsWith('自动扫描完成')) {
        return '自动扫描汇总';
    }
    if (entry.mode === 'auto' && entry.message && entry.message.startsWith('自动扫描')) {
        return '自动扫描';
    }
    if (entry.mode === 'manual' && entry.message && entry.message.includes('上一轮同步尚未结束')) {
        return '手动同步提示';
    }
    if (entry.status === 'info') {
        return '系统消息';
    }
    return entry.itemId || '系统消息';
}

function renderLoadMore(totalCount, shownCount) {
    const container = document.getElementById('activityLoadMore');
    if (!container) return;
    if (shownCount >= totalCount) {
        container.innerHTML = '';
        return;
    }

    container.innerHTML = `<button type="button" class="lg-secondary" id="loadMoreLogsButton">加载更多 (${shownCount}/${totalCount})</button>`;
    const button = document.getElementById('loadMoreLogsButton');
    if (button) {
        button.onclick = () => {
            logVisibleCount += LOG_BATCH_SIZE;
            renderLogs();
        };
    }
}

function renderLogs() {
    const container = document.getElementById('activityList');
    if (!container) return;
    const filteredLogs = getFilteredLogs();
    if (!state.logs.length) {
        container.innerHTML = '<div class="empty-state">暂无同步记录。手动或自动同步后，这里会显示最近活动。</div>';
        renderLoadMore(0, 0);
        return;
    }
    if (!filteredLogs.length) {
        container.innerHTML = '<div class="empty-state">无匹配记录。试试素材名、失败原因或远端 ID。</div>';
        renderLoadMore(0, 0);
        return;
    }

    const visibleLogs = filteredLogs.slice(0, logVisibleCount);
    container.innerHTML = visibleLogs.map(entry => {
        const message = entry.remoteId
            ? `${entry.message || ''}${entry.message ? ' · ' : ''}${entry.remoteId}`
            : (entry.message || '—');
        const modeLabel = entry.mode === 'auto' ? '自动' : '手动';
        const statusClass = ['success', 'duplicate', 'skipped', 'error'].includes(entry.status) ? entry.status : 'info';
        const title = getLogTitle(entry);
        const meta = `${formatDateTime(entry.at)} · ${modeLabel}${entry.entityType ? ` · ${entry.entityType}` : ''}`;
        return `
            <div class="activity-item">
                <div class="activity-row">
                    <div class="activity-title">${escapeHtml(title)}</div>
                    <span class="pill ${statusClass}">${escapeHtml(getStatusLabel(entry.status))}</span>
                </div>
                <div class="activity-meta">${escapeHtml(meta)}</div>
                <div class="activity-message">${escapeHtml(message)}</div>
            </div>
        `;
    }).join('');
    renderLoadMore(filteredLogs.length, visibleLogs.length);
}

function getStatusLabel(status) {
    switch (status) {
        case 'success':
            return '成功';
        case 'duplicate':
            return '重复';
        case 'skipped':
            return '跳过';
        case 'error':
            return '失败';
        default:
            return '信息';
    }
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function addLog(entry) {
    const log = {
        at: new Date().toISOString(),
        ...entry
    };
    state.logs = [log, ...state.logs].slice(0, MAX_LOGS);
    saveState();
    if (uiVisible) {
        logVisibleCount = Math.max(LOG_BATCH_SIZE, Math.min(logVisibleCount + 1, MAX_LOGS));
        renderLogs();
        renderStatusSummary();
    }
}

function handleLogSearchInput(value) {
    logSearchTerm = String(value || '').trim().toLowerCase();
    logVisibleCount = LOG_BATCH_SIZE;
    renderLogs();
}

function recordCooldown(itemId, message) {
    state.cooldowns[itemId] = {
        until: Date.now() + DEFAULT_COOLDOWN_MS,
        lastError: message || 'Temporary failure'
    };
    saveState();
}

function clearCooldown(itemId) {
    if (state.cooldowns[itemId]) {
        delete state.cooldowns[itemId];
        saveState();
    }
}

function getCooldown(itemId) {
    pruneCooldowns();
    return state.cooldowns[itemId] || null;
}

async function loadSelectedCount() {
    try {
        const selectedItems = await eagle.item.getSelected();
        renderSelectionInfo((selectedItems || []).length);
    } catch (error) {
        console.warn('[UIBook Sync] Failed to load selected count:', error);
        renderSelectionInfo(0);
    }
}

function startSelectedWatcher() {
    stopSelectedWatcher();
    loadSelectedCount();
    selectedWatcherId = setInterval(loadSelectedCount, 2000);
}

function stopSelectedWatcher() {
    if (selectedWatcherId) {
        clearInterval(selectedWatcherId);
        selectedWatcherId = null;
    }
}

function startUiCountdown() {
    stopUiCountdown();
    renderStatusSummary();
    countdownId = setInterval(renderStatusSummary, 1000);
}

function stopUiCountdown() {
    if (countdownId) {
        clearInterval(countdownId);
        countdownId = null;
    }
}

function bindUi() {
    const saveButton = document.getElementById('saveButton');
    const syncButton = document.getElementById('syncButton');
    const logSearchInput = document.getElementById('logSearchInput');

    if (saveButton) {
        saveButton.onclick = async () => {
            try {
                updateConfigFromUi();
                saveConfig();
                scheduleAutoSync(true);
                renderStatusSummary();
                showToast('设置已保存', 'success');
            } catch (error) {
                console.error('[UIBook Sync] Failed to save config:', error);
                showToast(`保存失败: ${error.message}`, 'error');
            }
        };
    }

    if (syncButton) {
        syncButton.onclick = () => {
            handleManualSync();
        };
    }

    if (logSearchInput) {
        logSearchInput.oninput = event => {
            handleLogSearchInput(event.target.value);
        };
    }
}

function scheduleAutoSync(runSoon) {
    if (autoTimerId) {
        clearTimeout(autoTimerId);
        autoTimerId = null;
    }

    if (!config.autoEnabled) {
        nextAutoRunAt = null;
        if (uiVisible) renderStatusSummary();
        return;
    }

    const delay = runSoon ? 1000 : config.intervalMinutes * 60 * 1000;
    nextAutoRunAt = Date.now() + delay;
    autoTimerId = setTimeout(async () => {
        autoTimerId = null;
        await runAutoSync();
        scheduleAutoSync(false);
    }, delay);

    if (uiVisible) renderStatusSummary();
}

function getMimeTypeForPath(filePath, fallbackExt) {
    const ext = normalizeExt(path.extname(filePath || '') || fallbackExt);
    switch (ext) {
        case 'jpg':
        case 'jpeg':
            return 'image/jpeg';
        case 'png':
            return 'image/png';
        case 'webp':
            return 'image/webp';
        case 'gif':
            return 'image/gif';
        case 'avif':
            return 'image/avif';
        default:
            return 'application/octet-stream';
    }
}

async function readBlobFromFile(filePath, fallbackExt) {
    const buffer = await fsp.readFile(filePath);
    return new Blob([buffer], { type: getMimeTypeForPath(filePath, fallbackExt) });
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

function wait(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function inspectSourceImage(filePath, fallbackExt) {
    try {
        await fsp.access(filePath, fs.constants.R_OK);
    } catch (error) {
        return { ok: false, reason: 'file_not_stable' };
    }

    let firstStat;
    let secondStat;
    try {
        firstStat = await fsp.stat(filePath);
        await wait(FILE_STABILITY_DELAY_MS);
        secondStat = await fsp.stat(filePath);
    } catch (error) {
        return { ok: false, reason: 'file_not_stable' };
    }

    if (!firstStat.isFile() || !secondStat.isFile() || firstStat.size <= 0 || secondStat.size <= 0 || !areSnapshotsEqual(firstStat, secondStat)) {
        return {
            ok: false,
            reason: 'file_not_stable',
            snapshot: createFileSnapshot(secondStat || firstStat, null, null)
        };
    }

    let buffer;
    try {
        buffer = await fsp.readFile(filePath);
    } catch (error) {
        return { ok: false, reason: 'file_not_stable' };
    }

    const blob = new Blob([buffer], { type: getMimeTypeForPath(filePath, fallbackExt) });
    let bitmap;
    try {
        bitmap = await createImageBitmap(blob);
    } catch (error) {
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
        blob,
        snapshot: createFileSnapshot(secondStat, width, height)
    };
}

async function loadImageBitmapFromPath(filePath) {
    const blob = await readBlobFromFile(filePath);
    return createImageBitmap(blob);
}

function blobFromCanvas(canvas, mimeType, quality) {
    return new Promise((resolve, reject) => {
        canvas.toBlob(blob => {
            if (blob) {
                resolve(blob);
                return;
            }
            reject(new Error('Failed to render image blob'));
        }, mimeType, quality);
    });
}

async function generateContainedThumbnail(imagePath, targetWidth) {
    const bitmap = await loadImageBitmapFromPath(imagePath);
    const width = bitmap.width > targetWidth ? targetWidth : bitmap.width;
    const height = Math.max(1, Math.round(bitmap.height * (width / bitmap.width)));

    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(bitmap, 0, 0, width, height);
    if (typeof bitmap.close === 'function') bitmap.close();

    return blobFromCanvas(canvas, 'image/jpeg', 0.9);
}

async function generateCoverThumbnail(imagePath) {
    const bitmap = await loadImageBitmapFromPath(imagePath);
    const targetWidth = 600;
    const targetHeight = 800;
    const targetRatio = targetWidth / targetHeight;
    const sourceRatio = bitmap.width / bitmap.height;
    let sourceX = 0;
    let sourceY = 0;
    let sourceWidth = bitmap.width;
    let sourceHeight = bitmap.height;

    if (sourceRatio > targetRatio) {
        sourceWidth = Math.round(bitmap.height * targetRatio);
        sourceX = Math.max(0, Math.round((bitmap.width - sourceWidth) / 2));
    } else if (sourceRatio < targetRatio) {
        sourceHeight = Math.round(bitmap.width / targetRatio);
    }

    const canvas = document.createElement('canvas');
    canvas.width = targetWidth;
    canvas.height = targetHeight;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(
        bitmap,
        sourceX,
        sourceY,
        sourceWidth,
        sourceHeight,
        0,
        0,
        targetWidth,
        targetHeight
    );
    if (typeof bitmap.close === 'function') bitmap.close();

    return blobFromCanvas(canvas, 'image/jpeg', 0.95);
}

async function buildThumbnailAsset(item, basename, entityType) {
    const generatedBlob = entityType === 'section'
        ? await generateContainedThumbnail(item.filePath, 800)
        : await generateCoverThumbnail(item.filePath);
    return {
        blob: generatedBlob,
        filename: `${basename}-thumb.jpg`,
        mimeType: 'image/jpeg'
    };
}

async function buildAdminThumbAsset(item, basename, thumbnailAsset) {
    if (item.thumbnailPath && !item.noThumbnail) {
        try {
            const ext = normalizeExt(path.extname(item.thumbnailPath) || item.ext || 'png');
            const blob = await readBlobFromFile(item.thumbnailPath, ext);
            return {
                blob,
                filename: `${basename}-admin.${ext || 'png'}`,
                mimeType: blob.type || getMimeTypeForPath(item.thumbnailPath, ext)
            };
        } catch (error) {
            console.warn('[UIBook Sync] Eagle thumbnail unavailable for admin thumb, generating fallback:', error);
        }
    }

    try {
        const blob = await generateContainedThumbnail(item.filePath, 200);
        return {
            blob,
            filename: `${basename}-admin.jpg`,
            mimeType: 'image/jpeg'
        };
    } catch (error) {
        console.warn('[UIBook Sync] Admin thumb fallback generation failed, falling back to thumbnail:', error);
    }

    return {
        blob: thumbnailAsset.blob,
        filename: `${basename}-admin${path.extname(thumbnailAsset.filename) || '.jpg'}`,
        mimeType: thumbnailAsset.mimeType
    };
}

function getStableMainFilename(item) {
    if (item.filePath) {
        const basename = path.basename(item.filePath);
        if (basename && basename !== path.sep) return basename;
    }
    const ext = normalizeExt(item.ext || 'jpg');
    return `${item.id}.${ext || 'jpg'}`;
}

function getBaseName(filename) {
    const parsed = path.parse(filename);
    return parsed.name || filename || 'image';
}

function getItemTimestamp(item) {
    return item.importedAt || item.modifiedAt || null;
}

async function fetchFolderMap() {
    const now = Date.now();
    if (now - folderCache.loadedAt < 5 * 60 * 1000 && Object.keys(folderCache.data).length > 0) {
        return folderCache.data;
    }

    const response = await fetch('http://localhost:41595/api/folder/list');
    const result = await response.json();
    if (!response.ok || result.status !== 'success' || !Array.isArray(result.data)) {
        throw new Error('Failed to fetch folder list');
    }

    const folderMap = {};
    const walk = folders => {
        folders.forEach(folder => {
            if (folder && folder.id && folder.name) {
                folderMap[folder.id] = folder.name;
            }
            if (folder && Array.isArray(folder.children) && folder.children.length) {
                walk(folder.children);
            }
        });
    };
    walk(result.data);

    folderCache = {
        loadedAt: now,
        data: folderMap
    };
    return folderMap;
}

function normalizeTokens(values) {
    return new Set((values || []).map(value => String(value || '').trim().toLowerCase()).filter(Boolean));
}

function getFolderTokens(folderNames) {
    const tokens = new Set();
    (folderNames || []).forEach(folderName => {
        const normalized = String(folderName || '').trim().toLowerCase();
        if (!normalized) return;
        tokens.add(normalized);
        if (normalized.includes('_')) {
            tokens.add(normalized.split('_')[0]);
        }
    });
    return tokens;
}

function resolveFolderNames(item, folderMap) {
    const names = [];
    (item.folders || []).forEach(folderId => {
        if (folderMap[folderId]) {
            names.push(folderMap[folderId]);
        } else if (typeof folderId === 'string') {
            names.push(folderId);
        }
    });
    return names;
}

function resolveEntityType(item, folderMap) {
    const tagTokens = normalizeTokens(item.tags || []);
    const folderNames = resolveFolderNames(item, folderMap);
    const folderTokens = getFolderTokens(folderNames);
    const sectionTagRules = normalizeTokens(config.entityRules.sectionTags);
    const sectionFolderRules = normalizeTokens(config.entityRules.sectionFolders);
    const websiteTagRules = normalizeTokens(config.entityRules.websiteTags);
    const websiteFolderRules = normalizeTokens(config.entityRules.websiteFolders);

    const hasAny = (ruleSet, tokenSet) => Array.from(ruleSet).some(rule => tokenSet.has(rule));

    if (hasAny(sectionTagRules, tagTokens) || hasAny(sectionFolderRules, folderTokens)) {
        return 'section';
    }
    if (hasAny(websiteTagRules, tagTokens) || hasAny(websiteFolderRules, folderTokens)) {
        return 'website';
    }
    return null;
}

function itemHasTag(item, tag) {
    const target = String(tag || '').trim();
    if (!target) return false;
    return (item.tags || []).some(existing => String(existing || '').trim() === target);
}

function getSkipReason(reason) {
    switch (reason) {
        case 'sync_in_progress':
            return '该素材正在同步中';
        case 'already_synced_local':
            return '该素材已在本机登记为已同步';
        case 'already_synced':
            return '素材已带同步成功标签';
        case 'unsupported_ext':
            return '扩展名不在允许列表';
        case 'missing_url':
            return '素材缺少 URL';
        case 'missing_required_tag':
            return '未命中同步必需标签';
        case 'missing_entity_type':
            return '未命中 website / section 规则';
        case 'missing_file':
            return '素材缺少原图文件路径';
        case 'file_not_stable':
            return '原图仍在同步或写入中';
        case 'decode_failed':
            return '原图暂时无法解码';
        case 'invalid_dimensions':
            return '原图尺寸异常（<= 1x1）';
        case 'cooldown':
            return '处于失败冷却期';
        default:
            return reason || '已跳过';
    }
}

function formatEligibilityReason(prepared) {
    if (!prepared || !prepared.reason) return '已跳过';

    const base = prepared.reason === 'cooldown'
        ? `${getSkipReason(prepared.reason)}，${formatDateTime(prepared.cooldown.until)} 后重试`
        : getSkipReason(prepared.reason);

    if (prepared.reason === 'missing_required_tag' && Array.isArray(prepared.missingRequiredTags) && prepared.missingRequiredTags.length > 0) {
        const missing = prepared.missingRequiredTags.map(tag => `「${tag}」`).join('、');
        return `${base}：缺少 ${missing}`;
    }

    return base;
}

function evaluateEligibility(item, mode, folderMap) {
    if (!item || !item.filePath) {
        return { eligible: false, reason: 'missing_file' };
    }

    maybeBackfillSyncedItem(item);

    if (getInflightRecord(item.id)) {
        return { eligible: false, reason: 'sync_in_progress' };
    }

    if (getSyncedRecord(item.id)) {
        return { eligible: false, reason: 'already_synced_local' };
    }

    const successTag = config.successTag;
    if (itemHasTag(item, successTag)) {
        return { eligible: false, reason: 'already_synced' };
    }

    const ext = normalizeExt(item.ext || path.extname(item.filePath));
    const allowedExts = mode === 'auto' ? config.autoAllowedExts : config.manualAllowedExts;
    if (!allowedExts.includes(ext)) {
        return { eligible: false, reason: 'unsupported_ext' };
    }

    const url = cleanURL(item.url || '');
    if (config.requireUrl && !url) {
        return { eligible: false, reason: 'missing_url' };
    }

    if (config.requiredTags.length > 0) {
        const missingRequiredTags = config.requiredTags.filter(tag => !itemHasTag(item, tag));
        if (missingRequiredTags.length > 0) {
            return {
                eligible: false,
                reason: 'missing_required_tag',
                missingRequiredTags
            };
        }
    }

    if (mode === 'auto') {
        const cooldown = getCooldown(item.id);
        if (cooldown) {
            return { eligible: false, reason: 'cooldown', cooldown };
        }
    }

    const entityType = resolveEntityType(item, folderMap);
    if (!entityType) {
        return { eligible: false, reason: 'missing_entity_type' };
    }

    return {
        eligible: true,
        entityType,
        cleanedUrl: url,
        capturedDate: getItemTimestamp(item) ? new Date(getItemTimestamp(item)).toISOString() : undefined
    };
}

async function updateItemViaHTTP(itemId, fields) {
    const response = await fetch('http://localhost:41595/api/item/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: itemId, ...fields })
    });
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    const result = await response.json();
    if (result.status !== 'success') {
        throw new Error(result.message || `Eagle API returned ${result.status}`);
    }
    return result.data;
}

async function applySyncSuccessMarker(item, result, entityType) {
    const fullItem = await eagle.item.getById(item.id);
    if (!fullItem) {
        throw new Error(`Failed to reload item ${item.id}`);
    }

    const currentTags = fullItem.tags || [];
    const newTags = currentTags.includes(config.successTag)
        ? currentTags
        : [...currentTags, config.successTag];

    const line = `- 同步于 ${formatDateTime(new Date())} (uibook, ${entityType}, ${result.id || result.existingId || 'unknown'}, sourceItemId=${item.id})`;
    const currentAnnotation = fullItem.annotation || '';
    const filteredLines = currentAnnotation
        .split('\n')
        .filter(text => text && !text.match(/^- 同步于 .* \(uibook, .*?\)$/));
    const newAnnotation = [...filteredLines, line].join('\n');

    await updateItemViaHTTP(fullItem.id, {
        tags: newTags,
        annotation: newAnnotation
    });
}

async function refreshItemSelection(itemIds) {
    if (!itemIds.length) return;
    try {
        await eagle.item.select([]);
        await eagle.item.select(itemIds);
    } catch (error) {
        console.warn('[UIBook Sync] Selection refresh skipped:', error.message);
    }
}

async function fetchWithTimeout(url, options, timeoutMs) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => {
        controller.abort();
    }, timeoutMs);

    try {
        return await fetch(url, {
            ...options,
            signal: controller.signal
        });
    } finally {
        clearTimeout(timeoutId);
    }
}

async function safeParseJson(response) {
    try {
        return await response.json();
    } catch (error) {
        return {};
    }
}

async function sendItemToUiBook(item, prepared, inspectedFile) {
    const mainFilename = getStableMainFilename(item);
    const baseName = getBaseName(mainFilename);
    const mainBlob = inspectedFile && inspectedFile.blob
        ? inspectedFile.blob
        : await readBlobFromFile(item.filePath, item.ext);
    const thumbnailAsset = await buildThumbnailAsset(item, baseName, prepared.entityType);
    const adminAsset = await buildAdminThumbAsset(item, baseName, thumbnailAsset);

    const formData = new FormData();
    formData.append('image', mainBlob, mainFilename);
    formData.append('thumbnail', thumbnailAsset.blob, thumbnailAsset.filename);
    formData.append('adminThumb', adminAsset.blob, adminAsset.filename);
    formData.append('metadata', JSON.stringify({
        name: item.name || baseName,
        url: prepared.cleanedUrl || undefined,
        entityType: prepared.entityType,
        capturedDate: prepared.capturedDate,
        sourceItemId: item.id
    }));

    const response = await fetchWithTimeout(config.endpointUrl, {
        method: 'POST',
        headers: {
            Authorization: `Bearer ${config.syncSecret}`
        },
        body: formData
    }, DEFAULT_TIMEOUT_MS);
    const result = await safeParseJson(response);

    if (!response.ok) {
        throw new Error(result.error || `Sync failed (${response.status})`);
    }

    if (result && result.error === 'duplicate') {
        return {
            status: 'duplicate',
            id: result.existingId,
            message: result.existingUrl || '云端已存在相同素材'
        };
    }

    if (!result || result.success !== true) {
        throw new Error(result.error || 'Sync failed');
    }

    return {
        status: 'success',
        id: result.id,
        message: result.name || item.name || '同步成功'
    };
}

async function syncSingleItem(item, mode, folderMap) {
    const prepared = evaluateEligibility(item, mode, folderMap);
    if (!prepared.eligible) {
        const reason = formatEligibilityReason(prepared);
        if (mode === 'manual') {
            addLog({
                itemId: item.id,
                itemName: item.name,
                mode,
                status: 'skipped',
                entityType: null,
                message: reason
            });
        }
        return {
            status: 'skipped',
            itemId: item.id,
            reason
        };
    }

    const inspectedFile = await inspectSourceImage(item.filePath, item.ext);
    if (!inspectedFile.ok) {
        const reason = getSkipReason(inspectedFile.reason);
        if (mode === 'manual') {
            addLog({
                itemId: item.id,
                itemName: item.name,
                mode,
                status: 'skipped',
                entityType: prepared.entityType,
                message: reason
            });
        }
        return {
            status: 'skipped',
            itemId: item.id,
            reason
        };
    }

    markItemInflight(item.id, prepared.entityType);

    try {
        const result = await sendItemToUiBook(item, prepared, inspectedFile);
        rememberSyncedItem(item, result.id || null, prepared.entityType, new Date().toISOString());
        try {
            await applySyncSuccessMarker(item, result, prepared.entityType);
        } catch (markerError) {
            console.warn('[UIBook Sync] Local marker write failed after remote sync:', markerError);
        }
        clearCooldown(item.id);
        addLog({
            itemId: item.id,
            itemName: item.name,
            mode,
            status: result.status,
            entityType: prepared.entityType,
            message: result.status === 'duplicate' ? '云端已存在，已回写本地同步状态' : '同步成功',
            remoteId: result.id || null
        });
        return {
            status: result.status,
            itemId: item.id,
            remoteId: result.id || null
        };
    } catch (error) {
        clearItemInflight(item.id);
        recordCooldown(item.id, error.message);
        addLog({
            itemId: item.id,
            itemName: item.name,
            mode,
            status: 'error',
            entityType: prepared.entityType,
            message: error.message
        });
        return {
            status: 'error',
            itemId: item.id,
            error: error.message
        };
    }
}

async function processItemsWithConcurrency(items, mode, concurrency) {
    const folderMap = await fetchFolderMap();
    const results = [];
    let index = 0;

    async function worker() {
        while (index < items.length) {
            const currentIndex = index++;
            const result = await syncSingleItem(items[currentIndex], mode, folderMap);
            results[currentIndex] = result;
        }
    }

    const workers = Array.from({ length: Math.min(concurrency, items.length) }, () => worker());
    await Promise.all(workers);
    return results;
}

function beginBatch(mode) {
    if (syncBatchInProgress || autoRunInProgress) {
        addLog({
            mode,
            status: 'info',
            message: mode === 'auto'
                ? '自动扫描跳过：上一轮同步尚未结束'
                : '上一轮同步尚未结束，本次请求已跳过。'
        });
        if (mode === 'manual') {
            showToast('上一轮同步尚未结束', 'error');
        }
        return false;
    }
    syncBatchInProgress = mode === 'manual';
    autoRunInProgress = mode === 'auto';
    return true;
}

function endBatch(mode) {
    if (mode === 'manual') syncBatchInProgress = false;
    if (mode === 'auto') autoRunInProgress = false;
    if (uiVisible) renderStatusSummary();
}

function summarizeResults(results) {
    return results.reduce((summary, result) => {
        const key = result.status === 'duplicate' ? 'skipped' : result.status;
        if (!summary[key]) summary[key] = 0;
        summary[key] += 1;
        return summary;
    }, { success: 0, skipped: 0, error: 0 });
}

async function handleManualSync() {
    if (!beginBatch('manual')) return;

    setButtonLoading('syncButton', true, '同步中...');
    try {
        updateConfigFromUi();
        saveConfig();

        if (!config.endpointUrl || !config.syncSecret) {
            throw new Error('请先填写 Endpoint 和 Sync Secret');
        }

        const selectedItems = await eagle.item.getSelected();
        if (!selectedItems || selectedItems.length === 0) {
            showToast('请先在 Eagle 中选择素材', 'error');
            return;
        }
        backfillSyncedItems(selectedItems);

        const results = await processItemsWithConcurrency(selectedItems, 'manual', 2);
        const summary = summarizeResults(results);
        const refreshedIds = results
            .filter(result => result.status === 'success' || result.status === 'duplicate')
            .map(result => result.itemId);
        await refreshItemSelection(refreshedIds);
        showToast(`完成：成功 ${summary.success}，跳过 ${summary.skipped}，失败 ${summary.error}`, summary.error > 0 ? 'error' : 'success');
    } catch (error) {
        console.error('[UIBook Sync] Manual sync failed:', error);
        showToast(error.message, 'error');
    } finally {
        setButtonLoading('syncButton', false, '同步选中项');
        endBatch('manual');
    }
}

async function loadItemsForAutoSync() {
    const exts = Array.from(new Set(config.autoAllowedExts));
    const responses = await Promise.all(exts.map(ext => eagle.item.get({ ext })));
    const unique = new Map();
    responses.forEach(items => {
        (items || []).forEach(item => {
            if (!unique.has(item.id)) unique.set(item.id, item);
        });
    });
    const values = Array.from(unique.values());
    backfillSyncedItems(values);
    return values.filter(item => {
        const timestamp = getItemTimestamp(item);
        return timestamp && isSameDay(timestamp);
    });
}

async function runAutoSync() {
    if (!config.autoEnabled) return;
    if (!beginBatch('auto')) return;

    state.lastAutoScanAt = new Date().toISOString();
    saveState();
    if (uiVisible) renderStatusSummary();

    try {
        if (!config.endpointUrl || !config.syncSecret) {
            addLog({
                mode: 'auto',
                status: 'error',
                message: '自动同步已启用，但 Endpoint 或 Secret 尚未配置'
            });
            return;
        }

        const items = await loadItemsForAutoSync();
        if (!items.length) {
            addLog({
                mode: 'auto',
                status: 'info',
                message: '自动扫描完成，今天暂无候选素材'
            });
            return;
        }

        const results = await processItemsWithConcurrency(items, 'auto', 1);
        const summary = summarizeResults(results);
        const refreshedIds = results
            .filter(result => result.status === 'success' || result.status === 'duplicate')
            .map(result => result.itemId);
        await refreshItemSelection(refreshedIds);
        addLog({
            mode: 'auto',
            status: 'info',
            title: '自动扫描汇总',
            message: `自动扫描完成：成功 ${summary.success}，跳过 ${summary.skipped}，失败 ${summary.error}`
        });
    } catch (error) {
        console.error('[UIBook Sync] Auto sync failed:', error);
        addLog({
            mode: 'auto',
            status: 'error',
            message: error.message
        });
    } finally {
        endBatch('auto');
    }
}

eagle.onPluginCreate(async () => {
    console.log('[UIBook Sync] Plugin created');
    loadConfig();
    loadState();
    scheduleAutoSync(true);
});

eagle.onPluginRun(async () => {
    console.log('[UIBook Sync] Plugin run');
    loadConfig();
    loadState();
});

eagle.onPluginShow(async () => {
    console.log('[UIBook Sync] Plugin show');
    uiVisible = true;
    logSearchTerm = '';
    logVisibleCount = LOG_BATCH_SIZE;
    loadConfig();
    loadState();
    updateUiFromConfig();
    bindUi();
    const logSearchInput = document.getElementById('logSearchInput');
    if (logSearchInput) logSearchInput.value = '';
    renderLogs();
    renderStatusSummary();
    startSelectedWatcher();
    startUiCountdown();
});

eagle.onPluginHide(() => {
    console.log('[UIBook Sync] Plugin hide');
    uiVisible = false;
    stopSelectedWatcher();
    stopUiCountdown();
});

eagle.onLibraryChanged && eagle.onLibraryChanged(() => {
    loadState();
    if (uiVisible) {
        renderLogs();
        renderStatusSummary();
    }
});

if (typeof window !== 'undefined') {
    window.toggleCheckbox = toggleCheckbox;
}
