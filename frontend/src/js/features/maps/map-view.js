// frontend/src/js/features/maps/map-view.js

import { initMapSandbox } from './map-sandbox.js';

const initializedRoots = new WeakSet();

function initView(root) {
    if (initializedRoots.has(root)) return;

    const message = root.querySelector('[data-map-view-message]');
    const image = root.querySelector('[data-map-view-background]');
    const sandbox = root.querySelector('[data-map-sandbox]');

    if (!message || !image || !sandbox) return;

    initializedRoots.add(root);

    const listeners = new AbortController();
    const options = { signal: listeners.signal };
    const disposeSandbox = initMapSandbox(sandbox, image);
    let disposed = false;

    root.addEventListener('htmx:beforeCleanupElement', (event) => {
        if (event.detail?.elt !== root || disposed) return;

        disposed = true;
        listeners.abort();
        disposeSandbox();
        image.removeAttribute('src');
        initializedRoots.delete(root);
    }, options);

    const backgroundUrl = root.dataset.backgroundUrl?.trim();

    if (!backgroundUrl) {
        message.textContent = 'Фоновое изображение не задано. Сетка доступна на пустом фоне.';
        return;
    }

    let url;

    try {
        url = new URL(backgroundUrl, window.location.origin);

        if (!['http:', 'https:'].includes(url.protocol) || url.origin !== window.location.origin || url.username || url.password) {
            throw new Error('Недопустимый адрес изображения.');
        }
    } catch {
        message.textContent = 'Не удалось определить адрес фона. Проверьте карту через страницу редактирования.';
        return;
    }

    image.addEventListener('load', () => {
        if (disposed || !root.isConnected) return;

        message.textContent = 'Фоновое изображение загружено.';
    }, options);

    image.addEventListener('error', () => {
        if (disposed || !root.isConnected) return;

        message.textContent = 'Не удалось загрузить фон. Проверьте изображение через редактирование карты; удаление карты не требуется.';
    }, options);

    message.textContent = 'Загрузка фонового изображения…';
    image.src = url.href;
}

export function initMapView() {
    document.querySelectorAll('[data-map-view]').forEach(initView);
}
