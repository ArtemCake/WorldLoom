// frontend/src/js/features/game-systems/book/book-basis-changes.js

import {collectEngineOverrides, jsonEqual} from '../editor/game-system-engine-origin.js';
import {elementIn} from '../../../shared/dom/elements.js';

function record(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function ensure(condition, message) {
    if (!condition) throw new Error(message);
}

function compareCollection(base, current, initial = null) {
    const codes = new Set([...Object.keys(base), ...Object.keys(current)]);
    const changes = [];

    for (const code of codes) {
        const inherited = Object.hasOwn(base, code);
        const present = Object.hasOwn(current, code);

        let status;

        if (!inherited) {
            status = 'added';
        } else if (!present) {
            status = 'removed';
        } else {
            const sameDefinition = jsonEqual(base[code], current[code]);
            const sameInitial = initial === null || jsonEqual(initial.base[code], initial.current[code]);

            if (sameDefinition && sameInitial) continue;

            status = 'changed';
        }

        const definition = present ? current[code] : base[code];
        const label = typeof definition?.label === 'string' ? definition.label.trim() : '';

        changes.push({code, label: label || code, status});
    }

    return changes;
}

export function getBookBasisChanges(document) {
    ensure(record(document), 'Не удалось прочитать документ книги.');

    if (document.origin === null) return null;

    const origin = document.origin;
    const base = origin?.engine_version?.rules_json;
    const current = document.rules;

    ensure(record(base) && record(current), 'Не удалось прочитать правила системы и основы.');

    collectEngineOverrides(base, current, origin.rules_overrides);

    return [
        {
            code: 'attributes',
            title: 'Характеристики',
            items: compareCollection(base.calculations.attributes, current.calculations.attributes, {
                base: base.initial_attributes,
                current: current.initial_attributes
            })
        },
        {
            code: 'derived',
            title: 'Формулы и модификаторы',
            items: compareCollection(base.calculations.derived, current.calculations.derived)
        },
        {
            code: 'rulebook',
            title: 'Описание правил',
            items: compareCollection(base.rulebook ?? {}, current.rulebook ?? {})
        },
        {
            code: 'resources',
            title: 'Ресурсы',
            items: compareCollection(base.resources ?? {}, current.resources ?? {})
        },
    ];
}

export function renderBookBasisChanges(host, document, {onRestore = null, canRestore = false} = {}) {
    const groups = getBookBasisChanges(document);

    if (groups === null) return;

    const ownerDocument = host.ownerDocument;

    const section = elementIn(ownerDocument, 'section');
    const total = groups.reduce((count, group) => count + group.items.length, 0);

    section.append(elementIn(ownerDocument, 'h4', 'Изменения относительно основы'));

    if (total === 0) {
        section.append(elementIn(ownerDocument, 'p', 'Определения, начальные значения и описание правил совпадают с опубликованной основой.'));
    } else {
        const statuses = {
            added: 'Добавлено',
            changed: 'Изменено',
            removed: 'Удалено из системы'
        };

        for (const group of groups) {
            if (group.items.length === 0) continue;

            const list = elementIn(ownerDocument, 'ul');

            section.append(elementIn(ownerDocument, 'h5', group.title));

            for (const item of group.items) {
                const entry = elementIn(ownerDocument, 'li', `${statuses[item.status]}: ${item.label} (${item.code}).`);

                if (item.status !== 'added' && typeof onRestore === 'function') {
                    const action = elementIn(ownerDocument, 'button', 'Вернуть к основе', 'btn btn-outline-primary');

                    action.type = 'button';
                    action.disabled = !canRestore;
                    action.setAttribute('aria-label', `Вернуть к основе: ${item.label}`);
                    action.addEventListener('click', () => onRestore(group.code, item.code));

                    entry.append(ownerDocument.createTextNode(' '), action);
                }

                list.append(entry);
            }

            section.append(list);
        }
    }

    section.append(elementIn(ownerDocument, 
        'p',
         'Сравнение учитывает определения, начальные значения и описание глав. Исходная публикация не изменяется.',
        'rules-book__muted'
    ));

    if (typeof onRestore === 'function') {
        section.append(elementIn(ownerDocument, 
            'p',
            'Возврат заменяет выбранное определение или описание главы целиком. У исходного значения возвращается и начальное.',
            'rules-book__muted'
        ));
    }

    host.append(section);
}
