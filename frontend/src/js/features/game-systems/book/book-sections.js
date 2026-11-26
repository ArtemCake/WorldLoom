// frontend/src/js/features/game-systems/book/book-sections.js

// Два независимых уровня книги правил:
//
//   Текст   — главы rulebook: описание мира, концепция, процедуры.
//             Хранится в SystemTextContent.chapters.
//   Механика — числовые определения: исходные значения, вычисляемые
//             показатели, модификаторы и ресурсы.
//             Хранится в SystemMechanicContent.
//
// Раздел макета (section) остаётся свойством параметра механики и служит
// только для порядка внутри текстовой главы. Навигация редактора больше
// не смешивает текстовые главы и параметры.

import {ruleCollections, ruleSectionTitle} from '../editor/shared/rule-sections.js';
import {isBookModifierCode} from './book-definition-data.js';
import {BOOK_DESIGN_CHAPTERS} from './book-design-catalog.js';

const sections = [
    ...BOOK_DESIGN_CHAPTERS.map(({code, title}) => ({code, title})),
    {code: 'other_parameters', title: 'Прочие параметры'}
];

// Разделы макета: значение поля section у параметра механики.
export const BOOK_RULE_SECTIONS = Object.freeze(sections.map((section) => Object.freeze(section)));

const sectionCodes = new Set(BOOK_RULE_SECTIONS.map((section) => section.code));
const sectionByTitle = new Map(BOOK_RULE_SECTIONS.map((section) => [section.title, section.code]));

// Главы механики: навигация по техническому типу параметра.
export const BOOK_MECHANIC_CHAPTERS = Object.freeze([
    Object.freeze({code: 'basis', title: 'Основа правил'}),
    Object.freeze({code: 'attributes', title: 'Исходные значения'}),
    Object.freeze({code: 'derived', title: 'Вычисляемые показатели'}),
    Object.freeze({code: 'modifiers', title: 'Модификаторы'}),
    Object.freeze({code: 'resources', title: 'Ресурсы'})
]);

const mechanicCodes = new Set(BOOK_MECHANIC_CHAPTERS.map((chapter) => chapter.code));

export const BOOK_PARAMETER_KINDS = Object.freeze({
    attributes: 'Исходное значение',
    derived: 'Вычисляемый показатель',
    resources: 'Ресурс'
});

export function isBookRuleSection(code) {
    return sectionCodes.has(code);
}

export function isBookMechanicChapter(code) {
    return mechanicCodes.has(code);
}

export function bookMechanicChapterTitle(code) {
    const chapter = BOOK_MECHANIC_CHAPTERS.find((item) => item.code === code);

    if (!chapter) {
        throw new Error('Неизвестная глава механики.');
    }

    return chapter.title;
}

export function bookRuleSectionTitle(code) {
    const section = BOOK_RULE_SECTIONS.find((item) => item.code === code);

    if (!section) {
        throw new Error('Неизвестный смысловой раздел книги.');
    }

    return section.title;
}

export function bookParameterId(kind, code) {
    if (!Object.hasOwn(BOOK_PARAMETER_KINDS, kind)) {
        throw new Error('Неизвестный тип параметра.');
    }

    return `${kind}:${code}`;
}

function definitionKind(kind, code) {
    if (kind !== 'derived') return kind;

    return isBookModifierCode(code) ? 'modifiers' : 'derived';
}

// Параметры одного технического типа.
// modifiers и derived делят общую коллекцию calculations.derived
// по соглашению об именах кодов.
export function getBookKindEntries(rules, kind) {
    if (!isBookMechanicChapter(kind) || kind === 'basis' || !rules) return [];

    const entries = [];

    for (const [collection, definitions] of Object.entries(ruleCollections(rules))) {
        for (const [code, definition] of Object.entries(definitions)) {
            if (definitionKind(collection, code) !== kind) continue;

            entries.push({
                id: bookParameterId(collection, code),
                kind: collection,
                code,
                definition,
                sectionTitle: ruleSectionTitle(definition)
            });
        }
    }

    return entries;
}

export function findBookKindEntry(rules, kind, id) {
    return getBookKindEntries(rules, kind).find((entry) => entry.id === id) ?? null;
}

// Параметры, привязанные к смысловому разделу книги.
// Используется только при переносе параметра между главами текста.
export function getBookSectionEntries(rules, chapter) {
    if (!isBookRuleSection(chapter) || !rules) return [];

    const entries = [];

    for (const [kind, collection] of Object.entries(ruleCollections(rules))) {
        for (const [code, definition] of Object.entries(collection)) {
            const sectionTitle = ruleSectionTitle(definition);
            const sectionCode = sectionByTitle.get(sectionTitle) ?? 'other_parameters';

            if (sectionCode !== chapter) continue;

            const id = bookParameterId(kind, code);

            entries.push({id, kind, code, definition, sectionTitle});
        }
    }

    return entries;
}

export function findBookSectionEntry(rules, chapter, id) {
    return getBookSectionEntries(rules, chapter).find((entry) => entry.id === id) ?? null;
}

export function bookParameterLabel(entry) {
    const title = entry.definition.label || entry.code;
    const kind = BOOK_PARAMETER_KINDS[entry.kind];

    return `${title} · ${kind}`;
}
