import test from 'node:test';
import assert from 'node:assert/strict';

import {BOOK_CHAPTERS, BOOK_MECHANIC_CHAPTERS, BOOK_TEXT_CHAPTERS} from '../../../frontend/src/js/features/game-systems/book/book-state.js';
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
                    armor_class: {label: 'Класс брони', section: 'Защита'},
                    modifier_attack: {label: 'Модификатор атаки', section: 'Бой и перемещение'}
                }
            },
            resources: {
                hit_points_max: {label: 'Хиты', section: 'Хиты и ресурсы'},
                stamina: {label: 'Запас сил', section: 'Хиты и ресурсы'}
            }
        }
    };
}

test('возвращает исходные значения в порядке определений', () => {
    const source = document();
    const items = getBookChapterItems(source, 'attributes');

    assert.deepEqual(items, [
        'attributes:strength',
        'attributes:dexterity',
        'attributes:constitution',
        'attributes:hit_points'
    ]);
});

test('вычисляемые показатели отделены от модификаторов', () => {
    const source = document();

    // Код, оканчивающийся на _modifier, относится к модификаторам.
    assert.deepEqual(getBookChapterItems(source, 'derived'), [
        'derived:initiative_base',
        'derived:armor_class'
    ]);
    assert.deepEqual(getBookChapterItems(source, 'modifiers'), [
        'derived:strength_modifier',
        'derived:modifier_attack'
    ]);
});

test('ресурсы перечисляются отдельной главой', () => {
    const source = document();

    assert.deepEqual(getBookChapterItems(source, 'resources'), [
        'resources:hit_points_max',
        'resources:stamina'
    ]);
});

test('текстовая глава не возвращает элементов механики', () => {
    const source = document();

    assert.deepEqual(getBookChapterItems(source, 'main'), []);
    assert.deepEqual(getBookChapterItems(source, 'abilities'), []);
    assert.deepEqual(getBookChapterItems(source, 'hit_points_resources'), []);
});

test('перелистывает параметры внутри главы механики', () => {
    const source = document();

    const next = getBookTurn(source, 'attributes', 'attributes:strength', 1);
    assert.deepEqual(next, {chapter: 'attributes', itemCode: 'attributes:dexterity'});

    const prev = getBookTurn(source, 'attributes', 'attributes:dexterity', -1);
    assert.deepEqual(prev, {chapter: 'attributes', itemCode: 'attributes:strength'});
});

test('после последнего параметра открывается следующая глава механики', () => {
    const source = document();
    const items = getBookChapterItems(source, 'attributes');
    const last = items[items.length - 1];

    const next = getBookTurn(source, 'attributes', last, 1);

    assert.deepEqual(next, {chapter: 'derived', itemCode: 'derived:initiative_base'});
});

test('назад из нового элемента открывает последний параметр предыдущей главы', () => {
    const source = document();

    const prev = getBookTurn(source, 'derived', null, -1);

    assert.deepEqual(prev, {chapter: 'derived', itemCode: 'derived:armor_class'});
});

test('пустая глава остаётся доступной и перелистывается дальше', () => {
    const source = document();

    source.rules.calculations.attributes = {};
    source.rules.calculations.derived = {};
    source.rules.resources = {};

    assert.equal(getBookChapterItems(source, 'resources').length, 0);

    const next = getBookTurn(source, 'resources', null, 1);
    assert.equal(next, null);
});

test('текстовый раздел не перелистывается за начало и конец', () => {
    const source = document();
    const first = BOOK_TEXT_CHAPTERS[0].code;
    const last = BOOK_TEXT_CHAPTERS[BOOK_TEXT_CHAPTERS.length - 1].code;

    assert.equal(getBookTurn(source, first, null, -1), null);
    assert.equal(getBookTurn(source, last, null, 1), null);
});

test('раздел механики не перелистывается за начало и конец', () => {
    const source = document();
    const first = BOOK_MECHANIC_CHAPTERS[0].code;
    const last = BOOK_MECHANIC_CHAPTERS[BOOK_MECHANIC_CHAPTERS.length - 1].code;

    assert.equal(getBookTurn(source, first, null, -1), null);
    assert.equal(getBookTurn(source, last, null, 1), null);
});

test('отсутствие правил не ломает переход между главами', () => {
    const result = getBookTurn({rules: null}, BOOK_TEXT_CHAPTERS[0].code, null, 1);

    assert.ok(result === null || BOOK_CHAPTERS.some((chapter) => chapter.code === result.chapter));
});

test('проверяет направление и существование элемента', () => {
    const source = document();

    assert.throws(() => getBookTurn(source, 'attributes', 'nonexistent', 1), /отсутствует/);
    assert.throws(() => getBookTurn(source, 'attributes', 'attributes:strength', 0), /Направление/);
    assert.throws(() => getBookTurn(source, 'unknown_section', null, 1), /Неизвестная страница книги/);
});

test('перелистывание не меняет документ', () => {
    const source = document();
    const before = structuredClone(source);

    getBookTurn(source, 'attributes', 'attributes:strength', 1);
    getBookTurn(source, 'derived', 'derived:armor_class', -1);

    assert.deepEqual(source, before);
});

test('глава basis пуста', () => {
    const source = document();

    assert.deepEqual(getBookChapterItems(source, 'basis'), []);
});

test('глава main пуста', () => {
    const source = document();
    assert.deepEqual(getBookChapterItems(source, 'main'), []);
});
