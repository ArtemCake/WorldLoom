// frontend/src/js/features/games/lobby.js

import { requestGameJson } from './game-http.js';
import { renderGames, renderSystems } from './lobby-view.js';
import {showBoxMessage} from '../../shared/ui/message-box.js';

const initializedRoots = new WeakSet();

function showMessage(box, text, isError = false) {
    showBoxMessage(box, text, isError);
    box.classList.toggle('alert-success', Boolean(text) && !isError);
}

function errorText(error) {
    return error instanceof Error ? error.message : 'Не удалось выполнить операцию.';
}

function requireList(value, label, textField) {
    if (!Array.isArray(value) || !value.every((item) => item && typeof item.id === 'string' && typeof item[textField] === 'string')) {
        throw new Error(`Сервер вернул неподдерживаемый список: ${label}.`);
    }

    return value;
}

function invitePayload(form) {
    const fields = new FormData(form);
    const expiresLocal = String(fields.get('expires_at') || '');
    const usesText = String(fields.get('uses_limit') || '');
    const expires = expiresLocal ? new Date(expiresLocal) : null;
    const usesLimit = usesText ? Number(usesText) : null;

    if (expires && (!Number.isFinite(expires.getTime()) || expires.getTime() <= Date.now())) {
        throw new Error('Укажите будущую дату и время окончания приглашения.');
    }

    if (usesLimit !== null && (!Number.isSafeInteger(usesLimit) || usesLimit < 1)) {
        throw new Error('Количество использований должно быть положительным целым числом.');
    }

    return {
        expires_at: expires ? expires.toISOString() : null,
        uses_limit: usesLimit,
        message: String(fields.get('message') || '') || null
    };
}

export function initLobby() {
    const root = document.querySelector('[data-games-lobby]');

    if (!root || initializedRoots.has(root)) return;

    initializedRoots.add(root);

    const message = root.querySelector('[data-lobby-message]');
    const createPanel = root.querySelector('[data-create-panel]');
    const invitePanel = root.querySelector('[data-invite-panel]');
    const createForm = root.querySelector('[data-create-form]');
    const inviteForm = root.querySelector('[data-invite-form]');
    const claimForm = root.querySelector('[data-claim-form]');
    const createMessage = root.querySelector('[data-create-message]');
    const inviteMessage = root.querySelector('[data-invite-message]');
    const systemSelect = createForm.elements.namedItem('system_id');
    const tokenOutput = inviteForm.elements.namedItem('token_output');
    const inviteResult = root.querySelector('[data-invite-result]');

    let busy = false;
    let loadingGames = false;
    let inviteGameId = null;
    let knownGames = new Map();

    async function loadGames() {
        if (loadingGames || !root.isConnected) return;

        loadingGames = true;
        root.querySelector('[data-games-list]').setAttribute('aria-busy', 'true');

        try {
            const data = await requestGameJson(root.dataset.listUrl);
            const games = requireList(data, 'игры', 'title');

            if (!root.isConnected) return;

            knownGames = new Map(games.map((game) => [game.id, game]));
            renderGames(root, games, root.dataset.userId);
        } catch (error) {
            if (root.isConnected) {
                showMessage(message, `Список игр не обновлён. ${errorText(error)}`, true);
            }
        } finally {
            loadingGames = false;
            root.querySelector('[data-games-list]').setAttribute('aria-busy', 'false');
        }
    }

    async function loadSystems() {
        systemSelect.disabled = true;

        try {
            const data = await requestGameJson(root.dataset.systemsUrl);
            const systems = requireList(data, 'игровые системы', 'name');

            if (!root.isConnected) return;

            renderSystems(systemSelect, systems);
        } catch (error) {
            if (!root.isConnected) return;

            systemSelect.replaceChildren(new Option('Не удалось загрузить игровые системы', ''));
            showMessage(createMessage, errorText(error), true);
        }
    }

    async function perform(box, operation) {
        if (busy || !root.isConnected) return;

        if (!document.querySelector('meta[name="csrf-token"]')?.content) {
            showMessage(box, 'Не найден защитный токен. Перезагрузите страницу.', true);
            return;
        }

        busy = true;
        root.setAttribute('aria-busy', 'true');

        const buttons = Array.from(root.querySelectorAll('button'));
        const disabledStates = buttons.map((button) => button.disabled);

        buttons.forEach((button) => {
            button.disabled = true;
        });

        showMessage(box, '');

        try {
            await operation();
        } catch (error) {
            if (root.isConnected) {
                showMessage(box, errorText(error), true);
            }
        } finally {
            busy = false;
            root.setAttribute('aria-busy', 'false');

            buttons.forEach((button, index) => {
                button.disabled = disabledStates[index];
            });
        }
    }

    createForm.addEventListener('submit', (event) => {
        event.preventDefault();

        if (busy || !createForm.reportValidity()) return;

        const fields = new FormData(createForm);
        const title = String(fields.get('title') || '').trim();
        const systemId = String(fields.get('system_id') || '');

        if (!title || !systemId) {
            showMessage(createMessage, 'Укажите название и выберите игровую систему.', true);
            return;
        }

        const payload = {
            title,
            description: String(fields.get('description') || '') || null,
            system_id: systemId,
            privacy_level: fields.get('privacy_level'),
            is_homebrew_allowed: fields.has('is_homebrew_allowed')
        };

        void perform(createMessage, async () => {
            const game = await requestGameJson(root.dataset.createUrl, { method: 'POST', body: payload });

            if (!root.isConnected) return;

            if (!game || typeof game.id !== 'string') {
                throw new Error('Создание не подтверждено ожидаемым ответом. Обновите список перед повтором.');
            }

            createPanel.hidden = true;
            createForm.reset();
            showMessage(message, 'Игра создана.');
            await loadGames();
        });
    });

    inviteForm.addEventListener('submit', (event) => {
        event.preventDefault();

        if (busy || !inviteGameId || !inviteForm.reportValidity()) return;

        let payload;

        try {
            payload = invitePayload(inviteForm);
        } catch (error) {
            showMessage(inviteMessage, errorText(error), true);
            return;
        }

        const gameId = inviteGameId;

        void perform(inviteMessage, async () => {
            const data = await requestGameJson(`/games/${encodeURIComponent(gameId)}/invites`, { method: 'POST', body: payload });

            if (!root.isConnected) return;

            if (data?.game_id !== gameId || typeof data.token !== 'string' || !data.token) {
                throw new Error('Сервер не вернул ожидаемый токен. Приглашение могло быть создано; не повторяйте запрос автоматически.');
            }

            tokenOutput.value = data.token;
            inviteResult.hidden = false;
            showMessage(inviteMessage, 'Приглашение создано.');
        });
    });

    claimForm.addEventListener('submit', (event) => {
        event.preventDefault();

        if (busy || !claimForm.reportValidity()) return;

        const input = claimForm.elements.namedItem('token');
        const token = input.value.trim();

        if (!token) {
            showMessage(message, 'Вставьте токен приглашения.', true);
            return;
        }

        void perform(message, async () => {
            const data = await requestGameJson(root.dataset.claimUrl, { method: 'POST', body: { token } });

            if (!root.isConnected) return;

            if (!data || typeof data.game_id !== 'string' || data.user_id !== root.dataset.userId || data.is_active !== true) {
                throw new Error('Ответ о присоединении не подтверждён. Обновите список игр перед повтором.');
            }

            input.value = '';
            showMessage(message, 'Вы присоединились к игре.');
            await loadGames();
        });
    });

    root.addEventListener('click', (event) => {
        const trigger = event.target instanceof Element ? event.target.closest('[data-lobby-action]') : null;

        if (!trigger || !root.contains(trigger) || busy) return;

        const action = trigger.dataset.lobbyAction;

        if (action === 'create-open') {
            createPanel.hidden = false;
            createForm.elements.namedItem('title').focus();
        } else if (action === 'create-close') {
            createPanel.hidden = true;
            createForm.reset();
            showMessage(createMessage, '');
        } else if (action === 'invite-open') {
            const game = knownGames.get(trigger.dataset.gameId);

            if (!game || game.master_id !== root.dataset.userId) return;

            inviteGameId = game.id;
            inviteForm.reset();
            inviteResult.hidden = true;
            invitePanel.hidden = false;
            showMessage(inviteMessage, '');
            inviteForm.elements.namedItem('expires_at').focus();
        } else if (action === 'invite-close') {
            invitePanel.hidden = true;
            inviteGameId = null;
            inviteForm.reset();
            inviteResult.hidden = true;
            showMessage(inviteMessage, '');
        } else if (action === 'copy-invite') {
            if (!tokenOutput.value) return;

            tokenOutput.focus();
            tokenOutput.select();

            void (async () => {
                try {
                    await navigator.clipboard.writeText(tokenOutput.value);

                    if (root.isConnected) showMessage(inviteMessage, 'Токен скопирован.');
                } catch {
                    if (root.isConnected) showMessage(inviteMessage, 'Скопируйте выделенный токен вручную.', true);
                }
            })();
        } else if (action === 'reload') {
            void loadGames();
        } else if (action === 'leave-game') {
            const game = knownGames.get(trigger.dataset.gameId);

            if (!game || game.master_id === root.dataset.userId || !window.confirm('Покинуть эту игру?')) return;

            void perform(message, async () => {
                await requestGameJson(`/games/${encodeURIComponent(game.id)}/leave`, { method: 'POST' });

                if (!root.isConnected) return;

                showMessage(message, 'Вы покинули игру.');
                await loadGames();
            });
        }
    });

    void loadGames();
    void loadSystems();
}
