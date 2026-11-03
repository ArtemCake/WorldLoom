// frontend/src/js/shared/http/network-error-handler.js

import { showNotice } from '../ui/notifications.js';

let handlersBound = false;

function requestPath(detail) {
    const path = detail?.requestConfig?.path;
    if (typeof path !== 'string') return null;

    try {
        const url = new URL(path, window.location.origin);
        return url.origin === window.location.origin ? url.pathname : null;
    } catch {
        return null;
    }
}

function isSharedRequest(detail) {
    const path = requestPath(detail);
    return path !== null && path !== '/auth' && !path.startsWith('/auth/');
}

function errorMessage(xhr) {
    const fallback = `Не удалось выполнить запрос (${xhr.status}).`;

    try {
        const data = JSON.parse(xhr.responseText);
        if (typeof data?.detail === 'string') return data.detail;
        if (typeof data?.error === 'string') return data.error;

        if (Array.isArray(data?.detail)) {
            const messages = data.detail.map((item) => typeof item?.msg === 'string' ? item.msg : '').filter(Boolean);
            if (messages.length) return messages.join(' ');
        }
    } catch {
        return fallback;
    }

    return fallback;
}

export function initNetworkErrorHandlers() {
    if (handlersBound) return;
    handlersBound = true;

    document.addEventListener('htmx:beforeOnLoad', (event) => {
        if (!isSharedRequest(event.detail)) return;

        const token = event.detail.xhr.getResponseHeader('X-CSRF-Token');
        if (token) document.querySelector('meta[name="csrf-token"]')?.setAttribute('content', token);
    });

    document.addEventListener('htmx:responseError', (event) => {
        if (!isSharedRequest(event.detail)) return;
        showNotice(errorMessage(event.detail.xhr), 'error');
    });

    for (const name of ['htmx:sendError', 'htmx:timeout']) {
        document.addEventListener(name, (event) => {
            if (!isSharedRequest(event.detail)) return;
            showNotice('Ответ сервера не получен. Результат операции неизвестен; автоматического повтора нет.', 'error');
        });
    }
}