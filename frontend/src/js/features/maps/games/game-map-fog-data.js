// frontend/src/js/features/maps/games/game-map-fog-data.js

import { requestMapJson } from '../map-http.js';
import { isMapUuid } from './game-map-data.js';

export async function readStoredMapFog(map) {
    if (!isMapUuid(map.id) || !Number.isInteger(map.cols) || !Number.isInteger(map.rows)
        || map.cols < 1 || map.cols > 200 || map.rows < 1 || map.rows > 200) {
        throw new Error('Не удалось определить карту и размеры сетки для чтения видимости.');
    }

    const data = await requestMapJson(`/maps/${map.id}/hex-grid`);

    if (!data || data.map_id !== map.id || !Array.isArray(data.cells)) {
        throw new Error('Сервер вернул неподдерживаемые данные видимости.');
    }

    if (!data.cells.length) {
        throw new Error('На сервере нет гексов этой карты. Сохранённую видимость показать нельзя.');
    }

    if (data.cells.length !== map.cols * map.rows) {
        throw new Error('Серверная сетка не полностью соответствует размерам карты. Затемнение не показано.');
    }

    const identifiers = new Set();
    const coordinates = new Set();

    return data.cells.map((cell) => {
        if (!cell || !isMapUuid(cell.id) || !Number.isInteger(cell.col) || !Number.isInteger(cell.row)
            || cell.col < 0 || cell.col >= map.cols || cell.row < 0 || cell.row >= map.rows
            || typeof cell.is_visible_to_players !== 'boolean' || typeof cell.explored_by_players !== 'boolean') {
            throw new Error('Сервер вернул некорректные координаты или признаки видимости гекса.');
        }

        const coordinate = `${cell.col}:${cell.row}`;

        if (identifiers.has(cell.id) || coordinates.has(coordinate)) {
            throw new Error('В данных видимости повторяются гексы или их координаты.');
        }

        identifiers.add(cell.id);
        coordinates.add(coordinate);

        return {
            col: cell.col,
            row: cell.row,
            visible: cell.is_visible_to_players,
            explored: cell.explored_by_players
        };
    });
}
