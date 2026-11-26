// tests/js/game-systems/split-editor-session.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';

import { createSplitEditorSession } from '../../../frontend/src/js/features/game-systems/editor/split-editor-session.js';

const SYSTEM_ID = '11111111-1111-4111-8111-111111111111';

const MECHANIC = Object.freeze({
    schema_version: 1,
    calculations: { attributes: { str: { kind: 'roll', dice: '4d4kh1' } }, derived: {} },
    initial_attributes: { str: 10 },
    resources: { hp: { maximum: 30, initial: 30 } }
});

const TEXT = Object.freeze({
    schema_version: 1,
    chapters: { main: { title: 'Об системе', body: 'Текст' } }
});

const PROFILE = Object.freeze({
    schema_version: 4,
    calculations: MECHANIC.calculations,
    initial_attributes: MECHANIC.initial_attributes,
    resources: MECHANIC.resources,
    rulebook: TEXT.chapters
});

function draftRecord(block, content, revision, isPublished = false) {
    return {
        id: '22222222-2222-4222-8222-222222222222',
        system_id: SYSTEM_ID,
        revision,
        is_published: isPublished,
        [block]: content,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z'
    };
}

function createBlockApi(block, responses) {
    const calls = [];
    const queue = [...responses];

    const api = {
        calls,
        getDraft: async () => {
            calls.push(['GET', null]);
            return queue.shift() ?? { draft: null };
        },
        createDraft: async (systemId, data) => {
            calls.push(['POST', data]);

            assert.equal(systemId, SYSTEM_ID);
            return { revision: 1, [block]: data[block] };
        },
        updateDraft: async (systemId, data) => {
            calls.push(['PATCH', data]);

            assert.equal(systemId, SYSTEM_ID);
            return { revision: data.expected_revision + 1, [block]: data[block] };
        }
    };

    return api;
}

function createVersionApi(response = { id: '3', version_number: 5 }) {
    const calls = [];

    return {
        calls,
        publish: async (systemId, data) => {
            calls.push([systemId, data]);
            return response;
        }
    };
}

function sessionWith({ textResponses = [], mechanicResponses = [], versionResponse } = {}) {
    const textApi = createBlockApi('text', textResponses);
    const mechanicApi = createBlockApi('mechanic', mechanicResponses);
    const versionApi = createVersionApi(versionResponse);

    const session = createSplitEditorSession({
        systemId: SYSTEM_ID,
        textApi,
        mechanicApi,
        versionApi
    });

    return { session, textApi, mechanicApi, versionApi };
}

// ── Загрузка ──────────────────────────────────────────────────────────

test('Загрузка собирает единый документ из двух черновиков', async () => {
    const { session } = sessionWith({
        textResponses: [{ draft: draftRecord('text', TEXT, 4) }],
        mechanicResponses: [{ draft: draftRecord('mechanic', MECHANIC, 7) }]
    });
    const state = await session.load();

    assert.deepEqual(state.document, PROFILE);
    assert.deepEqual(state.revisions, { text: 4, mechanic: 7 });
    assert.deepEqual(state.published, { text: false, mechanic: false });
    assert.equal(state.hasDraft, true);
});

test('Отсутствие обоих черновиков даёт пустой документ', async () => {
    const { session } = sessionWith({
        textResponses: [{ draft: null }],
        mechanicResponses: [{ draft: null }]
    });
    const state = await session.load();

    assert.equal(state.document, null);
    assert.deepEqual(state.revisions, { text: null, mechanic: null });
    assert.equal(state.hasDraft, false);
});

test('Механика без текста даёт документ с пустыми главами', async () => {
    const { session } = sessionWith({
        mechanicResponses: [{ draft: draftRecord('mechanic', MECHANIC, 2) }]
    });
    const state = await session.load();

    assert.deepEqual(state.document.rulebook, {});
    assert.deepEqual(state.document.calculations, MECHANIC.calculations);
    assert.equal(state.revisions.text, null);
    assert.equal(state.revisions.mechanic, 2);
});

test('Загрузка читает оба черновика параллельно и помечает публикацию', async () => {
    const { session } = sessionWith({
        textResponses: [{ draft: draftRecord('text', TEXT, 3, true) }],
        mechanicResponses: [{ draft: draftRecord('mechanic', MECHANIC, 5, true) }]
    });
    const state = await session.load();

    assert.deepEqual(state.published, { text: true, mechanic: true });
    assert.equal(state.document.schema_version, 4);
});

test('Некорректная ревизия сервера отклоняется', async () => {
    const { session } = sessionWith({
        textResponses: [{ draft: { ...draftRecord('text', TEXT, 0) } }]
    });

    await assert.rejects(() => session.load(), TypeError);
});

test('Некорректный ответ черновика отклоняется', async () => {
    const { session } = sessionWith({
        textResponses: [{ draft: 'текст' }]
    });

    await assert.rejects(() => session.load(), TypeError);
});

// ── Сохранение ────────────────────────────────────────────────────────

test('Сохранение отправляет PATCH по существующим ревизиям', async () => {
    const { session, textApi, mechanicApi } = sessionWith();

    const revisions = await session.save(PROFILE, { text: 4, mechanic: 7 });

    assert.deepEqual(revisions, { text: 5, mechanic: 8 });
    assert.deepEqual(textApi.calls[0], ['PATCH', { expected_revision: 4, text: TEXT }]);
    assert.deepEqual(mechanicApi.calls[0], ['PATCH', { expected_revision: 7, mechanic: MECHANIC }]);
});

test('Отсутствие ревизии переводит запись на создание черновика', async () => {
    const { session, textApi, mechanicApi } = sessionWith();

    const revisions = await session.save(PROFILE, { text: null, mechanic: null });

    assert.deepEqual(revisions, { text: 1, mechanic: 1 });
    assert.equal(textApi.calls[0][0], 'POST');
    assert.deepEqual(textApi.calls[0][1], { text: TEXT });
    assert.equal(mechanicApi.calls[0][0], 'POST');
    assert.deepEqual(mechanicApi.calls[0][1], { mechanic: MECHANIC });
});

test('Смешанное состояние: текст создаётся, механика обновляется', async () => {
    const { session, textApi, mechanicApi } = sessionWith();

    const revisions = await session.save(PROFILE, { text: null, mechanic: 3 });

    assert.deepEqual(revisions, { text: 1, mechanic: 4 });
    assert.equal(textApi.calls[0][0], 'POST');
    assert.equal(mechanicApi.calls[0][0], 'PATCH');
});

test('Сохранение не передаёт ревизию, которой не было', async () => {
    const { session, textApi } = sessionWith();

    await session.save(PROFILE, { mechanic: 2 });

    assert.equal(textApi.calls[0][0], 'POST');
    assert.equal(textApi.calls[0][1].expected_revision, undefined);
});

test('Пустой документ не отправляется на сервер', async () => {
    const { session, textApi, mechanicApi } = sessionWith();

    await assert.rejects(() => session.save(null, { text: 1, mechanic: 1 }), TypeError);
    assert.equal(textApi.calls.length, 0);
    assert.equal(mechanicApi.calls.length, 0);
});

test('Сохранение не изменяет исходный документ', async () => {
    const { session } = sessionWith();
    const document = structuredClone(PROFILE);
    const before = structuredClone(PROFILE);

    await session.save(document, { text: 1, mechanic: 1 });

    assert.deepEqual(document, before);
});

// ── Публикация комплекта ──────────────────────────────────────────────

test('Публикация передаёт обе ревизии комплекта', async () => {
    const { session, versionApi } = sessionWith({ versionResponse: { id: '9', version_number: 3 } });

    const version = await session.publish({ text: 4, mechanic: 7 });

    assert.deepEqual(versionApi.calls[0], [SYSTEM_ID, { expected_mechanic_revision: 7, expected_text_revision: 4 }]);
    assert.equal(version.version_number, 3);
});

test('Публикация без текста передаёт null ревизию текста', async () => {
    const { session, versionApi } = sessionWith();

    await session.publish({ mechanic: 6 });

    assert.deepEqual(versionApi.calls[0][1], { expected_mechanic_revision: 6, expected_text_revision: null });
});

test('Публикация без ревизии механики отклоняется', async () => {
    const { session, versionApi } = sessionWith();

    await assert.rejects(() => session.publish({ text: 3 }), TypeError);
    await assert.rejects(() => session.publish({}), TypeError);
    await assert.rejects(() => session.publish(null), TypeError);
    assert.equal(versionApi.calls.length, 0);
});

// ── Контракт зависимостей ─────────────────────────────────────────────

test('Сессия требует полный набор API-методов', () => {
    const base = createBlockApi('text', []);
    const mechanic = createBlockApi('mechanic', []);

    assert.throws(() => createSplitEditorSession({ systemId: '', textApi: base, mechanicApi: mechanic, versionApi: createVersionApi() }), TypeError);

    for (const broken of [undefined, null, {}, { getDraft: () => {} }]) {
        assert.throws(() => createSplitEditorSession({
            systemId: SYSTEM_ID,
            textApi: broken,
            mechanicApi: mechanic,
            versionApi: createVersionApi()
        }), TypeError);

        assert.throws(() => createSplitEditorSession({
            systemId: SYSTEM_ID,
            textApi: base,
            mechanicApi: broken,
            versionApi: createVersionApi()
        }), TypeError);

        assert.throws(() => createSplitEditorSession({
            systemId: SYSTEM_ID,
            textApi: base,
            mechanicApi: mechanic,
            versionApi: broken
        }), TypeError);
    }
});

test('Публичный интерфейс сессии заморожен', () => {
    const { session } = sessionWith();

    assert.equal(Object.isFrozen(session), true);
    assert.deepEqual(Object.keys(session).sort(), ['load', 'publish', 'save']);
});
