// frontend/src/js/features/rules/books/book-inline-data.js

function httpAddress(value) {
    if (!/^https?:\/\//iu.test(value)) return null;
    if (/[\s\u0000-\u001f\u007f<>"\\]/u.test(value)) return null;

    try {
        const address = new URL(value);

        if (!['http:', 'https:'].includes(address.protocol)) return null;
        if (!address.hostname || address.username || address.password) return null;

        return value;
    } catch {
        return null;
    }
}

function inlinePart(marked) {
    if (marked.startsWith('`')) {
        return { type: 'code', text: marked.slice(1, -1) };
    }

    if (marked.startsWith('![')) {
        return { type: 'text', text: marked };
    }

    if (marked.startsWith('[')) {
        const separator = marked.indexOf('](');
        const text = marked.slice(1, separator);
        const href = httpAddress(marked.slice(separator + 2, -1));

        if (!href || !text.trim()) return { type: 'text', text: marked };

        return { type: 'link', text, href };
    }

    const strong = marked.startsWith('**');
    const width = strong ? 2 : 1;

    return { type: strong ? 'strong' : 'em', text: marked.slice(width, -width) };
}

export function readBookInline(value) {
    if (typeof value !== 'string') {
        throw new TypeError('Содержание должно быть строкой.');
    }

    const pattern = /(`[^`\n]+`|!?\[[^\[\]\n]+\]\([^\s()]+\)|\*\*[^*\n]+\*\*|\*[^*\n]+\*)/gu;
    const parts = [];
    let position = 0;

    for (const match of value.matchAll(pattern)) {
        if (match.index > position) {
            parts.push({ type: 'text', text: value.slice(position, match.index) });
        }

        parts.push(inlinePart(match[0]));
        position = match.index + match[0].length;
    }

    if (position < value.length) {
        parts.push({ type: 'text', text: value.slice(position) });
    }

    return parts;
}
