/* UMD: Eagle loads this as a page script; Node tests load it with require(). */
(function initLocalAnalysis(root, factory) {
    'use strict';
    const api = factory(require('crypto'));
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = api;
    }
    root.UIBookLocalAnalysis = api;
}(typeof globalThis !== 'undefined' ? globalThis : window, function buildLocalAnalysis(crypto) {
    'use strict';

const MIRROR_SCHEMA_VERSION = 4;
const PRODUCER_NAME = 'eagle-uibook-vision-notes';
const PRODUCER_RELEASE = '0.5.0';
const MIRROR_HEADING = '## UIBook Mirror Data';

function sha256Buffer(value) {
    const buffer = Buffer.isBuffer(value) ? value : Buffer.from(value);
    return `sha256:${crypto.createHash('sha256').update(buffer).digest('hex')}`;
}

function extractMirrorData(annotation) {
    const text = String(annotation || '');
    const headingIndex = text.indexOf(MIRROR_HEADING);
    if (headingIndex < 0) return null;
    const tail = text.slice(headingIndex + MIRROR_HEADING.length);
    const match = tail.match(/```json\s*([\s\S]*?)\s*```/i);
    if (!match) return null;
    try {
        const value = JSON.parse(match[1]);
        return value && typeof value === 'object' && !Array.isArray(value) ? value : null;
    } catch (error) {
        return null;
    }
}

function waiting(code, message, mirror) {
    return { ok: false, code, message, mirror: mirror || null };
}

function validateLocalAnalysis({ annotation, itemId, entityType, imageFingerprint }) {
    const mirror = extractMirrorData(annotation);
    if (!mirror) {
        return waiting('local_analysis_missing', '尚未找到 Eagle Visual 最新版分析');
    }
    if (mirror.schemaVersion !== MIRROR_SCHEMA_VERSION) {
        return waiting('local_analysis_old_schema', `需要 Mirror v${MIRROR_SCHEMA_VERSION}，当前为 v${mirror.schemaVersion || '未知'}`, mirror);
    }
    const producer = mirror.producer && typeof mirror.producer === 'object' ? mirror.producer : {};
    if (producer.name !== PRODUCER_NAME || producer.release !== PRODUCER_RELEASE) {
        return waiting('local_analysis_unsupported_release', `需要 Eagle Visual ${PRODUCER_RELEASE} 最新版分析`, mirror);
    }
    if (String(mirror.sourceItemId || '') !== String(itemId || '')) {
        return waiting('local_analysis_item_mismatch', '本地分析对应的 Eagle item 不一致', mirror);
    }
    if (!['website', 'section'].includes(mirror.entityType) || mirror.entityType !== entityType) {
        return waiting('local_analysis_entity_mismatch', '本地分析的 website / section 类型与同步规则不一致', mirror);
    }
    if (!/^sha256:[a-f0-9]{64}$/i.test(String(mirror.imageFingerprint || '')) || mirror.imageFingerprint !== imageFingerprint) {
        return waiting('local_analysis_image_changed', '原图已变化，需要用 Eagle Visual 最新版重新分析', mirror);
    }
    if (!Array.isArray(mirror.visibleText)) {
        return waiting('local_analysis_invalid', '本地分析缺少结构化 visibleText', mirror);
    }
    if (!mirror.uiContext || typeof mirror.uiContext.en !== 'string' || !mirror.uiContext.en.trim()) {
        return waiting('local_analysis_invalid', '本地分析缺少 uiContext.en', mirror);
    }
    const validation = mirror.validation && typeof mirror.validation === 'object' ? mirror.validation : {};
    const issues = Array.isArray(validation.issues) ? validation.issues : [];
    if (
        validation.status !== 'valid'
        || issues.length > 0
        || validation.policyVersion !== mirror.policyVersion
        || validation.taxonomySnapshot !== mirror.taxonomySnapshot
    ) {
        return waiting('local_analysis_invalid', '本地分析未通过当前 validation', mirror);
    }
    return { ok: true, mirror, release: PRODUCER_RELEASE };
}

    return {
        MIRROR_SCHEMA_VERSION,
        PRODUCER_NAME,
        PRODUCER_RELEASE,
        extractMirrorData,
        sha256Buffer,
        validateLocalAnalysis
    };
}));
