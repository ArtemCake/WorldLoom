// frontend/src/js/features/games/game-http.js

import { sessionClient } from '../../shared/http/session-client.js';

export class GameRequestError extends Error {
    constructor(message, status = 0) {
        super(message);
        this.name = 'GameRequestError';
        this.status = status;
    }
}

function errorMessage(data, status) {
    if (typeof data?.detail === 'string' && data.detail) {
        return data.detail;
    }

    if (Array.isArray(data?.detail)) {
        const messages = data.detail
            .map((item) => typeof item?.msg === 'string' ? item.msg : '')
            .filter(Boolean);

        if (messages.length) return messages.join('; ');
    }

    switch (status) {
        case 401:
            return 'Сессия завершена. Выполните вход снова.';
        case 403:
            return 'Недостаточно прав или защитный токен устарел. Обновите страницу.';
        case 404:
            return 'Игра или сохранённое задание удаления не найдены.';
        case 409:
            return 'Операция конфликтует с текущим состоянием игры. Обновите данные.';
        case 422:
            return 'Проверьте значения полей.';
        default:
            return `Не удалось выполнить запрос (${status}).`;
    }
}

export async function requestGameJson(path, { method = 'GET', body } = {}) {
    const requestMethod = method.toUpperCase();
    const headers = new Headers({ Accept: 'application/json' });

    if (body !== undefined) {
        headers.set('Content-Type', 'application/json');
    }

    let response;

    try {
        response = await sessionClient.sessionFetch(path, {
            method: requestMethod,
            headers,
            body: body === undefined ? undefined : JSON.stringify(body),
            retryAfterRefresh: requestMethod === 'GET' || requestMethod === 'HEAD'
        });
    } catch {
        throw new GameRequestError(
            'Не удалось получить ответ. Проверьте соединение и состояние игры перед повторной отправкой.'
        );
    }

    if (response.status === 204 && response.ok) return null;

    const contentType = response.headers.get('Content-Type') || '';
    const isJson = /\bapplication\/(?:[\w.-]+\+)?json\b/i.test(contentType);
    let data = null;

    if (isJson) {
        try {
            data = await response.json();
        } catch {
            throw new GameRequestError(
                'Сервер вернул некорректный JSON. Результат операции не подтверждён.',
                response.status
            );
        }
    }

    if (!response.ok) {
        throw new GameRequestError(errorMessage(data, response.status), response.status);
    }

    if (!isJson) {
        throw new GameRequestError(
            'Вместо данных сервер вернул неожиданный ответ. Результат операции не подтверждён.',
            response.status
        );
    }

    return data;
}