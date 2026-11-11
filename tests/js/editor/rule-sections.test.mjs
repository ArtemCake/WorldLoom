import test from 'node:test';
import assert from 'node:assert/strict';
import {groupedRuleEntries, normalizeRuleSection} from '../../../frontend/src/js/features/game-systems/editor/shared/rule-sections.js';
import {assignDnd2014Sections, createDnd5e2014NumericProfile} from '../../../frontend/src/js/features/game-systems/editor/presets/dnd5e-2014.js';
import {validateResources} from '../../../frontend/src/js/features/game-systems/editor/shared/resource-contract.js';

test('Старые параметры без разделов не теряются', () => {
    const rules = {
        calculations: {
            attributes: {
                custom_value: {label: 'Свой параметр'}
            },
            derived: {}
        }
    };

    const groups = groupedRuleEntries(rules, 'attributes');

    assert.equal(groups.length, 1);
    assert.equal(groups[0].title, 'Прочие параметры');
    assert.equal(groups[0].entries[0][0], 'custom_value');
});

test('В разделе исходных характеристик D&D остаются шесть характеристик', () => {
    const rules = createDnd5e2014NumericProfile();
    const groups = groupedRuleEntries(rules, 'attributes');
    const abilities = groups.find((group) => group.title === 'Характеристики');

    assert.deepEqual(abilities.entries.map(([code]) => code), [
        'strength',
        'dexterity',
        'constitution',
        'intelligence',
        'wisdom',
        'charisma'
    ]);
});

test('Каждый параметр попадает ровно в одну группу', () => {
    const rules = createDnd5e2014NumericProfile();
    const collections = {
        attributes: rules.calculations.attributes,
        derived: rules.calculations.derived,
        resources: rules.resources
    };

    for (const [kind, collection] of Object.entries(collections)) {
        const groups = groupedRuleEntries(rules, kind);
        const codes = groups.flatMap((group) => group.entries.map(([code]) => code));

        assert.equal(codes.length, new Set(codes).size);
        assert.deepEqual([...codes].sort(), Object.keys(collection).sort());
    }
});

test('Разметка не меняет формулы, значения и назначенные пользователем разделы', () => {
    const rules = createDnd5e2014NumericProfile();

    rules.calculations.attributes.strength.section = 'Мои характеристики';

    const before = structuredClone(rules);

    assignDnd2014Sections(rules);

    assert.deepEqual(rules, before);
});

test('Проверка ресурсов сохраняет раздел', () => {
    const resources = {
        hit_points: {
            label: 'Хиты',
            section: 'Хиты и ресурсы',
            maximum: 12,
            initial: 'full',
            recovery: {}
        }
    };

    const checked = validateResources(resources);

    assert.equal(checked.hit_points.section, 'Хиты и ресурсы');
    assert.equal(checked.hit_points.maximum, 12);
});

test('Некорректные разделы отклоняются', () => {
    assert.equal(normalizeRuleSection('  Навыки  '), 'Навыки');
    assert.equal(normalizeRuleSection(), '');
    assert.throws(() => normalizeRuleSection(12));
    assert.throws(() => normalizeRuleSection('а'.repeat(101)));
});
