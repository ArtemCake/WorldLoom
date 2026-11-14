// frontend/src/js/features/rules/draft/draft-toc-data.js

import { ruleId } from '../rules-http.js';

const MAX_NODES = 2000;
const MAX_DEPTH = 32;
const KEY_PATTERN = /^[a-z0-9]+(?:[-_][a-z0-9]+)*$/u;

function ensure(condition, message) {
    if (!condition) throw new TypeError(message);
}

function validKey(value) {
    if (typeof value !== 'string' || value.length > 100) return false;
    return KEY_PATTERN.exec(value)?.[0] === value;
}

function validTitle(value) {
    return typeof value === 'string' && value.trim().length > 0 && [...value].length <= 200;
}

function isObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function limitedText(value, maximum, label, minimum = 0) {
    ensure(typeof value === 'string', `${label}: ожидается строка.`);

    const length = [...value].length;
    ensure(length >= minimum && length <= maximum, `${label}: недопустимая длина.`);
}

function optionalText(value, maximum, label) {
    if (value !== undefined && value !== null) limitedText(value, maximum, label);
}

function sourceUrl(value) {
    if (value === undefined || value === null) return;

    ensure(typeof value === 'string', 'Адрес источника должен быть строкой.');

    let parsed;

    try {
        parsed = new URL(value);
    } catch {
        throw new TypeError('Некорректный адрес источника.');
    }

    ensure(['http:', 'https:'].includes(parsed.protocol), 'Источник должен использовать HTTP или HTTPS.');
}

function validateTextSource(source) {
    ensure(isObject(source), 'Некорректный источник текста.');

    const fields = ['title', 'publisher', 'locator', 'url', 'license_name', 'license_url', 'attribution'];
    ensure(Object.keys(source).every((key) => fields.includes(key)), 'Неизвестное поле источника.');
    ensure(validTitle(source.title), 'Укажите название источника длиной до 200 символов.');

    optionalText(source.publisher, 200, 'Издатель');
    optionalText(source.locator, 500, 'Место в источнике');
    optionalText(source.license_name, 200, 'Название лицензии');
    optionalText(source.attribution, 5000, 'Атрибуция');
    sourceUrl(source.url);
    sourceUrl(source.license_url);
}

export function readBookTextContent(value) {
    ensure(isObject(value), 'Не задано содержание собственного текста.');

    const defaults = {
        schema_version: 1,
        summary: '',
        body: '',
        language: 'ru',
        edition_key: null,
        audience: 'both',
        rule_kind: 'base',
        sources: []
    };
    const fields = ['title', ...Object.keys(defaults)];

    ensure(Object.keys(value).every((key) => fields.includes(key)), 'Неизвестное поле собственного текста.');

    const content = { ...defaults, ...structuredClone(value) };

    ensure(content.schema_version === 1, 'Неподдерживаемый формат собственного текста.');
    ensure(validTitle(content.title), 'Укажите название текста длиной до 200 символов.');
    limitedText(content.summary, 5000, 'Описание текста');
    limitedText(content.body, 300000, 'Содержание текста');
    limitedText(content.language, 20, 'Код языка', 2);
    ensure(Boolean(content.language.trim()), 'Код языка не может состоять из пробелов.');

    if (content.edition_key !== null) {
        limitedText(content.edition_key, 100, 'Код редакции', 1);
        ensure(Boolean(content.edition_key.trim()), 'Код редакции не может состоять из пробелов.');
    }

    ensure(['players', 'gm', 'both'].includes(content.audience), 'Неизвестная аудитория текста.');
    ensure(['base', 'optional', 'supplement', 'homebrew'].includes(content.rule_kind), 'Неизвестный вид правила.');
    ensure(Array.isArray(content.sources) && content.sources.length <= 100, 'Некорректный список источников текста.');

    for (const source of content.sources) validateTextSource(source);

    return content;
}

export function validateBookToc(value) {
    ensure(Array.isArray(value), 'Оглавление должно быть списком.');
    ensure(value.length <= MAX_NODES, 'В оглавлении может быть не более 2000 пунктов.');

    const nodes = new Map();
    const positions = new Map();

    for (const node of value) {
        ensure(node && typeof node === 'object' && !Array.isArray(node), 'Некорректный пункт оглавления.');
        ensure(validKey(node.key), 'Некорректный ключ пункта оглавления.');
        ensure(!nodes.has(node.key), 'Повторяется ключ пункта оглавления.');
        ensure(['chapter', 'article', 'text'].includes(node.kind), 'Неизвестный тип пункта оглавления.');
        ensure(node.parent_key === null || validKey(node.parent_key), 'Некорректный ключ родительской главы.');
        ensure(Number.isSafeInteger(node.position) && node.position >= 0, 'Некорректная позиция пункта.');

        if (node.kind === 'chapter') {
            ensure(validTitle(node.title), 'Название главы должно содержать от 1 до 200 символов и не быть пустым.');
        } else {
            ensure(node.title === null || validTitle(node.title), 'Некорректное название раздела.');

            if (node.kind === 'article') {
                ruleId(node.article_version_id);
            } else {
                const fields = ['kind', 'key', 'parent_key', 'position', 'title', 'content'];

                ensure(Object.keys(node).every((key) => fields.includes(key)), 'Неизвестное поле собственного раздела.');
                readBookTextContent(node.content);
            }
        }

        const occupied = positions.get(node.parent_key) || new Set();
        ensure(!occupied.has(node.position), 'У пунктов одного уровня совпадают позиции.');
        occupied.add(node.position);
        positions.set(node.parent_key, occupied);
        nodes.set(node.key, node);
    }

    for (const node of nodes.values()) {
        const visited = new Set([node.key]);
        let parent = node.parent_key;

        while (parent !== null) {
            ensure(nodes.has(parent), 'Не найдена родительская глава.');
            ensure(!visited.has(parent), 'Оглавление содержит цикл.');

            const ancestor = nodes.get(parent);
            ensure(ancestor.kind === 'chapter', 'Родителем пункта может быть только глава.');

            visited.add(parent);
            ensure(visited.size <= MAX_DEPTH, 'Глубина оглавления превышает 32 уровня.');
            parent = ancestor.parent_key;
        }
    }

    return structuredClone(value);
}

export function applyChapterCommand(value, command) {
    const toc = validateBookToc(value);
    ensure(command && typeof command === 'object', 'Не задана операция с главой.');

    if (command.type === 'add') {
        ensure(validKey(command.key), 'Некорректный ключ новой главы.');
        ensure(!toc.some((node) => node.key === command.key), 'Такой ключ главы уже существует.');
        ensure(validTitle(command.title), 'Укажите название главы длиной не более 200 символов.');

        const parent = command.parent_key;

        if (parent !== null) {
            ensure(toc.some((node) => node.key === parent && node.kind === 'chapter'), 'Не найдена родительская глава.');
        }

        const siblings = toc.filter((node) => node.parent_key === parent);
        const lastPosition = siblings.reduce((maximum, node) => Math.max(maximum, node.position), -1);
        const position = lastPosition + 1;

        ensure(Number.isSafeInteger(position), 'Невозможно добавить позицию после последнего пункта.');
        toc.push({ kind: 'chapter', key: command.key, parent_key: parent, position, title: command.title });
        return validateBookToc(toc);
    }

    const chapter = toc.find((node) => node.key === command.key);
    ensure(chapter?.kind === 'chapter', 'Не найдена глава для изменения.');

    if (command.type === 'rename') {
        ensure(validTitle(command.title), 'Укажите название главы длиной не более 200 символов.');
        chapter.title = command.title;
    } else if (command.type === 'move') {
        ensure([-1, 1].includes(command.delta), 'Некорректное направление перемещения.');

        const siblings = toc.filter((node) => node.parent_key === chapter.parent_key);
        siblings.sort((left, right) => left.position - right.position);

        const index = siblings.findIndex((node) => node.key === chapter.key);
        const neighbor = siblings[index + command.delta];

        if (neighbor) {
            [chapter.position, neighbor.position] = [neighbor.position, chapter.position];
        }
    } else if (command.type === 'remove') {
        ensure(!toc.some((node) => node.parent_key === chapter.key), 'Можно удалить только пустую главу.');
        toc.splice(toc.indexOf(chapter), 1);
    } else {
        throw new TypeError('Неизвестная операция с главой.');
    }

    return validateBookToc(toc);
}