import test from 'node:test';
import assert from 'node:assert/strict';

import {getBookBasisChanges} from '../../frontend/src/js/features/game-systems/book/book-basis-changes.js';

function fixture() {
    const rules = {
        schema_version: 4,
        calculations: {
            attributes: {
                strength: {
                    label: 'Сила',
                    field_type: 'integer',
                    min_value: 1,
                    max_value: 30
                }
            },
            derived: {
                score: {
                    label: 'Показатель',
                    formula: {operation: 'sum', arguments: ['attribute.strength', 1]}
                }
            }
        },
        initial_attributes: {strength: 10},
        resources: {
            energy: {
                label: 'Энергия',
                maximum: 10,
                initial: 'full',
                recovery: {}
            }
        }
    };

    return {
        rules: structuredClone(rules),
        origin: {
            engine_version: {rules_json: structuredClone(rules)},
            rules_overrides: {}
        }
    };
}

function items(document, code) {
    return getBookBasisChanges(document).find((group) => group.code === code).items;
}

test('Самостоятельная система не сравнивается с отсутствующей основой', () => {
    const document = fixture();

    document.origin = null;

    assert.equal(getBookBasisChanges(document), null);
});

test('Одинаковые правила не содержат отличий', () => {
    const groups = getBookBasisChanges(fixture());

    assert.equal(groups.length, 3);
    assert.equal(groups.every((group) => group.items.length === 0), true);
});

test('Изменение начального значения отмечает характеристику', () => {
    const document = fixture();

    document.rules.initial_attributes.strength = 12;

    assert.deepEqual(items(document, 'attributes'), [
        {code: 'strength', label: 'Сила', status: 'changed'}
    ]);
});

test('Новое краткое обозначение считается изменением определения', () => {
    const document = fixture();

    document.rules.calculations.derived.score.short_label = 'Пок';

    assert.deepEqual(items(document, 'derived'), [
        {code: 'score', label: 'Показатель', status: 'changed'}
    ]);
});

test('Добавленный элемент отличается от изменённого', () => {
    const document = fixture();

    document.rules.calculations.attributes.agility = {
        label: 'Ловкость',
        field_type: 'integer',
        min_value: 1,
        max_value: 30
    };

    document.rules.initial_attributes.agility = 10;

    assert.deepEqual(items(document, 'attributes'), [
        {code: 'agility', label: 'Ловкость', status: 'added'}
    ]);
});

test('Отсутствующий ресурс основы отмечается как удалённый из системы', () => {
    const document = fixture();

    delete document.rules.resources.energy;

    assert.deepEqual(items(document, 'resources'), [
        {code: 'energy', label: 'Энергия', status: 'removed'}
    ]);
});

test('Изменение формулы и максимума ресурса отражается в разных разделах', () => {
    const document = fixture();

    document.rules.calculations.derived.score.formula.arguments[1] = 2;
    document.rules.resources.energy.maximum = 12;

    assert.equal(items(document, 'derived')[0].status, 'changed');
    assert.equal(items(document, 'resources')[0].status, 'changed');
    assert.deepEqual(items(document, 'attributes'), []);
});

test('Порядок ключей не создаёт ложного отличия', () => {
    const document = fixture();
    const definition = document.rules.calculations.attributes.strength;

    document.rules.calculations.attributes.strength = Object.fromEntries(
        Object.entries(definition).reverse()
    );

    assert.deepEqual(items(document, 'attributes'), []);
});

test('Совпадающее явное переопределение не изображается отличием и не удаляется', () => {
    const document = fixture();

    document.origin.rules_overrides = {
        initial_attributes: structuredClone(document.rules.initial_attributes)
    };

    const before = structuredClone(document);

    assert.equal(getBookBasisChanges(document).every((group) => group.items.length === 0), true);
    assert.deepEqual(document, before);
});

test('Сравнение не изменяет правила, основу или переопределения', () => {
    const document = fixture();

    document.rules.initial_attributes.strength = 12;

    const before = structuredClone(document);
    const groups = getBookBasisChanges(document);

    groups[0].items[0].label = 'Изменено снаружи';

    assert.deepEqual(document, before);
});

test('Недопустимое изменение вне переопределяемых разделов не скрывается', () => {
    const document = fixture();

    document.origin.engine_version.rules_json.resources = {};
    delete document.rules.resources;

    document.rules.schema_version = 3;

    const before = structuredClone(document);

    assert.throws(() => getBookBasisChanges(document), /schema_version/u);
    assert.deepEqual(document, before);
});