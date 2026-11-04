// tests/js/engine-presets.test.mjs

import test from 'node:test';
import assert from 'node:assert/strict';

import {
    createEnginePreset,
    listEnginePresets
} from '../../frontend/src/js/features/game-systems/editor/engine-presets.js';

import {
    formatEngineFormula,
    parseEngineFormula
} from '../../frontend/src/js/features/game-systems/editor/engine-formula-text.js';

test('каталог содержит отдельные редакции и собственную основу', () => {
    assert.deepEqual(
        listEnginePresets().map((item) => item.code),
        [
            'custom',
            'dnd5e_2014_srd51',
            'dnd5e_2024',
            'pf2e_remaster'
        ]
    );
});

test('собственная основа не навязывает показатели готовой системы', () => {
    assert.deepEqual(createEnginePreset('custom'), {
        schema_version: 3,
        calculations: {
            attributes: {},
            derived: {}
        },
        initial_attributes: {}
    });
});

test('каждый профиль имеет начальные значения для всех исходных полей', () => {
    for (const { code } of listEnginePresets()) {
        const profile = createEnginePreset(code);

        assert.equal(profile.schema_version, 3);

        assert.deepEqual(
            Object.keys(profile.initial_attributes).sort(),
            Object.keys(profile.calculations.attributes).sort()
        );

        for (const [key, definition] of Object.entries(
            profile.calculations.attributes
        )) {
            const value = profile.initial_attributes[key];

            assert.ok(Number.isSafeInteger(value));
            assert.ok(value >= definition.min_value);
            assert.ok(value <= definition.max_value);
        }

        for (const definition of Object.values(
            profile.calculations.derived
        )) {
            assert.deepEqual(
                parseEngineFormula(formatEngineFormula(definition.formula)),
                definition.formula
            );
        }
    }
});

test('изменение копии не меняет шаблон и другую редакцию', () => {
    const edited = createEnginePreset('dnd5e_2014_srd51');
    const otherEdition = createEnginePreset('dnd5e_2024');

    edited.initial_attributes.strength = 18;
    edited.calculations.attributes.strength.label = 'Своя характеристика';
    edited.calculations.derived.strength_modifier.formula.arguments[1] = 4;

    for (const profile of [
        createEnginePreset('dnd5e_2014_srd51'),
        otherEdition
    ]) {
        assert.equal(profile.initial_attributes.strength, 10);
        assert.equal(profile.calculations.attributes.strength.label, 'Сила');
        assert.equal(
            profile.calculations.derived.strength_modifier.formula.arguments[1],
            2
        );
    }
});

test('Remaster не получает оценки характеристик и формулы D&D', () => {
    const profile = createEnginePreset('pf2e_remaster');

    assert.equal(Object.keys(profile.calculations.attributes).length, 6);
    assert.ok(
        Object.values(profile.initial_attributes).every((value) => value === 0)
    );
    assert.deepEqual(profile.calculations.derived, {});
});

test('неизвестный шаблон отклоняется', () => {
    assert.throws(() => createEnginePreset('missing'));
});
