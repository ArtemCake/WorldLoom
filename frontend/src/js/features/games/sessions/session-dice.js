// frontend/src/js/features/games/sessions/session-dice.js

import { gameStateApi } from './../game-state-api.js';

const initializedRoots = new WeakSet();
const HISTORY_LIMIT = 100;

function errorText(error) {
    return error instanceof Error ? error.message : 'Не удалось выполнить операцию.';
}

function readRollPayload(form) {
    const values = new FormData(form);
    let formula = String(values.get('formula') || '').trim().toLowerCase();
    const mode = String(values.get('advantage') || '');

    if (!formula || formula.length > 100) {
        throw new Error('Введите формулу длиной от 1 до 100 символов.');
    }

    if (!['', 'advantage', 'disadvantage'].includes(mode)) {
        throw new Error('Выберите доступный режим броска.');
    }

    if (mode) {
        const match = /^1d20([+-][0-9]+)?$/.exec(formula);

        if (!match) {
            throw new Error('Для преимущества или помехи укажите 1d20 с необязательным модификатором.');
        }

        const selection = mode === 'advantage' ? 'kh1' : 'kl1';
        formula = `2d20${selection}${match[1] || ''}`;
    }

    return { formula, is_gm_hidden: false };
}

function validateRoll(roll, sessionId) {
    if (!roll || typeof roll.id !== 'string' || roll.session_id !== sessionId || typeof roll.formula !== 'string') {
        throw new Error('Сервер вернул неподдерживаемую запись броска.');
    }

    if (!Number.isSafeInteger(roll.result_total) || !Array.isArray(roll.individual_results)
        || !roll.individual_results.every((value) => Number.isSafeInteger(value))) {
        throw new Error('Сервер вернул некорректный результат броска.');
    }

    return roll;
}

function describeRoll(roll) {
    const parts = [`Выпавшие значения: ${roll.individual_results.join(', ')}`];

    if (roll.advantage === 'advantage') parts.push('Преимущество');
    if (roll.advantage === 'disadvantage') parts.push('Помеха');
    if (roll.is_gm_hidden) parts.push('Скрытый бросок');

    const date = typeof roll.created_at === 'string' ? new Date(roll.created_at) : null;

    if (date && Number.isFinite(date.getTime())) {
        parts.push(date.toLocaleString('ru-RU'));
    }

    return parts.join(' · ');
}

function renderRolls(list, empty, rolls) {
    const fragment = document.createDocumentFragment();

    for (const roll of rolls) {
        const item = document.createElement('li');
        const result = document.createElement('strong');
        const details = document.createElement('span');

        item.className = 'session-dice__entry';
        result.textContent = `${roll.formula} → ${roll.result_total}`;
        details.className = 'session-dice__hint';
        details.textContent = describeRoll(roll);

        item.append(result, details);
        fragment.append(item);
    }

    list.replaceChildren(fragment);
    empty.hidden = rolls.length !== 0;
}

function initPanel(root) {
    if (initializedRoots.has(root)) return;

    const sessionId = root.dataset.sessionId;
    const form = root.querySelector('[data-session-dice-form]');
    const fieldset = form?.querySelector('fieldset');
    const refresh = root.querySelector('[data-session-dice-refresh]');
    const message = root.querySelector('[data-session-dice-message]');
    const list = root.querySelector('[data-session-dice-list]');
    const empty = root.querySelector('[data-session-dice-empty]');

    if (!sessionId || !form || !fieldset || !refresh || !message || !list || !empty) return;

    initializedRoots.add(root);

    const canRoll = root.dataset.sessionActive === 'true';
    let busy = false;
    let rolls = [];

    function setBusy(value) {
        busy = value;
        fieldset.disabled = value || !canRoll;
        refresh.disabled = value;
        root.setAttribute('aria-busy', String(value));
    }

    function showMessage(text, isError = false) {
        message.textContent = text;
        message.classList.toggle('alert-error', isError);
    }

    async function loadHistory() {
        if (busy || !root.isConnected) return;

        setBusy(true);
        showMessage('');

        try {
            const data = await gameStateApi.listRolls(sessionId, { limit: HISTORY_LIMIT });

            if (!root.isConnected) return;

            if (!Array.isArray(data)) {
                throw new Error('Сервер вернул неподдерживаемый журнал бросков.');
            }

            const checked = data.map((roll) => validateRoll(roll, sessionId));
            rolls = checked;
            renderRolls(list, empty, rolls);
        } catch (error) {
            if (!root.isConnected) return;

            showMessage(`Журнал не обновлён. ${errorText(error)}`, true);
        } finally {
            setBusy(false);
        }
    }

    form.addEventListener('submit', async (event) => {
        event.preventDefault();

        if (busy || !canRoll || !form.reportValidity()) return;

        let payload;

        try {
            payload = readRollPayload(form);
        } catch (error) {
            showMessage(errorText(error), true);
            return;
        }

        setBusy(true);
        showMessage('');

        try {
            const data = await gameStateApi.rollDice(sessionId, payload);

            if (!root.isConnected) return;

            const roll = validateRoll(data, sessionId);
            rolls = [roll, ...rolls.filter((item) => item.id !== roll.id)].slice(0, HISTORY_LIMIT);
            renderRolls(list, empty, rolls);
            showMessage(`${roll.formula}: результат ${roll.result_total}.`);
        } catch (error) {
            if (!root.isConnected) return;

            showMessage(`${errorText(error)} Перед новым броском обновите журнал: операция могла сохраниться.`, true);
        } finally {
            setBusy(false);
        }
    });

    refresh.addEventListener('click', () => {
        void loadHistory();
    });

    setBusy(false);
    void loadHistory();
}

export function initSessionDice() {
    document.querySelectorAll('[data-session-dice]').forEach(initPanel);
}
