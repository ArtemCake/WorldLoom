// frontend/src/js/features/rules/draft/draft-text-data.js

import { readBookTextContent, validateBookToc } from './draft-toc-data.js';

function ensure(condition, message) {
    if (!condition) throw new TypeError(message);
}

function isObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export function applyBookTextCommand(value, command) {
    const toc = validateBookToc(value);

    ensure(isObject(command), 'Не задана операция с собственным текстом.');

    if (command.type === 'add') {
        ensure(isObject(command.node) && command.node.kind === 'text', 'Добавить можно только собственный текст.');

        const node = structuredClone(command.node);
        node.content = readBookTextContent(node.content);
        toc.push(node);

        return validateBookToc(toc);
    }

    const index = toc.findIndex((node) => node.key === command.key);
    ensure(index >= 0 && toc[index].kind === 'text', 'Не найден собственный текст для изменения.');

    if (command.type === 'update') {
        toc[index].content = readBookTextContent(command.content);
    } else if (command.type === 'remove') {
        toc.splice(index, 1);
    } else {
        throw new TypeError('Неизвестная операция с собственным текстом.');
    }

    return validateBookToc(toc);
}