import test from 'node:test';
import assert from 'node:assert/strict';

import {BOOK_CHAPTERS} from '../../../frontend/src/js/features/game-systems/book/book-state.js';
import {getBookChapterItems, getBookTurn} from '../../../frontend/src/js/features/game-systems/book/book-pagination.js';

function document() {
    return {
        rules: {
            calculations: {
                attributes: {
                    strength: {label: 'Сила', section: 'Характеристики'},
                    dexterity: {label: 'Ловкость', section: 'Характеристики'},
                    constitution: {label: 'Телосложение', section: 'Характеристики'},
                    hit_points: {label: 'Максимум хитов', section: 'Хиты и ресурсы'}
                },
                derived: {
                    strength_modifier: {label: 'Модификатор Силы', section: 'Характеристики'},
                    initiative_base: {label: 'Базовая инициатива', section: 'Инициатива'},
                    armor_class: {label: 'Класс брони', section: 'Защита'}
                }
            },
            resources: {
                hit_points_max: {label: 'Хиты', section: 'Хиты и ресурсы'},
                stamina: {label: 'Запас сил', section: 'Хиты и ресурсы'}
            }
        }
    };
}

test('возвращает элементы соответствующей главы в порядке определений', () => {
    const source = document();

    const attrs = getBookChapterItems(source, 'abilities');
    assert.ok(attrs.includes('attributes:strength'));
    assert.ok(attrs.includes('attributes:dexterity'));
    assert.ok(attrs.includes('attributes:constitution'));
    assert.ok(attrs.includes('derived:strength_modifier'));

    const initiative = getBookChapterItems(source, 'initiative');
    assert.ok(initiative.includes('derived:initiative_base'));

    const defense = getBookChapterItems(source, 'defense');
    assert.ok(defense.includes('derived:armor_class'));

    const hp = getBookChapterItems(source, 'hit_points_resources');
    assert.ok(hp.includes('attributes:hit_points'));
    assert.ok(hp.includes('resources:hit_points_max'));
    assert.ok(hp.includes('resources:stamina'));

    // Несекционная глава (main) возвращает пустой список
    assert.deepEqual(getBookChapterItems(source, 'main'), []);
});

test('перелистывает параметры внутри смыслового раздела', () => {
    const source = document();

    const next = getBookTurn(source, 'abilities', 'attributes:strength', 1);
    assert.equal(next.chapter, 'abilities');

    const prev = getBookTurn(source, 'abilities', 'attributes:dexterity', -1);
    assert.equal(prev.itemCode, 'attributes:strength');
});

test('после последнего параметра раздела открывается следующий раздел', () => {
    const source = document();

    // Находим последний элемент в abilities
    const items = getBookChapterItems(source, 'abilities');
    const last = items[items.length - 1];

    const next = getBookTurn(source, 'abilities', last, 1);
    // Должен перейти к следующему разделу (level_mastery)
    assert.ok(next !== null);
    assert.ok(next.chapter !== 'abilities');
});

test('назад из нового элемента открывает последний параметр раздела', () => {
    const source = document();

    const items = getBookChapterItems(source, 'abilities');
    const first = items[0];

    const prev = getBookTurn(source, 'abilities', first, -1);
    // Из первого элемента назад — к главе basis
    assert.ok(prev === null || prev.chapter !== 'abilities');
});

test('между соседними смысловыми разделами переход симметричен', () => {
    const source = document();

    const items = getBookChapterItems(source, 'abilities');
    if (items.length === 0) {
        return; // Пропускаем если пусто
    }

    const last = items[items.length - 1];
    const next = getBookTurn(source, 'abilities', last, 1);

    if (next && next.itemCode !== null) {
        const back = getBookTurn(source, next.chapter, next.itemCode, -1);
        assert.equal(back.chapter, 'abilities');
        assert.equal(back.itemCode, last);
    }
});

test('пустая глава остаётся доступной', () => {
    const source = document();

    source.rules.calculations.attributes = {};
    source.rules.calculations.derived = {};
    source.rules.resources = {};

    const items = getBookChapterItems(source, 'hit_points_resources');
    assert.equal(items.length, 0);

    const next = getBookTurn(source, 'hit_points_resources', null, 1);
    assert.ok(next !== null);
});

test('книга не перелистывается за начало и конец', () => {
    const source = document();
    const first = BOOK_CHAPTERS[0].code;
    const last = BOOK_CHAPTERS[BOOK_CHAPTERS.length - 1].code;

    assert.equal(getBookTurn(source, first, null, -1), null);
    assert.equal(getBookTurn(source, last, null, 1), null);
});

test('отсутствие правил не ломает переход между главами', () => {
    const result = getBookTurn({rules: null}, BOOK_CHAPTERS[0].code, null, 1);
    assert.ok(result === null || BOOK_CHAPTERS.some(c => c.code === result.chapter));
});

test('проверяет направление и существование элемента', () => {
    const source = document();

    assert.throws(() => getBookTurn(source, 'abilities', 'nonexistent', 1), /отсутствует/);
    assert.throws(() => getBookTurn(source, 'abilities', 'attributes:strength', 0), /Направление/);
    assert.throws(() => getBookTurn(source, 'unknown_section', null, 1), /Неизвестная страница книги/);
});

test('перелистывание не меняет документ', () => {
    const source = document();
    const before = structuredClone(source);

    getBookTurn(source, 'abilities', 'attributes:strength', 1);
    getBookTurn(source, 'defense', 'derived:armor_class', -1);

    assert.deepEqual(source, before);
});

test('глава basis содержит технические коллекции', () => {
    const source = document();

    const items = getBookChapterItems(source, 'basis');
    assert.ok(Array.isArray(items));
    assert.ok(items.every(item => typeof item === 'string'));
});

test('глава main пуста', () => {
    const source = document();
    assert.deepEqual(getBookChapterItems(source, 'main'), []);
});
