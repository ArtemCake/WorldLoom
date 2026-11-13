// frontend/src/js/features/rules/books-api.js

import { catalogQuery, requestRulesJson, ruleId } from './rules-http.js';

export function createBooksApi(request = requestRulesJson) {
    if (typeof request !== 'function') throw new TypeError('Требуется функция HTTP-запроса.');

    return Object.freeze({
        list(filters = {}, { signal } = {}) {
            return request(`/rules/books${catalogQuery(filters)}`, { signal });
        },

        create(payload, { signal } = {}) {
            return request('/rules/books', { method: 'POST', body: payload, signal });
        },

        getDraft(bookId, { signal } = {}) {
            return request(`/rules/books/${ruleId(bookId)}/draft`, { signal });
        },

        saveDraft(bookId, payload, { signal } = {}) {
            const path = `/rules/books/${ruleId(bookId)}/draft`;
            return request(path, { method: 'PUT', body: payload, signal });
        },

        publish(bookId, payload, { signal } = {}) {
            const path = `/rules/books/${ruleId(bookId)}/publish`;
            return request(path, { method: 'POST', body: payload, signal });
        },

        getVersion(bookId, versionId, { signal } = {}) {
            const path = `/rules/books/${ruleId(bookId)}/versions/${ruleId(versionId)}`;
            return request(path, { signal });
        },

        read(bookId, versionId, { signal } = {}) {
            const path = `/rules/books/${ruleId(bookId)}/versions/${ruleId(versionId)}/reading`;
            return request(path, { signal });
        }
    });
}

export const booksApi = createBooksApi();
