// frontend/src/js/features/rules/draft/draft-source-data.js

const SOURCE_FIELDS = ['title', 'publisher', 'locator', 'url', 'license_name', 'license_url', 'attribution'];

export const MAX_DRAFT_SOURCES = 100;

function ensure(condition, message) {
    if (!condition) throw new TypeError(message);
}

function isObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export function applyDraftSourceCommand(value, command) {
    ensure(Array.isArray(value), 'Отсутствует список источников.');
    ensure(isObject(command), 'Не задана операция с источником.');

    const sources = structuredClone(value);

    if (command.type === 'add') {
        ensure(sources.length < MAX_DRAFT_SOURCES, 'Достигнуто максимальное количество источников.');
        sources.push({ title: 'Новый источник' });
        return sources;
    }

    const index = command.index;
    ensure(Number.isSafeInteger(index) && index >= 0 && index < sources.length, 'Не найден источник для изменения.');

    if (command.type === 'remove') {
        sources.splice(index, 1);
    } else if (command.type === 'input') {
        ensure(isObject(sources[index]), 'Некорректный источник.');
        ensure(SOURCE_FIELDS.includes(command.field), 'Это поле источника не редактируется.');
        ensure(typeof command.value === 'string', 'Значение поля источника должно быть строкой.');

        const optionalEmpty = command.field !== 'title' && command.value === '';
        sources[index][command.field] = optionalEmpty ? null : command.value;
    } else {
        throw new TypeError('Неизвестная операция с источником.');
    }

    return sources;
}
