import test from 'node:test';
import assert from 'node:assert/strict';

import * as origin from '../../../frontend/src/js/features/game-systems/editor/game-system-engine-origin.js';
import * as preset from '../../../frontend/src/js/features/game-systems/editor/presets/dnd5e-2014.js';
import {writeBookAttribute} from '../../../frontend/src/js/features/game-systems/book/book-attributes.js';
import {writeBookDefinition} from '../../../frontend/src/js/features/game-systems/book/book-definition-data.js';

function linkedDocument(rules = preset.createDnd5e2014NumericProfile()) {
    return {
        rules: structuredClone(rules),
        origin: {
            engine_version: {
                id: 'published-base',
                engine_id: 'rules-base',
                rules_json: structuredClone(rules)
            },
            rules_overrides: {}
        }
    };
}

function collect(document) {
    const source = document.origin;

    return origin.collectEngineOverrides(source.engine_version.rules_json, document.rules, source.rules_overrides);
}

test('Неизменённые правила формата 4 не создают переопределений', () => {
    assert.deepEqual(collect(linkedDocument()), {});
});

test('Правила формата 3 поддерживаются без автоматического перехода на формат 4', () => {
    const rules = preset.createDnd5e2014NumericProfile();

    rules.schema_version = 3;
    delete rules.resources;

    const document = linkedDocument(rules);

    assert.deepEqual(collect(document), {});
    assert.equal(document.rules.schema_version, 3);
    assert.equal(Object.hasOwn(document.rules, 'resources'), false);
});

test('Начальные значения сохраняются отдельным переопределением', () => {
    const document = linkedDocument();
    const original = structuredClone(document.origin.engine_version.rules_json);

    document.rules.initial_attributes.strength = 12;

    const overrides = collect(document);

    assert.deepEqual(Object.keys(overrides), ['initial_attributes']);
    assert.equal(overrides.initial_attributes.strength, 12);
    assert.deepEqual(document.origin.engine_version.rules_json, original);
});

test('Явное переопределение сохраняется при совпадении с основой', () => {
    const document = linkedDocument();

    document.origin.rules_overrides = {
        initial_attributes: structuredClone(document.rules.initial_attributes)
    };

    assert.deepEqual(collect(document), document.origin.rules_overrides);
});

test('Изменение версии схемы не отправляется как обычное переопределение', () => {
    const document = linkedDocument();

    document.rules.schema_version = 3;
    document.rules.resources = {};

    assert.throws(() => collect(document), /schema_version/u);
});

test('Устаревшие разделы переопределений отклоняются', () => {
    const document = linkedDocument();

    document.origin.rules_overrides = {modifier_offset: 10};

    assert.throws(() => collect(document), /нельзя переопределять/u);
});

test('Характеристика связанной системы редактируется без изменения основы', () => {
    const document = linkedDocument();
    const original = structuredClone(document.origin.engine_version.rules_json);
    const definition = document.rules.calculations.attributes.strength;

    writeBookAttribute(document, 'strength', {
        ...definition,
        code: 'strength',
        field_type: 'integer',
        initial: 12,
        short_label: 'СИЛ'
    });

    const overrides = collect(document);

    assert.equal(overrides.calculations.attributes.strength.short_label, 'СИЛ');
    assert.equal(overrides.initial_attributes.strength, 12);
    assert.deepEqual(document.origin.engine_version.rules_json, original);
});

test('Формула связанной системы редактируется без изменения основы', () => {
    const document = linkedDocument();
    const original = structuredClone(document.origin.engine_version.rules_json);
    const definition = document.rules.calculations.derived.proficiency_bonus;

    writeBookDefinition(document, 'derived', 'proficiency_bonus', 'proficiency_bonus', {
        ...definition,
        description: definition.description ?? '',
        short_label: 'Мастерство'
    });

    assert.equal(collect(document).calculations.derived.proficiency_bonus.short_label, 'Мастерство');
    assert.deepEqual(document.origin.engine_version.rules_json, original);
});

test('Ресурс связанной системы формата 4 сохраняется как переопределение', () => {
    const document = linkedDocument();
    const original = structuredClone(document.origin.engine_version.rules_json);
    const definition = document.rules.resources.hit_points;

    writeBookDefinition(document, 'resources', 'hit_points', 'hit_points', {
        ...definition,
        description: definition.description ?? '',
        short_label: 'ХП'
    });

    assert.equal(collect(document).resources.hit_points.short_label, 'ХП');
    assert.deepEqual(document.origin.engine_version.rules_json, original);
});

test('Ресурс не переводит связанную систему формата 3 в формат 4', () => {
    const rules = preset.createDnd5e2014NumericProfile();

    rules.schema_version = 3;
    rules.resources = {};

    const document = linkedDocument(rules);
    const before = structuredClone(document);

    const write = () => writeBookDefinition(document, 'resources', null, 'energy', {
        label: 'Энергия',
        description: '',
        maximum: 10,
        initial: 'full',
        recovery: {}
    });

    assert.throws(write, /нужна основа формата 4/u);
    assert.deepEqual(document, before);
});

test('Переопределения восстанавливают тот же профиль после повторной загрузки', () => {
    const document = linkedDocument();
    const version = document.origin.engine_version;

    document.rules.initial_attributes.strength = 12;

    const overrides = collect(document);
    const draft = {
        engine_version_id: version.id,
        rules: structuredClone(document.rules),
        rules_overrides: structuredClone(overrides)
    };

    assert.deepEqual(origin.readEngineOverrides(draft, version), overrides);

    draft.rules.initial_attributes.strength = 13;

    assert.throws(() => origin.readEngineOverrides(draft, version), /не совпадают/u);
});

test('Публикация другой основы не принимается при загрузке', () => {
    const document = linkedDocument();
    const version = document.origin.engine_version;
    const draft = {
        engine_version_id: 'another-publication',
        rules: document.rules,
        rules_overrides: {}
    };

    assert.throws(() => origin.readEngineOverrides(draft, version), /не соответствует/u);
});

test('Изменение собранного переопределения не изменяет документ или основу', () => {
    const document = linkedDocument();

    document.rules.initial_attributes.strength = 12;

    const overrides = collect(document);
    const originalStrength = document.origin.engine_version.rules_json.initial_attributes.strength;

    overrides.initial_attributes.strength = 14;

    assert.equal(document.rules.initial_attributes.strength, 12);
    assert.equal(document.origin.engine_version.rules_json.initial_attributes.strength, originalStrength);
});
