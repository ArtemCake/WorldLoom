// frontend/src/js/features/game-systems/api/text-api.js

// Клиент раздельных текстовых правил системы.
// Черновики и публикация — маршруты /admin/game-systems/{id}/text/*,
// чтение версий — публичные /game-systems/items/{id}/text/*.
// Фабрика принимает request-функцию (по умолчанию — requestGameSystem),
// чтобы модуль можно было подменить в тестах без DOM.

import { requestGameSystem } from './game-system-api.js';

function systemPath(systemId) {
    if (typeof systemId !== 'string' || !systemId) {
        throw new TypeError('Не указан идентификатор игровой системы.');
    }

    return encodeURIComponent(systemId);
}

function versionQuery({ limit = 20, before = null } = {}) {
    if (!Number.isSafeInteger(limit) || limit < 1 || limit > 100) {
        throw new TypeError('Размер страницы должен быть целым числом от 1 до 100.');
    }

    const params = new URLSearchParams({ limit: String(limit) });

    if (before !== null) {
        if (!Number.isSafeInteger(before) || before < 1) {
            throw new TypeError('Граница истории должна быть положительным целым числом.');
        }

        params.set('before', String(before));
    }

    return `?${params.toString()}`;
}

export function createTextApi(request = requestGameSystem) {
    if (typeof request !== 'function') {
        throw new TypeError('Требуется функция запроса к API системы.');
    }

    const adminBase = (systemId) => `/admin/game-systems/${systemPath(systemId)}/text`;
    const publicBase = (systemId) => `/game-systems/items/${systemPath(systemId)}/text`;

    return Object.freeze({
        // Состояние черновика: {draft: {...} | null}.
        getDraft: (systemId) => request(`${adminBase(systemId)}/draft`),

        // Создание: {text: SystemTextContent}.
        createDraft: (systemId, data) => request(`${adminBase(systemId)}/draft`, 'POST', data),

        // Замена: {expected_revision, text: SystemTextContent}.
        updateDraft: (systemId, data) => request(`${adminBase(systemId)}/draft`, 'PATCH', data),

        // Публикация версии текста: {expected_revision}.
        publish: (systemId, data) => request(`${adminBase(systemId)}/publish`, 'POST', data),

        // Последняя версия текста: {version: {...} | null}.
        getLatest: (systemId) => request(`${publicBase(systemId)}/latest`),

        // Страница версий текста: {items, next_before}.
        listVersions: (systemId, options) => request(`${publicBase(systemId)}/versions${versionQuery(options)}`),

        getVersion: (systemId, versionId) => request(`${publicBase(systemId)}/versions/${systemPath(versionId)}`)
    });
}
