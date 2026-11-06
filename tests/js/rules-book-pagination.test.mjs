import test from 'node:test';
import assert from 'node:assert/strict';

import {BOOK_CHAPTERS} from '../../frontend/src/js/features/game-systems/book/book-state.js';
import {getBookChapterItems, getBookTurn} from '../../frontend/src/js/features/game-systems/book/book-pagination.js';

function document() {
    return {
        rules: {
            calculations: {
                attributes: {
                    strength: {label: 'Сила'},
                    dexterity: {label: 'Ловкость'},
                    endurance: {label: 'Выносливость'}
                },
                derived: {
                    defense: {label: 'Защита'},
                    initiative: {label: 'Инициатива'}
                }
            },
            resources: {
                health: {label: 'Хиты'},
                stamina: {label: 'Запас сил'}
            }
        }
    };
}

test('возвращает элементы соответствующей главы в порядке определений', () => {
    const source = document();

    assert.deepEqual(getBookChapterItems(source, 'attributes'), ['strength', 'dexterity', 'endurance']);
    assert.deepEqual(getBookChapterItems(source, 'derived'), ['defense', 'initiative']);
    assert.deepEqual(getBookChapterItems(source, 'resources'), ['health', 'stamina']);
    assert.deepEqual(getBookChapterItems(source, 'main'), []);
});

test('перелистывает характеристики в обе стороны', () => {
    const source = document();

    assert.deepEqual(getBookTurn(source, 'attributes', 'strength', 1), {
        chapter: 'attributes',
        itemCode: 'dexterity'
    });

    assert.deepEqual(getBookTurn(source, 'attributes', 'endurance', -1), {
        chapter: 'attributes',
        itemCode: 'dexterity'
    });
});

test('после последней характеристики открывает следующую главу', () => {
    assert.deepEqual(getBookTurn(document(), 'attributes', 'endurance', 1), {
        chapter: 'modifiers',
        itemCode: null
    });
});

test('назад из модификаторов открывает последнюю характеристику', () => {
    assert.deepEqual(getBookTurn(document(), 'modifiers', null, -1), {
        chapter: 'attributes',
        itemCode: 'endurance'
    });
});

test('вперёд из модификаторов открывает первый показатель', () => {
    assert.deepEqual(getBookTurn(document(), 'modifiers', null, 1), {
        chapter: 'derived',
        itemCode: 'defense'
    });
});

test('между соседними главами со списками переход симметричен', () => {
    const source = document();

    assert.deepEqual(getBookTurn(source, 'derived', 'initiative', 1), {
        chapter: 'resources',
        itemCode: 'health'
    });

    assert.deepEqual(getBookTurn(source, 'resources', 'health', -1), {
        chapter: 'derived',
        itemCode: 'initiative'
    });
});

test('пустая глава остаётся доступной', () => {
    const source = document();

    source.rules.calculations.derived = {};

    assert.deepEqual(getBookTurn(source, 'modifiers', null, 1), {
        chapter: 'derived',
        itemCode: null
    });

    assert.deepEqual(getBookTurn(source, 'derived', null, 1), {
        chapter: 'resources',
        itemCode: 'health'
    });
});

test('из новой характеристики назад открывается последняя существующая', () => {
    assert.deepEqual(getBookTurn(document(), 'attributes', null, -1), {
        chapter: 'attributes',
        itemCode: 'endurance'
    });
});

test('из новой характеристики вперёд открывается следующая глава', () => {
    assert.deepEqual(getBookTurn(document(), 'attributes', null, 1), {
        chapter: 'modifiers',
        itemCode: null
    });
});

test('книга не перелистывается за начало и конец', () => {
    const source = document();
    const first = BOOK_CHAPTERS[0].code;
    const last = BOOK_CHAPTERS[BOOK_CHAPTERS.length - 1].code;

    assert.equal(getBookTurn(source, first, null, -1), null);
    assert.equal(getBookTurn(source, last, null, 1), null);
});

test('отсутствие правил не ломает переход между главами', () => {
    assert.deepEqual(getBookTurn({rules: null}, 'attributes', null, 1), {
        chapter: 'modifiers',
        itemCode: null
    });
});

test('проверяет направление и существование элемента', () => {
    const source = document();

    assert.throws(() => getBookTurn(source, 'attributes', 'missing', 1), /отсутствует/);
    assert.throws(() => getBookTurn(source, 'attributes', 'strength', 0), /Направление/);
    assert.throws(() => getBookTurn(source, 'unknown', null, 1), /Неизвестная страница книги/);
});

test('перелистывание не меняет документ', () => {
    const source = document();
    const before = structuredClone(source);

    getBookTurn(source, 'attributes', 'strength', 1);
    getBookTurn(source, 'resources', 'health', -1);

    assert.deepEqual(source, before);
});
