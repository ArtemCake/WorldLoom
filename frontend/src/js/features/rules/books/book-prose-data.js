// frontend/src/js/features/rules/books/book-prose-data.js

import { readBookTable } from './book-table-data.js';

function textValue(value) {
    if (typeof value !== 'string') throw new TypeError('Содержание должно быть строкой.');
    return value;
}

function lineKind(line) {
    if (/^```[^`]*$/u.test(line)) return { type: 'fence' };

    const heading = /^(#{1,6})[ \t]+(.+)$/u.exec(line);
    if (heading) return { type: 'heading', level: heading[1].length, text: heading[2] };

    const quote = /^>[ \t]?(.*)$/u.exec(line);
    if (quote) return { type: 'quote', text: quote[1] };

    const bullet = /^[-+*][ \t]+(.+)$/u.exec(line);
    if (bullet) return { type: 'list', ordered: false, text: bullet[1] };

    const ordered = /^(\d{1,9})[.)][ \t]+(.+)$/u.exec(line);
    if (ordered) return { type: 'list', ordered: true, start: Number(ordered[1]), text: ordered[2] };

    return { type: 'paragraph', text: line };
}

export function readBookProse(value) {
    const lines = textValue(value).replace(/\r\n?/gu, '\n').split('\n');
    const blocks = [];
    let index = 0;

    while (index < lines.length) {
        if (!lines[index].trim()) {
            index += 1;
            continue;
        }

        const table = readBookTable(lines, index);

        if (table) {
            blocks.push(table.block);
            index = table.nextIndex;
            continue;
        }

        const first = lineKind(lines[index]);
        index += 1;

        if (first.type === 'fence') {
            const content = [];

            while (index < lines.length && !/^```[ \t]*$/u.test(lines[index])) {
                content.push(lines[index]);
                index += 1;
            }

            if (index < lines.length) index += 1;
            blocks.push({ type: 'code', text: content.join('\n') });
            continue;
        }

        if (first.type === 'heading') {
            blocks.push(first);
            continue;
        }

        if (first.type === 'list') {
            const items = [first.text];

            while (index < lines.length) {
                const next = lineKind(lines[index]);
                if (next.type !== 'list' || next.ordered !== first.ordered) break;
                items.push(next.text);
                index += 1;
            }

            blocks.push({
                type: 'list',
                ordered: first.ordered,
                start: first.ordered ? first.start : null,
                items
            });
            continue;
        }

        const content = [first.text];

        while (index < lines.length && lines[index].trim()) {
            const next = lineKind(lines[index]);
            if (next.type !== first.type || readBookTable(lines, index)) break;
            content.push(next.text);
            index += 1;
        }

        blocks.push({ type: first.type, text: content.join('\n') });
    }

    return blocks;
}

export { readBookInline } from './book-inline-data.js';
