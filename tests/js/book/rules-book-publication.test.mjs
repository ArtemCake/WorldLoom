import test from 'node:test';
import assert from 'node:assert/strict';
import {createRulesBookState} from '../../../frontend/src/js/features/game-systems/book/book-state.js';
import {publishBookRules} from '../../../frontend/src/js/features/game-systems/book/book-publication.js';

function documentFixture() {
    return {
        system: {name: 'Проверка', slug: 'test', is_active: true, rules_engine_version: '1.0'},
        rules: {
            schema_version: 4,
            calculations: {attributes: {}, derived: {}},
            initial_attributes: {},
            resources: {}
        },
        origin: null
    };
}

function stateFixture(options = {}) {
    return createRulesBookState({document: documentFixture(), mode: 'edit', revision: 4, ...options});
}

function versionFixture() {
    return {
        id: 'version-a',
        system_id: 'system-a',
        version_number: 1,
        text_version_id: 'text-a',
        mechanic_version_id: 'mechanic-a',
        published_at: '2026-01-01T00:00:00Z'
    };
}

function sessionFixture(onPublish = async () => versionFixture()) {
    return Object.freeze({
        publish: async (revisions) => onPublish(revisions)
    });
}

function publish(state, session, options = {}) {
    return publishBookRules({
        state,
        session,
        systemId: 'system-a',
        allowed: true,
        hasPendingChanges: () => false,
        ...options
    });
}

test('Публикация отправляет ревизии обоих блоков и обновляет состояние', async () => {
    const state = stateFixture();
    const calls = [];

    const version = await publish(state, sessionFixture(async (revisions) => {
        calls.push(revisions);
        return versionFixture();
    }));

    assert.deepEqual(calls, [{text: 4, mechanic: 4}]);
    assert.equal(version.version_number, 1);
    assert.equal(state.read().revision, 5);
    assert.equal(state.read().dirty, false);
    assert.equal(state.read().writePending, null);
    assert.equal(state.read().canPublish, false);

    const save = state.beginSave();

    assert.equal(save.expectedRevision, 5);

    state.acceptSave(save, state.read().document, 6);

    assert.equal(state.read().canPublish, true);
});

test('Неверная следующая ревизия не подтверждает публикацию', () => {
    const state = stateFixture();
    const ticket = state.beginPublish();

    assert.throws(() => state.acceptPublish(ticket, 4), /ревизии/);
    assert.equal(state.read().revision, 4);
    assert.equal(state.read().writePending, 'publish');

    state.failWrite(ticket, {mustReload: true});

    assert.equal(state.read().blocked, true);
});

test('Несохранённые и неприменённые изменения не отправляются', async () => {
    let calls = 0;
    const session = sessionFixture(async () => {
        calls += 1;
        return versionFixture();
    });

    const dirty = stateFixture();

    dirty.update((document) => {
        document.system.name = 'Изменено';
    });

    await assert.rejects(publish(dirty, session), /Сохраните/);
    await assert.rejects(publish(stateFixture(), session, {hasPendingChanges: () => true}), /примените/);

    assert.equal(calls, 0);
});

test('Права, режим чтения и активность проверяются до запроса', async () => {
    let calls = 0;
    const session = sessionFixture(async () => {
        calls += 1;
        return versionFixture();
    });

    const inactive = documentFixture();

    inactive.system.is_active = false;

    await assert.rejects(publish(stateFixture(), session, {allowed: false}), /недоступна/);
    await assert.rejects(publish(stateFixture({mode: 'view'}), session));
    await assert.rejects(publish(stateFixture({document: inactive}), session), /активируйте/);

    assert.equal(calls, 0);
});

test('Повторный запрос и изменение документа заблокированы во время публикации', async () => {
    const state = stateFixture();
    let finish;

    const pending = publish(state, sessionFixture(() => new Promise((resolve) => {
        finish = resolve;
    })));

    assert.equal(state.read().writePending, 'publish');
    assert.throws(() => state.update(() => {}), /текущей записи/);
    await assert.rejects(publish(state, sessionFixture(async () => versionFixture())));

    finish(versionFixture());
    await pending;

    assert.equal(state.read().revision, 5);
});

for (const status of [409, 500, null, 422]) {
    test(`Ошибка публикации: ${status ?? 'потеря соединения'}`, async () => {
        const state = stateFixture();
        const before = state.read().document;
        const error = new Error('Ошибка запроса');

        if (status !== null) error.status = status;

        await assert.rejects(publish(state, sessionFixture(async () => {
            throw error;
        })));

        assert.equal(state.read().revision, 4);
        assert.equal(state.read().writePending, null);
        assert.equal(state.read().blocked, status !== 422);
        assert.deepEqual(state.read().document, before);
    });
}

test('Ответ другой системы блокирует запись и не меняет ревизию', async () => {
    const state = stateFixture();

    await assert.rejects(publish(state, sessionFixture(async () => {
        return {...versionFixture(), system_id: 'system-b'};
    })), /другой системе/);

    assert.equal(state.read().revision, 4);
    assert.equal(state.read().blocked, true);
});

test('Ответ без версии механики не принимается', async () => {
    const state = stateFixture();

    await assert.rejects(publish(state, sessionFixture(async () => {
        return {...versionFixture(), mechanic_version_id: null};
    })), /механики/);

    assert.equal(state.read().revision, 4);
    assert.equal(state.read().blocked, true);
});

test('Не подключённая сессия раздельных черновиков отклоняется до запроса', async () => {
    const state = stateFixture();

    await assert.rejects(publishBookRules({
        state,
        session: null,
        systemId: 'system-a',
        allowed: true,
        hasPendingChanges: () => false
    }), /публикации комплекта/);
});
