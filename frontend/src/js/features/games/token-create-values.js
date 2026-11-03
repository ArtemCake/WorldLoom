// frontend/src/js/features/games/token-create-values.js

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const DB_INT_MIN = -2147483648;
const DB_INT_MAX = 2147483647;

function readInteger(form, name, label, minimum = DB_INT_MIN) {
    const field = form.elements.namedItem(name);
    const raw = field.value.trim();
    const value = Number(raw);

    if (!raw || !Number.isInteger(value) || value < minimum || value > DB_INT_MAX) {
        throw new Error(`Проверьте поле «${label}»: требуется целое число в допустимом диапазоне.`);
    }

    return value;
}

function readImageAddress(form) {
    const field = form.elements.namedItem('image_url');
    const value = field.value.trim();

    if (!value || value.length > 1000) {
        throw new Error('Укажите адрес изображения длиной не более 1000 символов.');
    }

    const localPath = value.startsWith('/') && !value.startsWith('//');
    const absoluteAddress = /^https?:\/\//i.test(value);

    if (!localPath && !absoluteAddress) {
        throw new Error('Укажите путь от корня сайта или полный HTTP/HTTPS-адрес изображения.');
    }

    let url;

    try {
        url = new URL(value, window.location.origin);
    } catch {
        throw new Error('Не удалось разобрать адрес изображения.');
    }

    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) {
        throw new Error('Адрес изображения не должен содержать логин, пароль или неподдерживаемую схему.');
    }

    if (url.origin !== window.location.origin && url.protocol !== 'https:') {
        throw new Error('Для изображения с другого сайта используйте HTTPS.');
    }

    field.value = value;
    return value;
}

export function readTokenCreateValues(form, sessionId) {
    if (typeof sessionId !== 'string' || !UUID_PATTERN.test(sessionId)) {
        throw new Error('Не удалось определить выбранную сессию. Перезагрузите страницу.');
    }

    const nameInput = form.elements.namedItem('display_name');
    const displayName = nameInput.value.trim();

    if (displayName.length > 100) {
        throw new Error('Название токена не должно превышать 100 символов.');
    }

    nameInput.value = displayName;

    return {
        session_id: sessionId,
        image_url: readImageAddress(form),
        display_name: displayName || null,
        grid_x: readInteger(form, 'grid_x', 'Координата X'),
        grid_y: readInteger(form, 'grid_y', 'Координата Y'),
        hp_current: readInteger(form, 'hp_current', 'Текущее здоровье'),
        hp_max: readInteger(form, 'hp_max', 'Максимальное здоровье'),
        vision_radius_cells: readInteger(form, 'vision_radius_cells', 'Дальность обзора', 0),
        is_visible_to_players: form.elements.namedItem('is_visible_to_players').checked
    };
}
