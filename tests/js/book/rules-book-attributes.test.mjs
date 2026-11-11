import test from 'node:test';
import assert from 'node:assert/strict';

import {createRulesBookState} from '../../../frontend/src/js/features/game-systems/book/book-state.js';
import {writeBookAttribute, removeBookAttribute} from '../../../frontend/src/js/features/game-systems/book/book-attributes.js';

function document() {
    return {
        system: {name: 'Пограничье'},
        origin: null,
        rules: {
            schema_version: 4,
            calculations: {attributes: {}, derived: {}},
            initial_attributes: {},
            resources: {}
        }
    };
}

function numeric(code = 'strength') {
    return {code, label: 'Сила', field_type: 'integer', min_value: 0, max_value: 30, initial: 10};
}

function choice() {
    return {
        code: 'training',
        label: 'Подготовка',
        field_type: 'choice',
        initial: 2,
        choices: [{label: 'Нет', value: 0}, {label: 'Есть', value: 2}]
    };
}

test('добавляет число и начальное значение', () => {
    const source = document();

    writeBookAttribute(source, null, numeric());

    assert.equal(source.rules.calculations.attributes.strength.label, 'Сила');
    assert.equal(source.rules.initial_attributes.strength, 10);
});

test('редактирование сохраняет дополнительные поля и соседние правила', () => {
    const source = document();

    writeBookAttribute(source, null, numeric());
    source.rules.calculations.attributes.strength.additional_setting = {enabled: true};
    source.rules.resources.stamina = {label: 'Запас сил', maximum: 5};

    writeBookAttribute(source, 'strength', {...numeric(), label: 'Мощь'});

    assert.deepEqual(source.rules.calculations.attributes.strength.additional_setting, {enabled: true});
    assert.deepEqual(source.rules.resources.stamina, {label: 'Запас сил', maximum: 5});
});

test('не разрешает повторный код и не переименовывает существующий', () => {
    const source = document();

    writeBookAttribute(source, null, numeric());

    assert.throws(() => writeBookAttribute(source, null, numeric()), /уже существует/);
    assert.throws(() => writeBookAttribute(source, 'strength', numeric('power')), /нельзя изменить/);
    assert.equal(Object.hasOwn(source.rules.calculations.attributes, 'power'), false);
});

test('границы выбора вычисляются из вариантов', () => {
    const source = document();

    writeBookAttribute(source, null, choice());

    const definition = source.rules.calculations.attributes.training;

    assert.equal(definition.min_value, 0);
    assert.equal(definition.max_value, 2);
    assert.equal(source.rules.initial_attributes.training, 2);
});

test('выбор проверяет принадлежность, а не только попадание между границами', () => {
    const source = document();

    assert.throws(() => writeBookAttribute(source, null, {...choice(), initial: 1}), /из заданных вариантов/);
    assert.deepEqual(source.rules.calculations.attributes, {});
});

test('повторяющиеся числовые варианты запрещены', () => {
    const source = document();
    const input = choice();

    input.choices[1].value = 0;

    assert.throws(() => writeBookAttribute(source, null, input), /повторяется/);
});

test('неверный диапазон не оставляет частичное изменение', () => {
    const source = document();

    writeBookAttribute(source, null, numeric());

    const before = structuredClone(source);

    assert.throws(() => writeBookAttribute(source, 'strength', {...numeric(), max_value: 5}), /между/);
    assert.deepEqual(source, before);
});

test('не принимает дроби и числа вне технического диапазона', () => {
    const source = document();

    assert.throws(() => writeBookAttribute(source, null, {...numeric(), initial: 1.5}), /целое число/);
    assert.throws(() => writeBookAttribute(source, null, {...numeric(), max_value: 1_000_000_001}), /диапазоне/);
});

test('переход к числу убирает варианты только у выбранного определения', () => {
    const source = document();

    writeBookAttribute(source, null, choice());
    writeBookAttribute(source, 'training', {...numeric('training'), initial: 2});

    assert.equal(Object.hasOwn(source.rules.calculations.attributes.training, 'choices'), false);
    assert.equal(source.rules.calculations.attributes.training.field_type, 'integer');
});

test('вложенная формула защищает характеристику от удаления', () => {
    const source = document();

    writeBookAttribute(source, null, numeric());

    source.rules.calculations.derived.bonus = {
        label: 'Бонус',
        formula: {
            operation: 'sum',
            arguments: [1, {operation: 'multiply', arguments: ['attribute.strength', 2]}]
        }
    };

    assert.throws(() => removeBookAttribute(source, 'strength'), /используется/);
    assert.equal(source.rules.initial_attributes.strength, 10);
});

test('источник максимума ресурса защищён от удаления', () => {
    const source = document();

    writeBookAttribute(source, null, numeric());
    source.rules.resources.stamina = {label: 'Запас сил', maximum: 'attribute.strength'};

    assert.throws(() => removeBookAttribute(source, 'strength'), /используется/);
});

test('удаление свободной характеристики удаляет и начальное значение', () => {
    const source = document();

    writeBookAttribute(source, null, numeric());
    removeBookAttribute(source, 'strength');

    assert.deepEqual(source.rules.calculations.attributes, {});
    assert.deepEqual(source.rules.initial_attributes, {});
});

test('не преобразует старый профиль при попытке редактирования', () => {
    const legacy = document();

    legacy.rules.schema_version = 2;

    const before = structuredClone(legacy);

    assert.throws(() => writeBookAttribute(legacy, null, numeric()), /формата/u);
    assert.deepEqual(legacy, before);
});

test('не изменяет документ при неполных сведениях об основе', () => {
    const linked = document();

    linked.origin = {publication: {version_number: 1}};

    const before = structuredClone(linked);

    assert.throws(
        () => writeBookAttribute(linked, null, numeric()),
        {name: 'Error', message: 'Для связанной системы требуется профиль правил формата 3 или 4.'}
    );

    assert.deepEqual(linked, before);
});

test('применение меняет состояние книги и отменяет старый предпросмотр', () => {
    const state = createRulesBookState({document: document(), mode: 'edit', revision: 1});
    const ticket = state.beginPreview();

    state.update((draft) => writeBookAttribute(draft, null, numeric()));

    assert.equal(state.read().dirty, true);
    assert.equal(state.acceptPreview(ticket, {derived: {}}), false);
    assert.equal(state.read().document.rules.initial_attributes.strength, 10);
});
