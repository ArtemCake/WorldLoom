// tests/js/rules/rules-system-books-api.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';

import { createBooksApi } from '../../../frontend/src/js/features/rules/books/books-api.js';
import { createRulesRequester } from '../../../frontend/src/js/features/rules/rules-http.js';

const BOOK_ID = '11111111-1111-4111-8111-111111111111';
const SYSTEM_ID = '22222222-2222-4222-8222-222222222222';

function recorder(result = {}) {
    const calls = [];
    const api = createBooksApi(async (path, options) => {
        calls.push({ path, options });
        return result;
    });

    return { api, calls };
}

test('Каталог передаёт систему вместе с поиском, областью доступа и курсором', async () => {
    const { api, calls } = recorder();
    const filters = { system_id: SYSTEM_ID, scope: 'mine', q: '100% & правила', after: BOOK_ID, limit: 2 };
    const original = structuredClone(filters);

    await api.list(filters);

    const url = new URL(calls[0].path, 'https://worldloom.test');

    assert.equal(url.pathname, '/rules/books');
    assert.equal(url.searchParams.get('system_id'), SYSTEM_ID);
    assert.equal(url.searchParams.get('scope'), 'mine');
    assert.equal(url.searchParams.get('q'), '100% & правила');
    assert.equal(url.searchParams.get('after'), BOOK_ID);
    assert.equal(url.searchParams.get('limit'), '2');
    assert.deepEqual(filters, original);
});

test('Общий каталог без системы сохраняет прежний путь', async () => {
    const { api, calls } = recorder();

    await api.list();

    assert.equal(calls[0].path, '/rules/books');
});

test('Ошибочные фильтры не отправляются', () => {
    const { api, calls } = recorder();

    assert.throws(() => api.list(null), TypeError);
    assert.throws(() => api.list({ system_id: '../other' }), TypeError);
    assert.throws(() => api.list({ owner_id: SYSTEM_ID }), TypeError);
    assert.throws(() => api.list({ limit: '2' }), TypeError);
    assert.equal(calls.length, 0);
});

test('Создание передаёт систему и исходное содержимое без изменений', async () => {
    const { api, calls } = recorder();
    const payload = { system_id: SYSTEM_ID, slug: 'new-book', content: { title: 'Правила' } };

    await api.create(payload);

    assert.equal(calls[0].path, '/rules/books');
    assert.equal(calls[0].options.method, 'POST');
    assert.strictEqual(calls[0].options.body, payload);
});

test('Создание без системы отклоняется до HTTP-запроса', () => {
    const { api, calls } = recorder();

    assert.throws(() => api.create({ slug: 'unassigned-book' }), TypeError);
    assert.equal(calls.length, 0);
});

test('Назначение передаёт текущую ревизию и возвращает серверную', async () => {
    const { api, calls } = recorder({ draft_revision: 8 });
    const payload = { system_id: SYSTEM_ID, expected_revision: 7 };
    const controller = new AbortController();

    const result = await api.assignSystem(BOOK_ID, payload, { signal: controller.signal });

    assert.equal(calls[0].path, `/rules/books/${BOOK_ID}/system`);
    assert.equal(calls[0].options.method, 'PUT');
    assert.strictEqual(calls[0].options.body, payload);
    assert.strictEqual(calls[0].options.signal, controller.signal);
    assert.equal(payload.expected_revision, 7);
    assert.equal(result.draft_revision, 8);
});

test('Назначение проверяет оба идентификатора до отправки', () => {
    const { api, calls } = recorder();

    assert.throws(() => api.assignSystem('../book', { system_id: SYSTEM_ID }), TypeError);
    assert.throws(() => api.assignSystem(BOOK_ID, { system_id: 'invalid' }), TypeError);
    assert.equal(calls.length, 0);
});

test('Конфликт назначения не повторяет изменяющий запрос', async () => {
    const calls = [];
    const request = createRulesRequester({
        async sessionFetch(path, options) {
            calls.push({ path, options });
            return new Response(JSON.stringify({ detail: 'Конфликт назначения' }), {
                status: 409,
                headers: { 'Content-Type': 'application/json' }
            });
        }
    });
    const api = createBooksApi(request);

    await assert.rejects(
        api.assignSystem(BOOK_ID, { system_id: SYSTEM_ID, expected_revision: 1 }),
        (error) => error.status === 409 && !error.uncertain
    );

    assert.equal(calls.length, 1);
    assert.equal(calls[0].options.retryAfterRefresh, false);
});

test('Потеря ответа назначения оставляет результат неопределённым', async () => {
    let calls = 0;
    const request = createRulesRequester({
        async sessionFetch() {
            calls += 1;
            throw new TypeError('Сеть недоступна');
        }
    });
    const api = createBooksApi(request);

    await assert.rejects(
        api.assignSystem(BOOK_ID, { system_id: SYSTEM_ID, expected_revision: 1 }),
        (error) => error.uncertain
    );

    assert.equal(calls, 1);
});
