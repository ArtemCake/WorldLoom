// frontend/src/js/features/games/sessions/session-management.js

import { requestGameJson } from './../game-http.js';

const initializedRoots = new WeakSet();

function readTitle(form) {
    const fields = new FormData(form);
    const title = String(fields.get('title') || '').trim();

    if (title.length > 255) {
        throw new Error('Название сессии не должно превышать 255 символов.');
    }

    return title || null;
}

function validateSession(value, gameId, sessionId, expectedActive) {
    if (!value || typeof value.id !== 'string' || !value.id || value.game_id !== gameId
        || typeof value.is_active !== 'boolean') {
        throw new Error('Сервер не подтвердил ожидаемую сессию.');
    }

    if (sessionId !== null && value.id !== sessionId) {
        throw new Error('Сервер вернул другую сессию.');
    }

    if (expectedActive !== null && value.is_active !== expectedActive) {
        throw new Error('Сервер не подтвердил ожидаемый статус сессии.');
    }

    return value;
}

function initPanel(root) {
    if (initializedRoots.has(root)) return;

    const gameId = root.dataset.gameId;
    const message = root.querySelector('[data-session-management-message]');
    const createForm = root.querySelector('[data-session-create-form]');
    const updateForm = root.querySelector('[data-session-update-form]');
    const endForm = root.querySelector('[data-session-end-form]');

    if (!gameId || !message) return;

    initializedRoots.add(root);
    let busy = false;

    function showMessage(text, isError = false) {
        message.textContent = text;
        message.classList.toggle('alert-error', isError);
    }

    async function perform(form, method, body, sessionId = null, expectedActive = null) {
        if (busy || !root.isConnected) return;

        if (!document.querySelector('meta[name="csrf-token"]')?.content) {
            showMessage('Не найден защитный токен. Перезагрузите страницу.', true);
            return;
        }

        busy = true;
        root.setAttribute('aria-busy', 'true');
        showMessage('');

        const controls = Array.from(root.querySelectorAll('button, input, textarea, select'));
        const disabledStates = controls.map((control) => control.disabled);
        let navigating = false;

        controls.forEach((control) => {
            control.disabled = true;
        });

        try {
            const data = await requestGameJson(form.action, { method, body });

            if (!root.isConnected) return;

            const saved = validateSession(data, gameId, sessionId, expectedActive);
            const target = new URL(window.location.href);

            target.searchParams.set('session_id', saved.id);
            target.hash = '';

            showMessage('Операция выполнена. Открывается актуальное состояние сессии.');
            window.location.assign(target.href);
            navigating = true;
        } catch (error) {
            if (!root.isConnected) return;

            const text = error instanceof Error ? error.message : 'Не удалось получить результат операции.';

            showMessage(
                `${text} Перед повторной отправкой проверьте состояние сессии, обновив страницу. `
                + 'Если нужно, сначала скопируйте введённые итоги.',
                true
            );
        } finally {
            if (!navigating) {
                busy = false;
                root.setAttribute('aria-busy', 'false');

                controls.forEach((control, index) => {
                    control.disabled = disabledStates[index];
                });
            }
        }
    }

    createForm?.addEventListener('submit', (event) => {
        event.preventDefault();

        if (busy || !createForm.reportValidity()) return;

        let title;

        try {
            title = readTitle(createForm);
        } catch (error) {
            showMessage(error.message, true);
            return;
        }

        void perform(createForm, 'POST', { title }, null, true);
    });

    updateForm?.addEventListener('submit', (event) => {
        event.preventDefault();

        if (busy || !updateForm.reportValidity()) return;

        let title;

        try {
            title = readTitle(updateForm);
        } catch (error) {
            showMessage(error.message, true);
            return;
        }

        const fields = new FormData(updateForm);
        const summary = String(fields.get('summary_log') || '');
        const payload = { title, summary_log: summary || null };

        void perform(updateForm, 'PATCH', payload, updateForm.dataset.sessionId);
    });

    endForm?.addEventListener('submit', (event) => {
        event.preventDefault();

        if (busy) return;

        const approved = window.confirm(
            'Завершить выбранную сессию? Новые броски станут недоступны. '
            + 'Несохранённые изменения названия и итогов не будут отправлены.'
        );

        if (!approved) return;

        void perform(endForm, 'POST', undefined, endForm.dataset.sessionId, false);
    });
}

export function initSessionManagement() {
    document.querySelectorAll('[data-session-management]').forEach(initPanel);
}
