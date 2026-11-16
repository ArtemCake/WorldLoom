// frontend/src/js/features/rules/books/book-sources-view.js

function element(document, tag, className, text = '') {
    const node = document.createElement(tag);
    node.className = className;
    node.textContent = text;
    return node;
}

function sourceLink(document, value, title) {
    if (!value) return null;

    let parsed;

    try {
        parsed = new URL(value);
    } catch {
        return null;
    }

    if (!['http:', 'https:'].includes(parsed.protocol)) return null;

    const link = element(document, 'a', '', title);
    link.href = value;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.setAttribute('hx-boost', 'false');

    const line = element(document, 'p', '');
    line.append(link);
    return line;
}

export function createBookSources(document, sources, title = 'Источники и условия использования') {
    if (!sources.length) return null;

    const details = element(document, 'details', 'rules-catalog__sources');
    details.append(element(document, 'summary', '', title));

    for (const source of sources) {
        const item = element(document, 'div', 'rules-catalog__source');
        item.append(element(document, 'p', '', source.title));

        for (const key of ['publisher', 'locator', 'license_name', 'attribution']) {
            if (source[key]) {
                item.append(element(document, 'p', 'rules-catalog__prose', source[key]));
            }
        }

        for (const key of ['url', 'license_url']) {
            const caption = key === 'url' ? 'Источник' : 'Условия лицензии';
            const line = sourceLink(document, source[key], caption);
            if (line) item.append(line);
        }

        details.append(item);
    }

    return details;
}
