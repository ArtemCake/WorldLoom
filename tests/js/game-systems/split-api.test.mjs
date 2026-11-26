// tests/js/game-systems/split-api.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';

import { createTextApi } from '../../../frontend/src/js/features/game-systems/api/text-api.js';
import { createMechanicApi } from '../../../frontend/src/js/features/game-systems/api/mechanic-api.js';
import { createVersionApi } from '../../../frontend/src/js/features/game-systems/api/version-api.js';

const SYSTEM_ID = '11111111-1111-4111-8111-111111111111';
const VERSION_ID = '22222222-2222-4222-8222-222222222222';

function recorder(response = { ok: true }) {
    const calls = [];

    const request = async (path, method = 'GET', payload) => {
        calls.push({ path, method, payload });
        return response;
    };

    return { request, calls };
}

// ── Текст ─────────────────────────────────────────────────────────────

test('Текстовый черновик использует админские маршруты и методы', async () => {
    const { request, calls } = recorder();
    const api = createTextApi(request);
    const text = { schema_version: 1, chapters: { main: { title: 'Титул', body: 'Текст' } } };

    await api.getDraft(SYSTEM_ID);
    await api.createDraft(SYSTEM_ID, { text });
    await api.updateDraft(SYSTEM_ID, { expected_revision: 4, text });

    assert.deepEqual(calls.map((call) => [call.method, call.path]), [
        ['GET', `/admin/game-systems/${SYSTEM_ID}/text/draft`],
        ['POST', `/admin/game-systems/${SYSTEM_ID}/text/draft`],
        ['PATCH', `/admin/game-systems/${SYSTEM_ID}/text/draft`]
    ]);
    assert.deepEqual(calls[1].payload, { text });
    assert.deepEqual(calls[2].payload, { expected_revision: 4, text });
});

test('Публикация текста отправляет только ожидаемую ревизию', async () => {
    const { request, calls } = recorder();
    const api = createTextApi(request);

    await api.publish(SYSTEM_ID, { expected_revision: 7 });

    assert.equal(calls[0].method, 'POST');
    assert.equal(calls[0].path, `/admin/game-systems/${SYSTEM_ID}/text/publish`);
    assert.deepEqual(calls[0].payload, { expected_revision: 7 });
});

test('Чтение версий текста идёт по публичным маршрутам', async () => {
    const { request, calls } = recorder();
    const api = createTextApi(request);

    await api.getLatest(SYSTEM_ID);
    await api.listVersions(SYSTEM_ID);
    await api.listVersions(SYSTEM_ID, { limit: 50, before: 12 });
    await api.getVersion(SYSTEM_ID, VERSION_ID);

    assert.deepEqual(calls.map((call) => call.path), [
        `/game-systems/items/${SYSTEM_ID}/text/latest`,
        `/game-systems/items/${SYSTEM_ID}/text/versions?limit=20`,
        `/game-systems/items/${SYSTEM_ID}/text/versions?limit=50&before=12`,
        `/game-systems/items/${SYSTEM_ID}/text/versions/${VERSION_ID}`
    ]);
    assert.ok(calls.every((call) => call.method === 'GET'));
});

// ── Механика ──────────────────────────────────────────────────────────

test('Механический черновик использует админские маршруты механики', async () => {
    const { request, calls } = recorder();
    const api = createMechanicApi(request);
    const mechanic = { schema_version: 1, calculations: { attributes: {}, derived: {} }, initial_attributes: {}, resources: {} };

    await api.getDraft(SYSTEM_ID);
    await api.createDraft(SYSTEM_ID, { mechanic });
    await api.updateDraft(SYSTEM_ID, { expected_revision: 2, mechanic });
    await api.publish(SYSTEM_ID, { expected_revision: 2 });

    assert.deepEqual(calls.map((call) => [call.method, call.path]), [
        ['GET', `/admin/game-systems/${SYSTEM_ID}/mechanic/draft`],
        ['POST', `/admin/game-systems/${SYSTEM_ID}/mechanic/draft`],
        ['PATCH', `/admin/game-systems/${SYSTEM_ID}/mechanic/draft`],
        ['POST', `/admin/game-systems/${SYSTEM_ID}/mechanic/publish`]
    ]);
    assert.deepEqual(calls[2].payload, { expected_revision: 2, mechanic });
});

test('Чтение версий механики идёт по публичным маршрутам', async () => {
    const { request, calls } = recorder();
    const api = createMechanicApi(request);

    await api.getLatest(SYSTEM_ID);
    await api.listVersions(SYSTEM_ID, { limit: 30 });
    await api.getVersion(SYSTEM_ID, VERSION_ID);

    assert.deepEqual(calls.map((call) => call.path), [
        `/game-systems/items/${SYSTEM_ID}/mechanic/latest`,
        `/game-systems/items/${SYSTEM_ID}/mechanic/versions?limit=30`,
        `/game-systems/items/${SYSTEM_ID}/mechanic/versions/${VERSION_ID}`
    ]);
});

// ── Комплект ──────────────────────────────────────────────────────────

test('Публикация комплекта отправляет обе ожидаемые ревизии', async () => {
    const { request, calls } = recorder();
    const api = createVersionApi(request);

    await api.publish(SYSTEM_ID, { expected_mechanic_revision: 6, expected_text_revision: 9 });

    assert.equal(calls[0].method, 'POST');
    assert.equal(calls[0].path, `/admin/game-systems/${SYSTEM_ID}/versions/publish`);
    assert.deepEqual(calls[0].payload, { expected_mechanic_revision: 6, expected_text_revision: 9 });
});

test('Текущий комплект читается публично и закрепляется админски', async () => {
    const { request, calls } = recorder();
    const api = createVersionApi(request);

    await api.getCurrent(SYSTEM_ID);
    await api.listVersions(SYSTEM_ID);
    await api.bindCurrent(SYSTEM_ID, { version_id: VERSION_ID, expected_version_id: null });

    assert.deepEqual(calls.map((call) => [call.method, call.path]), [
        ['GET', `/game-systems/items/${SYSTEM_ID}/versions/current`],
        ['GET', `/game-systems/items/${SYSTEM_ID}/versions?limit=20`],
        ['PUT', `/admin/game-systems/${SYSTEM_ID}/versions/current`]
    ]);
    assert.deepEqual(calls[2].payload, { version_id: VERSION_ID, expected_version_id: null });
});

// ── Общие проверки границ ─────────────────────────────────────────────

test('Идентификаторы кодируются и не ломают структуру пути', async () => {
    const { request, calls } = recorder();
    const api = createTextApi(request);

    await api.getVersion('a b/c', 'd/e');

    const path = calls[0].path;

    assert.ok(path.startsWith('/game-systems/items/'), path);
    assert.ok(path.endsWith('/text/versions/d%2Fe'), path);
    assert.ok(!path.includes('a b'), path);
    assert.equal(path.split('/').length, 7, path);
});

test('Некорректные параметры страницы отклоняются до запроса', () => {
    const { request, calls } = recorder();
    const api = createVersionApi(request);

    for (const options of [{ limit: 0 }, { limit: 101 }, { limit: '20' }, { before: 0 }, { before: 1.5 }]) {
        assert.throws(() => api.listVersions(SYSTEM_ID, options), TypeError);
    }

    assert.equal(calls.length, 0);
});

test('Отсутствующий идентификатор системы отклоняется', () => {
    const { request } = recorder();
    const apis = [createTextApi(request), createMechanicApi(request), createVersionApi(request)];

    for (const api of apis) {
        assert.throws(() => api.getDraft(''), TypeError);
        assert.throws(() => api.listVersions(''), TypeError);
    }

    assert.throws(() => createVersionApi({}), TypeError);
});
