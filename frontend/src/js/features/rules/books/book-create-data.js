// frontend/src/js/features/rules/books/book-create-data.js

import { ruleId } from '../rules-http.js';

export const NEW_BOOK_DEFAULTS = Object.freeze({
    system_id: '',
    title: '',
    summary: '',
    language: 'ru',
    edition_key: ''
});

function ensure(condition, message) {
    if (!condition) throw new TypeError(message);
}

function field(values, name, maximum, required = false) {
    const value = values[name];
    ensure(typeof value === 'string', 'Значения полей книги должны быть строками.');

    const result = value.trim();
    ensure(result.length <= maximum, 'Превышена допустимая длина поля книги.');
    ensure(!required || result.length > 0, 'Заполните обязательные поля книги.');

    return result;
}

export function newBookPayload(values, slug) {
    ensure(values && typeof values === 'object' && !Array.isArray(values), 'Не заданы данные новой книги.');
    ensure(typeof slug === 'string' && slug.length <= 100, 'Некорректный технический код книги.');
    ensure(/^[a-z0-9]+(?:[-_][a-z0-9]+)*$/u.test(slug), 'Некорректный технический код книги.');

    const systemId = field(values, 'system_id', 36, true);
    ruleId(systemId);

    const language = field(values, 'language', 20, true);
    ensure(language.length >= 2, 'Код языка должен содержать не менее двух символов.');

    return {
        system_id: systemId,
        slug,
        visibility: 'private',
        content: {
            schema_version: 1,
            title: field(values, 'title', 200, true),
            summary: field(values, 'summary', 5000),
            introduction: '',
            language,
            edition_key: field(values, 'edition_key', 100) || null,
            category: 'rules',
            audience: 'both',
            sources: [],
            toc: []
        }
    };
}

export function createdBookId(result, systemId) {
    ensure(result?.book && result?.draft, 'Сервер не подтвердил создание книги.');

    const bookId = ruleId(result.book.id);
    ensure(result.book.system_id === systemId, 'Сервер вернул книгу другой игровой системы.');
    ensure(result.draft.book_id === bookId, 'Сервер вернул черновик другой книги.');
    ensure(Number.isSafeInteger(result.draft.revision) && result.draft.revision > 0, 'Некорректная ревизия новой книги.');

    return bookId;
}
