// frontend/src/js/features/games/game-delete.js

import { requestGameJson } from './game-http.js';

const initializedRoots = new WeakSet();

export function initGameDelete() {
    const root = document.querySelector('[data-game-delete]');

    if (!root || initializedRoots.has(root)) return;

    const button = root.querySelector('[data-game-delete-button]');
    const message = root.querySelector('[data-game-delete-message]');
    const settingsForm = document.querySelector('[data-game-settings]');

    if (!button || !message || !root.dataset.deleteUrl || !root.dataset.returnUrl || !root.dataset.gameId) {
        return;
    }

    initializedRoots.add(root);

    let busy = false;
    let approved = false;
    let cleanupPending = false;

    button.addEventListener('click', async () => {
        if (busy) return;

        if (settingsForm?.dataset.saving === 'true') {
            message.textContent = 'Дождитесь завершения сохранения настроек.';
            return;
        }

        if (!document.querySelector('meta[name="csrf-token"]')?.content) {
            message.textContent = 'Не найден защитный токен. Перезагрузите страницу.';
            return;
        }

        if (!approved) {
            approved = window.confirm(
                'Удалить игру навсегда вместе с её картами, сессиями, игровыми листами и историей? '
                + 'Отменить это действие будет нельзя.'
            );

            if (!approved) return;
        }

        busy = true;
        button.disabled = true;
        root.setAttribute('aria-busy', 'true');
        message.textContent = cleanupPending ? 'Проверка очистки файлов…' : 'Проверка результата удаления…';

        // После начала удаления не сохраняем настройки потенциально удалённой игры.
        if (settingsForm) {
            settingsForm.dataset.deleting = 'true';

            settingsForm.querySelectorAll('input, textarea, select, button').forEach((control) => {
                control.disabled = true;
            });
        }

        try {
            const data = await requestGameJson(root.dataset.deleteUrl, { method: 'DELETE' });

            if (!root.isConnected) return;

            if (data?.deleted !== true || data.game_id !== root.dataset.gameId || typeof data.cleanup_complete !== 'boolean') {
                message.textContent = 'Сервер не подтвердил ожидаемый результат. Проверьте список игр.';
                button.textContent = 'Проверить удаление';
                return;
            }

            cleanupPending = !data.cleanup_complete;

            if (cleanupPending) {
                message.textContent = 'Игра удалена из базы данных. Очистка файлов ещё не завершена.';
                button.textContent = 'Проверить очистку файлов';
                return;
            }

            message.textContent = 'Игра удалена, очистка файлов завершена.';
            window.location.assign(root.dataset.returnUrl);
        } catch (error) {
            if (!root.isConnected) return;

            message.textContent = error instanceof Error
                ? error.message
                : 'Результат удаления не получен. Проверьте список игр.';

            button.textContent = 'Проверить удаление';
        } finally {
            busy = false;
            button.disabled = false;
            root.setAttribute('aria-busy', 'false');
        }
    });
}