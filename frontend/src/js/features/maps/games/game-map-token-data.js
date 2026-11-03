// frontend/src/js/features/maps/game-map-token-data.js

import { gameStateApi } from '../../games/game-state-api.js';
import { isMapUuid } from './game-map-data.js';

function isGridInteger(value) {
    return Number.isInteger(value) && value >= -2147483648 && value <= 2147483647;
}

export async function readStoredMapTokens(sessionId, map) {
    if (!isMapUuid(sessionId) || !isMapUuid(map.id)) {
        throw new Error('Не удалось определить сессию или карту для чтения токенов.');
    }

    const data = await gameStateApi.listTokens(sessionId);

    if (!Array.isArray(data)) {
        throw new Error('Сервер вернул неподдерживаемый список токенов.');
    }

    const identifiers = new Set();
    const tokens = [];
    let outsideCount = 0;

    for (const token of data) {
        if (!token || !isMapUuid(token.id) || token.session_id !== sessionId) {
            throw new Error('В списке найден некорректный токен или токен другой сессии.');
        }

        if (identifiers.has(token.id)) {
            throw new Error('В списке повторяется идентификатор токена.');
        }

        identifiers.add(token.id);

        if (token.current_map_id !== null && !isMapUuid(token.current_map_id)) {
            throw new Error('Сервер вернул некорректное назначение карты токена.');
        }

        if (token.current_map_id !== map.id) continue;

        if (!isGridInteger(token.grid_x) || !isGridInteger(token.grid_y)
            || typeof token.is_visible_to_players !== 'boolean'
            || (token.display_name !== null && typeof token.display_name !== 'string')) {
            throw new Error('Сервер вернул некорректные параметры токена выбранной карты.');
        }

        if (token.grid_x < 0 || token.grid_x >= map.cols || token.grid_y < 0 || token.grid_y >= map.rows) {
            outsideCount += 1;
            continue;
        }

        tokens.push({
            id: token.id,
            gridX: token.grid_x,
            gridY: token.grid_y,
            name: token.display_name?.trim() || 'Без названия',
            visibleToPlayers: token.is_visible_to_players
        });
    }

    return { tokens, outsideCount };
}