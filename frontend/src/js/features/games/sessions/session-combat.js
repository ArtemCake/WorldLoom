// frontend/src/js/features/games/sessions/session-combat.js

import { gameStateApi, GameStateApiError } from './../game-state-api.js';
import { readCombatants, validateCombatState } from './../combat-values.js';

const initializedRoots = new WeakSet();
const REJECTED_STATUSES = new Set([400, 401, 403, 404, 409, 413, 415, 422]);

function renderState(status, round, list, state) {
    const fragment = document.createDocumentFragment();
    const active = state.session_active && state.combat_active;

    state.turn_order.forEach((entry, index) => {
        const item = document.createElement('li');
        const name = entry.name?.trim() || `Участник ${index + 1}`;
        const initiative = entry.initiative === null ? 'не указана' : String(entry.initiative);

        item.textContent = `${name} — инициатива: ${initiative}`;

        if (index === state.current_index) {
            if (active) {
                const marker = document.createElement('strong');

                marker.textContent = ' — текущий ход';
                item.setAttribute('aria-current', 'step');
                item.append(marker);
            } else {
                item.append(' — сохранённая позиция');
            }
        }

        fragment.append(item);
    });

    list.replaceChildren(fragment);
    round.hidden = !state.hasTracker;
    round.textContent = state.hasTracker ? `Раунд: ${state.round_number}` : '';

    if (!state.hasTracker) {
        status.textContent = state.session_active
            ? 'Сохранённой очереди нет. Можно подготовить новый бой.'
            : 'Сессия завершена. Сохранённой очереди нет.';
    } else if (!state.session_active) {
        status.textContent = 'Сессия завершена. Показана сохранённая очередь.';
    } else if (!state.combat_active) {
        status.textContent = 'Сохранённая очередь неактивна. Перед новым боем её необходимо удалить.';
    } else {
        status.textContent = state.turn_order.length ? 'Бой идёт.' : 'Бой активен, но очередь пуста.';
    }
}

function initPanel(root) {
    if (initializedRoots.has(root)) return;

    const sessionId = root.dataset.sessionId;
    const refresh = root.querySelector('[data-combat-refresh]');
    const status = root.querySelector('[data-combat-status]');
    const message = root.querySelector('[data-combat-message]');
    const round = root.querySelector('[data-combat-round]');
    const list = root.querySelector('[data-combat-order]');
    const form = root.querySelector('[data-combat-start-form]');
    const fieldset = form?.querySelector('fieldset');
    const next = root.querySelector('[data-combat-next]');
    const end = root.querySelector('[data-combat-end]');

    if (!sessionId || !refresh || !status || !message || !round || !list) return;

    const canManage = root.dataset.canManage === 'true'
        && form instanceof HTMLFormElement && Boolean(fieldset && next && end);
    const listeners = new AbortController();
    const options = { signal: listeners.signal };
    let state = null;
    let disposed = false;
    let busy = false;
    let locked = true;

    initializedRoots.add(root);

    function isActive() {
        return !disposed && root.isConnected;
    }

    function showMessage(text, isError = false) {
        message.textContent = text;
        message.classList.toggle('alert-error', isError);
    }

    function syncControls() {
        root.setAttribute('aria-busy', busy ? 'true' : 'false');
        refresh.disabled = busy;

        const unavailable = busy || locked || !canManage || state === null;

        if (fieldset) {
            fieldset.disabled = unavailable || !state?.session_active || state?.hasTracker;
        }

        if (next) {
            next.disabled = unavailable || !state?.session_active || !state?.combat_active || !state?.turn_order.length;
        }

        if (end) {
            end.disabled = unavailable || !state?.hasTracker;
        }
    }

    function clearState() {
        state = null;
        list.replaceChildren();
        round.hidden = true;
        round.textContent = '';
        status.textContent = 'Актуальное состояние очереди не получено.';
    }

    async function readState() {
        clearState();

        const data = await gameStateApi.getCombatState(sessionId);

        if (!isActive()) return false;

        state = validateCombatState(data, sessionId);
        renderState(status, round, list, state);
        locked = false;
        return true;
    }

    async function loadState() {
        if (!isActive() || busy) return;

        busy = true;
        locked = true;
        syncControls();
        showMessage('Загрузка состояния боя…');

        try {
            if (await readState()) {
                showMessage('Очередь получена с сервера.');
            }
        } catch (error) {
            if (!isActive()) return;

            clearState();
            showMessage(error instanceof Error ? error.message : 'Не удалось загрузить состояние боя.', true);
        } finally {
            busy = false;

            if (isActive()) syncControls();
        }
    }

    async function writeState(action, combatants = null) {
        if (!isActive() || busy || locked || !canManage || !state) return;

        if (action === 'start') {
            if (!state.session_active || state.hasTracker) return;
        } else if (action === 'next') {
            if (!state.session_active || !state.combat_active || !state.turn_order.length) return;
        } else if (action === 'end') {
            if (!state.hasTracker) return;
        } else {
            return;
        }

        if (!document.querySelector('meta[name="csrf-token"]')?.content) {
            showMessage('Не найден защитный токен. Перезагрузите страницу.', true);
            return;
        }

        const successText = action === 'start' ? 'Бой начат.' : action === 'next' ? 'Ход переключён.' : 'Очередь боя удалена.';
        let confirmed = false;

        busy = true;
        locked = true;
        syncControls();
        showMessage('Сохранение изменения очереди…');

        try {
            let data;

            if (action === 'start') {
                data = await gameStateApi.startCombat(sessionId, combatants);
            } else if (action === 'next') {
                data = await gameStateApi.nextTurn(sessionId);
            } else {
                data = await gameStateApi.endCombat(sessionId);
            }

            if (!isActive()) return;

            if (action === 'end') {
                if (data !== null) {
                    throw new Error('Сервер вернул неожиданный ответ завершения боя.');
                }
            } else if (!data || data.session_id !== sessionId || !Array.isArray(data.turn_order)
                || !Number.isInteger(data.current_index) || data.current_index < 0 || data.current_index >= data.turn_order.length
                || !Number.isInteger(data.round_number) || data.round_number < 1) {
                throw new Error('Сервер не подтвердил ожидаемое состояние очереди.');
            }

            confirmed = true;

            if (action === 'start') form.reset();

            if (await readState()) {
                showMessage(`${successText} Текущее состояние перечитано.`);
            }
        } catch (error) {
            if (!isActive()) return;

            locked = true;
            clearState();

            const text = error instanceof Error ? error.message : 'Не удалось получить результат операции.';
            const rejected = error instanceof GameStateApiError && REJECTED_STATUSES.has(error.status);

            if (confirmed) {
                showMessage(`${successText} Но перечитать состояние не удалось. ${text} Нажмите «Обновить очередь».`, true);
            } else if (rejected) {
                showMessage(`${text} Перед следующей операцией нажмите «Обновить очередь».`, true);
            } else {
                showMessage(`${text} Операция могла сохраниться. Нажмите «Обновить очередь» и проверьте результат перед повтором.`, true);
            }
        } finally {
            busy = false;

            if (isActive()) syncControls();
        }
    }

    form?.addEventListener('submit', (event) => {
        event.preventDefault();

        if (!isActive() || busy || locked || !canManage || !state?.session_active || state.hasTracker || !form.reportValidity()) return;

        try {
            const combatants = readCombatants(form);

            if (window.confirm('Начать бой? Порядок ходов будет соответствовать порядку строк, без сортировки по инициативе.')) {
                void writeState('start', combatants);
            }
        } catch (error) {
            showMessage(error instanceof Error ? error.message : 'Проверьте список участников.', true);
        }
    }, options);

    next?.addEventListener('click', () => {
        void writeState('next');
    }, options);

    end?.addEventListener('click', () => {
        if (!isActive() || busy || locked || !canManage || !state?.hasTracker) return;

        if (window.confirm('Завершить бой и удалить очередь? История этой очереди не сохранится.')) {
            void writeState('end');
        }
    }, options);

    refresh.addEventListener('click', () => void loadState(), options);

    root.addEventListener('htmx:beforeCleanupElement', (event) => {
        if (event.detail?.elt !== root || disposed) return;

        disposed = true;
        listeners.abort();
        state = null;
        initializedRoots.delete(root);
    }, options);

    void loadState();
}

export function initSessionCombat() {
    document.querySelectorAll('[data-session-combat]').forEach(initPanel);
}
