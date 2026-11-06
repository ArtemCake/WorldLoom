import test from 'node:test';
import assert from 'node:assert/strict';
import {generateShortLabel, getShortLabel, normalizeShortLabel} from '../../frontend/src/js/features/game-systems/editor/shared/short-label.js';

test('Произвольные названия сокращаются без игрового словаря', () => {
    assert.equal(generateShortLabel('Скорость обучения навыку'), 'СОН');
    assert.equal(generateShortLabel('Бонус мастерства'), 'БМ');
    assert.equal(generateShortLabel('Владение спасброском'), 'ВС');
});

test('Обозначение категории сохраняет название параметра в скобках', () => {
    assert.equal(generateShortLabel('Модификатор: Сила'), 'М[Сила]');
    assert.equal(generateShortLabel('Владение спасброском: Сила'), 'ВС[Сила]');
    assert.equal(generateShortLabel('Скорость обучения навыку: Атлетика'), 'СОН[Атлетика]');
    assert.equal(generateShortLabel('Модификатор[Сила]'), 'М[Сила]');
});

test('Короткое слово сохраняется, длинное сокращается', () => {
    assert.equal(generateShortLabel('Сила'), 'Сила');
    assert.equal(generateShortLabel('Телосложение'), 'ТЕЛ');
});

test('Ручное обозначение имеет приоритет', () => {
    const definition = {label: 'Скорость обучения навыку', short_label: 'Обучение'};

    assert.equal(getShortLabel(definition), 'Обучение');
    assert.equal(getShortLabel({...definition, label: 'Другое название'}), 'Обучение');
});

test('Автоматический режим восстанавливается после загрузки', () => {
    const saved = JSON.stringify({label: 'Скорость обучения навыку', short_label: null});

    assert.equal(getShortLabel(JSON.parse(saved)), 'СОН');
    assert.equal(getShortLabel({label: 'Скорость освоения заклинаний'}), 'СОЗ');
});

test('Пустое ручное значение означает автоматический режим', () => {
    assert.equal(normalizeShortLabel('   '), null);
    assert.equal(normalizeShortLabel(undefined), null);
    assert.equal(normalizeShortLabel(null), null);
    assert.equal(normalizeShortLabel('  М[Сила]  '), 'М[Сила]');
});

test('Некорректное ручное значение отклоняется', () => {
    assert.throws(() => normalizeShortLabel(123));
    assert.throws(() => normalizeShortLabel('А'.repeat(41)));
});

test('Автоматическое обозначение ограничено по длине и сохраняет закрывающую скобку', () => {
    const result = generateShortLabel(`Скорость обучения навыку: ${'А'.repeat(100)}`);

    assert.ok([...result].length <= 40);
    assert.ok(result.startsWith('СОН['));
    assert.ok(result.endsWith(']'));
});
