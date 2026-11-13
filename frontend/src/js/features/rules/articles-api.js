// frontend/src/js/features/rules/articles-api.js

import { catalogQuery, requestRulesJson, ruleId } from './rules-http.js';

export function createArticlesApi(request = requestRulesJson) {
    if (typeof request !== 'function') throw new TypeError('Требуется функция HTTP-запроса.');

    return Object.freeze({
        list(filters = {}, { signal } = {}) {
            return request(`/rules/articles${catalogQuery(filters)}`, { signal });
        },

        create(payload, { signal } = {}) {
            return request('/rules/articles', { method: 'POST', body: payload, signal });
        },

        getDraft(articleId, { signal } = {}) {
            return request(`/rules/articles/${ruleId(articleId)}/draft`, { signal });
        },

        saveDraft(articleId, payload, { signal } = {}) {
            const path = `/rules/articles/${ruleId(articleId)}/draft`;
            return request(path, { method: 'PUT', body: payload, signal });
        },

        publish(articleId, payload, { signal } = {}) {
            const path = `/rules/articles/${ruleId(articleId)}/publish`;
            return request(path, { method: 'POST', body: payload, signal });
        },

        getVersion(articleId, versionId, { signal } = {}) {
            const path = `/rules/articles/${ruleId(articleId)}/versions/${ruleId(versionId)}`;
            return request(path, { signal });
        }
    });
}

export const articlesApi = createArticlesApi();
