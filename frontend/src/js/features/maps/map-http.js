// frontend/src/js/features/maps/map-http.js

import { sessionClient } from '../../shared/http/session-client.js';

export class MapRequestError extends Error {
    constructor(message, status = 0) {
        super(message);
        this.name = 'MapRequestError';
        this.status = status;
    }
}

function errorMessage(data, status) {
    if (typeof data?.detail === 'string' && data.detail.trim()) {
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
            return 'Карта или задание очистки не найдены.';
        case 409:
            return 'Состояние карты изменилось. Проверьте актуальные данные.';
        case 413:
            return 'Загружаемое изображение превышает допустимый размер.';
        case 422:
            return 'Проверьте переданные значения.';
        default:
            return `Не удалось выполнить запрос (${status}).`;
    }
}

export async function requestMapJson(path, { method = 'GET', body, signal } = {}) {
    const requestMethod = method.toUpperCase();
    const headers = new Headers({ Accept: 'application/json' });
    const isForm = body instanceof FormData;

    if (body !== undefined && !isForm) {
        headers.set('Content-Type', 'application/json');
    }

    let response;

    try {
        response = await sessionClient.sessionFetch(path, {
            method: requestMethod,
            headers,
            signal,
            body: body === undefined || isForm ? body : JSON.stringify(body),
            retryAfterRefresh: requestMethod === 'GET' || requestMethod === 'HEAD'
        });
    } catch (error) {
        if (signal?.aborted) throw error;
        throw new MapRequestError('Ответ не получен. Проверьте состояние карты перед повторной отправкой.');
    }

    const contentType = response.headers.get('Content-Type') || '';
    const isJson = /\bapplication\/(?:[\w.-]+\+)?json\b/i.test(contentType);
    let data = null;

    if (isJson) {
        try {
            data = await response.json();
        } catch {
            throw new MapRequestError('Сервер вернул некорректный JSON. Результат операции не подтверждён.', response.status);
        }
    }

    if (!response.ok) {
        throw new MapRequestError(errorMessage(data, response.status), response.status);
    }

    if (!isJson) {
        throw new MapRequestError('Получен неожиданный ответ сервера. Результат операции не подтверждён.', response.status);
    }

    return data;
}
