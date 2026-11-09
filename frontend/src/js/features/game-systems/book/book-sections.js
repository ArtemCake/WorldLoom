// frontend/src/js/features/game-systems/book/book-sections.js

import {ruleCollections, ruleSectionTitle} from '../editor/shared/rule-sections.js';

const sections = [
    {code: 'abilities', title: 'Характеристики'},
    {code: 'level_mastery', title: 'Уровень и мастерство'},
    {code: 'saving_throws', title: 'Спасброски'},
    {code: 'skills', title: 'Навыки'},
    {code: 'passive_checks', title: 'Пассивные проверки'},
    {code: 'initiative', title: 'Инициатива'},
    {code: 'defense', title: 'Защита'},
    {code: 'hit_points_resources', title: 'Хиты и ресурсы'},
    {code: 'features', title: 'Особенности'},
    {code: 'ability_checks', title: 'Проверки характеристик'},
    {code: 'other_parameters', title: 'Прочие параметры'}
];

export const BOOK_RULE_SECTIONS = Object.freeze(sections.map((section) => Object.freeze(section)));

const sectionCodes = new Set(BOOK_RULE_SECTIONS.map((section) => section.code));
const sectionByTitle = new Map(BOOK_RULE_SECTIONS.map((section) => [section.title, section.code]));

export const BOOK_PARAMETER_KINDS = Object.freeze({
    attributes: 'Исходное значение',
    derived: 'Вычисляемый показатель',
    resources: 'Ресурс'
});

export function isBookRuleSection(code) {
    return sectionCodes.has(code);
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
