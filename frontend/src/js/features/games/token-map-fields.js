// frontend/src/js/features/games/token-map-fields.js

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function fillTokenMapField(form, token) {
    const select = form.elements.namedItem('current_map_id');

    if (!(select instanceof HTMLSelectElement)) return;

    select.querySelectorAll('[data-token-current-map]').forEach((option) => option.remove());

    const currentMapId = token.current_map_id;

    if (currentMapId === null) {
        select.value = '';
        return;
    }

    if (typeof currentMapId !== 'string' || !UUID_PATTERN.test(currentMapId)) {
        throw new Error('Сервер вернул некорректное назначение карты.');
    }

    const available = Array.from(select.options).some((option) => option.value === currentMapId);

    if (!available) {
        const option = document.createElement('option');

        option.value = currentMapId;
        option.textContent = 'Текущая карта вне списка — оставить назначение без изменения';
        option.dataset.tokenCurrentMap = 'true';
        select.append(option);
    }

    select.value = currentMapId;
}

export function readTokenMapChanges(form, token) {
    const select = form.elements.namedItem('current_map_id');

    if (!(select instanceof HTMLSelectElement)) return {};

    if (select.selectedIndex < 0) {
        throw new Error('Выберите карту или вариант «Карта не назначена».');
    }

    const value = select.value;
    const currentMapId = value === '' ? null : value;

    if (currentMapId !== null && !UUID_PATTERN.test(currentMapId)) {
        throw new Error('В списке выбрана некорректная карта.');
    }

    if (currentMapId === token.current_map_id) return {};

    const option = select.selectedOptions[0];

    if (option?.dataset.tokenCurrentMap === 'true') {
        throw new Error('Для нового назначения выберите карту из доступного списка.');
    }

    return { current_map_id: currentMapId };
}
