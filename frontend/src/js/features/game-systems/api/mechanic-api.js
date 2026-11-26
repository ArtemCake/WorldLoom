// frontend/src/js/features/game-systems/api/mechanic-api.js

// Клиент раздельной механики системы (исполняемый числовой профиль).
// Черновики и публикация — маршруты /admin/game-systems/{id}/mechanic/*,
// чтение версий — публичные /game-systems/items/{id}/mechanic/*.

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

export function createMechanicApi(request = requestGameSystem) {
    if (typeof request !== 'function') {
        throw new TypeError('Требуется функция запроса к API системы.');
    }

    const adminBase = (systemId) => `/admin/game-systems/${systemPath(systemId)}/mechanic`;
    const publicBase = (systemId) => `/game-systems/items/${systemPath(systemId)}/mechanic`;

    return Object.freeze({
        // Состояние черновика: {draft: {...} | null}.
        getDraft: (systemId) => request(`${adminBase(systemId)}/draft`),

        // Создание: {mechanic: SystemMechanicContent}.
        createDraft: (systemId, data) => request(`${adminBase(systemId)}/draft`, 'POST', data),

        // Замена: {expected_revision, mechanic: SystemMechanicContent}.
        updateDraft: (systemId, data) => request(`${adminBase(systemId)}/draft`, 'PATCH', data),

        // Публикация версии механики: {expected_revision}.
        publish: (systemId, data) => request(`${adminBase(systemId)}/publish`, 'POST', data),

        // Последняя версия механики: {version: {...} | null}.
        getLatest: (systemId) => request(`${publicBase(systemId)}/latest`),

        // Страница версий механики: {items, next_before}.
        listVersions: (systemId, options) => request(`${publicBase(systemId)}/versions${versionQuery(options)}`),

        getVersion: (systemId, versionId) => request(`${publicBase(systemId)}/versions/${systemPath(versionId)}`)
    });
}
