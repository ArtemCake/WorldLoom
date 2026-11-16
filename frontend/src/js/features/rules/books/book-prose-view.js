// frontend/src/js/features/rules/books/book-prose-view.js

import { readBookInline, readBookProse } from './book-prose-data.js';

function element(document, tag, text = '') {
    const node = document.createElement(tag);
    node.textContent = text;
    return node;
}

function appendInline(document, host, value) {
    const lines = value.split('\n');

    lines.forEach((line, index) => {
        if (index > 0) host.append(document.createElement('br'));

        for (const part of readBookInline(line)) {
            if (part.type === 'text') {
                host.append(document.createTextNode(part.text));
            } else {
                const tags = { strong: 'strong', em: 'em', code: 'code' };
                host.append(element(document, tags[part.type], part.text));
            }
        }
    });
}

function blockElement(document, block, headingLevel) {
    if (block.type === 'code') {
        const pre = document.createElement('pre');
        pre.append(element(document, 'code', block.text));
        return pre;
    }

    if (block.type === 'list') {
        const list = document.createElement(block.ordered ? 'ol' : 'ul');
        if (block.ordered) list.setAttribute('start', String(block.start));

        for (const value of block.items) {
            const item = document.createElement('li');
            appendInline(document, item, value);
            list.append(item);
        }

        return list;
    }

    const tag = block.type === 'heading'
        ? `h${Math.min(headingLevel + block.level - 1, 6)}`
        : block.type === 'quote' ? 'blockquote' : 'p';
    const node = document.createElement(tag);

    appendInline(document, node, block.text);
    return node;
}

export function createBookProse(document, value, { headingLevel = 4 } = {}) {
    if (!Number.isInteger(headingLevel) || headingLevel < 1 || headingLevel > 6) {
        throw new TypeError('Уровень заголовков должен быть целым числом от 1 до 6.');
    }

    const blocks = readBookProse(value);
    const host = document.createElement('div');
    host.className = 'rules-catalog__prose';

    for (const block of blocks) {
        host.append(blockElement(document, block, headingLevel));
    }

    return host;
}