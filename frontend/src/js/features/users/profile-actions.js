// frontend/src/js/features/users/profile-actions.js

import { sessionClient } from '../../shared/http/session-client.js';

class ProfileRequestError extends Error {
    constructor(message, uncertain = false) {
        super(message);
        this.name = 'ProfileRequestError';
        this.uncertain = uncertain;
    }
}

function responseMessage(data, fallback) {
    if (typeof data?.detail === 'string') return data.detail;
    if (typeof data?.error === 'string') return data.error;
    if (typeof data?.message === 'string') return data.message;

    if (Array.isArray(data?.detail)) {
        const messages = data.detail.map((item) => typeof item?.msg === 'string' ? item.msg : '').filter(Boolean);
        if (messages.length) return messages.join(' ');
    }

    return fallback;
}

export function showProfileStatus(box, message, success = false) {
    if (!box) return;

    const alert = document.createElement('div');
    alert.className = success ? 'alert alert-success' : 'alert alert-danger';
    alert.setAttribute('role', success ? 'status' : 'alert');
    alert.textContent = message;
    box.replaceChildren(alert);
}

export function unexpectedProfileResponse() {
    return new ProfileRequestError('Ответ сервера не позволяет подтвердить результат операции.', true);
}

export async function requestProfile(path, method, body = undefined) {
    if (!document.querySelector('meta[name="csrf-token"]')?.content) {
        throw new ProfileRequestError('Защитный токен отсутствует. Обновите страницу.');
    }

    let response;

    try {
        response = await sessionClient.sessionFetch(path, {
            method,
            body,
            headers: { Accept: 'application/json' },
            retryAfterRefresh: false
        });
    } catch {
        throw new ProfileRequestError('Ответ сервера не получен. Операция могла выполниться.', true);
    }

    let data;

    try {
        data = await response.json();
    } catch {
        throw new ProfileRequestError('Сервер вернул неожиданный ответ. Результат операции нужно проверить.', true);
    }

    if (!response.ok) {
        const fallback = response.status === 401
            ? 'Сессия истекла либо проверка учётных данных не пройдена.'
            : `Не удалось выполнить операцию (${response.status}).`;

        throw new ProfileRequestError(responseMessage(data, fallback), response.status >= 500);
    }

    if (!data || typeof data !== 'object' || Array.isArray(data)) throw unexpectedProfileResponse();
    return data;
}

export async function runProfileAction(scope, box, action) {
    if (scope.dataset.busy === 'true' || scope.dataset.blocked === 'true') return false;

    scope.dataset.busy = 'true';
    scope.setAttribute('aria-busy', 'true');

    const controls = scope.matches('button') ? [scope] : [...scope.querySelectorAll('button, input, select, textarea')];
    const previousStates = controls.map((control) => [control, control.disabled]);

    for (const [control] of previousStates) control.disabled = true;

    try {
        await action();
        return true;
    } catch (error) {
        const uncertain = !(error instanceof ProfileRequestError) || error.uncertain;
        const message = error instanceof ProfileRequestError ? error.message : 'Не удалось завершить обработку операции.';

        if (uncertain) scope.dataset.blocked = 'true';

        const suffix = uncertain ? ' Повтор заблокирован до перезагрузки: сначала обновите страницу и сверьте состояние.' : '';
        showProfileStatus(box, message + suffix);
        return false;
    } finally {
        delete scope.dataset.busy;
        scope.removeAttribute('aria-busy');

        if (scope.dataset.blocked !== 'true') {
            for (const [control, disabled] of previousStates) control.disabled = disabled;
        }
    }
}