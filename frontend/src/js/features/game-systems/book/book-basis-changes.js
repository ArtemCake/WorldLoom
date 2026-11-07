import {collectEngineOverrides, jsonEqual} from '../editor/game-system-engine-origin.js';

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
            code: 'resources',
            title: 'Ресурсы',
            items: compareCollection(base.resources ?? {}, current.resources ?? {})
        }
    ];
}

export function renderBookBasisChanges(host, document) {
    const groups = getBookBasisChanges(document);

    if (groups === null) return;

    const ownerDocument = host.ownerDocument;

    function node(tag, text = '', className = '') {
        const element = ownerDocument.createElement(tag);

        element.textContent = text;
        if (className) element.className = className;

        return element;
    }

    const section = node('section');
    const total = groups.reduce((count, group) => count + group.items.length, 0);

    section.append(node('h4', 'Изменения относительно основы'));

    if (total === 0) {
        section.append(node('p', 'Характеристики, формулы и ресурсы совпадают с опубликованной основой.'));
    } else {
        const statuses = {
            added: 'Добавлено',
            changed: 'Изменено',
            removed: 'Удалено из системы'
        };

        for (const group of groups) {
            if (group.items.length === 0) continue;

            const list = node('ul');

            section.append(node('h5', group.title));

            for (const item of group.items) {
                list.append(node('li', `${statuses[item.status]}: ${item.label} (${item.code}).`));
            }

            section.append(list);
        }
    }

    section.append(node(
        'p',
        'Сравнение учитывает определения и начальные значения характеристик. Исходная публикация не изменяется.',
        'rules-book__muted'
    ));

    host.append(section);
}
