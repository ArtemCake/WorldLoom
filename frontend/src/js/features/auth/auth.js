// frontend/src/js/features/auth/auth.js

const AUTH_PATHS = new Set([
    '/auth/register',
    '/auth/login',
    '/auth/login/verify-mfa',
    '/auth/logout',
    '/auth/forgot-password',
    '/auth/reset-password'
]);

let handlersBound = false;

function localUrl(value) {
    try {
        const url = new URL(value, window.location.origin);
        return url.origin === window.location.origin ? url : null;
    } catch {
        return null;
    }
}

function authRequestPath(detail) {
    const config = detail?.requestConfig;
    if (!config || String(config.verb).toLowerCase() !== 'post') return null;

    const url = localUrl(config.path);
    return url && AUTH_PATHS.has(url.pathname) ? url.pathname : null;
}

function setVisible(element, visible) {
    if (!element) return;
    element.hidden = !visible;
    element.classList.toggle('hidden', !visible);
}

export function clearLegacyTokens() {
    try {
        localStorage.removeItem('accessToken');
        localStorage.removeItem('refreshToken');
    } catch {
        // Cookie-сессия не зависит от доступности localStorage.
    }
}

function responseMessage(data, fallback) {
    if (typeof data?.error === 'string') return data.error;
    if (typeof data?.detail === 'string') return data.detail;
    if (typeof data?.message === 'string') return data.message;

    if (Array.isArray(data?.detail)) {
        return data.detail.map((item) => typeof item?.msg === 'string' ? item.msg : '').filter(Boolean).join(' ') || fallback;
    }

    return fallback;
}

export function showMessage(formEl, type, text, targetSelector = null) {
    let box = null;

    if (targetSelector) {
        try {
            box = document.querySelector(targetSelector);
        } catch {
            box = null;
        }
    }

    box ??= formEl?.closest('.auth-container')?.querySelector('#message-box');
    box ??= document.getElementById('message-box');
    if (!box) return;

    const alert = document.createElement('div');
    alert.className = type === 'success' ? 'alert alert-success' : 'alert alert-danger';
    alert.setAttribute('role', 'alert');
    alert.textContent = typeof text === 'string' ? text : 'Не удалось обработать ответ сервера.';
    box.replaceChildren(alert);
}

export function scrollToMessageBox(targetSelector = null) {
    let box = document.getElementById('message-box');

    if (targetSelector) {
        try {
            box = document.querySelector(targetSelector);
        } catch {
            return;
        }
    }

    box?.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function updateCsrfToken(xhr) {
    const token = xhr.getResponseHeader('X-CSRF-Token');
    if (token) document.querySelector('meta[name="csrf-token"]')?.setAttribute('content', token);
}

function redirectLocally(value) {
    const url = typeof value === 'string' ? localUrl(value) : null;
    if (!url) return false;

    window.location.assign(url.pathname + url.search + url.hash);
    return true;
}

function handleAuthResponse(event) {
    const path = authRequestPath(event.detail);
    if (!path) return;

    event.preventDefault();

    const xhr = event.detail.xhr;
    const form = event.detail.requestConfig.elt;
    updateCsrfToken(xhr);

    let data;
    try {
        data = JSON.parse(xhr.responseText);
    } catch {
        showMessage(form, 'danger', 'Сервер вернул неожиданный ответ. Обновите страницу перед повторной попыткой.');
        return;
    }

    if (xhr.status < 200 || xhr.status >= 300) {
        showMessage(form, 'danger', responseMessage(data, `Не удалось выполнить запрос (${xhr.status}).`));
        setVisible(document.getElementById('register-prompt'), data?.action === 'account_not_found');
        scrollToMessageBox();
        return;
    }

    if (path === '/auth/logout') {
        clearLegacyTokens();
        redirectLocally('/login');
        return;
    }

    if (path === '/auth/register') {
        form?.reset();
        showMessage(form, 'success', responseMessage(data, 'Аккаунт создан. Проверьте почту.'));
        renderResendVerification(document.getElementById('resend-section'), data?.resend_url);
        scrollToMessageBox();
        return;
    }

    if (path === '/auth/login' || path === '/auth/login/verify-mfa') {
        if (data?.mfa_required === true && typeof data.mfa_token === 'string' && data.mfa_token) {
            const tokenField = document.getElementById('mfa-token-field');
            const mfaForm = document.getElementById('mfa-code-form');

            if (!tokenField || !mfaForm) {
                showMessage(form, 'danger', 'Не найдена форма второго фактора. Обновите страницу.');
                return;
            }

            const password = document.querySelector('#login-form input[name="password"]');
            if (password) password.value = '';

            tokenField.value = data.mfa_token;
            setVisible(document.getElementById('login-form'), false);
            setVisible(mfaForm, true);
            setVisible(document.getElementById('register-prompt'), false);
            showMessage(mfaForm, 'success', responseMessage(data, 'Введите код второго фактора.'));
            mfaForm.querySelector('input[name="code"]')?.focus();
            return;
        }

        if (typeof data?.access_token !== 'string' || !data.access_token) {
            showMessage(form, 'danger', 'Сервер не подтвердил завершение входа.');
            return;
        }

        clearLegacyTokens();
        const tokenField = document.getElementById('mfa-token-field');
        if (tokenField) tokenField.value = '';

        redirectLocally('/profile');
        return;
    }

    showMessage(form, 'success', responseMessage(data, 'Запрос выполнен.'));
    if (path === '/auth/reset-password') {
        form?.reset();
        if (typeof data?.redirect_url === 'string') redirectLocally(data.redirect_url);
    }
    scrollToMessageBox();
}

export function renderResendVerification(container, resendUrl) {
    if (!container || typeof resendUrl !== 'string') return;

    const url = localUrl(resendUrl);
    if (!url || !/^\/auth\/resend-verification\/[0-9a-f-]{36}$/i.test(url.pathname) || url.search || url.hash) return;

    const text = document.createElement('p');
    text.className = 'resend-section__text';
    text.textContent = 'Письмо не пришло?';

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn btn-outline-primary';
    button.id = 'resend-verification-btn';
    button.textContent = 'Отправить письмо повторно';

    button.addEventListener('click', async () => {
        button.disabled = true;

        try {
            const token = document.querySelector('meta[name="csrf-token"]')?.content;
            if (!token) {
                showMessage(null, 'danger', 'Обновите страницу: защитный токен отсутствует.');
                return;
            }

            const response = await fetch(url.pathname, {
                method: 'POST',
                credentials: 'same-origin',
                redirect: 'error',
                headers: { 'X-CSRF-Token': token, 'Accept': 'application/json' }
            });
            const freshToken = response.headers.get('X-CSRF-Token');
            if (freshToken) document.querySelector('meta[name="csrf-token"]')?.setAttribute('content', freshToken);

            const data = await response.json();
            const fallback = response.ok ? 'Письмо отправлено повторно.' : 'Не удалось отправить письмо.';
            showMessage(null, response.ok ? 'success' : 'danger', responseMessage(data, fallback));
        } catch {
            showMessage(null, 'danger', 'Не удалось получить ответ. Перед повторной отправкой проверьте почту.');
        } finally {
            button.disabled = false;
        }
    });

    container.replaceChildren(text, button);
    setVisible(container, true);
}

export function initAuthPage() {
    const status = new URLSearchParams(window.location.search).get('verify');
    const messages = {
        success: 'Почта подтверждена. Теперь можно войти.',
        invalid: 'Ссылка подтверждения недействительна или устарела.',
        notfound: 'Аккаунт для подтверждения не найден или недоступен.'
    };

    if (window.location.pathname === '/login' && Object.hasOwn(messages, status)) {
        showMessage(null, status === 'success' ? 'success' : 'danger', messages[status]);
    }
}

export function setupAuthHandlers() {
    if (handlersBound) return;
    handlersBound = true;
    clearLegacyTokens();

    document.addEventListener('htmx:configRequest', (event) => {
        const detail = event.detail;
        if (!['post', 'put', 'patch', 'delete'].includes(String(detail.verb).toLowerCase())) return;
        if (!localUrl(detail.path)) return;

        const token = document.querySelector('meta[name="csrf-token"]')?.content;
        if (token) detail.headers['X-CSRF-Token'] = token;
    });

    document.addEventListener('htmx:beforeOnLoad', handleAuthResponse);

    for (const name of ['htmx:sendError', 'htmx:timeout']) {
        document.addEventListener(name, (event) => {
            if (!authRequestPath(event.detail)) return;
            showMessage(event.detail.requestConfig.elt, 'danger', 'Ответ не получен. Результат запроса неизвестен; автоматического повтора нет.');
        });
    }
}