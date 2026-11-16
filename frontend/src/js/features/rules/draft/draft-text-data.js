// frontend/src/js/features/rules/draft/draft-text-data.js

import { readBookTextContent, validateBookToc } from './draft-toc-data.js';
import { applyDraftSourceCommand } from './draft-source-data.js';

const SOURCE_FIELDS = ['title', 'publisher', 'locator', 'url', 'license_name', 'license_url', 'attribution'];

function ensure(condition, message) {
    if (!condition) throw new TypeError(message);
}

function isObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function moveText(toc, node, delta) {
    ensure([-1, 1].includes(delta), 'Некорректное направление перемещения.');

    const siblings = toc.filter((item) => item.parent_key === node.parent_key);
    siblings.sort((left, right) => left.position - right.position);

    const index = siblings.findIndex((item) => item.key === node.key);
    const neighbor = siblings[index + delta];

    if (neighbor) {
        [node.position, neighbor.position] = [neighbor.position, node.position];
    }
}

function reparentText(toc, node, parentKey) {
    const parentExists = parentKey === null || toc.some((item) => item.key === parentKey && item.kind === 'chapter');
    ensure(parentExists, 'Выберите существующую главу или корень книги.');

    if (parentKey === node.parent_key) return;

    const siblings = toc.filter((item) => item.parent_key === parentKey);
    const position = siblings.reduce((maximum, item) => Math.max(maximum, item.position), -1) + 1;

    ensure(Number.isSafeInteger(position), 'Невозможно добавить позицию после последнего пункта.');

    node.parent_key = parentKey;
    node.position = position;
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

    const node = toc[index];

    if (command.type === 'update') {
        node.content = readBookTextContent(command.content);
    } else if (command.type === 'remove') {
        toc.splice(index, 1);
    } else if (command.type === 'move') {
        moveText(toc, node, command.delta);
    } else if (command.type === 'reparent') {
        reparentText(toc, node, command.parent_key);
    } else {
        throw new TypeError('Неизвестная операция с собственным текстом.');
    }

    return validateBookToc(toc);
}

export function applyBookTextSourceCommand(value, command) {
    ensure(Array.isArray(value), 'Оглавление должно быть списком.');
    ensure(isObject(command), 'Не задана операция с источником.');

    const toc = structuredClone(value);
    const node = toc.find((item) => item?.key === command.key && item.kind === 'text');
    ensure(node && isObject(node.content), 'Не найден собственный текст для изменения.');

    node.content.sources = applyDraftSourceCommand(node.content.sources, command);
    return toc;
}