// frontend/src/js/features/maps/maps.js

import { MapRequestError, requestMapJson } from './map-http.js';
import { initMapSandbox } from './map-sandbox.js';

const initializedForms = new WeakSet();
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function initMaps() {
    const form = document.querySelector('[data-map-create-form]');

    if (!form || initializedForms.has(form)) return;

    const fieldset = form.querySelector('[data-map-create-fields]');
    const button = form.querySelector('button[type="submit"]');
    const message = form.querySelector('[data-map-create-message]');
    const input = form.querySelector('[name="background_image"]');
    const image = form.querySelector('[data-map-create-preview]');
    const previewMessage = form.querySelector('[data-map-create-preview-message]');

    if (!fieldset || !button || !message || !input || !image || !previewMessage) return;

    initializedForms.add(form);

    const listeners = new AbortController();
    const options = { signal: listeners.signal };
    let objectUrl = null;
    let busy = false;
    let locked = false;
    let disposed = false;

    function showMessage(text, isError = false) {
        message.textContent = text;
        message.classList.toggle('alert-error', isError);
    }

    function clearPreview() {
        image.hidden = true;
        image.removeAttribute('src');

        if (objectUrl) {
            URL.revokeObjectURL(objectUrl);
            objectUrl = null;
        }
    }

    input.addEventListener('change', () => {
        clearPreview();
        input.setCustomValidity('');
        previewMessage.textContent = '';

        const file = input.files?.[0];

        if (!file) return;

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
            previewMessage.textContent = input.validationMessage;
            input.reportValidity();
            return;
        }

        input.setCustomValidity('Дождитесь загрузки предпросмотра изображения.');
        previewMessage.textContent = 'Подготовка предпросмотра…';
        objectUrl = URL.createObjectURL(file);
        image.src = objectUrl;
    }, options);

    image.addEventListener('load', () => {
        if (!objectUrl || disposed) return;

        input.setCustomValidity('');
        image.hidden = false;
        previewMessage.textContent = 'Выбранный фон. Изображение ещё не загружено на сервер.';
    }, options);

    image.addEventListener('error', () => {
        if (!objectUrl || disposed) return;

        clearPreview();
        input.setCustomValidity('Браузер не смог прочитать изображение. Выберите другой файл.');
        previewMessage.textContent = input.validationMessage;
        input.reportValidity();
    }, options);

    const disposeSandbox = initMapSandbox(form.querySelector('[data-map-sandbox]'), image);

    form.addEventListener('submit', async (event) => {
        event.preventDefault();

        if (busy || locked || disposed || !form.isConnected) return;

        const titleInput = form.elements.namedItem('title');
        titleInput.value = titleInput.value.trim();

        if (!form.reportValidity()) return;

        if (!document.querySelector('meta[name="csrf-token"]')?.content) {
            showMessage('Не найден защитный токен. Перезагрузите страницу.', true);
            return;
        }

        const body = new FormData(form);
        const gameId = String(body.get('game_id') || '');

        if (!UUID_PATTERN.test(gameId)) {
            showMessage('Не выбрана корректная игра. Вернитесь в каталог карт.', true);
            return;
        }

        body.set('title', titleInput.value);
        body.set('show_grid', form.elements.namedItem('show_grid').checked ? 'true' : 'false');
        body.set('fog_of_war_enabled', form.elements.namedItem('fog_of_war_enabled').checked ? 'true' : 'false');

        if (!input.files?.length) {
            body.delete('background_image');
        }

        busy = true;
        fieldset.disabled = true;
        form.setAttribute('aria-busy', 'true');
        button.textContent = 'Создание…';
        showMessage('Отправка данных карты…');

        try {
            const data = await requestMapJson(form.action, { method: 'POST', body });

            if (disposed || !form.isConnected) return;

            if (!data || typeof data.id !== 'string' || !UUID_PATTERN.test(data.id) || data.game_id !== gameId) {
                throw new Error('Получен неожиданный ответ. Создание карты не подтверждено ожидаемыми данными.');
            }

            locked = true;
            button.textContent = 'Карта создана';
            showMessage('Карта создана. Открывается каталог.');
            window.location.assign(form.dataset.returnUrl);
        } catch (error) {
            if (disposed || !form.isConnected) return;

            const definiteRejection = error instanceof MapRequestError
                && error.status >= 400 && error.status < 500 && error.status !== 408;
            const text = error instanceof Error ? error.message : 'Не удалось получить результат создания.';

            locked = !definiteRejection;

            showMessage(
                locked
                    ? `${text} Проверьте каталог перед повторным созданием: карта могла сохраниться.`
                    : text,
                true
            );

            if (locked) button.textContent = 'Проверьте каталог карт';
        } finally {
            busy = false;
            form.setAttribute('aria-busy', 'false');

            if (!locked) {
                fieldset.disabled = false;
                button.textContent = 'Создать карту';
            }
        }
    }, options);

    form.addEventListener('htmx:beforeCleanupElement', (event) => {
        if (event.detail?.elt !== form || disposed) return;

        disposed = true;
        listeners.abort();
        disposeSandbox();
        clearPreview();
        initializedForms.delete(form);
    }, options);
}
