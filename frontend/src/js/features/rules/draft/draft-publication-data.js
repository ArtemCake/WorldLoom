// frontend/src/js/features/rules/draft/draft-publication-data.js

import { ruleId } from '../rules-http.js';
import { validateBookToc } from './draft-toc-data.js';

function ensure(condition, message) {
    if (!condition) throw new TypeError(message);
}

export function readBookPublication(value, bookId, expectedRevision) {
    ruleId(bookId);

    ensure(Number.isSafeInteger(expectedRevision) && expectedRevision > 0, 'Некорректная исходная ревизия.');
    ensure(Number.isSafeInteger(expectedRevision + 1), 'Ревизия вышла за поддерживаемый диапазон.');
    ensure(value && typeof value === 'object', 'Не получен результат публикации.');

    const publication = value.publication;

    ensure(publication && typeof publication === 'object', 'В ответе отсутствует публикация.');
    ruleId(publication.id);
    ensure(publication.book_id === bookId, 'Публикация относится к другой книге.');
    ensure(publication.source_draft_revision === expectedRevision, 'Опубликована другая ревизия черновика.');
    ensure(value.draft_revision === expectedRevision + 1, 'Сервер вернул неожиданную ревизию черновика.');

    const number = publication.version_number;
    ensure(Number.isSafeInteger(number) && number > 0, 'Некорректный номер публикации.');

    const content = publication.content_json;
    ensure(content && content.schema_version === 1, 'Неподдерживаемое содержание публикации.');

    const toc = validateBookToc(content.toc);
    ensure(toc.some((node) => node.kind === 'article'), 'Публикация книги не содержит разделов.');

    return structuredClone(value);
}