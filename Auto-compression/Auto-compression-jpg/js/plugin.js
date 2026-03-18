'use strict';

const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const PLUGIN_ID = 'auto-compression-jpg';
const DEFAULT_APP_PATH = '/Applications/图压.app';
const DEFAULT_INTERVAL_MINUTES = 5;

let timerId = null;
let config = {
  enabled: true,
  intervalMinutes: DEFAULT_INTERVAL_MINUTES,
  appPath: DEFAULT_APP_PATH
};
let lastRunTime = null;
let nextRunTime = null;
let countdownId = null;
let selectedCountWatcherId = null;
let selectedCountRefreshInFlight = false;
let pendingSelectedCountRefresh = false;

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

function ensureStorageDir() {
  const dir = getStorageDir();
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
  return dir;
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

function openWithApp(filePath, appPath, callback) {
  if (!eagle.app.isMac) {
    console.warn('[Auto-compression] open -a only supported on macOS');
    if (callback) callback(new Error('macOS only'));
    return;
  }
  const quotedFile = filePath.replace(/'/g, "'\\''");
  const quotedApp  = appPath.replace(/'/g, "'\\''");
  exec(`open -a '${quotedApp}' '${quotedFile}'`, (err) => {
    if (err) console.error('[Auto-compression] open failed:', err);
    if (callback) callback(err);
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
  return response.json();
}

async function addCompressionTag(item) {
  try {
    const currentTags = item.tags || [];
    if (currentTags.includes(COMPRESSION_TAG)) {
      console.log(`[Auto-compression] Tag already exists for ${item.id}`);
      return;
    }
    const newTags = [...currentTags, COMPRESSION_TAG];
    await updateItemViaHTTP(item.id, { tags: newTags });
    console.log(`[Auto-compression] ✓ Added tag to ${item.id}`);
  } catch (err) {
    console.error('[Auto-compression] Failed to add tag:', err);
    eagle.notification.show(`标签添加失败: ${item.id}`, 'error');
  }
}

function hasCompressionTag(item) {
  return item.tags && item.tags.includes(COMPRESSION_TAG);
}

function isJpegItem(item) {
  const ext = String(item.ext || '').toLowerCase();
  return ext === 'jpg' || ext === 'jpeg';
}

function isWithinDays(timestamp, days) {
  if (!timestamp) return false;
  if (days === null) return true; // "所有" 选项
  
  const now = Date.now();
  const itemDate = new Date(timestamp).getTime();
  const dayMs = days * 24 * 60 * 60 * 1000;
  return (now - itemDate) <= dayMs;
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
      const selectedItems = await eagle.item.getSelected();
      selectedCount = (selectedItems || []).filter(item => {
        if (!item || !item.filePath) return false;
        if (!isJpegItem(item)) return false;
        return !hasCompressionTag(item);
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
  // Eagle 没有稳定的“选中变化”事件时，使用轻量轮询保持按钮计数实时。
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
      return isWithinDays(ts, days) && !hasCompressionTag(item);
    }).length;
    const btn = document.getElementById(btnId);
    if (btn) {
      const label = days === null ? '所有图片' : `最近 ${days} 天`;
      btn.textContent = `${label} (${count})`;
    }
  }
  await refreshSelectedButtonCount();
}

async function batchCompress(days) {
  try {
    const daysLabel = days === null ? '所有' : `最近${days}天`;
    console.log(`[Auto-compression] Starting batch compression: ${daysLabel}`);
    
    // 获取所有 JPG 文件
    const items = await getAllJpgItems();
    
    // 筛选符合时间条件的文件
    const filtered = items.filter(item => {
      if (!item.filePath) return false;
      const ts = item.importedAt || item.modifiedAt;
      if (!ts) return false;
      return isWithinDays(ts, days);
    });
    
    // 排除已有标签的文件
    const toProcess = filtered.filter(item => !hasCompressionTag(item));
    
    console.log(`[Auto-compression] Found ${filtered.length} items, ${toProcess.length} need processing`);
    
    // 显示确认对话框
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
    
    // 批量处理
    eagle.notification.show(`开始处理 ${toProcess.length} 个文件...`, 'info');

    for (let i = 0; i < toProcess.length; i++) {
      const item = toProcess[i];
      openWithApp(item.filePath, config.appPath, () => {});
      await addCompressionTag(item);
      await new Promise(r => setTimeout(r, 500));

      // 每处理 10 个显示进度
      if ((i + 1) % 10 === 0) {
        console.log(`[Auto-compression] Progress: ${i + 1}/${toProcess.length}`);
      }
    }

    eagle.notification.show(`成功处理 ${toProcess.length} 个文件`, 'success');
    console.log(`[Auto-compression] Batch compression completed: ${toProcess.length} files`);
    await refreshBatchButtonCounts();
  } catch (err) {
    console.error('[Auto-compression] Batch compression error:', err);
    eagle.notification.show('批量压缩失败', 'error');
  }
}

async function batchCompressSelected() {
  try {
    const selectedItems = await eagle.item.getSelected();
    const selectable = (selectedItems || []).filter(item => {
      if (!item || !item.filePath) return false;
      return isJpegItem(item);
    });
    const toProcess = selectable.filter(item => !hasCompressionTag(item));

    if (selectable.length === 0) {
      eagle.notification.show('当前未选中可压缩的 JPG 图片', 'info');
      await refreshBatchButtonCounts();
      return;
    }

    if (toProcess.length === 0) {
      eagle.notification.show('选中图片均已压缩，无需处理', 'info');
      await refreshBatchButtonCounts();
      return;
    }

    const confirmed = confirm(`选中 ${selectable.length} 个 JPG 图片，其中 ${toProcess.length} 个需要压缩，是否继续？`);
    if (!confirmed) {
      console.log('[Auto-compression] Selected compression cancelled by user');
      return;
    }

    eagle.notification.show(`开始处理选中的 ${toProcess.length} 个文件...`, 'info');
    for (let i = 0; i < toProcess.length; i++) {
      const item = toProcess[i];
      openWithApp(item.filePath, config.appPath, () => {});
      await addCompressionTag(item);
      await new Promise(r => setTimeout(r, 500));

      if ((i + 1) % 10 === 0) {
        console.log(`[Auto-compression] Selected progress: ${i + 1}/${toProcess.length}`);
      }
    }

    eagle.notification.show(`成功处理选中的 ${toProcess.length} 个文件`, 'success');
    console.log(`[Auto-compression] Selected compression completed: ${toProcess.length} files`);
    await refreshBatchButtonCounts();
  } catch (err) {
    console.error('[Auto-compression] Selected compression error:', err);
    eagle.notification.show('选中项压缩失败', 'error');
  }
}

async function runTask() {
  if (!config.enabled) {
    console.log('[Auto-compression] Task skipped: disabled');
    return;
  }

  try {
    console.log('[Auto-compression] Running task...');
    const [jpgItems, jpegItems] = await Promise.all([
      eagle.item.get({ ext: 'jpg' }),
      eagle.item.get({ ext: 'jpeg' })
    ]);
    const items = [].concat(jpgItems || [], jpegItems || []);
    console.log(`[Auto-compression] Found ${items.length} JPG/JPEG items in total`);

    const processed = loadProcessed();
    const toProcess = [];
    const todayStr = getTodayStr();

    for (const item of items) {
      if (!item.filePath) continue;
      const ts = item.importedAt || item.modifiedAt;
      if (!ts) continue;
      if (!isToday(ts)) continue;
      if (processed.has(item.id)) continue;
      toProcess.push(item);
    }

    console.log(`[Auto-compression] Found ${toProcess.length} new JPG/JPEG file(s) added today`);

    for (const item of toProcess) {
      openWithApp(item.filePath, config.appPath, () => {});
      await addCompressionTag(item);
      processed.add(item.id);
      await new Promise(r => setTimeout(r, 500));
    }

    if (toProcess.length > 0) {
      saveProcessed(processed);
      console.log(`[Auto-compression] Opened ${toProcess.length} file(s) with 图压`);
    }

    lastRunTime = new Date().toLocaleTimeString('zh-CN');
    updateStatusUI();
    console.log('[Auto-compression] Task completed');
  } catch (err) {
    console.error('[Auto-compression] runTask error:', err);
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

function updateStatusUI() {
  const lastEl = document.getElementById('statusLastRun');
  const countEl = document.getElementById('statusProcessedCount');
  if (lastEl) lastEl.textContent = lastRunTime || '—';
  if (countEl) countEl.textContent = String(getTodayProcessedCount());
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

eagle.onPluginCreate(async (plugin) => {
  console.log('[Auto-compression] Plugin created');
  setTimeout(() => {
    loadConfig();
    startTimer();
  }, 1000);
});

eagle.onPluginRun(() => {
  console.log('[Auto-compression] Plugin run');
});

eagle.onPluginShow(() => {
  console.log('[Auto-compression] Plugin show');
  loadConfig();
  bindUI();
  startSelectedCountWatcher();
  startCountdown();
});

eagle.onPluginHide(() => {
  console.log('[Auto-compression] Plugin hide');
  stopSelectedCountWatcher();
  stopCountdown();
});

eagle.onLibraryChanged && eagle.onLibraryChanged(() => {
  loadProcessed();
});
