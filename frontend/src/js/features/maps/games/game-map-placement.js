// frontend/src/js/features/maps/game-map-placement.js

import { Graphics, Point } from 'pixi.js';
import { gameStateApi } from '../../games/game-state-api.js';
import { notifySessionTokensChanged } from '../../games/sessions/session-token-events.js';
import { requestMapJson } from '../map-http.js';
import { isMapUuid } from './game-map-data.js';
import { createMapDrag } from './game-map-drag.js';

const SIZE = 64;
const WIDTH = Math.sqrt(3) * SIZE;

function cellKey(col, row) {
    return `${col}:${row}`;
}

function cellCenter(col, row) {
    return {
        x: WIDTH * (col + 0.5 * (row & 1) + 0.5),
        y: SIZE * (1 + 1.5 * row)
    };
}

function findCell(point, map) {
    const nearestRow = Math.round((point.y - SIZE) / (1.5 * SIZE));

    for (let row = nearestRow - 1; row <= nearestRow + 1; row += 1) {
        if (row < 0 || row >= map.rows) continue;

        const nearestCol = Math.round(point.x / WIDTH - 0.5 - 0.5 * (row & 1));

        for (let col = nearestCol - 1; col <= nearestCol + 1; col += 1) {
            if (col < 0 || col >= map.cols) continue;

            const center = cellCenter(col, row);
            const dx = Math.abs(point.x - center.x);
            const dy = Math.abs(point.y - center.y);

            if (dx <= WIDTH / 2 && dy <= SIZE - dx / Math.sqrt(3)) {
                return { col, row };
            }
        }
    }

    return null;
}

async function readCells(map) {
    const data = await requestMapJson(`/maps/${map.id}/hex-grid`);

    if (!data || data.map_id !== map.id || !Array.isArray(data.cells)) {
        throw new Error('Не удалось распознать серверную сетку.');
    }

    const cells = new Map();
    const identifiers = new Set();

    for (const cell of data.cells) {
        if (!cell || !isMapUuid(cell.id) || !Number.isInteger(cell.col) || !Number.isInteger(cell.row)
            || cell.col < 0 || cell.col >= map.cols || cell.row < 0 || cell.row >= map.rows) {
            throw new Error('Серверные гексы не согласованы с размерами карты.');
        }

        const key = cellKey(cell.col, cell.row);

        if (cells.has(key) || identifiers.has(cell.id)) {
            throw new Error('В серверной сетке повторяются координаты или идентификаторы.');
        }

        cells.set(key, cell);
        identifiers.add(cell.id);
    }

    return cells;
}

export function createMapPlacement(root, renderer, onBusy) {
    const fieldset = root.querySelector('[data-map-placement]');
    const select = root.querySelector('[data-placement-token]');
    const xInput = root.querySelector('[data-placement-x]');
    const yInput = root.querySelector('[data-placement-y]');
    const pick = root.querySelector('[data-placement-pick]');
    const save = root.querySelector('[data-placement-save]');
    const message = root.querySelector('[data-placement-message]');
    const canvas = root.querySelector('[data-game-map-canvas]');

    if (!(fieldset instanceof HTMLFieldSetElement) || !(select instanceof HTMLSelectElement)
        || !(xInput instanceof HTMLInputElement) || !(yInput instanceof HTMLInputElement)
        || !(pick instanceof HTMLInputElement) || !(save instanceof HTMLButtonElement)
        || !(canvas instanceof HTMLCanvasElement) || !message) {
        throw new Error('Не найдены элементы управления размещением токенов.');
    }

    const listeners = new AbortController();
    const options = { signal: listeners.signal };
    const canMove = root.dataset.canMoveTokens === 'true';
    let disposed = false;
    let busy = true;
    let saving = false;
    let dragActive = false;
    let needsRefresh = false;
    let sequence = 0;
    let map = null;
    let tokens = [];
    let cells = new Map();
    let overlay = null;
    let refreshTokens = null;

    function active() {
        return !disposed && root.isConnected;
    }

    function selectedToken() {
        return tokens.find((token) => token.id === select.value) || null;
    }

    function targetCell() {
        if (!map || !xInput.value.trim() || !yInput.value.trim()) return null;

        const col = Number(xInput.value);
        const row = Number(yInput.value);

        if (!Number.isInteger(col) || !Number.isInteger(row)) return null;

        return cells.get(cellKey(col, row)) || null;
    }

    function enabled() {
        return active() && canMove && !busy && !saving && !needsRefresh && map && cells.size && tokens.length;
    }

    function syncControls() {
        if (!active()) return;

        fieldset.disabled = !enabled() || dragActive;
        save.disabled = !enabled() || dragActive || !selectedToken() || !targetCell();
    }

    function clearOverlay() {
        if (!overlay) return;

        overlay.removeFromParent();
        overlay.destroy();
        overlay = null;
    }

    function eventPosition(event) {
        if (!map || !renderer.scene?.visible) return null;

        const rect = canvas.getBoundingClientRect();

        if (!rect.width || !rect.height) return null;

        const global = new Point(
            (event.clientX - rect.left) * renderer.app.screen.width / rect.width,
            (event.clientY - rect.top) * renderer.app.screen.height / rect.height
        );

        return renderer.scene.toLocal(global);
    }

    function eventCell(event) {
        const position = eventPosition(event);

        return position && map ? findCell(position, map) : null;
    }

    function paintSelection() {
        clearOverlay();

        if (!active() || !map || !renderer.scene?.visible) return;

        overlay = new Graphics();
        overlay.eventMode = 'none';
        renderer.scene.addChild(overlay);

        const token = selectedToken();

        if (token) {
            const center = cellCenter(token.gridX, token.gridY);
            overlay.circle(center.x, center.y, 33);
            overlay.stroke({ width: 3, color: 0x66ccff });
        }

        const target = targetCell();

        if (!target) return;

        const center = cellCenter(target.col, target.row);

        for (let vertex = 0; vertex < 6; vertex += 1) {
            const angle = (60 * vertex - 30) * Math.PI / 180;
            const x = center.x + SIZE * Math.cos(angle);
            const y = center.y + SIZE * Math.sin(angle);

            if (vertex === 0) overlay.moveTo(x, y);
            else overlay.lineTo(x, y);
        }

        overlay.closePath();
        overlay.stroke({ width: 3, color: 0xffcc33 });
    }

    function restoreDragDraft(context) {
        dragActive = false;

        if (!active()) return;

        xInput.value = context.x;
        yInput.value = context.y;
        paintSelection();
        syncControls();
    }

    const drag = createMapDrag(canvas, {
        begin(event) {
            if (!enabled() || pick.checked) return null;

            const token = selectedToken();
            const position = eventPosition(event);

            if (!token || !position) return null;

            const center = cellCenter(token.gridX, token.gridY);
            const dx = position.x - center.x;
            const dy = position.y - center.y;

            if (dx * dx + dy * dy > 28 * 28) return null;

            const context = { x: xInput.value, y: yInput.value };
            dragActive = true;
            syncControls();
            return context;
        },

        update(event) {
            if (!active()) return;

            const cell = eventCell(event);
            const target = cell ? cells.get(cellKey(cell.col, cell.row)) : null;

            xInput.value = target ? String(target.col) : '';
            yInput.value = target ? String(target.row) : '';
            paintSelection();

            message.textContent = target
                ? `Назначение: X ${target.col}, Y ${target.row}. Отпустите указатель, затем подтвердите сохранение.`
                : 'Здесь нет доступного серверного гекса. Отпускание отменит перетаскивание.';
        },

        finish(event, context) {
            dragActive = false;

            if (!active()) return;

            const cell = eventCell(event);
            const target = cell ? cells.get(cellKey(cell.col, cell.row)) : null;

            if (!enabled() || !target) {
                restoreDragDraft(context);
                message.textContent = 'Перетаскивание отменено. Прежнее назначение восстановлено.';
                return;
            }

            xInput.value = String(target.col);
            yInput.value = String(target.row);
            paintSelection();
            syncControls();
            message.textContent = `Назначение: X ${target.col}, Y ${target.row}. Для записи нажмите «Сохранить размещение».`;
        },

        cancel(context, moved) {
            restoreDragDraft(context);

            if (active() && moved) {
                message.textContent = 'Перетаскивание отменено. Прежнее назначение восстановлено.';
            }
        }
    });

    function chooseToken() {
        const token = selectedToken();
        pick.checked = false;
        xInput.value = token ? String(token.gridX) : '';
        yInput.value = token ? String(token.gridY) : '';
        paintSelection();
        syncControls();
    }

    function reset() {
        drag.cancel();
        sequence += 1;
        map = null;
        tokens = [];
        cells = new Map();
        refreshTokens = null;
        needsRefresh = false;
        clearOverlay();
        select.replaceChildren(new Option('Выберите токен', ''));
        xInput.value = '';
        yInput.value = '';
        pick.checked = false;
        message.textContent = '';
        syncControls();
    }

    async function setMap(data, values, refresh) {
        const previousId = select.value;
        reset();
        const version = sequence;

        if (!canMove) {
            message.textContent = 'Размещение доступно мастеру в активной сессии.';
            return;
        }

        message.textContent = 'Чтение серверных гексов…';

        try {
            const loaded = await readCells(data);

            if (!active() || version !== sequence) return;

            map = data;
            tokens = values;
            cells = loaded;
            refreshTokens = refresh;
            xInput.max = String(data.cols - 1);
            yInput.max = String(data.rows - 1);

            for (const token of tokens) {
                select.add(new Option(`${token.name} — X: ${token.gridX}, Y: ${token.gridY}`, token.id));
            }

            if (tokens.some((token) => token.id === previousId)) select.value = previousId;
            chooseToken();

            if (!cells.size) {
                message.textContent = 'На сервере нет гексов этой карты. Размещение недоступно.';
            } else if (!tokens.length) {
                message.textContent = 'Нет отображаемых токенов этой карты. Назначьте токен через панель и обновите карту.';
            } else {
                message.textContent = 'Выберите токен, затем гекс назначения. Для записи нажмите «Сохранить размещение».';
            }
        } catch (error) {
            if (!active() || version !== sequence) return;

            message.textContent = error instanceof Error ? error.message : 'Не удалось прочитать серверные гексы.';
        } finally {
            if (active() && version === sequence) syncControls();
        }
    }

    select.addEventListener('change', chooseToken, options);

    for (const input of [xInput, yInput]) {
        input.addEventListener('input', () => {
            paintSelection();
            syncControls();
        }, options);
    }

    canvas.addEventListener('click', (event) => {
        if (!enabled()) return;

		const cell = eventCell(event);

        if (!cell) return;

        if (pick.checked) {
            if (!selectedToken()) {
                message.textContent = 'Сначала выберите токен.';
                return;
            }

            if (!cells.has(cellKey(cell.col, cell.row))) {
                message.textContent = 'В этой клетке нет сохранённого серверного гекса.';
                return;
            }

            xInput.value = String(cell.col);
            yInput.value = String(cell.row);
            paintSelection();
            syncControls();
            message.textContent = `Назначение: X ${cell.col}, Y ${cell.row}. Изменение ещё не сохранено.`;
            return;
        }

        const matches = tokens.filter((token) => token.gridX === cell.col && token.gridY === cell.row);

        if (matches.length === 1) {
            select.value = matches[0].id;
            chooseToken();
            message.textContent = `Выбран токен «${matches[0].name}».`;
        } else if (matches.length > 1) {
            message.textContent = 'В клетке несколько токенов. Выберите нужный в списке.';
        }
    }, options);

    save.addEventListener('click', async () => {
        if (!enabled() || dragActive) return;

        const token = selectedToken();
        const target = targetCell();

        if (!token || !target || !map || !refreshTokens) return;

        const mapId = map.id;
        const refresh = refreshTokens;
        saving = true;
        onBusy(true);
        syncControls();
        message.textContent = 'Сохранение размещения…';

        try {
            const result = await gameStateApi.moveToken(token.id, {
                grid_x: target.col,
                grid_y: target.row,
                hex_id: target.id
            });

            if (!active()) return;

            if (!result || result.id !== token.id || result.session_id !== root.dataset.sessionId
                || result.current_map_id !== mapId || result.current_hex_id !== target.id
                || result.grid_x !== target.col || result.grid_y !== target.row) {
                throw new Error('Ответ сервера не подтверждает запрошенное размещение.');
            }

            notifySessionTokensChanged(root);
            await refresh();

            if (active()) {
                message.textContent = 'Сервер подтвердил размещение. Поле перечитано; состояние загрузки токенов указано выше.';
            }
        } catch (error) {
            if (!active()) return;
			notifySessionTokensChanged(root);
            needsRefresh = true;
            clearOverlay();
            renderer.clearStoredTokens();

            const reason = error instanceof Error ? error.message : 'Не удалось подтвердить результат.';
            message.textContent = `${reason} Нажмите «Обновить карты» перед следующей записью. Автоматического повтора нет.`;
        } finally {
            saving = false;

            if (active()) {
                onBusy(false);
                syncControls();
            }
        }
    }, options);

    return {
        setMap,
        reset,

        hasDraft() {
            const token = selectedToken();

            return Boolean(dragActive || (map && token && (
                xInput.value !== String(token.gridX)
                || yInput.value !== String(token.gridY)
            )));
        },

        markStale() {
            if (!active()) return;

            needsRefresh = true;
            drag.cancel();
            pick.checked = false;
            syncControls();
            message.textContent = 'Токены изменены через панель. Незавершённое перетаскивание отменено. '
                + 'Прежние поля назначения сохранены, но запись заблокирована. '
                + 'Перед продолжением нажмите «Обновить карты»; обновление сбросит назначение.';
        },

        setBusy(value) {
            busy = value;
            if (value) drag.cancel();
            syncControls();
        },

        destroy() {
            if (disposed) return;

            disposed = true;
            sequence += 1;
            drag.destroy();
            listeners.abort();
            clearOverlay();
            map = null;
            tokens = [];
            cells.clear();
        }

    };
}