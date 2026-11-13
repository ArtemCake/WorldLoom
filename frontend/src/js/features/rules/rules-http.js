// frontend/src/js/features/rules/rules-http.js

import { sessionClient } from '../../shared/http/session-client.js';

const METHODS = new Set(['GET', 'POST', 'PUT']);
const FILTERS = new Set(['scope', 'limit', 'after', 'q', 'edition_key', 'language']);
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export class RulesRequestError extends Error {
    constructor(message, { status = 0, uncertain = false } = {}) {
        super(message);
        this.name = 'RulesRequestError';
        this.status = status;
        this.uncertain = uncertain;
    }
}

export function ruleId(value) {
    if (typeof value !== 'string' || !UUID_PATTERN.test(value)) {
        throw new TypeError('Не указан корректный идентификатор материала или публикации.');
    }

    return value;
}

export function catalogQuery(filters = {}) {
    if (!filters || typeof filters !== 'object' || Array.isArray(filters)) {
        throw new TypeError('Фильтры каталога должны быть объектом.');
    }

    const query = new URLSearchParams();

    for (const [key, value] of Object.entries(filters)) {
        if (!FILTERS.has(key)) throw new TypeError(`Неизвестный фильтр каталога: ${key}.`);
        if (value === undefined || value === null) continue;

        if (key === 'limit') {
            if (!Number.isSafeInteger(value) || value < 1 || value > 100) {
                throw new TypeError('Размер страницы должен быть целым числом от 1 до 100.');
            }
        } else if (typeof value !== 'string' || !value.trim()) {
            throw new TypeError(`Некорректное значение фильтра: ${key}.`);
        }

        if (key === 'scope' && !['available', 'mine'].includes(value)) {
            throw new TypeError('Неизвестный режим каталога.');
        }

        if (key === 'after') ruleId(value);

        query.set(key, String(value));
    }

    const encoded = query.toString();
    return encoded ? `?${encoded}` : '';
}

function localRulesPath(path) {
    if (typeof path !== 'string' || /[\\#\s]/u.test(path)) {
        throw new TypeError('Некорректный путь API правил.');
    }

    const pathname = path.split('?')[0];

    if (!/^\/rules\/(?:articles|books)(?:\/[a-zA-Z0-9/-]+)?$/u.test(pathname)) {
        throw new TypeError('Запрос должен относиться к API статей или книг.');
    }

    return path;
}

function isObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function statusMessage(status) {
    switch (status) {
        case 401:
            return 'Сессия завершена. Выполните вход снова.';
        case 403:
            return 'Недостаточно прав или защитный токен устарел. Обновите страницу.';
        case 404:
            return 'Материал или публикация не найдены.';
        case 409:
            return 'Данные изменились или операция конфликтует с состоянием материала. Загрузите актуальные данные.';
        case 422:
            return 'Проверьте параметры запроса и содержимое материала.';
        default:
            return 'Не удалось выполнить запрос к правилам.';
    }
}

export function createRulesRequester(client = sessionClient) {
    if (typeof client?.sessionFetch !== 'function') {
        throw new TypeError('Требуется клиент сессии.');
    }

    return async function requestRulesJson(path, { method = 'GET', body, signal } = {}) {
        localRulesPath(path);

        const verb = String(method).toUpperCase();

        if (!METHODS.has(verb)) throw new TypeError('Неподдерживаемый метод API правил.');
        if (verb === 'GET' && body !== undefined) throw new TypeError('Чтение не должно содержать тело запроса.');
        if (body !== undefined && !isObject(body)) throw new TypeError('Тело запроса должно быть объектом.');

        const headers = new Headers({ Accept: 'application/json' });
        const serialized = body === undefined ? undefined : JSON.stringify(body);
        const write = verb !== 'GET';

        if (body !== undefined) headers.set('Content-Type', 'application/json');
        if (signal?.aborted) throw signal.reason;

        let response;

        try {
            const options = { method: verb, headers, body: serialized, signal, retryAfterRefresh: !write };
            response = await client.sessionFetch(path, options);
        } catch (error) {
            if (signal?.aborted && !write) throw signal.reason;

            const message = write
                ? 'Ответ не получен. Операция могла выполниться; проверьте состояние перед повторной отправкой.'
                : error?.message || 'Не удалось получить данные правил.';

            throw new RulesRequestError(message, { uncertain: write });
        }

        const contentType = response.headers.get('Content-Type') || '';
        const json = /\bapplication\/(?:[\w.-]+\+)?json\b/iu.test(contentType);
        let data = null;

        if (json) {
            try {
                data = await response.json();
            } catch {
                const message = 'Ответ сервера не удалось прочитать. Результат операции не подтверждён.';
                throw new RulesRequestError(message, { status: response.status, uncertain: write });
            }
        }

        if (!response.ok) {
            const detail = isObject(data) && typeof data.detail === 'string' ? data.detail : null;
            const message = response.status >= 500 ? statusMessage(response.status) : detail || statusMessage(response.status);
            throw new RulesRequestError(message, { status: response.status, uncertain: write && response.status >= 500 });
        }

        if (!json || !isObject(data)) {
            const message = 'Сервер вернул неожиданный формат данных. Результат операции не подтверждён.';
            throw new RulesRequestError(message, { status: response.status, uncertain: write });
        }

        return data;
    };
}

export const requestRulesJson = createRulesRequester();
