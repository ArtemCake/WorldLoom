// frontend/src/js/features/admin/admin.js

import { sessionClient } from '../../shared/http/session-client.js';

const initializedRoots = new WeakSet();
const REPORT_STATUSES = { resolve: 'resolved', dismiss: 'dismissed' };

class AdminRequestError extends Error {
    constructor(message, uncertain = false) {
        super(message);
        this.name = 'AdminRequestError';
        this.uncertain = uncertain;
    }
}

function showMessage(box, message, success = false) {
    if (!box) return;

    const alert = document.createElement('div');
    alert.className = success ? 'alert alert-success' : 'alert alert-danger';
    alert.setAttribute('role', success ? 'status' : 'alert');
    alert.textContent = message;
    box.replaceChildren(alert);
}

function errorMessage(data, status) {
    if (typeof data?.detail === 'string') return data.detail;
    if (typeof data?.error === 'string') return data.error;

    if (Array.isArray(data?.detail)) {
        const messages = data.detail.map((item) => typeof item?.msg === 'string' ? item.msg : '').filter(Boolean);
        if (messages.length) return messages.join(' ');
    }

    return `Сервер отклонил запрос (${status}).`;
}

async function requestAdmin(path, method, body) {
    if (!document.querySelector('meta[name="csrf-token"]')?.content) {
        throw new AdminRequestError('Защитный токен отсутствует. Обновите страницу.');
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
        throw new AdminRequestError('Ответ сервера не получен. Операция могла выполниться.', true);
    }

    let data;

    try {
        data = await response.json();
    } catch {
        throw new AdminRequestError('Сервер вернул неожиданный ответ. Результат операции не подтверждён.', true);
    }

    if (!response.ok) {
        throw new AdminRequestError(errorMessage(data, response.status), response.status >= 500);
    }

    if (!data || typeof data !== 'object' || Array.isArray(data) || typeof data.message !== 'string' || !data.message) {
        throw new AdminRequestError('Ответ сервера не подтверждает результат операции.', true);
    }

    return data;
}

function setVisible(element, visible) {
    element.hidden = !visible;
    element.classList.toggle('hidden', !visible);
}

export function initAdminPanel() {
    const root = document.querySelector('[data-admin-root]');
    if (!root || initializedRoots.has(root)) return;
    initializedRoots.add(root);

    const modal = root.querySelector('#admin-manage-modal');
    const modalMessage = root.querySelector('#message-box-admin');
    const pageMessage = root.querySelector('#message-box-admin-page');
    const nickname = root.querySelector('#admin-manage-nickname');

    let selectedUser = null;
    let opener = null;
    let previousOverflow = '';
    let busy = false;
    let locked = false;

    function lockMutations() {
        for (const control of root.querySelectorAll('[data-admin-mutation], [data-admin-edit]')) {
            control.disabled = true;
        }
    }

    async function runAction(box, operation) {
        if (busy || locked) return;
        busy = true;
        root.setAttribute('aria-busy', 'true');

        const states = [...root.querySelectorAll('button, input, select, textarea')].map((control) => [control, control.disabled]);
        for (const [control] of states) control.disabled = true;

        try {
            const data = await operation();
            locked = true;
            showMessage(box, `${data.message} Обновите данные страницы перед следующим изменением.`, true);
        } catch (error) {
            const uncertain = !(error instanceof AdminRequestError) || error.uncertain;
            const message = error instanceof AdminRequestError ? error.message : 'Не удалось обработать результат операции.';

            if (uncertain) locked = true;

            const suffix = uncertain ? ' Изменения заблокированы: обновите страницу и сначала сверьте состояние.' : '';
            showMessage(box, message + suffix);
        } finally {
            busy = false;
            root.removeAttribute('aria-busy');

            for (const [control, disabled] of states) control.disabled = disabled;
            if (locked) lockMutations();

            if (modal && !modal.hidden && !modal.contains(document.activeElement)) {
                modal.querySelector('button:not(:disabled)')?.focus();
            }
        }
    }

    function openModal(trigger) {
        if (!modal || !nickname || busy || locked || !trigger.dataset.userId) return;

        selectedUser = trigger.dataset.userId;
        opener = trigger;
        previousOverflow = document.body.style.overflow;
        nickname.textContent = trigger.dataset.userNickname || '';

        const roles = new Set((trigger.dataset.userRoles || '').split(',').filter(Boolean));
        const permissions = new Set((trigger.dataset.userPermissions || '').split(',').filter(Boolean));

        for (const checkbox of modal.querySelectorAll('[data-role-checkbox]')) {
            checkbox.checked = roles.has(checkbox.value);
        }

        for (const checkbox of modal.querySelectorAll('[data-permission-checkbox]')) {
            checkbox.checked = permissions.has(checkbox.value);
        }

        modalMessage?.replaceChildren();
        setVisible(modal, true);
        document.body.style.overflow = 'hidden';
        modal.querySelector('input:not(:disabled), button:not(:disabled)')?.focus();
    }

    function closeModal() {
        if (!modal || modal.hidden || busy) return;

        setVisible(modal, false);
        selectedUser = null;
        document.body.style.overflow = previousOverflow;

        if (locked) {
            showMessage(pageMessage, 'Обновите данные страницы и сверьте состояние перед следующим изменением.');
            root.querySelector('a[href]')?.focus();
        } else if (opener?.isConnected) {
            opener.focus();
        }
    }

    function saveSelection(kind) {
        if (!selectedUser || !modal) return;

        const body = new URLSearchParams();
        const selector = kind === 'roles' ? '[data-role-checkbox]:checked' : '[data-permission-checkbox]:checked';

        for (const checkbox of modal.querySelectorAll(selector)) {
            body.append(kind, checkbox.value);
        }

        const path = `/admin/users/${encodeURIComponent(selectedUser)}/${kind}`;
        void runAction(modalMessage, () => requestAdmin(path, 'PATCH', body));
    }

    function deleteUser(permanent) {
        if (!selectedUser) return;

        const question = permanent ? 'Удалить пользователя навсегда? Это нельзя отменить.' : 'Деактивировать пользователя?';
        if (!window.confirm(question)) return;

        const body = new URLSearchParams({ permanent: String(permanent) });
        const path = `/admin/users/${encodeURIComponent(selectedUser)}/delete`;

        void runAction(modalMessage, () => requestAdmin(path, 'POST', body));
    }

    function updateReport(trigger) {
        const status = REPORT_STATUSES[trigger.dataset.reportAction];
        const reportId = trigger.dataset.reportId;
        if (!status || !reportId) return;

        const body = new URLSearchParams({ new_status: status });
        const path = `/admin/reports/${encodeURIComponent(reportId)}`;

        void runAction(pageMessage, async () => {
            const data = await requestAdmin(path, 'PATCH', body);

            if (data.status !== status) {
                throw new AdminRequestError('Ответ сервера не подтверждает выбранный статус жалобы.', true);
            }

            return data;
        });
    }

    root.addEventListener('click', (event) => {
        if (!(event.target instanceof Element)) return;

        const trigger = event.target.closest('[data-admin-action], [data-report-action]');
        if (!trigger || !root.contains(trigger)) return;
        event.preventDefault();

        if (busy) return;

        const action = trigger.dataset.adminAction;
        if (action === 'close') {
            closeModal();
            return;
        }

        if (locked) return;

        if (action === 'manage') openModal(trigger);
        else if (action === 'save-roles') saveSelection('roles');
        else if (action === 'save-permissions') saveSelection('permissions');
        else if (action === 'deactivate') deleteUser(false);
        else if (action === 'delete-permanent') deleteUser(true);
        else if (trigger.hasAttribute('data-report-action')) updateReport(trigger);
    });

    root.addEventListener('keydown', (event) => {
        if (!modal || modal.hidden) return;

        if (event.key === 'Escape') {
            event.preventDefault();
            closeModal();
            return;
        }

        if (event.key !== 'Tab') return;

        const controls = [...modal.querySelectorAll('button:not(:disabled), input:not(:disabled), a[href], [tabindex="0"]')];
        const first = controls[0];
        const last = controls.at(-1);
        const outside = !controls.includes(document.activeElement);

        if (!first) {
            event.preventDefault();
            modal.focus();
        } else if (event.shiftKey && (document.activeElement === first || outside)) {
            event.preventDefault();
            last.focus();
        } else if (!event.shiftKey && (document.activeElement === last || outside)) {
            event.preventDefault();
            first.focus();
        }
    });
}