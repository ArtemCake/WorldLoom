// frontend/src/js/features/rules/draft/draft-section-data.js

import { ruleId } from '../rules-http.js';
import { validateBookToc } from './draft-toc-data.js';

function ensure(condition, message) {
    if (!condition) throw new TypeError(message);
}

export function readSectionVersion(value, articleId, versionId) {
    ruleId(articleId);
    ruleId(versionId);

    ensure(value && typeof value === 'object', 'Не получена публикация раздела.');
    ensure(value.id === versionId && value.article_id === articleId, 'Сервер вернул другую публикацию.');
    ensure(Number.isSafeInteger(value.version_number) && value.version_number > 0, 'Некорректный номер публикации.');

    const content = value.content_json;

    ensure(content && content.schema_version === 1, 'Неподдерживаемое содержание раздела.');
    ensure(typeof content.title === 'string' && content.title.trim(), 'Не указано название раздела.');
    ensure([...content.title].length <= 200, 'Название раздела слишком длинное.');
    ensure(typeof content.body === 'string' && content.body.trim(), 'В публикации отсутствует текст.');
    ensure(Array.isArray(content.sources), 'В публикации отсутствует список источников.');

    return structuredClone(value);
}

export function applySectionCommand(value, command) {
    const toc = validateBookToc(value);
    ensure(command && typeof command === 'object', 'Не задана операция с разделом.');

    if (command.type === 'attach') {
        const publication = command.publication;
        const checked = readSectionVersion(publication, publication?.article_id, publication?.id);
        const siblings = toc.filter((node) => node.parent_key === command.parent_key);
        const lastPosition = siblings.reduce((maximum, node) => Math.max(maximum, node.position), -1);

        toc.push({
            kind: 'article',
            key: command.key,
            parent_key: command.parent_key,
            position: lastPosition + 1,
            title: checked.content_json.title,
            article_version_id: checked.id
        });

        return validateBookToc(toc);
    }

    const section = toc.find((node) => node.key === command.key);
    ensure(section?.kind === 'article', 'Не найден раздел для изменения.');

    if (command.type === 'remove') {
        toc.splice(toc.indexOf(section), 1);
    } else if (command.type === 'move') {
        ensure([-1, 1].includes(command.delta), 'Некорректное направление перемещения.');

        const siblings = toc.filter((node) => node.parent_key === section.parent_key);
        siblings.sort((left, right) => left.position - right.position);

        const index = siblings.findIndex((node) => node.key === section.key);
        const neighbor = siblings[index + command.delta];

        if (neighbor) {
            [section.position, neighbor.position] = [neighbor.position, section.position];
        }
    } else {
        throw new TypeError('Неизвестная операция с разделом.');
    }

    return validateBookToc(toc);
}
