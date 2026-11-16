// frontend/src/js/features/rules/draft/draft-working-data.js

import { ruleId } from '../rules-http.js';
import { validateBookToc } from './draft-toc-data.js';

function ensure(condition, message) {
    if (!condition) throw new TypeError(message);
}

function object(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function revision(value) {
    return Number.isSafeInteger(value) && value > 0;
}

function canonical(value) {
    if (Array.isArray(value)) return value.map(canonical);

    if (object(value)) {
        return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonical(value[key])]));
    }

    return value;
}

function same(left, right) {
    return JSON.stringify(canonical(left)) === JSON.stringify(canonical(right));
}

function readVersion(value, bookId) {
    ensure(object(value), 'Не получена последняя публикация книги.');
    ruleId(value.id);
    ensure(value.book_id === bookId, 'Публикация относится к другой книге.');
    ensure(revision(value.version_number), 'Некорректный номер публикации.');
    ensure(revision(value.source_draft_revision), 'Некорректная исходная ревизия публикации.');

    const content = value.content_json;
    ensure(object(content) && content.schema_version === 1, 'Неподдерживаемое содержание публикации.');
    ensure(Array.isArray(content.sources), 'В публикации отсутствует список источников.');

    const toc = validateBookToc(content.toc);
    ensure(toc.every((node) => node.kind !== 'text'), 'Публикация содержит незакреплённый собственный текст.');
    ensure(toc.some((node) => node.kind === 'article'), 'В публикации отсутствуют разделы.');

    return structuredClone(value);
}

export function readWorkingDraft(value, bookId) {
    ruleId(bookId);
    ensure(object(value), 'Не получен рабочий черновик.');
    ruleId(value.id);
    ensure(value.book_id === bookId, 'Черновик относится к другой книге.');
    ensure(revision(value.revision), 'Некорректная ревизия рабочего черновика.');

    const content = value.content_json;
    ensure(object(content) && content.schema_version === 2, 'Ожидается рабочее содержание формата 2.');
    ensure(Array.isArray(content.sources), 'В черновике отсутствует список источников.');
    validateBookToc(content.toc);

    return structuredClone(value);
}

export function readWorkingEditor(value, bookId) {
    ensure(object(value) && object(value.book), 'Не получено состояние рабочего редактора.');
    ensure(value.book.id === bookId, 'Редактор относится к другой книге.');

    const draft = readWorkingDraft(value.draft, bookId);
    const changed = value.has_unpublished_changes;
    ensure(typeof changed === 'boolean', 'Не получен признак неопубликованных изменений.');

    let publication = null;

    if (value.latest_publication !== null) {
        publication = readVersion(value.latest_publication, bookId);
        ensure(publication.source_draft_revision < draft.revision, 'Публикация не согласована с ревизией черновика.');
    } else {
        ensure(changed, 'Книга без публикации не может считаться опубликованной.');
    }

    return {
        ...structuredClone(value),
        draft,
        latest_publication: publication
    };
}

export function assertWorkingPublication(draftContent, publishedContent) {
    ensure(draftContent?.schema_version === 2, 'Ожидается рабочий формат книги.');
    ensure(publishedContent?.schema_version === 1, 'Ожидается опубликованный формат книги.');

    const draftToc = validateBookToc(draftContent.toc);
    const publishedToc = validateBookToc(publishedContent.toc);

    ensure(publishedToc.every((node) => node.kind !== 'text'), 'Собственные тексты не закреплены в публикации.');

    const byKey = new Map(publishedToc.map((node) => [node.key, node]));
    const externalIds = new Set(draftToc.filter((node) => node.kind === 'article').map((node) => node.article_version_id));
    const internalIds = new Set();
    const expected = structuredClone(draftContent);

    expected.schema_version = 1;
    expected.toc = draftToc.map((node) => {
        if (node.kind !== 'text') return structuredClone(node);

        const published = byKey.get(node.key);
        ensure(published?.kind === 'article', 'Для собственного текста отсутствует опубликованный снимок.');
        ruleId(published.article_version_id);

        const versionId = published.article_version_id;
        ensure(!externalIds.has(versionId), 'Собственный текст подменён внешней публикацией.');
        ensure(!internalIds.has(versionId), 'Разные собственные тексты ссылаются на один снимок.');
        internalIds.add(versionId);

        const result = structuredClone(node);
        delete result.content;
        result.kind = 'article';
        result.article_version_id = versionId;

        return result;
    });

    expected.toc.sort((left, right) => left.key.localeCompare(right.key));

    const actual = structuredClone(publishedContent);
    actual.toc = publishedToc.sort((left, right) => left.key.localeCompare(right.key));

    ensure(same(expected, actual), 'Структура или сведения публикации отличаются от рабочего черновика.');
}
