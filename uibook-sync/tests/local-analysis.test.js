'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
    extractMirrorData,
    sha256Buffer,
    validateLocalAnalysis
} = require('../js/local-analysis.js');

test('exposes the validator for Eagle page-script loading', () => {
    assert.equal(globalThis.UIBookLocalAnalysis.validateLocalAnalysis, validateLocalAnalysis);
});

function currentMirror(overrides = {}) {
    const fingerprint = sha256Buffer(Buffer.from('image'));
    return {
        schemaVersion: 4,
        producer: { name: 'eagle-uibook-vision-notes', release: '0.5.0' },
        sourceItemId: 'item-1',
        imageFingerprint: fingerprint,
        entityType: 'website',
        policyVersion: '2026-08-17.1',
        taxonomySnapshot: 'sha256:taxonomy',
        uiContext: { en: 'A landing page', zh: '落地页' },
        visibleText: ['Start now'],
        validation: {
            status: 'valid',
            policyVersion: '2026-08-17.1',
            taxonomySnapshot: 'sha256:taxonomy',
            issues: []
        },
        ...overrides
    };
}

function annotationFor(mirror) {
    return `## AI Screen Analysis\n\n## UIBook Mirror Data\n\n\`\`\`json\n${JSON.stringify(mirror)}\n\`\`\``;
}

test('extracts Mirror Data v4 from the annotation', () => {
    assert.equal(extractMirrorData(annotationFor(currentMirror())).schemaVersion, 4);
});

test('accepts an exact 0.5.0 analysis with matching item, entity, and image', () => {
    const mirror = currentMirror();
    const result = validateLocalAnalysis({
        annotation: annotationFor(mirror),
        itemId: 'item-1',
        entityType: 'website',
        imageFingerprint: mirror.imageFingerprint
    });
    assert.equal(result.ok, true);
    assert.equal(result.release, '0.5.0');
});

test('rejects old v3 data', () => {
    const mirror = currentMirror({ schemaVersion: 3 });
    const result = validateLocalAnalysis({ annotation: annotationFor(mirror), itemId: 'item-1', entityType: 'website', imageFingerprint: mirror.imageFingerprint });
    assert.equal(result.code, 'local_analysis_old_schema');
});

test('rejects another producer release', () => {
    const mirror = currentMirror({ producer: { name: 'eagle-uibook-vision-notes', release: '0.4.0' } });
    const result = validateLocalAnalysis({ annotation: annotationFor(mirror), itemId: 'item-1', entityType: 'website', imageFingerprint: mirror.imageFingerprint });
    assert.equal(result.code, 'local_analysis_unsupported_release');
});

test('rejects item, entity, fingerprint, and validation mismatches', () => {
    const mirror = currentMirror();
    assert.equal(validateLocalAnalysis({ annotation: annotationFor(mirror), itemId: 'other', entityType: 'website', imageFingerprint: mirror.imageFingerprint }).code, 'local_analysis_item_mismatch');
    assert.equal(validateLocalAnalysis({ annotation: annotationFor(mirror), itemId: 'item-1', entityType: 'section', imageFingerprint: mirror.imageFingerprint }).code, 'local_analysis_entity_mismatch');
    assert.equal(validateLocalAnalysis({ annotation: annotationFor(mirror), itemId: 'item-1', entityType: 'website', imageFingerprint: sha256Buffer(Buffer.from('changed')) }).code, 'local_analysis_image_changed');
    const invalid = currentMirror({ validation: { status: 'invalid', policyVersion: '2026-08-17.1', taxonomySnapshot: 'sha256:taxonomy', issues: [{ code: 'bad' }] } });
    assert.equal(validateLocalAnalysis({ annotation: annotationFor(invalid), itemId: 'item-1', entityType: 'website', imageFingerprint: invalid.imageFingerprint }).code, 'local_analysis_invalid');
});
