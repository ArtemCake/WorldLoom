import test from 'node:test';
import assert from 'node:assert/strict';
import {restoreBookBasisItem} from '../../frontend/src/js/features/game-systems/book/book-basis-restore.js';
import {createRulesBookState} from '../../frontend/src/js/features/game-systems/book/book-state.js';
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

test('Возврат характеристики восстанавливает определение и начальное значение', () => {
    const document = fixture();
    const base = document.origin.engine_version.rules_json;

    document.rules.calculations.attributes.strength.label = 'Другая сила';
    document.rules.calculations.attributes.strength.short_label = 'ДС';
    document.rules.initial_attributes.strength = 12;
    document.rules.resources.energy.maximum = 15;

    const originBefore = structuredClone(document.origin);
    const resourceBefore = structuredClone(document.rules.resources.energy);

    assert.equal(restoreBookBasisItem(document, 'attributes', 'strength'), true);
    assert.deepEqual(document.rules.calculations.attributes.strength, base.calculations.attributes.strength);
    assert.equal(document.rules.initial_attributes.strength, base.initial_attributes.strength);
    assert.deepEqual(document.rules.resources.energy, resourceBefore);
    assert.deepEqual(document.origin, originBefore);
    assert.deepEqual(items(document, 'attributes'), []);
});

test('Возврат формулы восстанавливает всё определение без изменения соседей', () => {
    const document = fixture();

    document.rules.calculations.derived.score.formula.arguments[1] = 5;
    document.rules.calculations.derived.score.description = 'Локальное описание';
    document.rules.initial_attributes.strength = 12;

    const base = document.origin.engine_version.rules_json;
    const initialBefore = structuredClone(document.rules.initial_attributes);

    assert.equal(restoreBookBasisItem(document, 'derived', 'score'), true);
    assert.deepEqual(document.rules.calculations.derived.score, base.calculations.derived.score);
    assert.deepEqual(document.rules.initial_attributes, initialBefore);
});

test('Возврат ресурса не изменяет другие определения', () => {
    const document = fixture();

    document.rules.resources.energy.maximum = 20;
    document.rules.resources.energy.recovery = {rest: 'full'};

    const calculationsBefore = structuredClone(document.rules.calculations);

    assert.equal(restoreBookBasisItem(document, 'resources', 'energy'), true);
    assert.deepEqual(document.rules.resources.energy, document.origin.engine_version.rules_json.resources.energy);
    assert.deepEqual(document.rules.calculations, calculationsBefore);
});

test('Удалённые элементы основы можно восстановить', () => {
    for (const group of ['attributes', 'derived', 'resources']) {
        const document = fixture();

        if (group === 'attributes') {
            delete document.rules.calculations.attributes.strength;
            delete document.rules.initial_attributes.strength;
            document.rules.calculations.derived.score.formula = {operation: 'sum', arguments: [1]};
        } else if (group === 'derived') {
            delete document.rules.calculations.derived.score;
        } else {
            delete document.rules.resources.energy;
        }

        const code = group === 'attributes' ? 'strength' : group === 'derived' ? 'score' : 'energy';

        assert.equal(restoreBookBasisItem(document, group, code), true);
        assert.deepEqual(items(document, group), []);
    }
});

test('Добавленный автором элемент не удаляется действием возврата к основе', () => {
    const document = fixture();

    document.rules.resources.custom = {
        label: 'Свой ресурс',
        maximum: 5,
        initial: 'full',
        recovery: {}
    };

    const before = structuredClone(document);

    assert.throws(() => restoreBookBasisItem(document, 'resources', 'custom'), /Добавленный автором/u);
    assert.deepEqual(document, before);
});

test('Возврат уже совпадающего элемента ничего не изменяет', () => {
    const document = fixture();
    const before = structuredClone(document);

    assert.equal(restoreBookBasisItem(document, 'attributes', 'strength'), false);
    assert.deepEqual(document, before);
});

test('Отсутствующая зависимость блокирует возврат формулы без частичной правки', () => {
    const document = fixture();

    delete document.rules.calculations.attributes.strength;
    delete document.rules.initial_attributes.strength;
    document.rules.calculations.derived.score.formula = {operation: 'sum', arguments: [1]};

    const before = structuredClone(document);

    assert.throws(() => restoreBookBasisItem(document, 'derived', 'score'), /недоступный источник/u);
    assert.deepEqual(document, before);

    assert.equal(restoreBookBasisItem(document, 'attributes', 'strength'), true);
    assert.equal(restoreBookBasisItem(document, 'derived', 'score'), true);
});

test('Цикл, возникающий при возврате формулы, отклоняется без изменения документа', () => {
    const document = fixture();
    const base = document.origin.engine_version.rules_json;

    base.calculations.derived.other = {
        label: 'Другой показатель',
        formula: {operation: 'sum', arguments: [1]}
    };

    base.calculations.derived.score.formula = {operation: 'sum', arguments: ['stat.other']};
    document.rules.calculations.derived.score.formula = {operation: 'sum', arguments: [1]};
    document.rules.calculations.derived.other = {
        label: 'Другой показатель',
        formula: {operation: 'sum', arguments: ['stat.score']}
    };

    const before = structuredClone(document);

    assert.throws(() => restoreBookBasisItem(document, 'derived', 'score'), /циклическая зависимость/u);
    assert.deepEqual(document, before);
});

test('Отсутствующий источник максимума блокирует возврат ресурса', () => {
    const document = fixture();

    document.origin.engine_version.rules_json.resources.energy.maximum = 'attribute.strength';
    delete document.rules.calculations.attributes.strength;
    delete document.rules.initial_attributes.strength;
    document.rules.calculations.derived.score.formula = {operation: 'sum', arguments: [1]};

    const before = structuredClone(document);

    assert.throws(() => restoreBookBasisItem(document, 'resources', 'energy'), /источник.*отсутствует/u);
    assert.deepEqual(document, before);
});

test('Восстановленное определение не разделяет вложенные объекты с основой', () => {
    const document = fixture();

    document.rules.calculations.derived.score.formula.arguments[1] = 5;

    restoreBookBasisItem(document, 'derived', 'score');
    document.rules.calculations.derived.score.formula.arguments[1] = 9;

    assert.equal(document.origin.engine_version.rules_json.calculations.derived.score.formula.arguments[1], 1);
});

test('Формат 3 сохраняется без добавления раздела ресурсов', () => {
    const document = fixture();

    document.rules.schema_version = 3;
    document.origin.engine_version.rules_json.schema_version = 3;

    delete document.rules.resources;
    delete document.origin.engine_version.rules_json.resources;

    document.rules.initial_attributes.strength = 12;

    assert.equal(restoreBookBasisItem(document, 'attributes', 'strength'), true);
    assert.equal(document.rules.schema_version, 3);
    assert.equal(Object.hasOwn(document.rules, 'resources'), false);
});

test('Явные переопределения не удаляются при возврате отдельного элемента', () => {
    const document = fixture();

    document.rules.initial_attributes.strength = 12;
    document.origin.rules_overrides = {
        initial_attributes: structuredClone(document.rules.initial_attributes)
    };

    const before = structuredClone(document.origin);

    restoreBookBasisItem(document, 'attributes', 'strength');

    assert.deepEqual(document.origin, before);
    assert.equal(document.rules.initial_attributes.strength, 10);
});

test('Самостоятельная система не допускает возврат к отсутствующей основе', () => {
    const document = fixture();

    document.origin = null;

    const before = structuredClone(document);

    assert.throws(() => restoreBookBasisItem(document, 'attributes', 'strength'), /нет опубликованной основы/u);
    assert.deepEqual(document, before);
});

test('Применение возврата через состояние книги отменяет устаревшую проверку', () => {
    const document = fixture();

    document.system = {name: 'Тестовая система', is_active: true};
    document.rules.initial_attributes.strength = 12;

    const state = createRulesBookState({document, mode: 'edit', revision: 1});
    const ticket = state.beginPreview();

    assert.equal(state.update((draft) => restoreBookBasisItem(draft, 'attributes', 'strength')), true);
    assert.equal(state.read().dirty, true);
    assert.equal(state.read().previewPending, false);
    assert.equal(state.acceptPreview(ticket, {}), false);
});

test('Режим просмотра запрещает применение возврата', () => {
    const document = fixture();

    document.system = {name: 'Тестовая система', is_active: true};
    document.rules.initial_attributes.strength = 12;

    const state = createRulesBookState({document, mode: 'view'});
    const before = state.read();

    assert.throws(
        () => state.update((draft) => restoreBookBasisItem(draft, 'attributes', 'strength')),
        /только для просмотра/u
    );

    assert.deepEqual(state.read(), before);
});
