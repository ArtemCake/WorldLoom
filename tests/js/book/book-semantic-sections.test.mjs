import test from 'node:test';
import assert from 'node:assert/strict';
import {BOOK_CHAPTERS} from '../../../frontend/src/js/features/game-systems/book/book-state.js';
import {BOOK_RULE_SECTIONS} from '../../../frontend/src/js/features/game-systems/book/book-sections.js';
import {getBookChapterItems, getBookTurn} from '../../../frontend/src/js/features/game-systems/book/book-pagination.js';
import {getBookSectionEntries} from '../../../frontend/src/js/features/game-systems/book/book-sections.js';

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
                    hit_points_max: {label: 'Расчёт максимума', section: 'Хиты и ресурсы'}
                }
            },
            resources: {
                hit_points_max: {label: 'Ресурс', section: 'Хиты и ресурсы'}
            }
        }
    };
}

test('Оглавление содержит самостоятельные смысловые разделы', () => {
    const codes = BOOK_CHAPTERS.map((chapter) => chapter.code);

    // Служебные главы до и после перечисляют смысловые разделы по порядку.
    assert.deepEqual(codes.slice(0, 2), ['main', 'basis']);
    assert.deepEqual(
        codes.slice(2, 2 + BOOK_RULE_SECTIONS.length),
        BOOK_RULE_SECTIONS.map((section) => section.code)
    );
    assert.deepEqual(codes.slice(2 + BOOK_RULE_SECTIONS.length), ['preview', 'publications', 'access']);

    for (const code of ['attributes', 'modifiers', 'derived', 'resources']) {
        assert.equal(BOOK_CHAPTERS.some((chapter) => chapter.code === code), false);
    }
});

test('Исходное значение и его модификатор находятся в одной главе', () => {
    const document = createDocument();
    const entries = getBookSectionEntries(document.rules, 'abilities');

    assert.deepEqual(entries.map((entry) => entry.id), [
        'attributes:strength',
        'derived:strength_modifier'
    ]);
});

test('Раздел ресурсов объединяет все технические типы', () => {
    const document = createDocument();
    const entries = getBookSectionEntries(document.rules, 'hit_points_resources');

    assert.deepEqual(entries.map((entry) => entry.kind), [
        'attributes',
        'derived',
        'resources'
    ]);
});

test('Одинаковые коды разных типов не конфликтуют', () => {
    const document = createDocument();
    const entries = getBookSectionEntries(document.rules, 'hit_points_resources');
    const identifiers = entries.map((entry) => entry.id);

    assert.equal(identifiers.length, 3);
    assert.equal(new Set(identifiers).size, 3);
});

test('Старые параметры без раздела остаются доступными', () => {
    const document = createDocument();
    const entries = getBookSectionEntries(document.rules, 'other_parameters');

    assert.deepEqual(entries.map((entry) => entry.id), ['attributes:custom']);
});

test('Перенос параметра меняет главу без изменения формулы и кода', () => {
    const document = createDocument();
    const definition = document.rules.calculations.derived.strength_modifier;

    definition.formula = {operation: 'sum', arguments: [1]};
    definition.section = 'Особенности';

    const abilities = getBookChapterItems(document, 'abilities');
    const features = getBookChapterItems(document, 'features');

    assert.equal(abilities.includes('derived:strength_modifier'), false);
    assert.equal(features.includes('derived:strength_modifier'), true);
    assert.deepEqual(definition.formula, {operation: 'sum', arguments: [1]});
});

test('Перелистывание проходит между техническими типами внутри главы', () => {
    const document = createDocument();
    const next = getBookTurn(document, 'abilities', 'attributes:strength', 1);

    assert.deepEqual(next, {
        chapter: 'abilities',
        itemCode: 'derived:strength_modifier'
    });
});

test('После последнего параметра открывается следующая смысловая глава', () => {
    const document = createDocument();
    const next = getBookTurn(document, 'abilities', 'derived:strength_modifier', 1);

    assert.deepEqual(next, {
        chapter: 'level_mastery',
        itemCode: null
    });
});

test('Построение глав не изменяет документ', () => {
    const document = createDocument();
    const before = structuredClone(document);

    for (const chapter of BOOK_CHAPTERS) {
        getBookChapterItems(document, chapter.code);
    }

    assert.deepEqual(document, before);
});
