// frontend/src/js/features/maps/map-delete.js

import { requestMapJson } from './map-http.js';
import { acquireMapOperation } from './map-operation-state.js';
import {messageShower} from '../../shared/ui/message-box.js';

const initializedButtons = new WeakSet();

function validateDeletion(data, mapId) {
    if (!data || data.map_id !== mapId || data.deleted !== true || typeof data.cleanup_complete !== 'boolean') {
        throw new Error('Сервер не подтвердил ожидаемый результат удаления.');
    }

    return data;
}

function initDeleteButton(button) {
    if (initializedButtons.has(button)) return;

    const root = button.closest('[data-map-operation-root]');
    const message = root?.querySelector('[data-map-delete-message]');
    const mapId = button.dataset.mapId;
    const deleteUrl = button.dataset.mapDelete;
    const cleanupUrl = button.dataset.cleanupUrl;

    if (!root || !message || !mapId || !deleteUrl || !cleanupUrl) return;

    initializedButtons.add(button);

    let approved = false;
    let phase = 'delete';
    let busy = false;

    const showMessage = messageShower(message);

    button.addEventListener('click', async () => {
        if (busy || phase === 'complete' || !root.isConnected) return;

        if (!approved) {
            const title = button.dataset.mapTitle || 'Без названия';

            approved = window.confirm(
                `Удалить карту «${title}»?\n\n`
                + 'Будут удалены её слои, гексы, объекты и аудиозоны. '
                + 'Токены останутся без привязки к этой карте. '
                + 'Загруженный фон удаляется отдельным шагом очистки. '
                + 'Отменить удаление нельзя.'
            );

            if (!approved) return;
        }

        if (!document.querySelector('meta[name="csrf-token"]')?.content) {
            showMessage('Не найден защитный токен. Перезагрузите страницу.', true);
            return;
        }

        const release = acquireMapOperation(root);

        if (!release) return;

        busy = true;
        const cleaning = phase === 'cleanup';

        button.textContent = cleaning ? 'Очистка файлов…' : 'Удаление карты…';
        showMessage('');

        try {
            const data = await requestMapJson(cleaning ? cleanupUrl : deleteUrl, {
                method: cleaning ? 'POST' : 'DELETE'
            });

            if (!root.isConnected) return;

            const result = validateDeletion(data, mapId);

            root.querySelectorAll('[data-map-existing]').forEach((node) => {
                node.hidden = true;
            });

            if (result.cleanup_complete) {
                phase = 'complete';
                showMessage('Карта удалена. Очистка файлов завершена.');
            } else {
                phase = 'cleanup';
                showMessage('Карта удалена из базы данных. Нажмите «Очистить файлы», чтобы завершить удаление фона.');
            }
        } catch (error) {
            if (!root.isConnected) return;

            const text = error instanceof Error ? error.message : 'Не удалось получить результат операции.';
            const advice = cleaning
                ? 'Карта уже удалена из базы данных. Завершение очистки не подтверждено; её можно повторить этой кнопкой.'
                : 'Удаление могло сохраниться. Обновите каталог или повторно проверьте удаление этой кнопкой.';

            showMessage(`${text} ${advice}`, true);
        } finally {
            busy = false;
            release();

            if (phase === 'complete') {
                button.textContent = 'Карта удалена';
                button.disabled = true;
            } else if (phase === 'cleanup') {
                button.textContent = 'Очистить файлы';
            } else {
                button.textContent = 'Повторить проверку удаления';
            }
        }
    });
}

export function initMapDelete() {
    document.querySelectorAll('[data-map-delete]').forEach(initDeleteButton);
}
