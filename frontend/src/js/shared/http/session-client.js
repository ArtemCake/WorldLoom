// frontend/src/js/shared/http/session-client.js

const READ_METHODS = new Set(['GET', 'HEAD']);

export class SessionRefreshError extends Error {
    constructor(status, message = null) {
        super(message || (status === 401 ? 'Сессия завершена. Выполните вход снова.' : `Не удалось обновить сессию (${status}).`));
        this.name = 'SessionRefreshError';
        this.status = status;
    }
}

function responseHeader(response, name) {
    return response.headers?.get?.(name) || response.getResponseHeader?.(name) || null;
}

export function isAuthenticationFailure(response) {
    return response.status === 401 && /^Bearer(?:\s|$)/i.test(responseHeader(response, 'WWW-Authenticate') || '');
}

function defaultGetCsrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.content || '';
}

function defaultSetCsrfToken(token) {
    document.querySelector('meta[name="csrf-token"]')?.setAttribute('content', token);
}

export function createSessionClient({ fetchImpl = (...args) => fetch(...args), origin = globalThis.location?.origin || 'http://localhost',
    getCsrfToken = defaultGetCsrfToken, setCsrfToken = defaultSetCsrfToken } = {}) {
    const siteOrigin = new URL(origin).origin;
    let generation = 0;
    let refreshInFlight = null;

    function localUrl(path) {
        const url = new URL(path, siteOrigin);

        if (url.origin !== siteOrigin || !['http:', 'https:'].includes(url.protocol) || url.username || url.password) {
            throw new TypeError('Клиент сессии разрешает только запросы к своему сайту.');
        }

        return url;
    }

    function retryAllowed(path, options) {
        const method = String(options.method || 'GET').toUpperCase();
        const pathname = localUrl(path).pathname;

        if (pathname === '/auth' || pathname.startsWith('/auth/')) return false;
        return options.retryAfterRefresh ?? READ_METHODS.has(method);
    }

    function prepareOptions(options) {
        const { retryAfterRefresh, ...requestOptions } = options;
        const method = String(requestOptions.method || 'GET').toUpperCase();
        const headers = new Headers(requestOptions.headers);

        headers.delete('Authorization');

        if (!READ_METHODS.has(method)) {
            const token = getCsrfToken();
            if (!token) throw new Error('Не найден защитный токен страницы. Обновите страницу.');

            headers.set('X-CSRF-Token', token);
        }

        return { ...requestOptions, method, headers, credentials: 'same-origin', redirect: 'error', cache: 'no-store' };
    }

    async function send(path, options = {}) {
        const response = await fetchImpl(localUrl(path).href, prepareOptions(options));
        const token = responseHeader(response, 'X-CSRF-Token');

        if (token) setCsrfToken(token);
        return response;
    }

    async function refreshSession(expectedGeneration = generation) {
        if (expectedGeneration !== generation) return;

        if (!refreshInFlight) {
            refreshInFlight = (async () => {
                let response;

                try {
                    response = await send('/auth/refresh', { method: 'POST' });
                } catch {
                    throw new SessionRefreshError(0, 'Ответ на обновление сессии не получен. Автоматического повтора нет.');
                }

                if (!response.ok) throw new SessionRefreshError(response.status);

                const contentType = response.headers.get('Content-Type') || '';
                if (!contentType.includes('application/json')) {
                    throw new SessionRefreshError(response.status, 'Сервер вернул неожиданный ответ при обновлении сессии.');
                }

                // Токены из тела не извлекаем: HttpOnly-cookie принимает браузер.
                generation += 1;
            })();
        }

        const pending = refreshInFlight;

        try {
            await pending;
        } finally {
            if (refreshInFlight === pending) refreshInFlight = null;
        }
    }

    async function recover(response, path, options = {}, expectedGeneration = generation) {
        if (!isAuthenticationFailure(response) || !retryAllowed(path, options)) return response;

        if (typeof ReadableStream !== 'undefined' && options.body instanceof ReadableStream) {
            throw new TypeError('Потоковое тело запроса нельзя автоматически отправить повторно.');
        }

        if (options.signal?.aborted) throw options.signal.reason;

        await refreshSession(expectedGeneration);

        if (options.signal?.aborted) throw options.signal.reason;

        // Повторный ответ возвращаем вызывающему коду без нового refresh.
        return send(path, options);
    }

    async function sessionFetch(path, options = {}) {
        if (retryAllowed(path, options) && typeof ReadableStream !== 'undefined' && options.body instanceof ReadableStream) {
            throw new TypeError('Для потокового тела отключите повтор после обновления сессии.');
        }

        const expectedGeneration = generation;
        const response = await send(path, options);
        return recover(response, path, options, expectedGeneration);
    }

    return { sessionFetch, recover, refreshSession, getGeneration: () => generation };
}

export const sessionClient = createSessionClient();