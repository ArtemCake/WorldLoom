// frontend/src/js/features/legal/cookie-banner.js

const STORAGE_KEY = 'cookie-notice-dismissed';
const boundButtons = new WeakSet();

function hideBanner(banner) {
    banner.hidden = true;
    banner.classList.add('hidden');
}

export function initCookieBanner() {
    const banner = document.getElementById('cookie-banner');
    const button = document.getElementById('cookie-banner-accept');
    if (!banner || !button) return;

    let dismissed = false;
    try {
        dismissed = localStorage.getItem(STORAGE_KEY) === '1';
    } catch {
        // Без хранилища уведомление можно закрыть до следующей загрузки.
    }

    banner.hidden = dismissed;
    banner.classList.toggle('hidden', dismissed);

    if (boundButtons.has(button)) return;
    boundButtons.add(button);

    button.addEventListener('click', () => {
        try {
            localStorage.setItem(STORAGE_KEY, '1');
        } catch {
            // Скрытие текущего уведомления не требует постоянного хранилища.
        }

        hideBanner(banner);
    });
}