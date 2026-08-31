'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
    buildStatusUrl,
    createStatusLookupUnsupportedError,
    createTimeoutError,
    isStatusLookupUnsupported,
    isStatusLookupUnsupportedError,
    isTimeoutError,
    isTimeoutMessage,
    normalizeStatusResponse
} = require('../js/sync-recovery.js');

test('exposes recovery helpers for Eagle page-script loading', () => {
    assert.equal(globalThis.UIBookSyncRecovery.buildStatusUrl, buildStatusUrl);
});

test('builds an authenticated status lookup URL without changing the endpoint path', () => {
    const result = new URL(buildStatusUrl('https://example.test/functions/v1/eagle-sync', 'item 1', 'website'));
    assert.equal(result.pathname, '/functions/v1/eagle-sync');
    assert.equal(result.searchParams.get('operation'), 'status');
    assert.equal(result.searchParams.get('sourceItemId'), 'item 1');
    assert.equal(result.searchParams.get('entityType'), 'website');
});

test('classifies explicit and legacy timeout errors', () => {
    const error = createTimeoutError(180000, 'https://example.test/eagle-sync');
    assert.equal(isTimeoutError(error), true);
    assert.equal(error.code, 'sync_result_unknown');
    assert.equal(isTimeoutMessage(error.message), true);
    assert.equal(isTimeoutMessage('请求超时 (60s)：https://example.test/eagle-sync'), true);
});

test('detects the old POST-only edge function without treating arbitrary 500s as unsupported', () => {
    assert.equal(isStatusLookupUnsupported({ status: 405 }, {}), true);
    assert.equal(isStatusLookupUnsupported({ status: 500 }, { error: 'Missing content type' }), true);
    assert.equal(isStatusLookupUnsupported({ status: 400 }, { error: 'Missing required fields: image, thumbnail' }), true);
    assert.equal(isStatusLookupUnsupported({ status: 500 }, { error: 'Database unavailable' }), false);

    const error = createStatusLookupUnsupportedError(500, 'Missing content type');
    assert.equal(isStatusLookupUnsupportedError(error), true);
    assert.equal(error.code, 'status_lookup_unsupported');
});

test('normalizes found and not-found status responses', () => {
    assert.deepEqual(
        normalizeStatusResponse(
            { success: true, status: 'found', found: true, id: 'remote-1', entityType: 'section' },
            { sourceItemId: 'item-1', entityType: 'section', analysisMode: 'cloud' }
        ),
        {
            ok: true,
            found: true,
            id: 'remote-1',
            imageUrl: null,
            sourceItemId: 'item-1',
            entityType: 'section',
            analysisSource: 'lovable_ai',
            analysisRelease: null
        }
    );
    assert.equal(
        normalizeStatusResponse(
            { success: true, status: 'not_found', found: false },
            { sourceItemId: 'item-1', entityType: 'website' }
        ).found,
        false
    );
});

test('rejects malformed found responses', () => {
    assert.equal(normalizeStatusResponse({ success: true, status: 'found', found: true }, {}).ok, false);
});
