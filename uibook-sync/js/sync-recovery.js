/* UMD: Eagle loads this as a page script; Node tests load it with require(). */
(function initSyncRecovery(root, factory) {
    'use strict';
    const api = factory();
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = api;
    }
    root.UIBookSyncRecovery = api;
}(typeof globalThis !== 'undefined' ? globalThis : window, function buildSyncRecovery() {
    'use strict';

    function createTimeoutError(timeoutMs, url) {
        const error = new Error(`请求等待超过 ${Math.round(timeoutMs / 1000)} 秒，云端结果待确认：${url}`);
        error.name = 'UIBookSyncTimeoutError';
        error.code = 'sync_result_unknown';
        error.timeoutMs = timeoutMs;
        return error;
    }

    function isTimeoutError(error) {
        return Boolean(error && (
            error.name === 'UIBookSyncTimeoutError'
            || error.code === 'sync_result_unknown'
            || (error.name === 'AbortError' && error.timeoutMs)
        ));
    }

    function isTimeoutMessage(message) {
        const value = String(message || '');
        return value.includes('请求超时')
            || value.includes('云端结果待确认')
            || value.includes('请求等待超过');
    }

    function isStatusLookupUnsupported(response, payload) {
        const status = Number(response && response.status);
        const value = payload && typeof payload === 'object' ? payload : {};
        const message = String(value.error || value.message || '').toLowerCase();
        if ([404, 405, 415].includes(status)) return true;
        return [400, 500].includes(status) && (
            message.includes('missing content type')
            || message.includes('multipart/form-data')
            || message.includes('missing required fields')
        );
    }

    function createStatusLookupUnsupportedError(status, message) {
        const error = new Error(message || `Status lookup is not supported (${status || 'unknown'})`);
        error.name = 'UIBookStatusLookupUnsupportedError';
        error.code = 'status_lookup_unsupported';
        error.status = status || null;
        return error;
    }

    function isStatusLookupUnsupportedError(error) {
        return Boolean(error && (
            error.name === 'UIBookStatusLookupUnsupportedError'
            || error.code === 'status_lookup_unsupported'
        ));
    }

    function buildStatusUrl(endpointUrl, sourceItemId, entityType) {
        const url = new URL(endpointUrl);
        url.searchParams.set('operation', 'status');
        url.searchParams.set('sourceItemId', String(sourceItemId || ''));
        url.searchParams.set('entityType', String(entityType || ''));
        return url.toString();
    }

    function normalizeStatusResponse(payload, fallback) {
        const value = payload && typeof payload === 'object' ? payload : {};
        const context = fallback && typeof fallback === 'object' ? fallback : {};
        if (value.success !== true || (value.status !== 'found' && value.status !== 'not_found')) {
            return { ok: false, error: value.error || 'Invalid status response' };
        }
        if (value.status === 'not_found' || value.found === false) {
            return {
                ok: true,
                found: false,
                sourceItemId: value.sourceItemId || context.sourceItemId || null,
                entityType: value.entityType || context.entityType || null
            };
        }
        if (!value.id) {
            return { ok: false, error: 'Status response is missing remote id' };
        }
        const analysisMode = context.analysisMode === 'local_latest' ? 'local_latest' : 'cloud';
        return {
            ok: true,
            found: true,
            id: value.id,
            imageUrl: value.imageUrl || null,
            sourceItemId: value.sourceItemId || context.sourceItemId || null,
            entityType: value.entityType || context.entityType || null,
            analysisSource: analysisMode === 'local_latest' ? 'eagle_visual' : 'lovable_ai',
            analysisRelease: analysisMode === 'local_latest' ? (context.analysisRelease || null) : null
        };
    }

    return {
        buildStatusUrl,
        createStatusLookupUnsupportedError,
        createTimeoutError,
        isStatusLookupUnsupported,
        isStatusLookupUnsupportedError,
        isTimeoutError,
        isTimeoutMessage,
        normalizeStatusResponse
    };
}));
