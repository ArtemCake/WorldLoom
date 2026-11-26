// frontend/src/js/features/game-systems/api/version-api.js

// Клиент комплекта системы: опубликованная версия системы связывает
// версию текстовых правил (необязательно) и версию механики (обязательно).
// Публикация и закрепление — маршруты /admin/game-systems/{id}/versions/*,
// чтение — публичные /game-systems/items/{id}/versions/*.

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

export function createVersionApi(request = requestGameSystem) {
    if (typeof request !== 'function') {
        throw new TypeError('Требуется функция запроса к API системы.');
    }

    const adminBase = (systemId) => `/admin/game-systems/${systemPath(systemId)}/versions`;
    const publicBase = (systemId) => `/game-systems/items/${systemPath(systemId)}/versions`;

    return Object.freeze({
        // Сборка комплекта из черновиков:
        // {expected_mechanic_revision, expected_text_revision?: number | null}.
        publish: (systemId, data) => request(`${adminBase(systemId)}/publish`, 'POST', data),

        // Страница комплектов системы: {items, next_before}.
        listVersions: (systemId, options) => request(`${publicBase(systemId)}${versionQuery(options)}`),

        // Текущий комплект: {version: {...} | null}.
        getCurrent: (systemId) => request(`${publicBase(systemId)}/current`),

        // Закрепление комплекта: {version_id, expected_version_id}.
        bindCurrent: (systemId, data) => request(`${adminBase(systemId)}/current`, 'PUT', data)
    });
}
