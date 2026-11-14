// frontend/src/js/features/rules/books/books-api.js

import { catalogQuery, requestRulesJson, ruleId } from './../rules-http.js';

function bookCatalogQuery(filters) {
    if (!filters || typeof filters !== 'object' || Array.isArray(filters)) {
        throw new TypeError('Фильтры каталога книг должны быть объектом.');
    }

    const { system_id: systemId, ...common } = filters;
    const query = new URLSearchParams(catalogQuery(common).slice(1));

    if (systemId !== undefined && systemId !== null) {
        query.set('system_id', ruleId(systemId));
    }

    const encoded = query.toString();
    return encoded ? `?${encoded}` : '';
}

function requireSystem(payload) {
    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
        throw new TypeError('Данные операции должны быть объектом.');
    }

    ruleId(payload.system_id);
}

export function createBooksApi(request = requestRulesJson) {
    if (typeof request !== 'function') throw new TypeError('Требуется функция HTTP-запроса.');

    return Object.freeze({
        list(filters = {}, { signal } = {}) {
            return request(`/rules/books${bookCatalogQuery(filters)}`, { signal });
        },

        create(payload, { signal } = {}) {
            requireSystem(payload);
            return request('/rules/books', { method: 'POST', body: payload, signal });
        },

        assignSystem(bookId, payload, { signal } = {}) {
            const path = `/rules/books/${ruleId(bookId)}/system`;
            requireSystem(payload);
            return request(path, { method: 'PUT', body: payload, signal });
        },

        getDraft(bookId, { signal } = {}) {
            return request(`/rules/books/${ruleId(bookId)}/draft`, { signal });
        },

        saveDraft(bookId, payload, { signal } = {}) {
            const path = `/rules/books/${ruleId(bookId)}/draft`;
            return request(path, { method: 'PUT', body: payload, signal });
        },
        getWorkingEditor(bookId, { signal } = {}) {
            return request(`/rules/books/${ruleId(bookId)}/working-editor`, { signal });
        },

        getWorkingDraft(bookId, { signal } = {}) {
            return request(`/rules/books/${ruleId(bookId)}/working-draft`, { signal });
        },

        saveWorkingDraft(bookId, payload, { signal } = {}) {
            const path = `/rules/books/${ruleId(bookId)}/working-draft`;
            return request(path, { method: 'PUT', body: payload, signal });
        },

        publishWorkingDraft(bookId, payload, { signal } = {}) {
            const path = `/rules/books/${ruleId(bookId)}/working-draft/publish`;
            return request(path, { method: 'POST', body: payload, signal });
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