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

		assert.ok([3, 4].includes(profile.schema_version), 'Пресет должен использовать поддерживаемую версию профиля');

		if (profile.schema_version === 4) {
		    assert.ok(Object.hasOwn(profile, 'resources'), 'Профиль версии 4 должен содержать раздел ресурсов');
		}

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
test('D&D 2014 содержит исходные и вычисляемые показатели', () => {
    const profile = createEnginePreset('dnd5e_2014_srd51');

    const attributes = profile.calculations.attributes;
    const derived = profile.calculations.derived;

    assert.equal(Object.keys(attributes).length, 32);
    assert.equal(Object.keys(derived).length, 51);

    const abilities = [
        'strength',
        'dexterity',
        'constitution',
        'intelligence',
        'wisdom',
        'charisma'
    ];

    for (const code of abilities) {
        assert.ok(Object.hasOwn(attributes, code));
        assert.ok(Object.hasOwn(derived, `${code}_modifier`));

        assert.ok(
            Object.hasOwn(attributes, `save_${code}_trained`)
        );

        assert.ok(
            Object.hasOwn(derived, `save_${code}`)
        );
    }

    const skills = [
        'acrobatics',
        'animal_handling',
        'arcana',
        'athletics',
        'deception',
        'history',
        'insight',
        'intimidation',
        'investigation',
        'medicine',
        'nature',
        'perception',
        'performance',
        'persuasion',
        'religion',
        'sleight_of_hand',
        'stealth',
        'survival'
    ];

    for (const code of skills) {
        assert.ok(
            Object.hasOwn(attributes, `skill_${code}_rank`)
        );

        assert.ok(
            Object.hasOwn(derived, `skill_${code}`)
        );

        assert.ok(
            Object.hasOwn(derived, `passive_${code}_base`)
        );
    }

    assert.ok(Object.hasOwn(attributes, 'level'));
    assert.ok(Object.hasOwn(derived, 'proficiency_bonus'));
    assert.ok(Object.hasOwn(derived, 'initiative_base'));

    assert.ok(
        Object.hasOwn(derived, 'armor_class_unarmored_base')
    );
});