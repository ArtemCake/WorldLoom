// frontend/src/js/features/games/sessions/session-tokens.js

import { gameStateApi, GameStateApiError } from './../game-state-api.js';
import { readTokenCreateValues } from '../token-create-values.js';
import { fillTokenMapField, readTokenMapChanges } from '../token-map-fields.js';
import { notifySessionTokensChanged, subscribeSessionTokensChanged } from './session-token-events.js';
import {messageShower} from '../../../shared/ui/message-box.js';

const initializedRoots = new WeakSet();
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const DB_INT_MIN = -2147483648;
const DB_INT_MAX = 2147483647;
const REJECTED_STATUSES = new Set([400, 401, 403, 404, 409, 413, 415, 422]);

function isUuid(value) {
    return typeof value === 'string' && UUID_PATTERN.test(value);
}

function isNullableUuid(value) {
    return value === null || isUuid(value);
}

function isDatabaseInteger(value) {
    return Number.isInteger(value) && value >= DB_INT_MIN && value <= DB_INT_MAX;
}

function validateToken(token, sessionId) {
    if (!token || !isUuid(token.id) || token.session_id !== sessionId) {
        throw new Error('Сервер вернул токен с неожиданным идентификатором или сессией.');
    }

    if (token.display_name !== null && typeof token.display_name !== 'string') {
        throw new Error('Сервер вернул некорректное название токена.');
    }

    if (!isDatabaseInteger(token.grid_x) || !isDatabaseInteger(token.grid_y)
        || !isDatabaseInteger(token.hp_current) || !isDatabaseInteger(token.hp_max)
        || !isDatabaseInteger(token.vision_radius_cells) || token.vision_radius_cells < 0) {
        throw new Error('Сервер вернул некорректные координаты, здоровье или дальность обзора.');
    }

    if (!isNullableUuid(token.current_map_id) || !isNullableUuid(token.current_hex_id)
        || typeof token.is_visible_to_players !== 'boolean') {
        throw new Error('Сервер вернул некорректное размещение или видимость токена.');
    }

    return token;
}

function validateTokens(data, sessionId) {
    if (!Array.isArray(data)) {
        throw new Error('Сервер вернул неподдерживаемый список токенов.');
    }

    const identifiers = new Set();

    for (const token of data) {
        validateToken(token, sessionId);

        if (identifiers.has(token.id)) {
            throw new Error('В списке повторяется токен.');
        }

        identifiers.add(token.id);
    }

    return data;
}

function describePlacement(token) {
    if (token.current_map_id === null) {
        return token.current_hex_id === null
            ? 'Карта не назначена'
            : 'Гекс указан без карты: требуется проверка состояния';
    }

    return token.current_hex_id === null ? 'На карте, без привязки к гексу' : 'На карте, привязан к гексу';
}

function appendCell(row, value) {
    const cell = document.createElement('td');
    cell.textContent = value;
    row.append(cell);
}

function renderTokens(body, tokens, canEdit) {
    const fragment = document.createDocumentFragment();

    for (const token of tokens) {
        const row = document.createElement('tr');
        const heading = document.createElement('th');

        heading.scope = 'row';
        heading.textContent = token.display_name?.trim() || 'Без названия';
        row.append(heading);

        appendCell(row, String(token.grid_x));
        appendCell(row, String(token.grid_y));
        appendCell(row, describePlacement(token));
        appendCell(row, `${token.hp_current} / ${token.hp_max}`);
        appendCell(row, String(token.vision_radius_cells));
        appendCell(row, token.is_visible_to_players ? 'Да' : 'Нет');

        if (canEdit) {
            const cell = document.createElement('td');

            for (const [action, title] of [['edit', 'Изменить'], ['delete', 'Удалить']]) {
                const button = document.createElement('button');

                button.type = 'button';
                button.className = action === 'delete' ? 'btn btn-danger' : 'btn btn-outline-primary';
                button.dataset.tokenAction = action;
                button.dataset.tokenId = token.id;
                button.textContent = title;
                cell.append(button, document.createTextNode(' '));
            }

            row.append(cell);
        }

        fragment.append(row);
    }

    body.replaceChildren(fragment);
}

function readEditValues(form, token) {
    const fields = form.elements;
    const displayName = fields.namedItem('display_name').value.trim();

    if (displayName.length > 100) {
        throw new Error('Название токена не должно превышать 100 символов.');
    }

	const values = {
        display_name: displayName || null,
        is_visible_to_players: fields.namedItem('is_visible_to_players').checked,
        ...readTokenMapChanges(form, token)
    };

    for (const name of ['hp_current', 'hp_max', 'vision_radius_cells']) {
        const raw = fields.namedItem(name).value.trim();
        const value = Number(raw);

        if (!raw || !isDatabaseInteger(value) || (name === 'vision_radius_cells' && value < 0)) {
            throw new Error('Проверьте целочисленные значения здоровья и дальности обзора.');
        }

        values[name] = value;
    }

    return Object.fromEntries(Object.entries(values).filter(([name, value]) => value !== token[name]));
}

function initTokenPanel(root) {
    if (initializedRoots.has(root)) return;

    const sessionId = root.dataset.sessionId;
    const canManage = root.dataset.canManage === 'true';
    const refresh = root.querySelector('[data-session-tokens-refresh]');
    const message = root.querySelector('[data-session-tokens-message]');
    const table = root.querySelector('[data-session-tokens-table]');
    const body = root.querySelector('[data-session-tokens-body]');
    const empty = root.querySelector('[data-session-tokens-empty]');
    const createForm = root.querySelector('[data-token-create-form]');
    const editForm = root.querySelector('[data-token-edit-form]');
    const cancel = editForm?.querySelector('[data-token-edit-cancel]');

    if (!isUuid(sessionId) || !refresh || !message || !table || !body || !empty) return;

    const canCreate = canManage && createForm instanceof HTMLFormElement;
    const canEdit = canManage && editForm instanceof HTMLFormElement && Boolean(cancel);
    const listeners = new AbortController();
    const options = { signal: listeners.signal };
    let records = new Map();
    let editing = null;
    let disposed = false;
    let busy = false;
    let locked = true;
    let pendingExternalRefresh = false;

    initializedRoots.add(root);

    function isActive() {
        return !disposed && root.isConnected;
    }

    const showMessage = messageShower(message);

    function applyExternalRefresh() {
        if (!isActive() || busy || !pendingExternalRefresh) return;

        pendingExternalRefresh = false;
        locked = true;
        syncControls();

        if (editing) {
            showMessage(
                'Токены изменены на карте. Форма оставлена без изменений, но сохранение заблокировано. '
                + 'Скопируйте нужные правки перед обновлением списка.',
                true
            );
            return;
        }1

        void loadTokens();
    }

    function syncControls() {
        root.setAttribute('aria-busy', busy ? 'true' : 'false');

        root.querySelectorAll('button').forEach((button) => {
            button.disabled = busy || (locked && button !== refresh);
        });

        root.querySelectorAll('fieldset').forEach((fieldset) => {
            fieldset.disabled = busy || locked;
        });
    }

    function closeEditor() {
        editing = null;

        if (editForm) {
            editForm.hidden = true;
            editForm.reset();
        }
    }

    function clearList() {
        records.clear();
        body.replaceChildren();
        table.hidden = true;
        empty.hidden = true;
    }

    async function readTokens() {
        clearList();

        const data = await gameStateApi.listTokens(sessionId);

        if (!isActive()) return false;

        const tokens = validateTokens(data, sessionId);
        records = new Map(tokens.map((token) => [token.id, token]));
        renderTokens(body, tokens, canEdit);
        table.hidden = tokens.length === 0;
        empty.hidden = tokens.length !== 0;
        locked = false;
        return true;
    }

    async function loadTokens() {
        if (!isActive() || busy) return;

        if (editing && !window.confirm('Обновить список и закрыть форму редактирования без сохранения?')) {
                    return;
        }

        busy = true;
        closeEditor();
        syncControls();
        showMessage('Загрузка сохранённых токенов…');

        try {
            if (await readTokens()) {
                showMessage('Список получен с сервера.');
            }
        } catch (error) {
            if (!isActive()) return;

            locked = true;
            clearList();
            showMessage(error instanceof Error ? error.message : 'Не удалось загрузить токены сессии.', true);
        } finally {
            busy = false;

            if (isActive()) {
                syncControls();

                if (pendingExternalRefresh) {
                    queueMicrotask(applyExternalRefresh);
                }
            }
        }
    }

    function openEditor(token) {
        if (!isActive() || !canEdit || busy || locked) return;

        if (editing && !window.confirm('Закрыть текущую форму без сохранения и выбрать другой токен?')) {
            return;
        }

        editing = token;

        for (const name of ['display_name', 'hp_current', 'hp_max', 'vision_radius_cells']) {
            editForm.elements.namedItem(name).value = token[name] ?? '';
        }

        editForm.elements.namedItem('is_visible_to_players').checked = token.is_visible_to_players;
        fillTokenMapField(editForm, token);
        editForm.hidden = false;
        showMessage('Изменения формы ещё не сохранены.');
        editForm.elements.namedItem('display_name').focus();
    }

    async function writeToken(action, token, changes = null) {
        if (!isActive() || busy || locked || !canManage) return;
        if (!['create', 'update', 'delete'].includes(action)) return;
        if (action === 'create' ? !canCreate : !canEdit) return;

        if (!document.querySelector('meta[name="csrf-token"]')?.content) {
            showMessage('Не найден защитный токен. Перезагрузите страницу.', true);
            return;
        }

        const creating = action === 'create';
        const deleting = action === 'delete';
        const pendingText = creating ? 'Создание токена…' : deleting ? 'Удаление токена…' : 'Сохранение токена…';
        const successText = creating ? 'Токен создан.' : deleting ? 'Токен удалён.' : 'Изменения токена сохранены.';
        let confirmed = false;

        busy = true;
        syncControls();
        showMessage(pendingText);

        try {
            if (deleting) {
                const data = await gameStateApi.deleteToken(token.id);

                if (data !== null) {
                    throw new Error('Сервер вернул неожиданный ответ удаления.');
                }
            } else {
                const data = creating
                    ? await gameStateApi.createToken(changes)
                    : await gameStateApi.updateToken(token.id, changes);

                validateToken(data, sessionId);

                if (Object.entries(changes).some(([name, value]) => data[name] !== value)) {
                    throw new Error('Сервер не подтвердил ожидаемые значения токена.');
                }
                if (!creating && Object.hasOwn(changes, 'current_map_id') && data.current_hex_id !== null) {
                    throw new Error('Сервер вернул неожиданную привязку к гексу после изменения карты.');
                }
                if (creating) {
                    if (records.has(data.id) || data.current_map_id !== null || data.current_hex_id !== null) {
                        throw new Error('Сервер вернул неожиданное состояние нового токена.');
                    }
                } else if (data.id !== token.id) {
                    throw new Error('Сервер вернул другой токен.');
                }
            }

            if (!isActive()) return;

            confirmed = true;
            notifySessionTokensChanged(root);
            closeEditor();

            if (creating) createForm.reset();

            locked = true;

            if (await readTokens()) {
                showMessage(`${successText} Список обновлён.`);
            }
        } catch (error) {
            if (!isActive()) return;

            const text = error instanceof Error ? error.message : 'Не удалось получить результат операции.';

            if (confirmed) {
                locked = true;
                clearList();
                showMessage(`${successText} Но обновить список не удалось. ${text} Нажмите «Обновить токены».`, true);
            } else {
                const rejected = error instanceof GameStateApiError && REJECTED_STATUSES.has(error.status);
                locked = !rejected;
                if (!rejected) notifySessionTokensChanged(root);

                const advice = creating
                    ? 'Операция могла сохраниться. Обновите список и проверьте наличие токена перед повторным созданием.'
                    : 'Операция могла сохраниться. Нажмите «Обновить токены» перед дальнейшими изменениями.';

                showMessage(locked ? `${text} ${advice}` : text, true);
            }
        } finally {
            busy = false;

            if (isActive()) {
                syncControls();

                if (pendingExternalRefresh) {
                    queueMicrotask(applyExternalRefresh);
                }
            }
        }
    }

    body.addEventListener('click', (event) => {
        const button = event.target instanceof Element ? event.target.closest('[data-token-action]') : null;

        if (!isActive() || !button || !body.contains(button) || button.disabled || busy || locked || !canEdit) return;

        const token = records.get(button.dataset.tokenId);

        if (!token) return;

        if (button.dataset.tokenAction === 'edit') {
            openEditor(token);
        } else if (button.dataset.tokenAction === 'delete') {
            const title = token.display_name?.trim() || 'Без названия';

            if (editing && !window.confirm('Продолжить удаление? После успеха открытая форма редактирования закроется без сохранения.')) {
                return;
            }

            if (window.confirm(`Удалить токен «${title}»? Отменить удаление нельзя.`)) {
                void writeToken('delete', token);
            }
        }
    }, options);

    createForm?.addEventListener('submit', (event) => {
        event.preventDefault();

        if (!isActive() || busy || locked || !canCreate || !createForm.reportValidity()) return;

        try {
            const payload = readTokenCreateValues(createForm, sessionId);

            if (editing && !window.confirm('Создать токен и после успеха закрыть форму редактирования без сохранения?')) {
                return;
            }

            void writeToken('create', null, payload);
        } catch (error) {
            showMessage(error instanceof Error ? error.message : 'Проверьте поля нового токена.', true);
        }
    }, options);

    editForm?.addEventListener('submit', (event) => {
        event.preventDefault();

        if (!isActive() || !editing || busy || locked || !canEdit || !editForm.reportValidity()) return;

        try {
            const changes = readEditValues(editForm, editing);

            if (!Object.keys(changes).length) {
                showMessage('Нет изменённых полей для сохранения.');
                return;
            }
            if (Object.hasOwn(changes, 'current_map_id') && editing.current_hex_id !== null) {
                const accepted = window.confirm('Изменить назначение карты? Привязка токена к гексу будет сброшена. Координаты X/Y сохранятся.');

                if (!accepted) return;
            }
            void writeToken('update', editing, changes);
        } catch (error) {
            showMessage(error instanceof Error ? error.message : 'Проверьте значения формы.', true);
        }
    }, options);

    cancel?.addEventListener('click', () => {
        if (!isActive() || busy || locked) return;

        closeEditor();
        showMessage('Форма закрыта без сохранения.');
    }, options);

    refresh.addEventListener('click', () => void loadTokens(), options);

    root.addEventListener('htmx:beforeCleanupElement', (event) => {
        if (event.detail?.elt !== root || disposed) return;

        disposed = true;
        listeners.abort();
        records.clear();
        editing = null;
        initializedRoots.delete(root);
    }, options);

    subscribeSessionTokensChanged(root, () => {
        pendingExternalRefresh = true;
        locked = true;

        if (!busy) {
            syncControls();
            queueMicrotask(applyExternalRefresh);
        }
    }, listeners.signal);

    void loadTokens();
}

export function initSessionTokens() {
    document.querySelectorAll('[data-session-tokens]').forEach(initTokenPanel);
}
