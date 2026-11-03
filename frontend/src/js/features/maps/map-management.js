// frontend/src/js/features/maps/map-management.js

import { MapRequestError, requestMapJson } from './map-http.js';
import { acquireMapOperation } from './map-operation-state.js';

const initializedRoots = new WeakSet();
const REJECTED_STATUSES = new Set([400, 401, 403, 404, 409, 413, 415, 422]);
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function confirmOperation(action, destinationTitle) {
    switch (action) {
        case 'activate':
            return window.confirm('Активировать карту? Остальные карты этой игры станут неактивными.');
        case 'deactivate':
            return window.confirm('Деактивировать карту? Другая карта автоматически выбрана не будет.');
        case 'copy':
            return window.confirm(
                `Создать копию основы карты в игре «${destinationTitle}»?\n\n`
                + 'Копируются фон, настройки, слои и гексы. '
                + 'Токены, объекты, аудиозоны и исследованные области не копируются. '
                + 'Оригинал останется в исходной игре.'
            );
        case 'move':
            return window.confirm(
                `Перенести оригинал карты в игру «${destinationTitle}»?\n\n`
                + 'Карта исчезнет из исходной игры, станет неактивной и отвяжется от сессии. '
                + 'Сетка и состояние тумана сохранятся. '
                + 'При наличии привязанных токенов, объектов или аудиозон сервер отклонит перенос.'
            );
        default:
            return false;
    }
}

function validateResult(data, action, mapId, sourceGameId, targetGameId) {
    if (!data || typeof data.id !== 'string' || !UUID_PATTERN.test(data.id) || typeof data.is_active_in_session !== 'boolean') {
        throw new Error('Сервер не подтвердил ожидаемые данные карты.');
    }

    const transferring = action === 'copy' || action === 'move';
    const expectedGameId = transferring ? targetGameId : sourceGameId;

    if (data.game_id !== expectedGameId || (action === 'copy' ? data.id === mapId : data.id !== mapId)) {
        throw new Error('Получена карта с неожиданным идентификатором или принадлежностью игре.');
    }

    if (transferring) {
        if (data.is_active_in_session || data.session_id !== null) {
            throw new Error('Состояние перенесённой или скопированной карты не соответствует ожидаемому.');
        }
    } else if (data.is_active_in_session !== (action === 'activate')) {
        throw new Error('Сервер не подтвердил изменение активности карты.');
    }

    return data;
}

function initManagement(root) {
    if (initializedRoots.has(root)) return;

    const operationRoot = root.closest('[data-map-operation-root]');
    const message = root.querySelector('[data-map-management-message]');
    const targetSelect = root.querySelector('[data-map-destination]');
    const targetLink = operationRoot?.querySelector('[data-map-target-catalog]');
    const mapId = root.dataset.mapId;
    const sourceGameId = root.dataset.sourceGameId;

    if (!operationRoot || !message || !mapId || !sourceGameId) return;

    initializedRoots.add(root);

    const listeners = new AbortController();
    const options = { signal: listeners.signal };
    let disposed = false;
    let busy = false;
    let locked = false;

    function showMessage(text, isError = false) {
        message.textContent = text;
        message.classList.toggle('alert-error', isError);
    }

    function updateTargetLink() {
        const option = targetSelect?.selectedOptions[0];
        const address = option?.dataset.catalogUrl;

        if (!targetLink) return;

        targetLink.hidden = !address;

        if (address) targetLink.href = address;
        else targetLink.removeAttribute('href');
    }

    async function perform(button) {
        if (disposed || busy || locked || button.disabled || !root.isConnected) return;

        const action = button.dataset.mapAction;
        const needsTarget = action === 'copy' || action === 'move';

        if (!['activate', 'deactivate', 'copy', 'move'].includes(action) || !button.dataset.mapUrl) return;

        const targetGameId = targetSelect?.value || '';
        const targetOption = targetSelect?.selectedOptions[0];

        if (needsTarget && (!UUID_PATTERN.test(targetGameId) || targetGameId === sourceGameId || !targetOption?.dataset.catalogUrl)) {
            showMessage('Выберите другую игру из списка.', true);
            targetSelect?.focus();
            return;
        }

        const destinationTitle = targetOption?.textContent?.trim() || '';

        if (!confirmOperation(action, destinationTitle)) return;

        if (!document.querySelector('meta[name="csrf-token"]')?.content) {
            showMessage('Не найден защитный токен. Перезагрузите страницу.', true);
            return;
        }

        const release = acquireMapOperation(operationRoot);

        if (!release) return;

        const originalText = button.textContent;
        const body = needsTarget ? { source_game_id: sourceGameId, target_game_id: targetGameId } : undefined;
        let canRelease = false;

        busy = true;
        button.textContent = 'Выполнение…';
        showMessage('Выполнение операции с картой…');

        try {
            const data = await requestMapJson(button.dataset.mapUrl, { method: 'POST', body });

            if (disposed || !root.isConnected) return;

            const result = validateResult(data, action, mapId, sourceGameId, targetGameId);
            locked = true;

            if (needsTarget) {
                showMessage(action === 'copy' ? 'Копия основы карты создана.' : 'Карта перенесена.');
                window.location.assign(`/maps/${encodeURIComponent(result.id)}/view`);
            } else {
                showMessage('Активность карты изменена.');
                window.location.reload();
            }
        } catch (error) {
            if (disposed || !root.isConnected) return;

            canRelease = error instanceof MapRequestError && REJECTED_STATUSES.has(error.status);
            locked = !canRelease;

            const text = error instanceof Error ? error.message : 'Не удалось получить результат операции.';
            const advice = needsTarget
                ? ' Проверьте каталоги исходной и выбранной игр перед повторением.'
                : ' Откройте сохранённое состояние карты заново перед повторением.';

            showMessage(locked ? `${text} Операция могла сохраниться.${advice}` : text, true);
        } finally {
            busy = false;

            if (canRelease || disposed || !root.isConnected) {
                release();
                button.textContent = originalText;
            } else {
                operationRoot.setAttribute('aria-busy', 'false');
                button.textContent = 'Откройте сохранённое состояние';
            }
        }
    }

    targetSelect?.addEventListener('change', updateTargetLink, options);

    root.querySelectorAll('[data-map-action]').forEach((button) => {
        button.addEventListener('click', () => void perform(button), options);
    });

    root.addEventListener('htmx:beforeCleanupElement', (event) => {
        if (event.detail?.elt !== root || disposed) return;

        disposed = true;
        listeners.abort();
        initializedRoots.delete(root);
    }, options);

    updateTargetLink();
}

export function initMapManagement() {
    document.querySelectorAll('[data-map-management]').forEach(initManagement);
}
