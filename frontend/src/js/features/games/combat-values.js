// frontend/src/js/features/games/combat-values.js

const DB_INT_MAX = 2147483647;

export function readCombatants(form) {
    const field = form.elements.namedItem('combatants');

    if (!(field instanceof HTMLTextAreaElement)) {
        throw new Error('Не найдено поле участников боя.');
    }

    const lines = field.value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);

    if (!lines.length || lines.length > 1000) {
        throw new Error('Укажите от 1 до 1000 участников: каждый на отдельной строке.');
    }

    return lines.map((line, index) => {
        const separator = line.lastIndexOf(';');
        const name = (separator < 0 ? line : line.slice(0, separator)).trim();
        const rawInitiative = separator < 0 ? '' : line.slice(separator + 1).trim();
        const initiative = rawInitiative === '' ? null : Number(rawInitiative);

        if (!name) {
            throw new Error(`В строке ${index + 1} не указано имя участника.`);
        }

        if (initiative !== null && !Number.isFinite(initiative)) {
            throw new Error(`В строке ${index + 1} инициатива должна быть числом или оставаться пустой.`);
        }

        return { name, initiative };
    });
}

export function validateCombatState(data, sessionId) {
    if (!data || data.session_id !== sessionId || typeof data.session_active !== 'boolean'
        || typeof data.combat_active !== 'boolean' || !Array.isArray(data.turn_order)) {
        throw new Error('Сервер вернул неподдерживаемое состояние боя.');
    }

    const order = data.turn_order;

    for (const entry of order) {
        if (!entry || typeof entry !== 'object' || Array.isArray(entry)
            || (entry.name !== null && typeof entry.name !== 'string')
            || (entry.initiative !== null && (typeof entry.initiative !== 'number' || !Number.isFinite(entry.initiative)))) {
            throw new Error('Сервер вернул некорректную запись участника боя.');
        }
    }

    const hasTracker = data.round_number !== null;

    if (!hasTracker) {
        if (data.combat_active || order.length || data.current_index !== null) {
            throw new Error('Сервер вернул противоречивое состояние отсутствующей очереди.');
        }
    } else {
        if (!Number.isInteger(data.round_number) || data.round_number < 1 || data.round_number > DB_INT_MAX) {
            throw new Error('Сервер вернул некорректный номер раунда.');
        }

        if (order.length === 0 ? data.current_index !== null
            : !Number.isInteger(data.current_index) || data.current_index < 0 || data.current_index >= order.length) {
            throw new Error('Сервер вернул некорректное положение текущего хода.');
        }
    }

    return { ...data, hasTracker };
}
