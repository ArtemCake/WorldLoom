// frontend/src/js/features/game-systems/api/game-system-api.js

import { sessionClient, SessionRefreshError } from '../../../shared/http/session-client.js';

const READ_METHODS = new Set(['GET', 'HEAD']);

export class GameSystemRequestError extends Error {
    constructor(message, status = 0, uncertain = false) {
        super(message);
        this.name = 'GameSystemRequestError';
        this.status = status;
        this.uncertain = uncertain;
    }
}

function errorText(data, status) {
    if (status === 401) return 'Сессия завершена. Войдите в аккаунт снова.';
    if (status === 403) return 'Недостаточно прав или запрос не прошёл защитную проверку.';
    if (typeof data?.detail === 'string') return data.detail;

    if (Array.isArray(data?.detail)) {
        const messages = data.detail.map((item) => {
            if (typeof item?.msg !== 'string') return '';

            const path = Array.isArray(item.loc) ? item.loc.filter((part) => part !== 'body').join('.') : '';
            return path ? `${path}: ${item.msg}` : item.msg;
        }).filter(Boolean);

        if (messages.length) return messages.join('; ');
    }

    return `Не удалось выполнить запрос (${status}).`;
}

export async function requestGameSystem(path, method = 'GET', payload, { readOnly = false } = {}) {
    const verb = String(method).toUpperCase();
    const mutation = !READ_METHODS.has(verb) && !readOnly;
    const headers = new Headers({ Accept: 'application/json' });

    if (payload !== undefined) headers.set('Content-Type', 'application/json');

    if (!READ_METHODS.has(verb) && !document.querySelector('meta[name="csrf-token"]')?.content) {
        throw new GameSystemRequestError('Не найден защитный токен страницы. Обновите страницу.', 403);
    }

    let response;

    try {
        response = await sessionClient.sessionFetch(path, {
            method: verb,
            headers,
            body: payload === undefined ? undefined : JSON.stringify(payload),
            retryAfterRefresh: !mutation
        });
    } catch (error) {
        if (error instanceof SessionRefreshError) {
            throw new GameSystemRequestError(error.message, error.status);
        }

        const message = mutation
            ? 'Ответ сервера не получен. Изменение могло сохраниться. Сверьте данные перед повторной попыткой.'
            : 'Не удалось связаться с сервером. Повторите загрузку.';

        throw new GameSystemRequestError(message, 0, mutation);
    }

    let data = null;
    const contentType = response.headers.get('Content-Type') || '';
    const jsonResponse = /(?:application\/json|application\/[^;]+\+json)(?:;|$)/i.test(contentType);

    if (jsonResponse) {
        try {
            data = await response.json();
        } catch {
            if (response.ok) {
                throw new GameSystemRequestError('Не удалось прочитать ответ сервера. Обновите данные перед повтором.', 0, mutation);
            }
        }
    }

    if (!response.ok) {
        throw new GameSystemRequestError(errorText(data, response.status), response.status, mutation && response.status >= 500);
    }

    if (data === null) {
        throw new GameSystemRequestError('Сервер вернул неожиданный формат ответа. Обновите данные перед повтором.', 0, mutation);
    }

    return data;
}