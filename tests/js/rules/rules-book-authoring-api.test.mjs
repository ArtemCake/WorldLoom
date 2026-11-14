// tests/js/rules/rules-book-authoring-api.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';

import { createBookAuthoringApi } from '../../../frontend/src/js/features/rules/books/book-authoring-api.js';
import { createRulesRequester } from '../../../frontend/src/js/features/rules/rules-http.js';

const BOOK_ID = '11111111-1111-4111-8111-111111111111';
const SYSTEM_ID = '22222222-2222-4222-8222-222222222222';

function recorder(result = {}) {
    const calls = [];
    const api = createBookAuthoringApi(async (path, options) => {
        calls.push({ path, options });
        return result;
    });

    return { api, calls };
}

test('Авторский список всегда запрашивает собственные книги', async () => {
    const { api, calls } = recorder();
    const controller = new AbortController();

    await api.list({}, { signal: controller.signal });

    const url = new URL(calls[0].path, 'https://worldloom.test');

    assert.equal(url.pathname, '/rules/books/authoring');
    assert.equal(url.searchParams.get('scope'), 'mine');
    assert.strictEqual(calls[0].options.signal, controller.signal);
});

test('Фильтры системы, поиска и продолжения передаются без изменения исходного объекта', async () => {
    const { api, calls } = recorder();
    const filters = { system_id: SYSTEM_ID, after: BOOK_ID, q: '100% & правила', limit: 2 };
    const original = structuredClone(filters);

    await api.list(filters);

    const url = new URL(calls[0].path, 'https://worldloom.test');

    assert.equal(url.searchParams.get('system_id'), SYSTEM_ID);
    assert.equal(url.searchParams.get('after'), BOOK_ID);
    assert.equal(url.searchParams.get('q'), '100% & правила');
    assert.equal(url.searchParams.get('limit'), '2');
    assert.deepEqual(filters, original);
});

test('Некорректные или расширяющие доступ фильтры не отправляются', () => {
    const { api, calls } = recorder();

    assert.throws(() => api.list(null), TypeError);
    assert.throws(() => api.list({ scope: 'available' }), TypeError);
    assert.throws(() => api.list({ owner_id: BOOK_ID }), TypeError);
    assert.throws(() => api.list({ system_id: '../system' }), TypeError);
    assert.throws(() => api.list({ limit: '2' }), TypeError);
    assert.equal(calls.length, 0);
});

test('Редактор запрашивает карточку и черновик выбранной книги', async () => {
    const expected = { book: { id: BOOK_ID }, draft: { revision: 3 } };
    const { api, calls } = recorder(expected);

    const result = await api.getEditor(BOOK_ID);

    assert.equal(calls[0].path, `/rules/books/${BOOK_ID}/editor`);
    assert.strictEqual(result, expected);
    assert.throws(() => api.getEditor('../book'), TypeError);
    assert.equal(calls.length, 1);
});

test('Новые пути проходят действующую проверку HTTP-клиента', async () => {
    const paths = [];
    const request = createRulesRequester({
        async sessionFetch(path) {
            paths.push(path);
            return new Response(JSON.stringify({ items: [] }), {
                status: 200,
                headers: { 'Content-Type': 'application/json' }
            });
        }
    });
    const api = createBookAuthoringApi(request);

    await api.list();
    await api.getEditor(BOOK_ID);

    assert.equal(paths.length, 2);
    assert.equal(paths[0], '/rules/books/authoring?scope=mine');
    assert.equal(paths[1], `/rules/books/${BOOK_ID}/editor`);
});
