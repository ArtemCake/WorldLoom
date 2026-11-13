// tests/js/rules/rules-api.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';

import { createSessionClient } from '../../../frontend/src/js/shared/http/session-client.js';
import { catalogQuery, createRulesRequester, RulesRequestError } from '../../../frontend/src/js/features/rules/rules-http.js';
import { createArticlesApi } from '../../../frontend/src/js/features/rules/articles-api.js';
import { createBooksApi } from '../../../frontend/src/js/features/rules/books-api.js';

const OBJECT_ID = '11111111-1111-4111-8111-111111111111';
const VERSION_ID = '22222222-2222-4222-8222-222222222222';

function jsonResponse(data, status = 200, headers = {}) {
    return new Response(JSON.stringify(data), {
        status,
        headers: { 'Content-Type': 'application/json', ...headers }
    });
}

function requesterWith(response) {
    const calls = [];
    const client = {
        async sessionFetch(path, options) {
            calls.push({ path, options });
            return response;
        }
    };

    return { request: createRulesRequester(client), calls };
}

test('Фильтры каталога кодируются без изменения поисковой строки', () => {
    const query = catalogQuery({ scope: 'mine', limit: 2, q: '100%_ & текст', after: OBJECT_ID });
    const params = new URLSearchParams(query.slice(1));

    assert.equal(params.get('q'), '100%_ & текст');
    assert.equal(params.get('scope'), 'mine');
    assert.equal(params.get('limit'), '2');
    assert.equal(params.get('after'), OBJECT_ID);
});

test('Неизвестные и некорректные фильтры отклоняются', () => {
    assert.throws(() => catalogQuery({ owner_id: OBJECT_ID }), TypeError);
    assert.throws(() => catalogQuery({ limit: '2' }), TypeError);
    assert.throws(() => catalogQuery({ scope: 'all' }), TypeError);
    assert.throws(() => catalogQuery({ after: '../other' }), TypeError);
    assert.throws(() => catalogQuery({ q: '   ' }), TypeError);
});

test('Клиент статьи передаёт ревизию и документ без изменений', async () => {
    const calls = [];
    const api = createArticlesApi(async (path, options) => {
        calls.push({ path, options });
        return { revision: 8 };
    });
    const payload = { expected_revision: 7, content: { title: 'Проверки', body: 'Правило' } };

    const result = await api.saveDraft(OBJECT_ID, payload);

    assert.equal(calls[0].path, `/rules/articles/${OBJECT_ID}/draft`);
    assert.equal(calls[0].options.method, 'PUT');
    assert.strictEqual(calls[0].options.body, payload);
    assert.equal(payload.expected_revision, 7);
    assert.equal(result.revision, 8);
});

test('Клиент книги использует отдельный маршрут чтения', async () => {
    const calls = [];
    const controller = new AbortController();
    const api = createBooksApi(async (path, options) => {
        calls.push({ path, options });
        return {};
    });

    await api.read(OBJECT_ID, VERSION_ID, { signal: controller.signal });

    assert.equal(calls[0].path, `/rules/books/${OBJECT_ID}/versions/${VERSION_ID}/reading`);
    assert.strictEqual(calls[0].options.signal, controller.signal);
});

test('Идентификатор не может изменить путь маршрута', () => {
    const api = createArticlesApi(async () => assert.fail('Запрос не должен отправляться'));

    assert.throws(() => api.getDraft('../books'), TypeError);
    assert.throws(() => api.getVersion(OBJECT_ID, 'version?other=1'), TypeError);
});

test('Чтение разрешает восстановление сессии', async () => {
    const { request, calls } = requesterWith(jsonResponse({ items: [], next_after: null }));

    await request('/rules/articles');

    assert.equal(calls[0].options.retryAfterRefresh, true);
    assert.equal(calls[0].options.headers.get('Accept'), 'application/json');
});

test('Изменение запрещает автоматический повтор', async () => {
    const { request, calls } = requesterWith(jsonResponse({ revision: 2 }));

    await request(`/rules/books/${OBJECT_ID}/draft`, { method: 'PUT', body: { expected_revision: 1 } });

    assert.equal(calls[0].options.retryAfterRefresh, false);
    assert.equal(calls[0].options.headers.get('Content-Type'), 'application/json');
    assert.deepEqual(JSON.parse(calls[0].options.body), { expected_revision: 1 });
});

test('Конфликт возвращается вызывающему коду без повтора', async () => {
    const { request, calls } = requesterWith(jsonResponse({ detail: 'Ревизия устарела' }, 409));

    await assert.rejects(
        request(`/rules/articles/${OBJECT_ID}/publish`, { method: 'POST', body: { expected_revision: 1 } }),
        (error) => error instanceof RulesRequestError && error.status === 409 && !error.uncertain
    );

    assert.equal(calls.length, 1);
});

test('Потеря ответа изменяющего запроса оставляет результат неизвестным', async () => {
    let calls = 0;
    const request = createRulesRequester({
        async sessionFetch() {
            calls += 1;
            throw new TypeError('Соединение прервано');
        }
    });

    await assert.rejects(
        request('/rules/articles', { method: 'POST', body: { slug: 'test' } }),
        (error) => error instanceof RulesRequestError && error.uncertain && error.status === 0
    );

    assert.equal(calls, 1);
});

test('Ошибка сериализации возникает до отправки запроса', async () => {
    let calls = 0;
    const request = createRulesRequester({ sessionFetch: async () => { calls += 1; } });
    const payload = {};
    payload.self = payload;

    await assert.rejects(request('/rules/books', { method: 'POST', body: payload }), TypeError);
    assert.equal(calls, 0);
});

test('HTML вместо успешного JSON не подтверждает сохранение', async () => {
    const response = new Response('<html>Ошибка</html>', { headers: { 'Content-Type': 'text/html' } });
    const { request } = requesterWith(response);

    await assert.rejects(
        request('/rules/books', { method: 'POST', body: {} }),
        (error) => error instanceof RulesRequestError && error.uncertain
    );
});

test('Повреждённый JSON не подтверждает сохранение', async () => {
    const response = new Response('{', { headers: { 'Content-Type': 'application/json' } });
    const { request } = requesterWith(response);

    await assert.rejects(
        request('/rules/articles', { method: 'POST', body: {} }),
        (error) => error instanceof RulesRequestError && error.uncertain
    );
});

test('Внешний адрес отклоняется до обращения к клиенту сессии', async () => {
    let calls = 0;
    const request = createRulesRequester({ sessionFetch: async () => { calls += 1; } });

    await assert.rejects(request('https://other.test/rules/articles'), TypeError);
    assert.equal(calls, 0);
});

test('Заранее отменённый запрос не отправляется', async () => {
    let calls = 0;
    const controller = new AbortController();
    const request = createRulesRequester({ sessionFetch: async () => { calls += 1; } });
    controller.abort(new Error('Отмена'));

    await assert.rejects(request('/rules/books', { signal: controller.signal }), /Отмена/u);
    assert.equal(calls, 0);
});

test('Настоящий клиент сессии обновляет cookie-сессию и повторяет чтение', async () => {
    const paths = [];
    let csrfToken = 'initial-csrf';
    const responses = [
        jsonResponse({ detail: 'Войдите снова' }, 401, { 'WWW-Authenticate': 'Bearer' }),
        jsonResponse({}, 200, { 'X-CSRF-Token': 'updated-csrf' }),
        jsonResponse({ items: [], next_after: null })
    ];
    const client = createSessionClient({
        origin: 'https://worldloom.test',
        getCsrfToken: () => csrfToken,
        setCsrfToken: (value) => { csrfToken = value; },
        fetchImpl: async (url, options) => {
            paths.push(new URL(url).pathname);
            if (options.method === 'POST') assert.equal(options.headers.get('X-CSRF-Token'), 'initial-csrf');
            assert.equal(options.credentials, 'same-origin');
            return responses.shift();
        }
    });

    const result = await createRulesRequester(client)('/rules/articles');

    assert.deepEqual(paths, ['/rules/articles', '/auth/refresh', '/rules/articles']);
    assert.equal(csrfToken, 'updated-csrf');
    assert.deepEqual(result.items, []);
});

test('Настоящий клиент сессии не повторяет публикацию после 401', async () => {
    const paths = [];
    const client = createSessionClient({
        origin: 'https://worldloom.test',
        getCsrfToken: () => 'csrf',
        setCsrfToken: () => {},
        fetchImpl: async (url, options) => {
            paths.push(new URL(url).pathname);
            assert.equal(options.headers.get('X-CSRF-Token'), 'csrf');
            return jsonResponse({ detail: 'Нужна авторизация' }, 401, { 'WWW-Authenticate': 'Bearer' });
        }
    });
    const request = createRulesRequester(client);

    await assert.rejects(
        request(`/rules/books/${OBJECT_ID}/publish`, { method: 'POST', body: { expected_revision: 1 } }),
        (error) => error.status === 401 && !error.uncertain
    );

    assert.deepEqual(paths, [`/rules/books/${OBJECT_ID}/publish`]);
});
