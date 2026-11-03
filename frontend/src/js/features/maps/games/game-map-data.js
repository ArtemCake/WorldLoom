// frontend/src/js/features/maps/game-map-data.js

import { sessionClient } from '../../../shared/http/session-client.js';
import { requestMapJson } from '../map-http.js';

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isMapUuid(value) {
    return typeof value === 'string' && UUID_PATTERN.test(value);
}

function requireUuid(value) {
    if (!isMapUuid(value)) {
        throw new Error('Некорректный идентификатор игры, сессии или карты.');
    }

    return value;
}

function readDimension(value) {
    if (!Number.isInteger(value) || value < 1 || value > 200) {
        throw new Error('Размеры сохранённой сетки должны быть целыми числами от 1 до 200.');
    }

    return value;
}

function validateMap(data, gameId) {
    if (!data || !isMapUuid(data.id) || data.game_id !== gameId) {
        throw new Error('Сервер вернул карту другой игры или некорректный идентификатор.');
    }

    if (data.session_id !== null && !isMapUuid(data.session_id)) {
        throw new Error('Сервер вернул некорректную привязку карты к сессии.');
    }

    if (typeof data.title !== 'string' || typeof data.is_active_in_session !== 'boolean'
        || typeof data.fog_of_war_enabled !== 'boolean') {
        throw new Error('Сервер вернул некорректные параметры карты.');
    }

    const grid = data.grid_settings_json;

    if (!grid || typeof grid !== 'object' || Array.isArray(grid)) {
        throw new Error('Сохранённые настройки сетки не распознаны.');
    }

    if (grid.orientation !== undefined && grid.orientation !== 'pointy-top') {
        throw new Error('Эта ориентация сетки пока не поддерживается игровым полем.');
    }

    if (grid.offset !== undefined && grid.offset !== 'odd-r') {
        throw new Error('Эта схема смещения гексов пока не поддерживается игровым полем.');
    }

    if (grid.show_grid !== undefined && typeof grid.show_grid !== 'boolean') {
        throw new Error('Некорректный параметр отображения сетки.');
    }

    if (data.background_image_url !== null && typeof data.background_image_url !== 'string') {
        throw new Error('Сервер вернул некорректный адрес фона.');
    }

    return {
        ...data,
        rows: readDimension(grid.rows ?? 20),
        cols: readDimension(grid.cols ?? 20),
        showGrid: grid.show_grid ?? true
    };
}

export function requireSessionMap(data, sessionId) {
    requireUuid(sessionId);

    if (data.session_id !== null && data.session_id !== sessionId) {
        throw new Error('Карта привязана к другой игровой сессии. Обновите список карт.');
    }

    return data;
}

export async function listGameMaps(gameId, sessionId) {
    requireUuid(gameId);
    requireUuid(sessionId);

    const data = await requestMapJson(`/maps/by-game/${gameId}`);

    if (!Array.isArray(data)) {
        throw new Error('Сервер вернул неподдерживаемый каталог карт.');
    }

    const identifiers = new Set();
    const maps = data.map((item) => {
        const map = validateMap(item, gameId);

        if (identifiers.has(map.id)) {
            throw new Error('В каталоге повторяется идентификатор карты.');
        }

        identifiers.add(map.id);
        return map;
    });

    return maps.filter((map) => map.session_id === null || map.session_id === sessionId);
}

export async function readGameMap(mapId, gameId, sessionId) {
    requireUuid(mapId);
    requireUuid(gameId);

    const data = await requestMapJson(`/maps/${mapId}`);
    const map = requireSessionMap(validateMap(data, gameId), sessionId);

    if (map.id !== mapId) {
        throw new Error('Сервер вернул другую карту.');
    }

    return map;
}

export async function readGameMapImage(map) {
    if (!map.background_image_url) return null;

    const expected = new URL(`/maps/${requireUuid(map.id)}/background`, window.location.origin);
    const actual = new URL(map.background_image_url, window.location.origin);

    if (actual.href !== expected.href) {
        throw new Error('Этот фон не использует защищённый маршрут карт. Откройте карту через её страницу редактирования.');
    }

    const response = await sessionClient.sessionFetch(expected.pathname, {
        method: 'GET',
        headers: { Accept: 'image/png' },
        cache: 'no-store',
        retryAfterRefresh: true
    });

    if (!response.ok) {
        throw new Error(`Не удалось прочитать фон карты (${response.status}).`);
    }

    const contentType = response.headers.get('Content-Type') || '';

    if (contentType.split(';')[0].trim().toLowerCase() !== 'image/png') {
        throw new Error('Вместо фонового изображения получен неподдерживаемый ответ.');
    }

    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const image = new Image();

    try {
        image.src = objectUrl;
        await image.decode();

        if (!image.naturalWidth || !image.naturalHeight) {
            throw new Error('Фоновое изображение не удалось декодировать.');
        }

        return image;
    } finally {
        URL.revokeObjectURL(objectUrl);
    }
}