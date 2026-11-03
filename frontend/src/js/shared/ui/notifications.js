// frontend/src/js/shared/ui/notifications.js

const NOTICE_TYPES = new Set(['success', 'error', 'warning', 'info']);

export function showNotice(message, type = 'info') {
    if (!document.body || typeof message !== 'string' || !message) return;

    let wrapper = document.getElementById('global-notifications');

    if (!wrapper) {
        wrapper = document.createElement('div');
        wrapper.id = 'global-notifications';
        wrapper.className = 'toast-wrapper';
        wrapper.setAttribute('aria-label', 'Уведомления');
        document.body.appendChild(wrapper);
    }

    const notice = document.createElement('div');
    const noticeType = NOTICE_TYPES.has(type) ? type : 'info';
    notice.className = `toast toast-${noticeType}`;
    notice.setAttribute('role', noticeType === 'error' ? 'alert' : 'status');

    const text = document.createElement('span');
    text.textContent = message;

    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'toast-close';
    close.textContent = '×';
    close.setAttribute('aria-label', 'Закрыть уведомление');
    close.addEventListener('click', () => notice.remove(), { once: true });

    notice.append(text, close);
    wrapper.appendChild(notice);
}