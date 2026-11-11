import test from 'node:test';
import assert from 'node:assert/strict';
import {readProfileResources, validateResources, validateResourcePreview} from '../../../frontend/src/js/features/game-systems/editor/shared/resource-contract.js';

function resource() {
    return {
        label: 'Очки',
        maximum: 'stat.points_max',
        initial: 'full',
        recovery: {long_rest: 'full', short_rest: 2}
    };
}

function profile(version = 4) {
    const result = {
        schema_version: version,
        calculations: {
            attributes: {level: {label: 'Уровень', min_value: 1, max_value: 20}},
            derived: {points_max: {label: 'Максимум', formula: {operation: 'sum', arguments: [6]}}}
        },
        initial_attributes: {level: 3}
    };

    if (version === 4) result.resources = {points: resource()};
    return result;
}

test('версия 3 без ресурсов остаётся допустимой', () => {
    assert.equal(Object.keys(readProfileResources(profile(3))).length, 0);
});

test('версия 4 требует явный раздел ресурсов', () => {
    const value = profile();
    delete value.resources;
    assert.throws(() => readProfileResources(value));
});

test('версия 3 не принимает непустые ресурсы', () => {
    const value = profile();
    value.schema_version = 3;
    assert.throws(() => readProfileResources(value));
});

test('пустой раздел версии 4 допустим', () => {
    const value = profile();
    value.resources = {};
    assert.equal(Object.keys(readProfileResources(value)).length, 0);
});

test('ресурсы и восстановление копируются без общих вложенных объектов', () => {
    const value = profile();
    const resources = readProfileResources(value);

    resources.points.recovery.short_rest = 5;

    assert.equal(value.resources.points.recovery.short_rest, 2);
});

test('ссылка проверяется по своему пространству имён', () => {
    const value = profile();
    value.resources.points.maximum = 'attribute.points_max';
    assert.throws(() => readProfileResources(value));
});

test('неизвестный источник максимума отклоняется', () => {
    const value = profile();
    value.resources.points.maximum = 'stat.missing';
    assert.throws(() => readProfileResources(value));
});

test('начальный запас не может превышать фиксированный максимум', () => {
    assert.throws(() => validateResources({points: {label: 'Очки', maximum: 2, initial: 3}}));
});

test('некорректные максимумы отклоняются', () => {
    for (const maximum of [-1, true, 1.5, null, 'stat.', 'resource.points']) {
        assert.throws(() => validateResources({points: {label: 'Очки', maximum}}));
    }
});

test('нулевое, дробное и логическое восстановление отклоняется', () => {
    for (const amount of [0, -1, true, 1.5]) {
        const definition = {label: 'Очки', maximum: 6, recovery: {long_rest: amount}};
        assert.throws(() => validateResources({points: definition}));
    }
});

test('неподдерживаемые поля ресурса не теряются молча', () => {
    const definition = {...resource(), unsupported: true};
    assert.throws(() => validateResources({points: definition}));
});

test('предпросмотр показывает полный начальный запас', () => {
    const resources = readProfileResources(profile());
    const result = {
        attributes: {level: 3},
        derived: {points_max: 6},
        resource_limits: {points: 6},
        resource_initial: {points: 6}
    };

    const rows = validateResourcePreview(resources, result);

    assert.deepEqual(rows, [{code: 'points', label: 'Очки', maximum: 6, initial: 6}]);
});

test('неполный ответ предпросмотра отклоняется', () => {
    const resources = readProfileResources(profile());
    assert.throws(() => validateResourcePreview(resources, {resource_limits: {}, resource_initial: {}}));
});

test('несогласованный максимум в ответе отклоняется', () => {
    const resources = readProfileResources(profile());
    const result = {
        derived: {points_max: 6},
        resource_limits: {points: 5},
        resource_initial: {points: 5}
    };

    assert.throws(() => validateResourcePreview(resources, result));
});
