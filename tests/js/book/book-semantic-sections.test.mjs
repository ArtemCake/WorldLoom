import test from 'node:test';
import assert from 'node:assert/strict';
import {
    BOOK_CHAPTERS,
    BOOK_MECHANIC_CHAPTERS,
    BOOK_TEXT_CHAPTERS
} from '../../../frontend/src/js/features/game-systems/book/book-state.js';
import {BOOK_DESIGN_CHAPTERS} from '../../../frontend/src/js/features/game-systems/book/book-design-catalog.js';
import {BOOK_RULE_SECTIONS, getBookKindEntries, isBookMechanicChapter} from '../../../frontend/src/js/features/game-systems/book/book-sections.js';
import {getBookChapterItems, getBookTurn} from '../../../frontend/src/js/features/game-systems/book/book-pagination.js';

function createDocument() {
    return {
        rules: {
            calculations: {
                attributes: {
                    strength: {label: 'Сила', section: 'Характеристики'},
                    hit_points_max: {label: 'Максимум хитов', section: 'Хиты и ресурсы'},
                    custom: {label: 'Свой параметр'}
                },
                derived: {
                    strength_modifier: {label: 'Модификатор Силы', section: 'Характеристики'},
                    initiative_base: {label: 'Базовая инициатива', section: 'Инициатива'},
                    modifier_attack: {label: 'Модификатор атаки', section: 'Бой и перемещение'}
                }
            },
            resources: {
                hit_points_max: {label: 'Ресурс', section: 'Хиты и ресурсы'}
            }
        }
    };
}

test('Текст и механика — независимые оглавления', () => {
    const textCodes = BOOK_TEXT_CHAPTERS.map((chapter) => chapter.code);
    const mechanicCodes = BOOK_MECHANIC_CHAPTERS.map((chapter) => chapter.code);

    assert.deepEqual(textCodes.slice(0, 1), ['main']);
    assert.deepEqual(
        textCodes.slice(1, 1 + BOOK_DESIGN_CHAPTERS.length),
        BOOK_DESIGN_CHAPTERS.map((chapter) => chapter.code)
    );
    assert.deepEqual(textCodes.slice(1 + BOOK_DESIGN_CHAPTERS.length), ['preview', 'publications', 'access']);

    assert.deepEqual(mechanicCodes, ['basis', 'attributes', 'derived', 'modifiers', 'resources']);
});

test('Общий список глав не содержит дублей', () => {
    const codes = BOOK_CHAPTERS.map((chapter) => chapter.code);

    assert.equal(new Set(codes).size, codes.length);
    assert.equal(BOOK_CHAPTERS.length, BOOK_TEXT_CHAPTERS.length + BOOK_MECHANIC_CHAPTERS.length);
});

test('Разделы макета остаются описанием текстовых глав', () => {
    const textCodes = new Set(BOOK_TEXT_CHAPTERS.map((chapter) => chapter.code));

    for (const section of BOOK_RULE_SECTIONS) {
        // other_parameters — запасной раздел для параметров без явного section.
        if (section.code === 'other_parameters') continue;

        assert.equal(textCodes.has(section.code), true);
    }
});

test('Механика отделяет исходные значения, показатели, модификаторы и ресурсы', () => {
    const document = createDocument();
    const rules = document.rules;

    assert.deepEqual(getBookKindEntries(rules, 'attributes').map((entry) => entry.id), [
        'attributes:strength',
        'attributes:hit_points_max',
        'attributes:custom'
    ]);
    // Код, оканчивающийся на _modifier, относится к модификаторам.
    assert.deepEqual(getBookKindEntries(rules, 'derived').map((entry) => entry.id), [
        'derived:initiative_base'
    ]);
    assert.deepEqual(getBookKindEntries(rules, 'modifiers').map((entry) => entry.id), [
        'derived:strength_modifier',
        'derived:modifier_attack'
    ]);
    assert.deepEqual(getBookKindEntries(rules, 'resources').map((entry) => entry.id), [
        'resources:hit_points_max'
    ]);
});

test('Основа правил не перечисляет параметры', () => {
    const document = createDocument();

    assert.deepEqual(getBookKindEntries(document.rules, 'basis'), []);
    assert.deepEqual(getBookChapterItems(document, 'basis'), []);
});

test('Одинаковые коды разных типов не конфликтуют', () => {
    const document = createDocument();
    const identifiers = [
        ...getBookKindEntries(document.rules, 'attributes'),
        ...getBookKindEntries(document.rules, 'resources')
    ].map((entry) => entry.id);

    assert.equal(new Set(identifiers).size, identifiers.length);
});

test('Текстовые главы не содержат элементов механики', () => {
    const document = createDocument();

    for (const chapter of BOOK_TEXT_CHAPTERS) {
        assert.deepEqual(getBookChapterItems(document, chapter.code), []);
    }
});

test('Главы механики перечисляют только свой технический тип', () => {
    const document = createDocument();
    const kinds = {
        attributes: 'attributes',
        derived: 'derived',
        modifiers: 'derived',
        resources: 'resources'
    };

    for (const chapter of BOOK_MECHANIC_CHAPTERS) {
        if (chapter.code === 'basis') continue;

        for (const item of getBookChapterItems(document, chapter.code)) {
            assert.equal(item.slice(0, item.indexOf(':')), kinds[chapter.code]);
        }
    }
});

test('Перелистывание не выходит за пределы раздела редактора', () => {
    const document = createDocument();

    assert.equal(getBookTurn(document, 'main', null, -1), null);
    assert.equal(getBookTurn(document, 'access', null, 1), null);

    const lastMechanic = BOOK_MECHANIC_CHAPTERS[BOOK_MECHANIC_CHAPTERS.length - 1].code;
    const firstMechanic = BOOK_MECHANIC_CHAPTERS[0].code;

    assert.equal(getBookTurn(document, lastMechanic, null, 1), null);
    assert.equal(getBookTurn(document, firstMechanic, null, -1), null);
});

test('Перелистывание внутри главы механики идёт по порядку параметров', () => {
    const document = createDocument();

    const next = getBookTurn(document, 'attributes', 'attributes:strength', 1);

    assert.deepEqual(next, {chapter: 'attributes', itemCode: 'attributes:hit_points_max'});
});

test('После последнего параметра открывается следующая глава механики', () => {
    const document = createDocument();
    const items = getBookChapterItems(document, 'attributes');
    const last = items[items.length - 1];

    const next = getBookTurn(document, 'attributes', last, 1);

    assert.deepEqual(next, {chapter: 'derived', itemCode: 'derived:initiative_base'});
});

test('Из первого параметра назад открывается предыдущая глава механики', () => {
    const document = createDocument();

    const previous = getBookTurn(document, 'attributes', 'attributes:strength', -1);

    assert.deepEqual(previous, {chapter: 'basis', itemCode: null});
});

test('isBookMechanicChapter распознаёт только главы механики', () => {
    assert.equal(isBookMechanicChapter('attributes'), true);
    assert.equal(isBookMechanicChapter('basis'), true);
    assert.equal(isBookMechanicChapter('concept'), false);
    assert.equal(isBookMechanicChapter('main'), false);
});

test('Построение глав не изменяет документ', () => {
    const document = createDocument();
    const before = structuredClone(document);

    for (const chapter of BOOK_CHAPTERS) {
        getBookChapterItems(document, chapter.code);
    }

    assert.deepEqual(document, before);
});
