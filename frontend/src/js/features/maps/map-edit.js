// frontend/src/js/features/maps/map-edit.js

import { MapRequestError, requestMapJson } from './map-http.js';

const initializedForms = new WeakSet();
const REJECTED_STATUSES = new Set([400, 401, 403, 404, 409, 413, 415, 422]);

function initEditPreview(form, input, image, message, options) {
    let objectUrl = null;
    let pendingImage = null;
    let sequence = 0;
    let disposed = false;

    function clearPreview() {
        sequence += 1;
        image.hidden = true;
        image.removeAttribute('src');

        if (pendingImage) {
            pendingImage.removeAttribute('src');
            pendingImage = null;
        }

        if (objectUrl) {
            URL.revokeObjectURL(objectUrl);
            objectUrl = null;
        }
    }

    async function refreshPreview() {
        clearPreview();

        const requestId = sequence;
        const file = input?.files?.[0];
        let source = '';

        input?.setCustomValidity('');

        if (file) {
            const allowedTypes = ['image/png', 'image/jpeg', 'image/webp'];
            const maxBytes = Number(input.dataset.maxBytes);

            if (file.type && !allowedTypes.includes(file.type)) {
                input.setCustomValidity('Выберите PNG, JPEG или WebP.');
            } else if (!file.size) {
                input.setCustomValidity('Выбран пустой файл.');
            } else if (maxBytes > 0 && file.size > maxBytes) {
                input.setCustomValidity('Изображение превышает допустимый размер.');
            }

            if (!input.checkValidity()) {
                message.textContent = input.validationMessage;
                input.reportValidity();
                return;
            }
        } else {
            const backgroundUrl = form.dataset.backgroundUrl?.trim();

            if (!backgroundUrl) {
                message.textContent = 'У карты пока нет фонового изображения.';
                return;
            }

            try {
                const url = new URL(backgroundUrl, window.location.origin);

                if (!['http:', 'https:'].includes(url.protocol) || url.origin !== window.location.origin
                    || url.username || url.password) {
                    throw new Error('Недопустимый адрес фона.');
                }

                source = url.href;
            } catch {
                message.textContent = 'Текущий фон нельзя показать. Можно сохранить остальные поля или выбрать новый файл.';
                return;
            }
        }

        message.textContent = file ? 'Подготовка нового фона…' : 'Загрузка текущего фона…';

        try {
            if (file) {
                input.setCustomValidity('Дождитесь загрузки предпросмотра изображения.');
                objectUrl = URL.createObjectURL(file);
                source = objectUrl;
            }

            const candidate = new Image();
            pendingImage = candidate;
            candidate.src = source;
            await candidate.decode();

            if (disposed || !form.isConnected || requestId !== sequence) return;

            pendingImage = null;
            image.src = source;
            image.hidden = false;
            input?.setCustomValidity('');

            message.textContent = file
                ? 'Предпросмотр нового фона. Изменения ещё не сохранены.'
                : 'Текущий фон карты.';
        } catch {
            if (disposed || !form.isConnected || requestId !== sequence) return;

            clearPreview();

            if (file) {
                input.setCustomValidity('Браузер не смог прочитать изображение. Выберите другой файл.');
                message.textContent = input.validationMessage;
                input.reportValidity();
            } else {
                message.textContent = 'Не удалось загрузить текущий фон. Можно сохранить остальные поля или выбрать новый файл.';
            }
        }
    }

    input?.addEventListener('change', () => void refreshPreview(), options);
    void refreshPreview();

    return function disposePreview() {
        disposed = true;
        clearPreview();
    };
}

function initEditForm(form) {
    if (initializedForms.has(form)) return;

    const fieldset = form.querySelector('[data-map-edit-fields]');
    const button = form.querySelector('button[type="submit"]');
    const message = form.querySelector('[data-map-edit-message]');
    const titleInput = form.querySelector('[name="title"]');
    const fogInput = form.querySelector('[name="fog_of_war_enabled"]');
    const fileInput = form.querySelector('[name="background_image"]');
    const image = form.querySelector('[data-map-edit-preview]');
    const previewMessage = form.querySelector('[data-map-edit-preview-message]');
    const mapId = form.dataset.mapId;
    const gameId = form.dataset.gameId;

    if (!fieldset || !button || !message || !titleInput || !fogInput || !image || !previewMessage || !mapId || !gameId) return;

    initializedForms.add(form);

    const listeners = new AbortController();
    const options = { signal: listeners.signal };
    const disposePreview = initEditPreview(form, fileInput, image, previewMessage, options);
    let busy = false;
    let locked = false;
    let disposed = false;

    function showMessage(text, isError = false) {
        message.textContent = text;
        message.classList.toggle('alert-error', isError);
    }

    form.addEventListener('submit', async (event) => {
        event.preventDefault();

        if (busy || locked || disposed || !form.isConnected) return;

        titleInput.value = titleInput.value.trim();

        if (!form.reportValidity()) return;

        if (!document.querySelector('meta[name="csrf-token"]')?.content) {
            showMessage('Не найден защитный токен. Перезагрузите страницу.', true);
            return;
        }

        let returnUrl;

        try {
            returnUrl = new URL(form.dataset.returnUrl, window.location.origin);

            if (returnUrl.origin !== window.location.origin || returnUrl.username || returnUrl.password) {
                throw new Error('Недопустимый адрес возврата.');
            }
        } catch {
            showMessage('Не удалось определить адрес каталога. Перезагрузите страницу.', true);
            return;
        }

        const title = titleInput.value;
        const fogEnabled = fogInput.checked;
        const body = new FormData(form);

        body.set('title', title);
        body.set('fog_of_war_enabled', fogEnabled ? 'true' : 'false');

        if (!fileInput?.files?.length) {
            body.delete('background_image');
        }

        busy = true;
        fieldset.disabled = true;
        form.setAttribute('aria-busy', 'true');
        button.textContent = 'Сохранение…';
        showMessage('Сохранение изменений карты…');

        try {
            const data = await requestMapJson(form.action, { method: 'PATCH', body });

            if (disposed || !form.isConnected) return;

            if (!data || data.id !== mapId || data.game_id !== gameId || data.title !== title
                || data.fog_of_war_enabled !== fogEnabled) {
                throw new Error('Сервер не подтвердил ожидаемые данные карты.');
            }

            locked = true;
            button.textContent = 'Изменения сохранены';
            showMessage('Изменения сохранены. Открывается каталог.');
            window.location.assign(returnUrl.href);
        } catch (error) {
            if (disposed || !form.isConnected) return;

            const rejected = error instanceof MapRequestError && REJECTED_STATUSES.has(error.status);
            const text = error instanceof Error ? error.message : 'Не удалось получить результат сохранения.';

            locked = !rejected;

            showMessage(
                locked
                    ? `${text} Повторная отправка отключена: изменения могли сохраниться. Откройте форму заново и проверьте данные.`
                    : text,
                true
            );

            if (locked) button.textContent = 'Проверьте сохранённые данные';
        } finally {
            busy = false;
            form.setAttribute('aria-busy', 'false');

            if (!locked) {
                fieldset.disabled = false;
                button.textContent = 'Сохранить изменения';
            }
        }
    }, options);

    form.addEventListener('htmx:beforeCleanupElement', (event) => {
        if (event.detail?.elt !== form || disposed) return;

        disposed = true;
        listeners.abort();
        disposePreview();
        initializedForms.delete(form);
    }, options);
}

export function initMapEdit() {
    document.querySelectorAll('[data-map-edit-form]').forEach(initEditForm);
}
