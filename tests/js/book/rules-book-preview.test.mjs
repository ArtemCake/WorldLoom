import test from 'node:test';
import assert from 'node:assert/strict';

import {createRulesBookState} from '../../../frontend/src/js/features/game-systems/book/book-state.js';
import {collectBookSample, previewBookRules} from '../../../frontend/src/js/features/game-systems/book/book-preview-data.js';

function fixture(mode = 'edit') {
    const rules = {
        schema_version: 4,
        calculations: {
            attributes: {
                strength: {label: 'Сила', field_type: 'integer', min_value: 1, max_value: 30},
                rank: {
                    label: 'Владение',
                    field_type: 'choice',
                    min_value: 0,
                    max_value: 2,
                    choices: [{value: 0, label: 'Нет'}, {value: 2, label: 'Есть'}]
                }
            },
            derived: {
                total: {
                    label: 'Итог',
                    formula: {operation: 'sum', arguments: ['attribute.strength', 'attribute.rank']}
                }
            }
        },
        initial_attributes: {strength: 10, rank: 0},
        resources: {}
    };

    const document = {
        system: {name: 'Тест', slug: 'test', description: '', is_active: true, rules_engine_version: '1.0'},
        rules,
        origin: null
    };

    const state = createRulesBookState({document, mode, revision: 1});

    state.setSample({strength: '12', rank: '2'});

    return state;
}

function response() {
    return {
        attributes: {strength: 12, rank: 2},
        derived: {total: 14},
        resource_limits: {},
        resource_initial: {},
        steps: [{
            code: 'total',
            operation: 'sum',
            arguments: ['attribute.strength', 'attribute.rank'],
            resolved_arguments: [12, 2],
            value: 14
        }]
    };
}

test('Проверка отправляет текущие правила и числовой пример без записи', async () => {
    const state = fixture();
    const before = state.read().document;
    let call;

    const request = async (...args) => {
        call = args;
        return response();
    };

    assert.equal(await previewBookRules({state, request}), true);
    assert.equal(call[0], '/admin/game-systems/rules/resources/preview');
    assert.equal(call[1], 'POST');
    assert.deepEqual(call[2].state, {schema_version: 1, attributes: {strength: 12, rank: 2}});
    assert.deepEqual(call[3], {readOnly: true});
    assert.deepEqual(state.read().document, before);
    assert.equal(state.read().dirty, false);
    assert.equal(state.read().preview.derived.total, 14);
});

test('Пустое значение и недопустимый вариант выбора отклоняются', () => {
    const state = fixture();
    const rules = state.read().document.rules;

    assert.throws(() => collectBookSample(rules, {strength: '', rank: 0}), /целое число/u);
    assert.throws(() => collectBookSample(rules, {strength: 12, rank: 1}), /допустимых вариантов/u);
    assert.throws(() => collectBookSample(rules, {strength: 31, rank: 0}), /больше допустимого/u);
});

test('Изменение примера отменяет ожидаемый результат', async () => {
    const state = fixture();
    let resolve;

    const request = () => new Promise((done) => {
        resolve = done;
    });

    const pending = previewBookRules({state, request});

    state.setSample({strength: 13, rank: 2});
    resolve(response());

    assert.equal(await pending, false);
    assert.equal(state.read().preview, null);
});

test('Ошибка запроса снимает ожидание, не блокируя сохранение', async () => {
    const state = fixture();

    const request = async () => {
        throw new Error('Нет соединения');
    };

    await assert.rejects(() => previewBookRules({state, request}), /Нет соединения/u);

    assert.equal(state.read().previewPending, false);
    assert.equal(state.read().blocked, false);
    assert.equal(state.read().writePending, null);
});

test('Другие исходные значения в ответе не принимаются', async () => {
    const state = fixture();

    const request = async () => {
        const result = response();

        result.attributes.strength = 13;
        return result;
    };

    await assert.rejects(() => previewBookRules({state, request}), /другое исходное значение/u);

    assert.equal(state.read().preview, null);
    assert.equal(state.read().previewPending, false);
});

test('Повторный запрос не отправляется, пока первый выполняется', async () => {
    const state = fixture();
    let resolve;
    let calls = 0;

    const request = () => {
        calls += 1;

        return new Promise((done) => {
            resolve = done;
        });
    };

    const pending = previewBookRules({state, request});

    await assert.rejects(() => previewBookRules({state, request}), /уже выполняется/u);

    assert.equal(calls, 1);

    resolve(response());
    await pending;
});

test('Режим просмотра допускает пример без изменения правил', async () => {
    const state = fixture('view');
    const before = state.read().document;

    assert.equal(await previewBookRules({state, request: async () => response()}), true);
    assert.deepEqual(state.read().document, before);
    assert.equal(state.read().mode, 'view');
});

test('Ответ после уничтожения панели не принимается', async () => {
    const state = fixture();

    const accepted = await previewBookRules({
        state,
        request: async () => response(),
        isCurrent: () => false
    });

    assert.equal(accepted, false);
    assert.equal(state.read().preview, null);
    assert.equal(state.read().previewPending, false);
});
