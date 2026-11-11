import test from 'node:test';
import assert from 'node:assert/strict';

import * as preset from '../../../frontend/src/js/features/game-systems/editor/presets/dnd5e-2014.js';
import * as contract from '../../../frontend/src/js/features/game-systems/editor/shared/resource-contract.js';

const {createDnd5e2014NumericProfile} = preset;
const {readProfileResources, validateResourcePreview} = contract;

test('пресет D&D 2014 использует версию 4 и содержит ресурс хитов', () => {
    const profile = createDnd5e2014NumericProfile();
    const resources = readProfileResources(profile);

    assert.equal(profile.schema_version, 4);
    assert.equal(resources.hit_points.maximum, 'attribute.hit_points_max');
    assert.equal(resources.hit_points.initial, 'full');
    assert.deepEqual({...resources.hit_points.recovery}, {long_rest: 'full'});
});

test('максимум хитов задан отдельным исходным показателем', () => {
    const profile = createDnd5e2014NumericProfile();
    const definition = profile.calculations.attributes.hit_points_max;

    assert.equal(definition.label, 'Максимум хитов');
    assert.equal(definition.min_value, 1);
    assert.equal(profile.initial_attributes.hit_points_max, 1);
    assert.ok(definition.max_value >= 1);
});

test('предпросмотр хитов использует переданный максимум', () => {
    const profile = createDnd5e2014NumericProfile();
    const resources = readProfileResources(profile);

    // Ответ сервера должен содержать все ресурсы пресета.
    const result = {
        attributes: {...profile.initial_attributes},
        derived: {},
        resource_limits: {},
        resource_initial: {}
    };

    result.attributes.hit_points_max = 12;

    for (const [code, definition] of Object.entries(resources)) {
        let maximum = definition.maximum;

        if (typeof maximum === 'string') {
            const [namespace, target] = maximum.split('.');
            const source = namespace === 'attribute' ? result.attributes : result.derived;

            if (!Object.hasOwn(source, target)) source[target] = 1;
            maximum = source[target];
        }

        result.resource_limits[code] = maximum;
        result.resource_initial[code] = definition.initial === 'full' ? maximum : definition.initial;
    }

    const rows = validateResourcePreview(resources, result);

    assert.equal(rows.length, Object.keys(resources).length);
    assert.deepEqual(rows.find((row) => row.code === 'hit_points'), {
        code: 'hit_points',
        label: 'Хиты',
        maximum: 12,
        initial: 12
    });
});

test('короткий отдых не получает автоматическое восстановление хитов', () => {
    const profile = createDnd5e2014NumericProfile();

    assert.equal(Object.hasOwn(profile.resources.hit_points.recovery, 'short_rest'), false);
});

test('состояние текущих хитов не включено в определения пресета', () => {
    const profile = createDnd5e2014NumericProfile();

    assert.equal(Object.hasOwn(profile.initial_attributes, 'hit_points'), false);
    assert.equal(Object.hasOwn(profile.resources.hit_points, 'current'), false);
});

test('разные экземпляры пресета не разделяют настройки ресурсов', () => {
    const first = createDnd5e2014NumericProfile();
    const second = createDnd5e2014NumericProfile();

    first.resources.hit_points.recovery.long_rest = 2;
    first.initial_attributes.hit_points_max = 20;

    assert.equal(second.resources.hit_points.recovery.long_rest, 'full');
    assert.equal(second.initial_attributes.hit_points_max, 1);
});

test('существующие показатели и поля выбора сохранены', () => {
    const profile = createDnd5e2014NumericProfile();
    const {attributes, derived} = profile.calculations;

    assert.equal(attributes.strength.min_value, 0);
    assert.equal(attributes.level.max_value, 20);
    assert.equal(attributes.skill_athletics_rank.field_type, 'choice');
    assert.equal(attributes.save_strength_trained.field_type, 'choice');
    assert.ok(derived.proficiency_bonus);
    assert.ok(derived.skill_athletics);
    assert.ok(derived.passive_perception_base);
    assert.ok(derived.armor_class_unarmored_base);
});
