// frontend/src/js/features/rules/books/book-authoring-api.js

import { catalogQuery, requestRulesJson, ruleId } from './../rules-http.js';

function authorQuery(filters) {
    if (!filters || typeof filters !== 'object' || Array.isArray(filters)) {
        throw new TypeError('Фильтры авторского каталога должны быть объектом.');
    }

    const { system_id: systemId, ...common } = filters;

    if (common.scope !== undefined && common.scope !== 'mine') {
        throw new TypeError('Авторский каталог содержит только собственные книги.');
    }

    const query = new URLSearchParams(catalogQuery({ ...common, scope: 'mine' }).slice(1));

    if (systemId !== undefined && systemId !== null) {
        query.set('system_id', ruleId(systemId));
    }

    return `?${query.toString()}`;
}

export function createBookAuthoringApi(request = requestRulesJson) {
    if (typeof request !== 'function') {
        throw new TypeError('Требуется функция HTTP-запроса.');
    }

    return Object.freeze({
        list(filters = {}, { signal } = {}) {
            return request(`/rules/books/authoring${authorQuery(filters)}`, { signal });
        },

        getEditor(bookId, { signal } = {}) {
            return request(`/rules/books/${ruleId(bookId)}/editor`, { signal });
        }
    });
}

export const bookAuthoringApi = createBookAuthoringApi();