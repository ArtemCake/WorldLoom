// frontend/src/js/features/game-systems/editor/shared/rule-sections.js

import {BOOK_DESIGN_CHAPTERS} from '../../book/book-design-catalog.js';

export const DEFAULT_RULE_SECTIONS = Object.freeze(
    BOOK_DESIGN_CHAPTERS.map((chapter) => chapter.title)
);

export const OTHER_RULE_SECTION = 'Прочие параметры';

export function normalizeRuleSection(value = '') {
    if (typeof value !== 'string') {
        throw new Error('Раздел параметра должен быть текстом.');
    }

    const section = value.trim();

    if ([...section].length > 100) {
        throw new Error('Название раздела: не более 100 символов.');
    }

    return section;
}

export function ruleSectionTitle(definition = {}) {
    return normalizeRuleSection(definition.section) || OTHER_RULE_SECTION;
}

export function ruleCollections(rules) {
    return {
        attributes: rules?.calculations?.attributes ?? {},
        derived: rules?.calculations?.derived ?? {},
        resources: rules?.resources ?? {}
    };
}

export function ruleSectionTitles(rules) {
    const titles = new Set();

    for (const collection of Object.values(ruleCollections(rules))) {
        for (const definition of Object.values(collection)) {
            titles.add(ruleSectionTitle(definition));
        }
    }

    const standard = DEFAULT_RULE_SECTIONS.filter((title) => titles.has(title));
    const custom = [...titles].filter((title) => !DEFAULT_RULE_SECTIONS.includes(title) && title !== OTHER_RULE_SECTION);

    return [
        ...standard,
        ...custom,
        ...(titles.has(OTHER_RULE_SECTION) ? [OTHER_RULE_SECTION] : [])
    ];
}

export function groupRuleEntries(rules, entries) {
    const groups = new Map();

    for (const [code, definition] of entries) {
        const title = ruleSectionTitle(definition);

        if (!groups.has(title)) groups.set(title, []);

        groups.get(title).push([code, definition]);
    }

    return ruleSectionTitles(rules)
        .filter((title) => groups.has(title))
        .map((title) => ({title, entries: groups.get(title)}));
}

export function groupedRuleEntries(rules, kind, allowedCodes = null) {
    const collection = ruleCollections(rules)[kind];

    if (!collection) {
        throw new Error('Неизвестный тип параметров макета.');
    }

    const allowed = allowedCodes === null ? null : new Set(allowedCodes);
    const entries = Object.entries(collection).filter(([code]) => allowed === null || allowed.has(code));

    return groupRuleEntries(rules, entries);
}

export function appendGroupedRuleOptions(select, rules, kind, allowedCodes = null) {
    const ownerDocument = select.ownerDocument;

    for (const group of groupedRuleEntries(rules, kind, allowedCodes)) {
        const options = ownerDocument.createElement('optgroup');

        options.label = group.title;

        for (const [code, definition] of group.entries) {
            const option = ownerDocument.createElement('option');

            option.value = code;
            option.textContent = definition.label || code;
            options.append(option);
        }

        select.append(options);
    }
}

let nextSectionField = 0;

export function createRuleSectionField(parent, definition = {}, rules = null) {
    const ownerDocument = parent.ownerDocument;
    const wrapper = ownerDocument.createElement('label');
    const caption = ownerDocument.createElement('span');
    const input = ownerDocument.createElement('input');
    const suggestions = ownerDocument.createElement('datalist');

    nextSectionField += 1;

    wrapper.className = 'rules-book__field';
    caption.textContent = 'Раздел макета';
    input.type = 'text';
    input.maxLength = 100;
    input.value = normalizeRuleSection(definition.section);
    input.placeholder = OTHER_RULE_SECTION;
    suggestions.id = `rule-section-options-${nextSectionField}`;
    input.setAttribute('list', suggestions.id);

    const titles = new Set([...DEFAULT_RULE_SECTIONS, ...ruleSectionTitles(rules)]);

    for (const title of titles) {
        const option = ownerDocument.createElement('option');

        option.value = title;
        suggestions.append(option);
    }

    wrapper.append(caption, input, suggestions);
    parent.append(wrapper);

    return {
        element: wrapper,
        input,
        collect: () => normalizeRuleSection(input.value)
    };
}
