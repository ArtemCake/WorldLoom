// frontend/src/js/features/maps/games/game-map-controller.js

import { subscribeSessionTokensChanged } from '../../games/sessions/session-token-events.js';
import { isMapUuid, listGameMaps, readGameMap, readGameMapImage } from './game-map-data.js';
import { readStoredMapFog } from './game-map-fog-data.js';
import { readStoredMapTokens } from './game-map-token-data.js';

const instances = new WeakMap();

function initGameMap(root) {
    if (instances.has(root)) return;

    const canvas = root.querySelector('[data-game-map-canvas]');
    const message = root.querySelector('[data-game-map-message]');
    const tokensMessage = root.querySelector('[data-game-map-tokens-message]');
    const fogToggle = root.querySelector('[data-game-map-fog-toggle]');
    const fogMessage = root.querySelector('[data-game-map-fog-message]');
    const select = root.querySelector('[data-game-map-select]');
    const refresh = root.querySelector('[data-game-map-refresh]');
    const gameId = root.dataset.gameId;
    const sessionId = root.dataset.sessionId;

    if (!(canvas instanceof HTMLCanvasElement) || !message || !tokensMessage || !fogMessage
        || !(fogToggle instanceof HTMLInputElement)
        || !(select instanceof HTMLSelectElement) || !(refresh instanceof HTMLButtonElement)) return;

    if (!isMapUuid(gameId) || !isMapUuid(sessionId)) {
        message.textContent = 'Не удалось определить игру и выбранную сессию.';
        return;
    }

    const listeners = new AbortController();
    const options = { signal: listeners.signal };
    const state = { disposed: false, busy: false, map: null, placement: null, fog: null };
    let pendingExternalRefresh = false;
    let fogAvailable = false;

    instances.set(root, state);

    function isActive() {
        return !state.disposed && root.isConnected;
    }

    function setBusy(value) {
        state.busy = value;
        state.placement?.setBusy(value);

        if (!isActive()) return;

        root.setAttribute('aria-busy', String(value));
        refresh.disabled = value;
        select.disabled = value || select.options.length <= 1;
        fogToggle.disabled = value || !fogAvailable;

        if (!value && pendingExternalRefresh) {
            queueMicrotask(flushExternalRefresh);
        }
    }

    function setMessage(text) {
        if (isActive()) message.textContent = text;
    }

    function clearFogView() {
        state.fog?.clear();
        fogAvailable = false;

        if (!isActive()) return;

        fogToggle.disabled = true;
        fogMessage.textContent = '';
    }

    function clearScene() {
        clearFogView();
        state.placement?.reset();
        state.map?.clearStoredMap();

        if (isActive()) {
            canvas.setAttribute('aria-label', 'Карта не отображается');
            tokensMessage.textContent = '';
        }
    }

    function dispose() {
        if (state.disposed) return;

        state.disposed = true;
        listeners.abort();
        state.placement?.destroy();
        state.fog?.destroy();
        instances.delete(root);

        if (state.map) {
            void state.map.destroy().catch((error) => {
                console.error('Не удалось освободить ресурсы карты.', error);
            });
        }
    }

    async function run(operation) {
        if (!isActive() || state.busy) return;

        setBusy(true);
        clearScene();

        try {
            await operation();
        } catch (error) {
            if (!isActive()) return;

            clearScene();
            setMessage(error instanceof Error ? error.message : 'Не удалось открыть сохранённую карту.');
        } finally {
            if (isActive()) setBusy(false);
        }
    }

    async function displayTokens(data) {
        if (!isActive()) return;

        state.map.clearStoredTokens();
        tokensMessage.textContent = 'Чтение сохранённых токенов…';

        try {
            const result = await readStoredMapTokens(sessionId, data);

            if (!isActive()) return;

            state.map.showStoredTokens(result.tokens);

            const hiddenCount = result.tokens.filter((token) => !token.visibleToPlayers).length;
            const parts = [
                `На карте показано токенов: ${result.tokens.length}.`,
                `Из них скрыто от игроков по флагу токена: ${hiddenCount}.`
            ];

            if (result.outsideCount) {
                parts.push(`Не показано за пределами сетки: ${result.outsideCount}. Проверьте координаты в панели токенов.`);
            }

            parts.push('Синие маркеры — видимые, фиолетовые — скрытые. Портреты пока не загружаются.');
            tokensMessage.textContent = parts.join(' ');
            canvas.setAttribute('aria-label', `Карта: ${data.title}. Показано токенов: ${result.tokens.length}.`);

            await state.placement?.setMap(data, result.tokens, () => displayTokens(data));
        } catch (error) {
            if (!isActive()) return;

            state.placement?.reset();
            state.map.clearStoredTokens();

            const reason = error instanceof Error ? error.message : 'Не удалось прочитать список.';
            tokensMessage.textContent = `Карта открыта, но токены не загружены. ${reason}`;
        }
    }

    async function displaySavedFog(data) {
        clearFogView();

        if (!isActive() || !state.fog) return;

        if (!data.fog_of_war_enabled) {
            fogMessage.textContent = 'Туман войны выключен в настройках карты. Затемнение не накладывается.';
            return;
        }

        fogMessage.textContent = 'Чтение сохранённой видимости…';

        try {
            const cells = await readStoredMapFog(data);

            if (!isActive()) return;

            state.fog.show(cells, fogToggle.checked);
            fogAvailable = true;
            fogToggle.disabled = state.busy;

            const visibleCount = cells.filter((cell) => cell.visible).length;
            const exploredHiddenCount = cells.filter((cell) => !cell.visible && cell.explored).length;
            const unexploredHiddenCount = cells.length - visibleCount - exploredHiddenCount;

            fogMessage.textContent = `По сохранённым данным: видимых гексов — ${visibleCount}; `
                + `исследованных вне видимости — ${exploredHiddenCount}; `
                + `неисследованных вне видимости — ${unexploredHiddenCount}. `
                + 'Это снимок состояния, а не новый расчёт обзора.';
        } catch (error) {
            if (!isActive()) return;

            clearFogView();

            const reason = error instanceof Error ? error.message : 'Не удалось прочитать состояние.';
            fogMessage.textContent = `Затемнение не показано. ${reason}`;
        }
    }

    function flushExternalRefresh() {
        if (!isActive() || state.busy || !pendingExternalRefresh || !state.map || !state.placement) return;

        pendingExternalRefresh = false;

        if (state.placement.hasDraft()) {
            state.placement.markStale();
            setMessage(
                'Данные токенов изменены. Отображение пока не обновлено, чтобы сохранить выбранное назначение. '
                + 'После проверки черновика нажмите «Обновить карты».'
            );
            return;
        }

        void run(reloadCatalog);
    }

    async function displaySelectedMap() {
        const mapId = select.value;

        if (!mapId) {
            setMessage('Выберите карту для мастерского просмотра.');
            return;
        }

        setMessage('Чтение сохранённой карты…');

        const data = await readGameMap(mapId, gameId, sessionId);

        if (!isActive()) return;

        const image = await readGameMapImage(data);

        if (!isActive()) return;

        await state.map.showStoredMap(data, image);

        if (!isActive()) return;

        const activity = data.is_active_in_session ? 'Активная карта игры.' : 'Предпросмотр неактивной карты.';
        const background = image ? 'Фон загружен.' : 'Фоновое изображение не задано.';
        const fog = data.fog_of_war_enabled
            ? 'Сохранённая видимость загружается отдельным слоем мастерского просмотра.'
            : 'Туман войны выключен в настройках карты.';

        canvas.setAttribute('aria-label', `Карта: ${data.title}`);
        setMessage(`${data.title}. Сетка ${data.cols} × ${data.rows}. ${activity} ${background} ${fog}`);

        await displayTokens(data);
        await displaySavedFog(data);
    }

    async function reloadCatalog() {
        const previousId = select.value;
        setMessage('Чтение доступных карт…');

        const maps = await listGameMaps(gameId, sessionId);

        if (!isActive()) return;

        const fragment = document.createDocumentFragment();
        fragment.append(new Option('Выберите карту', ''));

        for (const map of maps) {
            const suffix = map.is_active_in_session ? ' — активная' : '';
            fragment.append(new Option(`${map.title}${suffix}`, map.id));
        }

        select.replaceChildren(fragment);

        if (!maps.length) {
            setMessage('Для выбранной сессии нет доступных карт. Создайте карту в разделе карт этой игры.');
            return;
        }

        if (maps.some((map) => map.id === previousId)) {
            select.value = previousId;
        } else {
            const activeMaps = maps.filter((map) => map.is_active_in_session);

            if (activeMaps.length > 1) {
                throw new Error('Найдено несколько активных карт. Проверьте их состояние в разделе карт.');
            }

            select.value = activeMaps[0]?.id || '';
        }

        await displaySelectedMap();
    }

    select.addEventListener('change', () => {
        void run(displaySelectedMap);
    }, options);

    refresh.addEventListener('click', () => {
        void run(reloadCatalog);
    }, options);

    fogToggle.addEventListener('change', () => {
        if (!isActive() || state.busy || !fogAvailable) return;

        state.fog?.setVisible(fogToggle.checked);
    }, options);

    root.addEventListener('htmx:beforeCleanupElement', (event) => {
        if (event.detail?.elt === root) dispose();
    }, options);

    async function mount() {
        setBusy(true);
        setMessage('Подготовка графического поля…');

        try {
            const [{ StoredGameMap }, { createMapPlacement }, { StoredMapFog }] = await Promise.all([
                import('../stored-game-map.js'),
                import('./game-map-placement.js'),
                import('../rendering/stored-map-fog.js')
            ]);

            if (!isActive()) return;

            state.map = new StoredGameMap(canvas);
            await state.map.ready;

            if (!isActive()) return;

            state.fog = new StoredMapFog(state.map);
            state.placement = createMapPlacement(root, state.map, setBusy);
            state.placement.setBusy(true);

            await reloadCatalog();
        } catch (error) {
            if (!isActive()) return;

            clearScene();
            setMessage(error instanceof Error ? error.message : 'Не удалось подготовить графическое поле.');
        } finally {
            if (isActive()) setBusy(false);
        }
    }

    subscribeSessionTokensChanged(root, () => {
        pendingExternalRefresh = true;
        queueMicrotask(flushExternalRefresh);
    }, listeners.signal);

    void mount();
}

export function initGameMaps() {
    document.querySelectorAll('[data-game-map]').forEach(initGameMap);
}