// tests/js/vendor-assets.test.mjs

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { loadVendorAssets, vendorAssets } from '../../tools/vendor-assets.js';

const expectedFiles = [
    'vendor/htmx/2.0.4/htmx.min.js',
    'vendor/htmx-json-enc/2.0.1/json-enc.js'
];

test('Библиотеки загружаются из установленных пакетов', () => {
    const assets = loadVendorAssets();

    assert.deepEqual(assets.map((asset) => asset.fileName), expectedFiles);

    for (const asset of assets) {
        assert.equal(asset.type, 'asset');
        assert.ok(Buffer.isBuffer(asset.source));
        assert.ok(asset.source.length > 0);
    }
});

test('Содержимое HTMX переносится без изменения', () => {
    const source = new URL('../../node_modules/htmx.org/dist/htmx.min.js', import.meta.url);
    const [asset] = loadVendorAssets();

    assert.deepEqual(asset.source, readFileSync(source));
});

test('Содержимое расширения переносится без изменения', () => {
    const source = new URL('../../node_modules/htmx-ext-json-enc/json-enc.js', import.meta.url);
    const [, asset] = loadVendorAssets();

    assert.deepEqual(asset.source, readFileSync(source));
});

test('Плагин включает обе библиотеки в сборку', () => {
    const plugin = vendorAssets();
    const emitted = [];

    plugin.generateBundle.call({
        emitFile(asset) {
            emitted.push(asset);
        }
    });

    assert.equal(plugin.apply, 'build');
    assert.deepEqual(emitted.map((asset) => asset.fileName), expectedFiles);
});

test('Базовый шаблон использует локальные библиотеки в правильном порядке', () => {
    const path = new URL('../../frontend/templates/base.html', import.meta.url);
    const template = readFileSync(path, 'utf8');
    const core = "{{ static_url('vendor/htmx/2.0.4/htmx.min.js') }}";
    const extension = "{{ static_url('vendor/htmx-json-enc/2.0.1/json-enc.js') }}";

    assert.ok(template.includes(core));
    assert.ok(template.includes(extension));
    assert.ok(template.indexOf(core) < template.indexOf(extension));
    assert.equal(template.split(core).length - 1, 1);
    assert.equal(template.split(extension).length - 1, 1);
    assert.equal(template.includes('https://unpkg.com/htmx.org'), false);
    assert.equal(template.includes('https://unpkg.com/htmx-ext-json-enc'), false);
});
