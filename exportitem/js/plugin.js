// Global state
let selectedFormat = 'json';
let selectedSource = 'selected';
let selectedImageMode = 'package'; // 'none', 'base64', 'package'
let includeThumbnails = true; // Whether to include thumbnails in export
let allItems = [];
let isPluginReady = false; // Guard: Eagle API only available after plugin-create

// Initialize plugin
eagle.onPluginCreate(async (plugin) => {
    console.log('Eagle Data Exporter initialized');
    await loadItemsCount();
    adjustWindowSize();
    isPluginReady = true;
});

eagle.onPluginRun(async () => {
    console.log('Plugin running...');
    if (!isPluginReady) return;
    await loadItemsCount();
    adjustWindowSize();
});

eagle.onPluginShow(async () => {
    console.log('Plugin shown');
    if (!isPluginReady) return;
    await loadItemsCount();
    adjustWindowSize();
});

// Adjust window size based on screen
function adjustWindowSize() {
    try {
        // Try to set a comfortable height (around 85% of viewport height)
        const targetHeight = Math.min(1000, window.screen.availHeight * 0.85);
        const targetWidth = 680;
        
        if (eagle.window && eagle.window.resize) {
            eagle.window.resize({
                width: targetWidth,
                height: Math.floor(targetHeight)
            });
            console.log(`Window resized to ${targetWidth}x${Math.floor(targetHeight)}`);
        }
    } catch (error) {
        console.log('Could not resize window:', error);
    }
}

// Load items count
async function loadItemsCount(retries = 2, retryDelay = 500) {
    try {
        const selectedItems = await eagle.item.getSelected();
        const infoBox = document.getElementById('itemCount');
        const countText = document.getElementById('countText');
        
        // Try to get library info, but handle gracefully if API not available
        let libraryInfo = null;
        try {
            if (eagle.library && typeof eagle.library.getInfo === 'function') {
                libraryInfo = await eagle.library.getInfo();
            }
        } catch (e) {
            console.log('Library info not available in this Eagle version');
        }
        
        if (selectedItems && selectedItems.length > 0) {
            if (libraryInfo && libraryInfo.allItems) {
                countText.textContent = `已选 ${selectedItems.length} 项 · 库内共 ${libraryInfo.allItems} 项`;
            } else {
                countText.textContent = `已选 ${selectedItems.length} 项`;
            }
            infoBox.style.display = 'flex';
        } else if (libraryInfo && libraryInfo.allItems) {
            countText.textContent = `库内共 ${libraryInfo.allItems} 项`;
            infoBox.style.display = 'flex';
        } else {
            /* 无选中且无库规模信息时不占版面 */
            countText.textContent = '';
            infoBox.style.display = 'none';
        }
    } catch (error) {
        if (retries > 0) {
            await new Promise(r => setTimeout(r, retryDelay));
            return loadItemsCount(retries - 1, retryDelay * 2);
        }
        console.error('Failed to load items count after retries:', error);
    }
}

// Toggle field checkbox
function toggleField(fieldName) {
    const checkbox = document.getElementById(`field_${fieldName}`);
    checkbox.checked = !checkbox.checked;
    event.stopPropagation();
}

// Toggle more fields visibility
function toggleMoreFields() {
    const container = document.getElementById('moreFieldsContainer');
    const icon = document.getElementById('moreFieldsIcon');
    const text = document.getElementById('moreFieldsText');
    
    const isExpanded = container.classList.contains('expanded');
    
    if (isExpanded) {
        container.classList.remove('expanded');
        icon.classList.remove('expanded');
        text.textContent = '更多字段';
    } else {
        container.classList.add('expanded');
        icon.classList.add('expanded');
        text.textContent = '收起';
    }
}

// Select export format
function selectFormat(format) {
    selectedFormat = format;
    
    // Update UI
    document.getElementById('format_json').classList.toggle('active', format === 'json');
    document.getElementById('format_csv').classList.toggle('active', format === 'csv');
    
    // Show/hide image export section (only for JSON)
    const imageSection = document.getElementById('imageExportSection');
    if (format === 'json') {
        imageSection.style.display = 'block';
    } else {
        imageSection.style.display = 'none';
    }
}

// Select image export mode
function selectImageMode(mode) {
    selectedImageMode = mode;
    
    // Update UI
    document.getElementById('image_none').classList.toggle('active', mode === 'none');
    document.getElementById('image_base64').classList.toggle('active', mode === 'base64');
    document.getElementById('image_package').classList.toggle('active', mode === 'package');
}

// Select export source
function selectSource(source) {
    selectedSource = source;
    
    // Update UI
    document.getElementById('source_selected').classList.toggle('active', source === 'selected');
    document.getElementById('source_all').classList.toggle('active', source === 'all');
}

// Toggle thumbnail export option
function toggleThumbnailExport() {
    const checkbox = document.getElementById('export_thumbnail');
    checkbox.checked = !checkbox.checked;
    includeThumbnails = checkbox.checked;
    event.stopPropagation();
}

// Show toast notification
function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type} show`;
    
    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

// Get selected fields
function getSelectedFields() {
    const fields = [];
    const checkboxes = document.querySelectorAll('.field-item input[type="checkbox"][id^="field_"]:checked');
    
    checkboxes.forEach(cb => {
        const fieldName = cb.id.replace('field_', '');
        fields.push(fieldName);
    });
    
    return fields;
}

// Convert image to base64
async function imageToBase64(filePath) {
    try {
        const response = await fetch(`file://${filePath}`);
        const blob = await response.blob();
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onloadend = () => resolve(reader.result);
            reader.onerror = reject;
            reader.readAsDataURL(blob);
        });
    } catch (error) {
        console.error('Failed to convert image to base64:', error);
        return null;
    }
}

// Clean URL by removing query parameters (keep hash/anchor)
function cleanURL(url) {
    if (!url) return '';
    
    try {
        const urlObj = new URL(url);
        // Return origin + pathname + hash (no search params)
        return urlObj.origin + urlObj.pathname + urlObj.hash;
    } catch (error) {
        // If URL is invalid, try simple string manipulation
        // Split by '?', take first part, this preserves hash
        const cleanedUrl = url.split('?')[0];
        return cleanedUrl;
    }
}

// Extract data from items based on selected fields
async function extractItemData(items, fields, includeBase64 = false) {
    const results = [];
    
    for (const item of items) {
        const data = {};
        
        // Add ID for reference
        data.id = item.id;
        
        
        for (const field of fields) {
            switch(field) {
                case 'name':
                    data.name = item.name || '';
                    break;
                case 'url':
                    data.url = cleanURL(item.url);
                    break;
                case 'tags':
                    data.tags = item.tags || [];
                    break;
                case 'annotation':
                    data.annotation = item.annotation || '';
                    break;
                case 'size':
                    data.size = item.size || 0;
                    break;
                case 'ext':
                    data.ext = item.ext || '';
                    break;
                case 'folders':
                    data.folders = item.folders || [];
                    break;
                case 'mtime':
                    data.capturedDate = item.importedAt ? new Date(item.importedAt).toISOString() : '';
                    break;
                case 'filePath':
                    data.filePath = item.filePath || '';
                    break;
                case 'width':
                    data.width = item.width || 0;
                    break;
                case 'height':
                    data.height = item.height || 0;
                    break;
                case 'palettes':
                    data.palettes = item.palettes || [];
                    break;
            }
        }
        
        // Add image data if requested
        if (includeBase64 && item.filePath) {
            const base64 = await imageToBase64(item.filePath);
            if (base64) {
                data.imageBase64 = base64;
            }
        }
        
        // For package mode, add filename reference
        if (selectedImageMode === 'package' && item.filePath) {
            const ext = item.ext || 'png';
            data.imageFile = `${item.id}.${ext}`;
            
            // Add Eagle thumbnail reference if enabled and available
            if (includeThumbnails && item.thumbnailPath && !item.noThumbnail) {
                const thumbExt = item.thumbnailPath.split('.').pop() || 'png';
                data.thumbnailFile = `${item.id}_thumb.${thumbExt}`;
            }
            
            // Add custom thumbnail reference if image is vertical (height > width)
            if (item.height && item.width && item.height > item.width) {
                data.customThumbnailFile = `${item.id}_600x800.jpg`;
            }
        }
        
        results.push(data);
    }
    
    return results;
}

// Convert data to JSON
function convertToJSON(data) {
    return JSON.stringify(data, null, 2);
}

// Convert data to CSV
function convertToCSV(data) {
    if (data.length === 0) return '';
    
    // Get headers from first item
    const headers = Object.keys(data[0]);
    
    // Create CSV header row
    const csvHeaders = headers.map(h => `"${h}"`).join(',');
    
    // Create CSV data rows
    const csvRows = data.map(item => {
        return headers.map(header => {
            let value = item[header];
            
            // Handle arrays (tags, folders, palettes)
            if (Array.isArray(value)) {
                value = value.join('; ');
            }
            
            // Handle undefined/null
            if (value === undefined || value === null) {
                value = '';
            }
            
            // Escape quotes and wrap in quotes
            value = String(value).replace(/"/g, '""');
            return `"${value}"`;
        }).join(',');
    });
    
    return [csvHeaders, ...csvRows].join('\n');
}

// Download file
function downloadFile(content, filename, mimeType) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// Download blob
function downloadBlob(blob, filename) {
    try {
        console.log(`[Download] Starting download for: ${filename}`);
        console.log(`[Download] Blob size: ${blob.size} bytes (${(blob.size / 1024 / 1024).toFixed(2)} MB)`);
        console.log(`[Download] Blob type: ${blob.type}`);
        
        const url = URL.createObjectURL(blob);
        console.log(`[Download] Created object URL: ${url}`);
        
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        console.log(`[Download] Download attribute set to: ${a.download}`);
        
        document.body.appendChild(a);
        console.log(`[Download] Link element added to DOM`);
        
        a.click();
        console.log(`[Download] Click triggered for: ${filename}`);
        
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        console.log(`[Download] ✓ Download initiated successfully: ${filename}`);
    } catch (error) {
        console.error(`[Download] ✗ Failed to download ${filename}:`, error);
        throw error;
    }
}

// Generate export filename based on items and export mode
async function generateExportFilename(items, extension) {
    // Get compact datetime: 20260115_143025
    const now = new Date();
    const datetime = now.getFullYear() +
        String(now.getMonth() + 1).padStart(2, '0') +
        String(now.getDate()).padStart(2, '0') + '_' +
        String(now.getHours()).padStart(2, '0') +
        String(now.getMinutes()).padStart(2, '0') +
        String(now.getSeconds()).padStart(2, '0');
    
    // Get folder name prefix
    let prefix = 'eagle_export';
    
    if (selectedSource === 'all') {
        // Export all: use library name
        const library = await eagle.library.getInfo();
        prefix = library.name || 'eagle_export';
    } else if (items && items.length > 0) {
        // Get all folders from Eagle HTTP API to build ID -> name mapping
        let folderMap = {};
        
        try {
            // Call Eagle HTTP API to get folder list
            const response = await fetch('http://localhost:41595/api/folder/list');
            const result = await response.json();
            
            if (result.status === 'success' && result.data && Array.isArray(result.data)) {
                result.data.forEach(folder => {
                    if (folder.id && folder.name) {
                        folderMap[folder.id] = folder.name;
                    }
                });
                console.log('Folder map created:', folderMap);
            }
        } catch (error) {
            console.error('Failed to get folder list from Eagle API:', error);
        }
        
        // Collect unique folder IDs and convert to names
        const folderIds = new Set();
        items.forEach(item => {
            if (item.folders && item.folders.length > 0) {
                item.folders.forEach(folderId => folderIds.add(folderId));
            }
        });
        
        if (folderIds.size === 0) {
            prefix = 'eagle_export';
        } else if (folderIds.size === 1) {
            // Single folder: use folder name
            const folderId = Array.from(folderIds)[0];
            prefix = folderMap[folderId] || folderId;
        } else {
            // Multiple folders: use count
            prefix = `${folderIds.size}Folders`;
        }
    }
    
    // Sanitize prefix (remove invalid filename chars)
    prefix = prefix.replace(/[/\\?%*:|"<>]/g, '-');
    
    // Get count
    const count = items.length;
    
    return `${prefix}-${datetime}-${count}.${extension}`;
}

// Generate custom thumbnail (600x800, top-cropped)
async function generateCustomThumbnail(imagePath, width, height) {
    // Only generate for vertical images (height > width)
    if (height <= width) {
        return null;
    }
    
    try {
        // Load image
        const response = await fetch(`file://${imagePath}`);
        const blob = await response.blob();
        const img = await createImageBitmap(blob);
        
        // Calculate scale to fit width to 600px
        const scale = 600 / img.width;
        const scaledHeight = img.height * scale;
        
        // Create canvas 600x800
        const canvas = document.createElement('canvas');
        canvas.width = 600;
        canvas.height = 800;
        const ctx = canvas.getContext('2d');
        
        // Draw image scaled and cropped from top
        ctx.drawImage(
            img,
            0, 0, img.width, Math.min(img.height, 800 / scale), // Source
            0, 0, 600, 800 // Destination
        );
        
        // Convert to blob with 100% quality
        return new Promise(resolve => {
            canvas.toBlob(resolve, 'image/jpeg', 1.0);
        });
    } catch (error) {
        console.error('Failed to generate custom thumbnail:', error);
        return null;
    }
}

// Create ZIP package with images and JSON
async function createDataPackage(items, extractedData, filename) {
    if (typeof JSZip === 'undefined') {
        throw new Error('JSZip 库未加载，无法创建数据包');
    }
    
    const zip = new JSZip();
    
    // Add JSON metadata
    const jsonContent = JSON.stringify(extractedData, null, 2);
    zip.file('metadata.json', jsonContent);
    
    // Add images folder
    const imagesFolder = zip.folder('images');
    
    // Add thumbnails folder if needed
    const thumbnailsFolder = includeThumbnails ? zip.folder('admin list thumbnails') : null;
    
    // Add custom thumbnails folder
    const customThumbnailsFolder = zip.folder('custom_thumbnails');
    
    // Count items that need custom thumbnails (vertical images: height > width)
    const customThumbnailCount = items.filter(item => item.height && item.width && item.height > item.width).length;
    
    // Calculate total items for progress (images + Eagle thumbnails + custom thumbnails)
    let totalItems = items.length; // Original images
    if (includeThumbnails) totalItems += items.length; // Eagle thumbnails
    totalItems += customThumbnailCount; // Custom thumbnails
    
    let processedItems = 0;
    
    // Add each image file
    for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (!item.filePath) continue;
        
        try {
            const response = await fetch(`file://${item.filePath}`);
            const blob = await response.blob();
            const ext = item.ext || 'png';
            const imageFilename = `${item.id}.${ext}`;
            imagesFolder.file(imageFilename, blob);
            
            processedItems++;
            
            // Update progress
            const progress = Math.round((processedItems / totalItems) * 100);
            const btnText = document.getElementById('exportBtnText');
            btnText.innerHTML = `<span class="loading"></span> 打包中 ${progress}%`;
        } catch (error) {
            console.error(`Failed to add image ${item.name}:`, error);
        }
    }
    
    // Add Eagle thumbnails if enabled
    if (includeThumbnails && thumbnailsFolder) {
        for (let i = 0; i < items.length; i++) {
            const item = items[i];
            
            // Skip if no thumbnail available
            if (!item.thumbnailPath || item.noThumbnail) {
                processedItems++;
                continue;
            }
            
            try {
                const response = await fetch(`file://${item.thumbnailPath}`);
                const blob = await response.blob();
                const thumbExt = item.thumbnailPath.split('.').pop() || 'png';
                const thumbFilename = `${item.id}_thumb.${thumbExt}`;
                thumbnailsFolder.file(thumbFilename, blob);
                
                processedItems++;
                
                // Update progress
                const progress = Math.round((processedItems / totalItems) * 100);
                const btnText = document.getElementById('exportBtnText');
                btnText.innerHTML = `<span class="loading"></span> 打包中 ${progress}%`;
            } catch (error) {
                console.error(`Failed to add thumbnail for ${item.name}:`, error);
                processedItems++;
            }
        }
    }
    
    // Add custom thumbnails (600x800, top-cropped)
    for (let i = 0; i < items.length; i++) {
        const item = items[i];
        
        // Generate custom thumbnail for vertical images (height > width)
        if (item.height && item.width && item.height > item.width && item.filePath) {
            try {
                const customThumb = await generateCustomThumbnail(
                    item.filePath,
                    item.width,
                    item.height
                );
                
                if (customThumb) {
                    customThumbnailsFolder.file(`${item.id}_600x800.jpg`, customThumb);
                    processedItems++;
                    
                    // Update progress
                    const progress = Math.round((processedItems / totalItems) * 100);
                    const btnText = document.getElementById('exportBtnText');
                    btnText.innerHTML = `<span class="loading"></span> 生成缩略图 ${progress}%`;
                } else {
                    processedItems++;
                }
            } catch (error) {
                console.error(`Failed to generate custom thumbnail for ${item.name}:`, error);
                processedItems++;
            }
        }
    }
    
    // Generate ZIP file
    console.log(`[ZIP] Starting ZIP generation for: ${filename}`);
    console.log(`[ZIP] Total items in package: ${items.length}`);
    
    try {
        const blob = await zip.generateAsync({ 
            type: 'blob',
            compression: 'DEFLATE',
            compressionOptions: { level: 6 }
        });
        
        console.log(`[ZIP] ✓ ZIP generation successful`);
        console.log(`[ZIP] Final blob size: ${blob.size} bytes (${(blob.size / 1024 / 1024).toFixed(2)} MB)`);
        
        // Download
        console.log(`[ZIP] Initiating download for: ${filename}`);
        downloadBlob(blob, filename);
        console.log(`[ZIP] ✓ Download completed for: ${filename}`);
        
        return blob;
    } catch (error) {
        console.error(`[ZIP] ✗ Failed to generate or download ZIP for ${filename}:`, error);
        console.error(`[ZIP] Error details:`, {
            message: error.message,
            stack: error.stack,
            items: items.length,
            filename: filename
        });
        throw error;
    }
}

// Create unified ZIP package containing individual group ZIPs
async function createGroupedDataPackage(groups, groupKeys, fields, filename) {
    if (typeof JSZip === 'undefined') {
        throw new Error('JSZip 库未加载，无法创建数据包');
    }
    
    console.log(`[ZIP] Starting unified ZIP-of-ZIPs generation for: ${filename}`);
    console.log(`[ZIP] Groups to process: ${groupKeys.length}`);
    
    const mainZip = new JSZip();
    const btnText = document.getElementById('exportBtnText');
    
    try {
        // Process each group and create individual ZIP files
        for (let groupIndex = 0; groupIndex < groupKeys.length; groupIndex++) {
            const groupKey = groupKeys[groupIndex];
            const groupItems = groups[groupKey];
            
            console.log(`[ZIP] Creating individual ZIP ${groupIndex + 1}/${groupKeys.length}: "${groupKey}" (${groupItems.length} items)`);
            btnText.innerHTML = `<span class="loading"></span> 创建 ${groupKey} ZIP...`;
            
            // Create individual ZIP for this group
            const groupZip = new JSZip();
            
            // Extract data for this group
            const extractedData = await extractItemData(groupItems, fields, false);
            
            // Add metadata.json
            const jsonContent = JSON.stringify(extractedData, null, 2);
            groupZip.file('metadata.json', jsonContent);
            console.log(`[ZIP]   ✓ Added metadata.json (${groupItems.length} items)`);
            
            // Create folders
            const imagesFolder = groupZip.folder('images');
            const thumbnailsFolder = includeThumbnails ? groupZip.folder('admin list thumbnails') : null;
            const customThumbnailsFolder = groupZip.folder('custom_thumbnails');
            
            // Calculate total items for progress
            const customThumbnailCount = groupItems.filter(item => item.height && item.width && item.height > item.width).length;
            let totalItems = groupItems.length;
            if (includeThumbnails) totalItems += groupItems.length;
            totalItems += customThumbnailCount;
            let processedItems = 0;
            
            // Add images
            for (const item of groupItems) {
                if (!item.filePath) continue;
                
                try {
                    const response = await fetch(`file://${item.filePath}`);
                    const blob = await response.blob();
                    const ext = item.ext || 'png';
                    imagesFolder.file(`${item.id}.${ext}`, blob);
                    processedItems++;
                    
                    const progress = Math.round((processedItems / totalItems) * 100);
                    btnText.innerHTML = `<span class="loading"></span> ${groupKey}: ${progress}%`;
                } catch (error) {
                    console.error(`[ZIP]   Failed to add image ${item.name}:`, error);
                }
            }
            
            // Add Eagle thumbnails
            if (includeThumbnails && thumbnailsFolder) {
                for (const item of groupItems) {
                    if (!item.thumbnailPath || item.noThumbnail) {
                        processedItems++;
                        continue;
                    }
                    
                    try {
                        const response = await fetch(`file://${item.thumbnailPath}`);
                        const blob = await response.blob();
                        const thumbExt = item.thumbnailPath.split('.').pop() || 'png';
                        thumbnailsFolder.file(`${item.id}_thumb.${thumbExt}`, blob);
                        processedItems++;
                    } catch (error) {
                        console.error(`[ZIP]   Failed to add thumbnail:`, error);
                        processedItems++;
                    }
                }
            }
            
            // Add custom thumbnails
            for (const item of groupItems) {
                if (item.height && item.width && item.height > item.width && item.filePath) {
                    try {
                        const customThumb = await generateCustomThumbnail(item.filePath, item.width, item.height);
                        if (customThumb) {
                            customThumbnailsFolder.file(`${item.id}_600x800.jpg`, customThumb);
                            processedItems++;
                        } else {
                            processedItems++;
                        }
                    } catch (error) {
                        console.error(`[ZIP]   Failed to generate custom thumbnail:`, error);
                        processedItems++;
                    }
                }
            }
            
            // Generate this group's ZIP as blob
            console.log(`[ZIP]   Generating ZIP blob for "${groupKey}"...`);
            const groupZipBlob = await groupZip.generateAsync({ 
                type: 'blob',
                compression: 'DEFLATE',
                compressionOptions: { level: 6 }
            });
            
            // Generate filename for this group ZIP
            const now = new Date();
            const datetime = now.getFullYear() +
                String(now.getMonth() + 1).padStart(2, '0') +
                String(now.getDate()).padStart(2, '0') + '_' +
                String(now.getHours()).padStart(2, '0') +
                String(now.getMinutes()).padStart(2, '0') +
                String(now.getSeconds()).padStart(2, '0');
            const sanitizedGroupName = groupKey.replace(/[/\\?%*:|"<>]/g, '-');
            const groupZipFilename = `${sanitizedGroupName}-${datetime}-${groupItems.length}.zip`;
            
            // Add this group ZIP to main ZIP
            mainZip.file(groupZipFilename, groupZipBlob);
            console.log(`[ZIP]   ✓ Added ${groupZipFilename} (${(groupZipBlob.size / 1024 / 1024).toFixed(2)} MB)`);
        }
        
        // Generate final main ZIP
        console.log(`[ZIP] Generating main ZIP containing ${groupKeys.length} group ZIPs...`);
        btnText.innerHTML = `<span class="loading"></span> 生成最终 ZIP...`;
        
        const finalBlob = await mainZip.generateAsync({ 
            type: 'blob',
            compression: 'STORE'  // No compression for outer ZIP since inner ZIPs are already compressed
        });
        
        console.log(`[ZIP] ✓ Main ZIP generation successful`);
        console.log(`[ZIP] Final blob size: ${finalBlob.size} bytes (${(finalBlob.size / 1024 / 1024).toFixed(2)} MB)`);
        
        // Download
        console.log(`[ZIP] Initiating download for: ${filename}`);
        downloadBlob(finalBlob, filename);
        console.log(`[ZIP] ✓ Download completed for: ${filename}`);
        
        return finalBlob;
    } catch (error) {
        console.error(`[ZIP] ✗ Failed to generate ZIP-of-ZIPs:`, error);
        throw error;
    }
}

// Group items by folder prefix (e.g., Page_, Section_)
async function groupItemsByFolderPrefix(items) {
    const groups = {};
    
    // Get folder mapping (ID -> name)
    let folderMap = {};
    try {
        const response = await fetch('http://localhost:41595/api/folder/list');
        const result = await response.json();
        
        console.log('[Grouping] Raw API response:', result);
        
        if (result.status === 'success' && result.data) {
            // Recursively extract all folders including children
            function extractFolders(folders) {
                folders.forEach(folder => {
                    if (folder.id && folder.name) {
                        folderMap[folder.id] = folder.name;
                        console.log(`[Grouping]   Adding folder: "${folder.name}" (ID: ${folder.id})`);
                    }
                    // Recursively process children
                    if (folder.children && Array.isArray(folder.children) && folder.children.length > 0) {
                        console.log(`[Grouping]   Processing ${folder.children.length} children of "${folder.name}"`);
                        extractFolders(folder.children);
                    }
                });
            }
            
            console.log('[Grouping] Processing folder tree...');
            extractFolders(result.data);
            console.log(`[Grouping] ✓ Folder map created with ${Object.keys(folderMap).length} folders`);
            console.log('[Grouping] Complete folder map:', folderMap);
        }
    } catch (error) {
        console.error('[Grouping] Failed to get folder list:', error);
    }
    
    for (const item of items) {
        let groupKey = 'Other';
        let matchedFolderName = '';
        
        if (item.folders && item.folders.length > 0) {
            // Log all folder IDs for debugging
            console.log(`[Grouping] Item "${item.name}" (ID: ${item.id})`);
            console.log(`[Grouping]   Folder IDs: [${item.folders.join(', ')}]`);
            
            // Iterate through all folder levels to find the first one with underscore
            // This handles multi-level folder structures correctly
            let missingFolders = [];
            for (const folderId of item.folders) {
                const folderName = folderMap[folderId];
                
                if (!folderName) {
                    console.warn(`[Grouping]   ⚠ Folder ID "${folderId}" not found in folder map!`);
                    missingFolders.push(folderId);
                    continue;
                }
                
                console.log(`[Grouping]   - Folder ID "${folderId}" → "${folderName}"`);
                
                // Extract prefix (before underscore)
                if (folderName.includes('_')) {
                    groupKey = folderName.split('_')[0];
                    matchedFolderName = folderName;
                    console.log(`[Grouping]   ✓ Matched! Using prefix: "${groupKey}" from folder: "${folderName}"`);
                    break;  // Use the first folder that matches our naming convention
                }
            }
            
            if (groupKey === 'Other') {
                if (missingFolders.length > 0) {
                    console.error(`[Grouping]   ✗ Missing ${missingFolders.length} folder(s): ${missingFolders.join(', ')}`);
                    console.log(`[Grouping]   → Using "Other" because folders not found in map`);
                } else {
                    console.log(`[Grouping]   → No matching folder found (no underscore), using "Other"`);
                }
            }
        } else {
            console.log(`[Grouping] Item "${item.name}" has no folders → "Other"`);
        }
        
        if (!groups[groupKey]) {
            groups[groupKey] = [];
        }
        groups[groupKey].push(item);
    }
    
    console.log('[Grouping] Created groups:', Object.keys(groups));
    Object.keys(groups).forEach(key => {
        console.log(`[Grouping] ${key}: ${groups[key].length} items`);
    });
    
    return groups;
}

// Update item metadata via Eagle's HTTP REST API, bypassing the buggy item.save()
// which hangs forever for some item types (e.g. bookmarks) due to an Eagle-internal
// logger crash inside the save() promise chain.
async function updateItemViaHTTP(itemId, fields) {
    const payload = { id: itemId, ...fields };
    const response = await fetch('http://localhost:41595/api/item/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    const result = await response.json();
    if (result.status !== 'success') {
        throw new Error(`Eagle API returned status: ${result.status}`);
    }
    return result.data;
}

// Update exported items with export record and 5-star rating
async function updateExportedItemsMetadata(items) {
    console.log('[Metadata Update] ========================================');
    console.log('[Metadata Update] Starting update for', items.length, 'items');
    console.log('[Metadata Update] ========================================');
    
    let successCount = 0;
    let failCount = 0;
    const failedItems = [];
    
    try {
        // Get current datetime
        const now = new Date();
        const datetime = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
        const exportRecord = `- 导出于 ${datetime} (uibook)`;
        console.log('[Metadata Update] Export record:', exportRecord);
        
        for (let i = 0; i < items.length; i++) {
            const item = items[i];
            console.log(`[Metadata Update] ----------------------------------------`);
            console.log(`[Metadata Update] Processing item ${i+1}/${items.length}:`, item.id, item.name);
            
            try {
                // Get fresh item data
                const fullItem = await eagle.item.getById(item.id);
                if (!fullItem) {
                    throw new Error(`Failed to get item data for ${item.id}`);
                }
                console.log('[Metadata Update] ✓ Got item data:', fullItem.id);
                
                // Prepare new annotation (replace existing uibook export line, or append)
                const currentAnnotation = fullItem.annotation || '';
                const lines = currentAnnotation.split('\n');
                const filteredLines = lines.filter(line => !line.match(/^- 导出于 .+ \(uibook\)$/));
                const newAnnotation = [...filteredLines, exportRecord]
                    .filter(line => line.trim() !== '')
                    .join('\n');
                console.log('[Metadata Update] ✓ Prepared annotation');

                // Prepare new tags (keep existing non-export tags, add latest export tag)
                const currentTags = fullItem.tags || [];
                const filteredTags = currentTags.filter(tag => !tag.startsWith('- 导出于'));
                const newTags = [...filteredTags, exportRecord];
                console.log('[Metadata Update] ✓ Prepared tags:', newTags.length, 'tags');

                // Write via Eagle HTTP REST API — avoids item.save() which hangs
                // due to an Eagle-internal logger bug on certain item types (e.g. bookmarks)
                console.log('[Metadata Update] Writing via HTTP API for item:', fullItem.id);
                await updateItemViaHTTP(fullItem.id, {
                    annotation: newAnnotation,
                    tags: newTags,
                    star: 5,
                });

                successCount++;
                console.log(`[Metadata Update] ✓ Successfully updated ${i+1}/${items.length}`);
            } catch (error) {
                failCount++;
                failedItems.push({id: item.id, name: item.name, error: error.message});
                console.error(`[Metadata Update] ✗ Failed for item ${item.id} (${item.name}):`, error);
                console.error(`[Metadata Update] Error details:`, error);
            }
        }
        
        console.log('[Metadata Update] ========================================');
        console.log(`[Metadata Update] Completed: ${successCount} success, ${failCount} failed`);
        if (failedItems.length > 0) {
            console.error('[Metadata Update] Failed items:', failedItems);
        }
        console.log('[Metadata Update] ========================================');

        // Force Eagle UI to reload the updated items from disk (including tags).
        // HTTP REST API updates disk only; Eagle's in-memory panel cache stays stale.
        // Deselect-then-reselect forces Eagle to fully rebuild the info panel from disk,
        // ensuring annotation, stars, AND tags all show the new values immediately.
        if (successCount > 0) {
            try {
                const updatedIds = items
                    .filter(item => !failedItems.find(f => f.id === item.id))
                    .map(i => i.id);
                if (updatedIds.length > 0) {
                    await eagle.item.select([]);
                    await eagle.item.select(updatedIds);
                    console.log('[Metadata Update] ✓ Eagle UI refreshed for', updatedIds.length, 'items');
                }
            } catch (refreshErr) {
                console.log('[Metadata Update] UI refresh skipped (Eagle 4.0 build12+ required):', refreshErr.message);
            }
        }

        // If any items failed, throw error with details
        if (failCount > 0) {
            throw new Error(`Failed to update ${failCount} out of ${items.length} items. Check console for details.`);
        }
        
    } catch (error) {
        console.error('[Metadata Update] Fatal error:', error);
        throw error;
    }
}

// Handle export
async function handleExport() {
    try {
        const fields = getSelectedFields();
        
        if (fields.length === 0) {
            showToast('请至少选择一个导出字段', 'error');
            return;
        }
        
        // Show loading state
        const btn = document.querySelector('.export-btn');
        const btnText = document.getElementById('exportBtnText');
        btn.disabled = true;
        btnText.innerHTML = '<span class="loading"></span> 导出中...';
        
        // Get items based on source
        let items;
        if (selectedSource === 'selected') {
            items = await eagle.item.getSelected();
            if (!items || items.length === 0) {
                showToast('请先在 Eagle 中选择要导出的素材', 'error');
                btn.disabled = false;
                btnText.textContent = '导出';
                return;
            }
        } else {
            items = await eagle.item.get();
        }
        
        console.log(`Exporting ${items.length} items with fields:`, fields);
        console.log(`Image mode: ${selectedImageMode}`);
        
        let exportedFileName = '';
        
        // Handle different export modes
        if (selectedFormat === 'json' && selectedImageMode === 'package') {
            // Package mode with grouping: Create single ZIP with organized folders
            const groups = await groupItemsByFolderPrefix(items);
            const groupKeys = Object.keys(groups);
            
            console.log(`[Export] Grouped into ${groupKeys.length} categories:`, groupKeys);
            
            // Add visual feedback
            const groupNames = groupKeys.join(', ');
            showToast(`正在处理 ${groupKeys.length} 个分组: ${groupNames}`, 'success');
            
            // Generate datetime string for filenames
            const now = new Date();
            const datetime = now.getFullYear() +
                String(now.getMonth() + 1).padStart(2, '0') +
                String(now.getDate()).padStart(2, '0') + '_' +
                String(now.getHours()).padStart(2, '0') +
                String(now.getMinutes()).padStart(2, '0') +
                String(now.getSeconds()).padStart(2, '0');
            
            console.log(`[Export] Total items: ${items.length} across ${groupKeys.length} groups`);
            
            if (groupKeys.length === 1) {
                // Single group: download the group ZIP directly (no outer wrapper)
                const groupKey = groupKeys[0];
                const groupItems = groups[groupKey];
                const sanitizedName = groupKey.replace(/[/\\?%*:|"<>]/g, '-');
                exportedFileName = `${sanitizedName}-${datetime}-${groupItems.length}.zip`;
                console.log(`[Export] Single group "${groupKey}", creating direct ZIP: ${exportedFileName}`);
                const extractedData = await extractItemData(groupItems, fields, false);
                await createDataPackage(groupItems, extractedData, exportedFileName);
            } else {
                // Multiple groups: wrap all group ZIPs inside one outer export ZIP
                exportedFileName = `export-${datetime}-${items.length}.zip`;
                console.log(`[Export] Multiple groups, creating unified package: ${exportedFileName}`);
                await createGroupedDataPackage(groups, groupKeys, fields, exportedFileName);
            }
            
            showToast(`✓ 导出完成！正在更新 ${items.length} 个素材的元数据...`, 'success');
            
            // Update metadata for all items with better error handling
            try {
                await updateExportedItemsMetadata(items);
                showToast(`✓ 全部完成！已为 ${items.length} 个素材添加标注、标签和评级`, 'success');
            } catch (error) {
                console.error('[Export] Metadata update failed:', error);
                showToast(`⚠ 导出成功，但元数据更新失败: ${error.message}`, 'error');
            }
            
        } else if (selectedFormat === 'json' && selectedImageMode === 'base64') {
            // Base64 mode: JSON with embedded images
            btnText.innerHTML = '<span class="loading"></span> 转换图片中...';
            const extractedData = await extractItemData(items, fields, true);
            const content = convertToJSON(extractedData);
            exportedFileName = await generateExportFilename(items, 'json');
            downloadFile(content, exportedFileName, 'application/json');
            showToast(`成功导出 ${items.length} 个素材（含图片）`, 'success');
            
            // Update metadata in background (non-blocking)
            updateExportedItemsMetadata(items).catch(error => {
                console.error('[Export] Background metadata update failed:', error);
            });
            
        } else {
            // Normal mode: JSON or CSV without images
            const extractedData = await extractItemData(items, fields, false);
            let content, mimeType;
            
            if (selectedFormat === 'json') {
                content = convertToJSON(extractedData);
                exportedFileName = await generateExportFilename(items, 'json');
                mimeType = 'application/json';
            } else {
                content = convertToCSV(extractedData);
                exportedFileName = await generateExportFilename(items, 'csv');
                mimeType = 'text/csv';
            }
            
            downloadFile(content, exportedFileName, mimeType);
            showToast(`成功导出 ${items.length} 个素材到 ${exportedFileName}`, 'success');
            
            // Update metadata in background (non-blocking)
            updateExportedItemsMetadata(items).catch(error => {
                console.error('[Export] Background metadata update failed:', error);
            });
        }
        
        console.log('Export completed:', exportedFileName);
        
    } catch (error) {
        console.error('Export failed:', error);
        showToast(`导出失败: ${error.message}`, 'error');
    } finally {
        // Reset button state
        const btn = document.querySelector('.export-btn');
        const btnText = document.getElementById('exportBtnText');
        btn.disabled = false;
        btnText.textContent = '导出';
    }
}

/**
 * Liquid Glass 自定义气泡：带 data-lg-tip 的元素悬停/聚焦时显示，替代原生 title。
 */
function initLgTooltips() {
    const tip = document.getElementById('lg-tooltip');
    if (!tip) return;

    let showTimer = null;
    let hideTimer = null;

    function clearTimers() {
        if (showTimer) {
            clearTimeout(showTimer);
            showTimer = null;
        }
        if (hideTimer) {
            clearTimeout(hideTimer);
            hideTimer = null;
        }
    }

    function hideNow() {
        clearTimers();
        tip.classList.remove('lg-tooltip--visible');
        tip.textContent = '';
    }

    function place(trigger) {
        const msg = trigger.getAttribute('data-lg-tip');
        if (!msg) return;

        tip.textContent = msg;
        tip.classList.add('lg-tooltip--visible');

        const margin = 10;
        const gap = 8;
        const tr = trigger.getBoundingClientRect();
        const tw = tip.offsetWidth;
        const th = tip.offsetHeight;

        if (tw < 8) {
            requestAnimationFrame(() => place(trigger));
            return;
        }

        let top = tr.bottom + gap;
        if (top + th > window.innerHeight - margin) {
            top = tr.top - th - gap;
        }
        if (top < margin) {
            top = Math.min(tr.bottom + gap, window.innerHeight - th - margin);
        }

        let left = tr.left + tr.width / 2 - tw / 2;
        left = Math.max(margin, Math.min(left, window.innerWidth - tw - margin));

        tip.style.left = `${Math.round(left)}px`;
        tip.style.top = `${Math.round(top)}px`;
    }

    function scheduleShow(trigger) {
        clearTimeout(showTimer);
        showTimer = setTimeout(() => {
            showTimer = null;
            place(trigger);
            requestAnimationFrame(() => place(trigger));
        }, 500);
    }

    function scheduleHide() {
        clearTimeout(hideTimer);
        hideTimer = setTimeout(() => {
            hideTimer = null;
            hideNow();
        }, 100);
    }

    document.addEventListener('mouseover', (e) => {
        const el = e.target.closest('[data-lg-tip]');
        if (!el || !el.getAttribute('data-lg-tip')) return;
        if (hideTimer) {
            clearTimeout(hideTimer);
            hideTimer = null;
        }
        scheduleShow(el);
    });

    document.addEventListener('mouseout', (e) => {
        const fromEl = e.target.closest('[data-lg-tip]');
        if (!fromEl) return;
        const to = e.relatedTarget;
        if (to && fromEl.contains(to)) return;
        scheduleHide();
    });

    document.addEventListener('focusin', (e) => {
        const el = e.target.closest('[data-lg-tip]');
        if (!el || !el.getAttribute('data-lg-tip')) return;
        if (!el.matches('button, a[href], input, select, textarea')) return;
        clearTimers();
        place(el);
        requestAnimationFrame(() => place(el));
    });

    document.addEventListener('focusout', (e) => {
        const to = e.relatedTarget;
        if (to && e.target.closest('[data-lg-tip]') && to.closest && to.closest('[data-lg-tip]')) {
            return;
        }
        scheduleHide();
    });

    window.addEventListener('scroll', hideNow, true);
    window.addEventListener('resize', hideNow);
}

initLgTooltips();