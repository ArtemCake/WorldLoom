// frontend/src/js/features/games/game-details.js

import { initGameDelete } from './game-delete.js';
import { requestGameJson } from './game-http.js';

const initializedForms = new WeakSet();

export function initGameDetails() {
    initGameDelete();

    const form = document.querySelector('[data-game-settings]');

    if (!form || initializedForms.has(form)) return;

    const message = form.querySelector('[data-game-settings-message]');
    const button = form.querySelector('button[type="submit"]');

    if (!message || !button || !form.dataset.gameId) return;

    initializedForms.add(form);

    form.addEventListener('submit', async (event) => {
        event.preventDefault();

        if (form.dataset.saving === 'true' || form.dataset.deleting === 'true') return;

        message.textContent = '';

        if (!form.reportValidity()) return;

        const fields = new FormData(form);
        const title = String(fields.get('title') || '').trim();

        if (!title) {
            message.textContent = 'Укажите название игры.';
            return;
        }

        if (!document.querySelector('meta[name="csrf-token"]')?.content) {
            message.textContent = 'Не найден защитный токен. Перезагрузите страницу.';
            return;
        }

        const payload = {
            title,
            description: String(fields.get('description') || '') || null,
            status: fields.get('status'),
            privacy_level: fields.get('privacy_level'),
            is_homebrew_allowed: fields.has('is_homebrew_allowed')
        };

        form.dataset.saving = 'true';
        form.setAttribute('aria-busy', 'true');
        button.disabled = true;

        try {
            const data = await requestGameJson(form.action, { method: 'PATCH', body: payload });

            if (!form.isConnected) return;

            if (!data || data.id !== form.dataset.gameId) {
                message.textContent = 'Получен неожиданный ответ. Обновите страницу, чтобы проверить сохранение.';
                return;
            }

            message.textContent = 'Настройки сохранены.';
            window.location.reload();
        } catch (error) {
            if (!form.isConnected) return;

            message.textContent = error instanceof Error
                ? error.message
                : 'Не удалось подтвердить сохранение. Обновите страницу перед повторной отправкой.';
        } finally {
            delete form.dataset.saving;
            form.setAttribute('aria-busy', 'false');
            button.disabled = form.dataset.deleting === 'true';
        }
    });
}