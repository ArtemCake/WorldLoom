import test from 'node:test';
import assert from 'node:assert/strict';
import {createFormulaPresentation} from '../../frontend/src/js/features/game-systems/editor/shared/formula-presentation.js';

function operation(name, ...args) {
    return {operation: name, arguments: args};
}

function labels(reference) {
    const names = {
        'attribute.strength': 'Сила',
        'stat.strength_modifier': 'Модификатор силы'
    };

    return names[reference] || reference;
}

test('Модификатор отображается с названием характеристики и округлением вниз', () => {
    const difference = operation('subtract', 'attribute.strength', 10);
    const formula = operation('floor_div', difference, 2);
    const result = createFormulaPresentation(formula, {getLabel: labels});

    assert.equal(result.text, '⌊(Сила − 10) / 2⌋');
    assert.equal(result.tree.children[1].tag, 'mfrac');
    assert.deepEqual(result.notes, ['⌊…⌋ — округление вниз до целого.']);
});

test('Округление вверх не подменяется округлением вниз', () => {
    const result = createFormulaPresentation(operation('ceil_div', 9, 2));

    assert.equal(result.text, '⌈9 / 2⌉');
    assert.deepEqual(result.notes, ['⌈…⌉ — округление вверх до целого.']);
});

test('Вложенное вычитание сохраняет скобки', () => {
    const formula = operation('subtract', 10, operation('subtract', 5, 2));

    assert.equal(createFormulaPresentation(formula).text, '(10 − (5 − 2))');
});

test('Умножение суммы сохраняет группировку', () => {
    const formula = operation('multiply', operation('sum', 2, 3), 4);

    assert.equal(createFormulaPresentation(formula).text, '((2 + 3) × 4)');
});

test('Вычисляемые показатели используют читаемые названия ссылок', () => {
    const formula = operation('sum', 10, 'stat.strength_modifier');
    const result = createFormulaPresentation(formula, {getLabel: labels});

    assert.equal(result.text, '(10 + Модификатор силы)');
});

test('Минимум и максимум показываются читаемо', () => {
    assert.equal(createFormulaPresentation(operation('min', 2, 3)).text, 'мин(2 ; 3)');
    assert.equal(createFormulaPresentation(operation('max', 2, 3)).text, 'макс(2 ; 3)');
});

test('Отрицательные числа явно отделены скобками', () => {
    const formula = operation('sum', 10, -2);

    assert.equal(createFormulaPresentation(formula).text, '(10 + (−2))');
});

test('При отсутствии названия ссылка остаётся видимой', () => {
    const formula = operation('sum', 'stat.unknown', 1);

    assert.equal(createFormulaPresentation(formula).text, '(stat.unknown + 1)');
});

test('Преобразование не изменяет исходную формулу', () => {
    const formula = operation('floor_div', operation('subtract', 'attribute.strength', 10), 2);
    const before = JSON.stringify(formula);

    createFormulaPresentation(formula, {getLabel: labels});

    assert.equal(JSON.stringify(formula), before);
});

test('Неизвестная операция не изображается как допустимая формула', () => {
    assert.throws(() => createFormulaPresentation(operation('unknown', 1, 2)));
});

test('Неполная формула и деление на ноль не отображаются как корректные', () => {
    assert.throws(() => createFormulaPresentation(operation('sum', null, 1)));
    assert.throws(() => createFormulaPresentation(operation('floor_div', 10, 0)));
});

test('Тип ссылки отделяется от параметра квадратными скобками', () => {
    const formula = operation('sum', 'stat.strength_modifier', 'stat.strength_save');
    const names = {
        'stat.strength_modifier': 'Модификатор: Сила',
        'stat.strength_save': 'Владение спасброском: Сила'
    };

    const result = createFormulaPresentation(formula, {getLabel: (reference) => names[reference] || reference});

    assert.equal(result.text, '(Модификатор [Сила] + Владение спасброском [Сила])');
});
