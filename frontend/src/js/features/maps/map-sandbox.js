// frontend/src/js/features/maps/map-sandbox.js

import { MapRequestError, requestMapJson } from './map-http.js';
import { acquireMapOperation } from './map-operation-state.js';

const instances = new WeakMap();

function validatePreview(data) {
    if (!data || !Number.isInteger(data.rows) || data.rows < 1 || !Number.isInteger(data.cols) || data.cols < 1
        || typeof data.persisted_grid !== 'boolean' || typeof data.show_grid !== 'boolean' || !Array.isArray(data.hexes)) {
        throw new Error('Сервер вернул неподдерживаемые параметры предпросмотра.');
    }

    const coordinates = new Set();

    for (const cell of data.hexes) {
        if (!cell || !Number.isInteger(cell.q) || !Number.isInteger(cell.r) || !Number.isInteger(cell.col)
            || !Number.isInteger(cell.row) || cell.col < 0 || cell.col >= data.cols || cell.row < 0 || cell.row >= data.rows
            || typeof cell.visible !== 'boolean' || typeof cell.explored !== 'boolean') {
            throw new Error('Сервер вернул некорректную клетку предпросмотра.');
        }

        const coordinate = `${cell.q}:${cell.r}`;

        if (coordinates.has(coordinate)) {
            throw new Error('В предпросмотре повторяются координаты клеток.');
        }

        coordinates.add(coordinate);
    }

    return data;
}

export function initMapSandbox(root, image) {
    if (!root) return () => {};
    if (instances.has(root)) return instances.get(root);

    const canvas = root.querySelector('[data-preview-canvas]');
    const message = root.querySelector('[data-preview-message]');
    const mode = root.querySelector('[data-preview-mode]');
    const radius = root.querySelector('[data-preview-radius]');
    const memory = root.querySelector('[data-preview-memory]');
    const rowsInput = root.querySelector('[name="rows"]');
    const colsInput = root.querySelector('[name="cols"]');
    const grid = root.querySelector('[name="show_grid"]');
    const fog = root.querySelector('[name="fog_of_war_enabled"]');
    const reset = root.querySelector('[data-preview-reset]');
    const generate = root.querySelector('[data-preview-generate]');

    const requiredElements = [
        ['поле карты', canvas],
        ['сообщение предпросмотра', message],
        ['режим просмотра', mode],
        ['радиус обзора', radius],
        ['память исследованных клеток', memory],
        ['число строк', rowsInput],
        ['число столбцов', colsInput],
        ['переключатель сетки', grid],
        ['переключатель тумана', fog],
        ['сброс тестовой прогулки', reset]
    ];

    const missingElements = requiredElements.filter(([, element]) => !element).map(([label]) => label);

    if (missingElements.length > 0) {
        const text = `Не удалось подключить карту. Внутри блока предпросмотра не найдены: ${missingElements.join(', ')}.`;

        if (message) {
            message.textContent = text;
        } else {
            const notice = document.createElement('p');

            notice.dataset.previewMessage = '';
            notice.setAttribute('role', 'alert');
            notice.textContent = text;
            root.append(notice);
        }

        console.error(text, root);
        return () => {};
    }

    if (!(canvas instanceof HTMLCanvasElement)) {
        message.textContent = 'Не удалось подключить карту: поле предпросмотра должно быть элементом canvas.';
        console.error(message.textContent, canvas);
        return () => {};
    }

    if (!root.dataset.previewUrl || !root.dataset.gameId) {
        message.textContent = 'Не удалось подключить карту: не задан адрес расчёта предпросмотра или игра.';
        console.error(message.textContent, root);
        return () => {};
    }

    const ctx = canvas.getContext('2d');
    const mask = document.createElement('canvas');
    const maskCtx = mask.getContext('2d');

    if (!ctx || !maskCtx) {
        message.textContent = 'Браузер не поддерживает рисование предпросмотра.';
        return () => {};
    }

    const listeners = new AbortController();
    const options = { signal: listeners.signal };
    let cells = [];
    let origin = null;
    let explored = new Set();
    let rows = Number(rowsInput.value) || 20;
    let cols = Number(colsInput.value) || 20;
    let timer = null;
    let controller = null;
    let sequence = 0;
    let dragging = false;
    let initial = true;
    let ready = false;
    let disposed = false;
    let generating = false;

    const key = (cell) => `${cell.q}:${cell.r}`;

    function geometry() {
        const widthUnits = Math.sqrt(3) * (cols + (rows > 1 ? 0.5 : 0));
        const heightUnits = 2 + 1.5 * (rows - 1);

        return {
            sizeX: canvas.width / widthUnits,
            sizeY: canvas.height / heightUnits,
            left: 0,
            top: 0
        };
    }

    function center(cell, geometryValue) {
        const { left, top, sizeX, sizeY } = geometryValue;

        return {
            x: left + Math.sqrt(3) * sizeX * (cell.col + 0.5 * (cell.row & 1) + 0.5),
            y: top + sizeY * (1 + 1.5 * cell.row)
        };
    }

    function polygon(context, cell, geometryValue) {
        const point = center(cell, geometryValue);

        context.beginPath();

        for (let index = 0; index < 6; index += 1) {
            const angle = Math.PI / 180 * (60 * index - 30);
            const x = point.x + geometryValue.sizeX * Math.cos(angle);
            const y = point.y + geometryValue.sizeY * Math.sin(angle);

            if (index === 0) context.moveTo(x, y);
            else context.lineTo(x, y);
        }

        context.closePath();
    }

    function draw() {
        if (disposed || !root.isConnected) return;

        const hasImage = Boolean(image?.getAttribute('src') && image.complete && image.naturalWidth);
        const sourceWidth = hasImage ? image.naturalWidth : 1200;
        const sourceHeight = hasImage ? image.naturalHeight : 800;
        const scale = Math.min(1, 1600 / sourceWidth, 1600 / sourceHeight);
        const width = Math.max(1, Math.round(sourceWidth * scale));
        const height = Math.max(1, Math.round(sourceHeight * scale));

        if (canvas.width !== width || canvas.height !== height) {
            canvas.width = width;
            canvas.height = height;
        }

        ctx.clearRect(0, 0, width, height);
        ctx.fillStyle = '#ddd';
        ctx.fillRect(0, 0, width, height);

        if (hasImage) ctx.drawImage(image, 0, 0, width, height);

        const geometryValue = geometry();
        const player = mode.value === 'player';

        if (fog.checked) {
            mask.width = width;
            mask.height = height;
            maskCtx.fillStyle = '#000';
            maskCtx.fillRect(0, 0, width, height);
            maskCtx.globalCompositeOperation = 'destination-out';

            for (const cell of cells) {
                const seen = memory.checked && (cell.explored || explored.has(key(cell)));
                const visible = ready && cell.visible;

                if (!visible && !seen) continue;

                maskCtx.globalAlpha = visible ? 1 : 0.3;
                polygon(maskCtx, cell, geometryValue);
                maskCtx.fill();
            }

            maskCtx.globalAlpha = 1;
            maskCtx.globalCompositeOperation = 'source-over';
            ctx.globalAlpha = player ? 1 : 0.4;
            ctx.drawImage(mask, 0, 0);
            ctx.globalAlpha = 1;
        }

        if (grid.checked) {
            ctx.strokeStyle = 'rgba(230, 230, 230, 0.8)';
            ctx.lineWidth = 1;

            for (const cell of cells) {
                const seen = memory.checked && (cell.explored || explored.has(key(cell)));

                if (player && fog.checked && !(ready && cell.visible) && !seen) continue;

                polygon(ctx, cell, geometryValue);
                ctx.stroke();
            }
        }

        const current = origin && cells.find((cell) => key(cell) === key(origin));

        if (current) {
            const point = center(current, geometryValue);
            ctx.beginPath();
            const markerRadius = Math.max(3, Math.min(geometryValue.sizeX, geometryValue.sizeY) * 0.35);
            ctx.arc(point.x, point.y, markerRadius, 0, 2 * Math.PI);
            ctx.fillStyle = '#27a9ff';
            ctx.fill();
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = 2;
            ctx.stroke();
        }
    }

    async function refresh(requestId) {
        if (disposed || !root.isConnected || requestId !== sequence) return;

        if (!rowsInput.checkValidity() || !colsInput.checkValidity() || !radius.checkValidity()) {
            message.textContent = 'Проверьте параметры сетки и радиуса.';
            return;
        }

        const requestController = new AbortController();
        controller = requestController;
        message.textContent = 'Расчёт тестовой видимости…';

        try {
            const response = await requestMapJson(root.dataset.previewUrl, {
                method: 'POST',
                signal: requestController.signal,
                body: {
                    game_id: root.dataset.gameId,
                    map_id: root.dataset.mapId || null,
                    rows: Number(rowsInput.value),
                    cols: Number(colsInput.value),
                    origin_q: origin?.q ?? null,
                    origin_r: origin?.r ?? null,
                    vision_radius: Number(radius.value)
                }
            });

            if (disposed || !root.isConnected || requestId !== sequence) return;

            const data = validatePreview(response);
            cells = data.hexes;
            rows = data.rows;
            cols = data.cols;
            rowsInput.value = String(rows);
            colsInput.value = String(cols);

            if (root.dataset.mapId) {
                rowsInput.readOnly = data.persisted_grid;
                colsInput.readOnly = data.persisted_grid;

                if (initial) grid.checked = data.show_grid;
                if (generate) generate.hidden = data.persisted_grid;
            }

            for (const cell of cells) {
                if (cell.visible) explored.add(key(cell));
            }

            initial = false;
            ready = true;
            message.textContent = origin
                ? 'Тестовый обзор рассчитан. Изменения не записаны в игру.'
                : 'Нажмите на карту, чтобы поставить тестовую фишку.';

            if (root.dataset.mapId && !data.persisted_grid) {
                message.textContent += ' Сохранённой сетки нет: показана тестовая.';
            }

            draw();
        } catch (error) {
            if (disposed || !root.isConnected || requestId !== sequence || requestController.signal.aborted) return;

            ready = false;
            message.textContent = error instanceof Error ? error.message : 'Не удалось рассчитать предпросмотр.';
            draw();
        }
    }

    function schedule() {
        clearTimeout(timer);
        controller?.abort();
        const requestId = ++sequence;
        ready = false;
        draw();

        if (!disposed && root.isConnected) {
            timer = setTimeout(() => void refresh(requestId), 160);
        }
    }

    function place(event) {
        if (generating) return;

        const rect = canvas.getBoundingClientRect();

        if (!rect.width || !rect.height) return;

        const x = (event.clientX - rect.left) * canvas.width / rect.width;
        const y = (event.clientY - rect.top) * canvas.height / rect.height;
        const geometryValue = geometry();

        for (const cell of cells) {
            polygon(ctx, cell, geometryValue);

            if (!ctx.isPointInPath(x, y)) continue;
            if (origin && key(origin) === key(cell)) return;

            origin = { q: cell.q, r: cell.r };
            schedule();
            return;
        }
    }

    canvas.addEventListener('pointerdown', (event) => {
        if (event.button !== 0 || generating) return;

        canvas.focus();
        dragging = true;
        canvas.setPointerCapture(event.pointerId);
        place(event);
    }, options);

    canvas.addEventListener('pointermove', (event) => {
        if (dragging) place(event);
    }, options);

    for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) {
        canvas.addEventListener(type, () => {
            dragging = false;
        }, options);
    }

    canvas.addEventListener('keydown', (event) => {
        const directions = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
        const delta = directions[event.key];

        if (!delta || !origin || generating) return;

        event.preventDefault();

        const current = cells.find((cell) => key(cell) === key(origin));
        const next = current && cells.find((cell) => cell.col === current.col + delta[0] && cell.row === current.row + delta[1]);

        if (next) {
            origin = { q: next.q, r: next.r };
            schedule();
        }
    }, options);

    for (const input of [rowsInput, colsInput]) {
        input.addEventListener('change', () => {
            origin = null;
            explored.clear();
            cells = [];
            schedule();
        }, options);
    }

    radius.addEventListener('change', schedule, options);

    for (const input of [grid, fog, mode, memory]) {
        input.addEventListener('change', draw, options);
    }

    reset.addEventListener('click', () => {
        origin = null;
        explored.clear();
        schedule();
    }, options);

    generate?.addEventListener('click', async () => {
        if (disposed || generating || generate.disabled || !root.isConnected || !root.dataset.mapId) return;
        if (!rowsInput.reportValidity() || !colsInput.reportValidity()) return;
        if (!window.confirm('Создать и сохранить сетку на этой карте?')) return;

        if (!document.querySelector('meta[name="csrf-token"]')?.content) {
            message.textContent = 'Не найден защитный токен. Перезагрузите страницу.';
            return;
        }

        const operationRoot = root.closest('[data-map-operation-root]') || root;
        const release = acquireMapOperation(operationRoot);

        if (!release) return;

        const body = { rows: Number(rowsInput.value), cols: Number(colsInput.value) };
        let canRelease = false;
        let created = false;

        generating = true;
        dragging = false;
        clearTimeout(timer);
        controller?.abort();
        sequence += 1;
        ready = false;
        message.textContent = 'Сохранение сетки…';

        try {
            const data = await requestMapJson(root.dataset.generateUrl, { method: 'POST', body });

            if (disposed || !root.isConnected) return;

            if (!data || data.map_id !== root.dataset.mapId || data.layer_type !== 'vector_tiles') {
                throw new Error('Сервер не подтвердил создание ожидаемого слоя сетки.');
            }

            created = true;
            canRelease = true;
            generate.hidden = true;
            origin = null;
            explored.clear();
            cells = [];
            message.textContent = 'Сетка сохранена.';
        } catch (error) {
            if (disposed || !root.isConnected) return;

            canRelease = error instanceof MapRequestError && [400, 401, 403, 404, 409, 422].includes(error.status);

            const text = error instanceof Error ? error.message : 'Не удалось получить результат создания сетки.';

            message.textContent = canRelease
                ? `${text} Если сетка уже существует, откройте сохранённое состояние заново.`
                : `${text} Сетка могла сохраниться. Откройте сохранённое состояние заново перед повтором.`;
        } finally {
            generating = false;

            if (canRelease || disposed || !root.isConnected) {
                release();
            } else {
                operationRoot.setAttribute('aria-busy', 'false');
            }

            if (created && !disposed && root.isConnected) schedule();
        }
    }, options);

    image?.addEventListener('load', draw, options);
    image?.addEventListener('error', draw, options);

    const observer = image ? new MutationObserver(draw) : null;

    if (image) {
        observer.observe(image, { attributes: true, attributeFilter: ['src'] });
    }

    function dispose() {
        if (disposed) return;

        disposed = true;
        sequence += 1;
        clearTimeout(timer);
        controller?.abort();
        listeners.abort();
        observer?.disconnect();
        instances.delete(root);
    }

    root.addEventListener('htmx:beforeCleanupElement', (event) => {
        if (event.detail?.elt === root) dispose();
    }, options);

    instances.set(root, dispose);
    schedule();
    return dispose;
}
