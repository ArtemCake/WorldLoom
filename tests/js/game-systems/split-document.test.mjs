// tests/js/game-systems/split-document.test.mjs

import assert from 'node:assert/strict';
import test from 'node:test';

import {
    joinBlocks,
    joinPublished,
    mechanicToProfile,
    splitRules,
    toMechanicContent,
    toTextContent
} from '../../../frontend/src/js/features/game-systems/api/split-document.js';

const PROFILE = Object.freeze({
    schema_version: 4,
    calculations: {
        attributes: { str: { kind: 'roll', dice: '4d4kh1' } },
        derived: { prof: { kind: 'stat', expression: 'floor(str/2)' } }
    },
    initial_attributes: { str: 10 },
    resources: { hp: { maximum: 30, initial: 30 } },
    rulebook: {
        main: { title: 'Об системе', body: 'Текст главы' },
        classes: { title: 'Классы', body: 'Перечисление' }
    }
});

test('Механика содержит только числовые разделы без текстового', () => {
    const mechanic = toMechanicContent(PROFILE);

    assert.deepEqual(Object.keys(mechanic).sort(), ['calculations', 'initial_attributes', 'resources', 'schema_version']);
    assert.equal(mechanic.schema_version, 1);
    assert.equal(mechanic.rulebook, undefined);
    assert.deepEqual(mechanic.calculations, PROFILE.calculations);
    assert.deepEqual(mechanic.resources, PROFILE.resources);
});

test('Текст содержит только главы без числовых разделов', () => {
    const text = toTextContent(PROFILE);

    assert.deepEqual(Object.keys(text).sort(), ['chapters', 'schema_version']);
    assert.equal(text.schema_version, 1);
    assert.deepEqual(text.chapters, PROFILE.rulebook);
    assert.equal(text.calculations, undefined);
    assert.equal(text.initial_attributes, undefined);
    assert.equal(text.resources, undefined);
});

test('Разделение даёт пару блоков одной ревизии данных', () => {
    const split = splitRules(PROFILE);

    assert.deepEqual(split.text.chapters, PROFILE.rulebook);
    assert.deepEqual(split.mechanic.calculations, PROFILE.calculations);
    assert.equal(Object.isFrozen(split), true);
});

test('Отсутствующие правила дают null, а не пустой объект', () => {
    assert.equal(splitRules(null), null);
    assert.equal(splitRules(undefined), null);
});

test('Профиль версии 3 принимает разделение без ресурсов', () => {
    const profile = {
        schema_version: 3,
        calculations: PROFILE.calculations,
        initial_attributes: PROFILE.initial_attributes,
        rulebook: PROFILE.rulebook
    };
    const mechanic = toMechanicContent(profile);

    assert.deepEqual(mechanic.resources, {});
    assert.equal(mechanic.initial_attributes.str, 10);
});

test('Неподдерживаемая версия профиля отклоняется', () => {
    assert.throws(() => toMechanicContent({ schema_version: 2, calculations: {} }), TypeError);
    assert.throws(() => toMechanicContent({ schema_version: 5, calculations: {} }), TypeError);
});

test('Нечисловой вход отклоняется до обращения к серверу', () => {
    for (const value of [null, undefined, 'текст', 42, [], true]) {
        assert.throws(() => toMechanicContent(value), TypeError);
        assert.throws(() => toTextContent(value), TypeError);
    }
});

test('Нечисловой rulebook отклоняется', () => {
    assert.throws(() => toTextContent({ schema_version: 4, rulebook: 'текст' }), TypeError);
});

test('Механика приводится к профилю с пустым текстовым разделом', () => {
    const profile = mechanicToProfile(toMechanicContent(PROFILE));

    assert.equal(profile.schema_version, 4);
    assert.deepEqual(profile.rulebook, {});
    assert.deepEqual(profile.calculations, PROFILE.calculations);
    assert.deepEqual(profile.initial_attributes, PROFILE.initial_attributes);
    assert.deepEqual(profile.resources, PROFILE.resources);
});

test('Обратная сборка сохраняет и главы, и числа', () => {
    const restored = joinBlocks(splitRules(PROFILE));

    assert.equal(restored.schema_version, 4);
    assert.deepEqual(restored.rulebook, PROFILE.rulebook);
    assert.deepEqual(restored.calculations, PROFILE.calculations);
    assert.deepEqual(restored.initial_attributes, PROFILE.initial_attributes);
    assert.deepEqual(restored.resources, PROFILE.resources);
});

test('Сборка без текста оставляет пустые главы', () => {
    const restored = joinBlocks({ mechanic: toMechanicContent(PROFILE) });

    assert.deepEqual(restored.rulebook, {});
});

test('Сборка без механики невозможна', () => {
    assert.equal(joinBlocks({ text: toTextContent(PROFILE) }), null);
    assert.equal(joinBlocks({}), null);
    assert.equal(joinBlocks({ text: null, mechanic: null }), null);
});

test('Сборка не изменяет исходные блоки', () => {
    const split = splitRules(PROFILE);
    const before = structuredClone(split);
    const restored = joinBlocks(split);

    restored.calculations.attributes.str.dice = 'изменено';

    assert.deepEqual(split, before);
});

test('Нечисловые главы в сборке отклоняются', () => {
    assert.throws(() => joinBlocks({ mechanic: toMechanicContent(PROFILE), text: { chapters: 'текст' } }), TypeError);
});

test('Публикация комплекта собирает документ из составных версий', () => {
    const version = { id: '11111111-1111-4111-8111-111111111111', mechanic_version_id: '3', text_version_id: '2' };
    const textVersion = { text: toTextContent(PROFILE) };
    const mechanicVersion = { mechanic: toMechanicContent(PROFILE) };

    const restored = joinPublished({ version, textVersion, mechanicVersion });

    assert.deepEqual(restored.rulebook, PROFILE.rulebook);
    assert.deepEqual(restored.calculations, PROFILE.calculations);
});

test('Публикация без комплекта или без механики даёт null', () => {
    assert.equal(joinPublished({}), null);
    assert.equal(joinPublished({ version: { id: 'x' }, textVersion: { text: toTextContent(PROFILE) } }), null);
});
