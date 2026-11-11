import test from 'node:test';
import assert from 'node:assert/strict';

import * as basis from '../../../frontend/src/js/features/game-systems/book/book-basis-data.js';
import {createRulesBookState} from '../../../frontend/src/js/features/game-systems/book/book-state.js';

function fixture(mode = 'create') {
    const rules = {
        schema_version: 4,
        calculations: {attributes: {}, derived: {}},
        initial_attributes: {},
        resources: {}
    };

    const system = {
        name: 'Авторская система',
        slug: 'author-system',
        description: 'Описание автора',
        is_active: true,
        rules_engine_version: '1.0'
    };

    const engine = {id: 'base-one', name: 'Основа', is_active: true};
    const summary = {
        id: 'publication-one',
        engine_id: engine.id,
        version_number: 2,
        rules_engine_version: '1.0'
    };

    const version = {
        ...summary,
        source_draft_revision: 3,
        rules_json: structuredClone(rules),
        published_at: '2026-11-06T07:00:00Z'
    };

    const document = {system, rules, origin: null};
    const revision = mode === 'create' ? null : 1;
    const state = createRulesBookState({document, mode, revision});

    return {state, engine, summary, version};
}

test('Загружаются все страницы доступных основ', async () => {
    const paths = [];

    const request = async (path) => {
        paths.push(path);

        return paths.length === 1
            ? {items: [{id: 'first'}], next_offset: 50}
            : {items: [{id: 'second'}], next_offset: null};
    };

    const items = await basis.readBasisPages(request, '/admin/rule-engines');

    assert.deepEqual(items.map((item) => item.id), ['first', 'second']);
    assert.deepEqual(paths, [
        '/admin/rule-engines?limit=50&offset=0',
        '/admin/rule-engines?limit=50&offset=50'
    ]);
});

test('Некорректное продолжение списка отклоняется', async () => {
    const request = async () => ({items: [{id: 'first'}], next_offset: 0});

    await assert.rejects(() => basis.readBasisPages(request, '/bases'), /продолжение/u);
});

test('Повтор элемента между страницами не скрывается', async () => {
    let count = 0;

    const request = async () => {
        count += 1;

        return {items: [{id: 'same'}], next_offset: count === 1 ? 50 : null};
    };

    await assert.rejects(() => basis.readBasisPages(request, '/bases'), /изменился/u);
});

test('Применение основы сохраняет карточку и закрепляет выбранную публикацию', () => {
    const {state, engine, summary, version} = fixture();
    const before = state.read();

    const changed = basis.applyPublishedBookBasis(state, engine, summary, version, before);
    const after = state.read();

    assert.equal(changed, true);
    assert.deepEqual(after.document.system, before.document.system);
    assert.equal(after.document.origin.engine_version.id, version.id);
    assert.deepEqual(after.document.origin.rules_overrides, {});
    assert.deepEqual(after.document.rules, version.rules_json);
    assert.equal(after.dirty, true);

    version.rules_json.initial_attributes.external = 10;

    assert.equal(Object.hasOwn(state.read().document.rules.initial_attributes, 'external'), false);
});

test('Новая система получает версию исполнителя выбранной публикации', () => {
    const {state, engine, summary, version} = fixture();

    summary.rules_engine_version = '2.0';
    version.rules_engine_version = '2.0';

    basis.applyPublishedBookBasis(state, engine, summary, version, state.read());

    assert.equal(state.read().document.system.rules_engine_version, '2.0');
});

test('У существующей системы нельзя неявно сменить версию исполнителя', () => {
    const {state, engine, summary, version} = fixture('edit');
    const before = state.read();

    summary.rules_engine_version = '2.0';
    version.rules_engine_version = '2.0';

    const apply = () => basis.applyPublishedBookBasis(state, engine, summary, version, before);

    assert.throws(apply, /той же версией/u);
    assert.deepEqual(state.read(), before);
});

test('Публикация другой основы не применяется', () => {
    const {state, engine, summary, version} = fixture();
    const before = state.read();

    version.engine_id = 'another-base';

    const apply = () => basis.applyPublishedBookBasis(state, engine, summary, version, before);

    assert.throws(apply, /другой основы/u);
    assert.deepEqual(state.read(), before);
});

test('Запоздавший ответ не перезаписывает изменившуюся книгу', () => {
    const {state, engine, summary, version} = fixture();
    const expected = state.read();

    state.update((draft) => {
        draft.system.description = 'Изменено во время загрузки';
    });

    const before = state.read();
    const apply = () => basis.applyPublishedBookBasis(state, engine, summary, version, expected);

    assert.throws(apply, /изменилась/u);
    assert.deepEqual(state.read(), before);
});

test('Просмотр запрещает применение основы', () => {
    const {state, engine, summary, version} = fixture('view');
    const before = state.read();
    const apply = () => basis.applyPublishedBookBasis(state, engine, summary, version, before);

    assert.throws(apply, /просмотра/u);
    assert.deepEqual(state.read(), before);
});

test('Выбор новой публикации заменяет прежние переопределения после применения', () => {
    const {state, engine, summary, version} = fixture('edit');

    basis.applyPublishedBookBasis(state, engine, summary, version, state.read());

    state.update((draft) => {
        draft.origin.rules_overrides = {initial_attributes: {}};
    });

    const nextSummary = {...summary, id: 'publication-two', version_number: 3};
    const nextVersion = {...version, ...nextSummary};

    basis.applyPublishedBookBasis(state, engine, nextSummary, nextVersion, state.read());

    assert.equal(state.read().document.origin.engine_version.id, 'publication-two');
    assert.deepEqual(state.read().document.origin.rules_overrides, {});
});
