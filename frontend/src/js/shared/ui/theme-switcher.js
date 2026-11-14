// frontend/src/js/shared/ui/theme-switcher.js

import { isAuthenticationFailure, sessionClient } from '../http/session-client.js';
import { showNotice } from './notifications.js';

const PRESET_THEMES = ['dark-fantasy', 'light-fantasy', 'fantasy'];
const ALL_THEMES = new Set([...PRESET_THEMES, 'custom']);
const COLOR_PATTERN = /^#[0-9a-f]{6}$/i;
const DEFAULT_ACCENT = '#8a5cf6';
const THEME_FOLDERS = {
    'dark-fantasy': 'dark_fantasy',
    'light-fantasy': 'light_fantasy',
    fantasy: 'general_fantasy'
};

const loadedBodies = new WeakSet();
const boundControls = new WeakSet();
const backgroundCache = new Map();

let pendingSave = null;
let saving = false;
let saveBlocked = false;

function readStorage(name, key) {
    try {
        return window[name].getItem(key);
    } catch {
        return null;
    }
}

function writeStorage(name, key, value) {
    try {
        window[name].setItem(key, value);
    } catch {
        // Оформление текущей страницы работает и без хранилища.
    }
}

function normalizeTheme(value) {
    return ALL_THEMES.has(value) ? value : 'dark-fantasy';
}

function normalizeColor(value) {
    return typeof value === 'string' && COLOR_PATTERN.test(value) ? value : DEFAULT_ACCENT;
}

function applyThemeBackground(themeName, forceReroll) {
    const body = document.body;
    const folder = THEME_FOLDERS[themeName];

    if (!folder) {
        body.style.removeProperty('--bg-image-url');
        body.classList.remove('has-bg-image');
        return;
    }

    const images = Array.from({ length: 5 }, (_, index) => `/frontend/public/images/backgrounds/${folder}/fantasy-${index + 1}.webp`);
    const key = `theme-bg-${themeName}`;
    let chosen = forceReroll ? null : backgroundCache.get(key) || readStorage('sessionStorage', key);

    if (!images.includes(chosen)) chosen = images[Math.floor(Math.random() * images.length)];

    backgroundCache.set(key, chosen);
    writeStorage('sessionStorage', key, chosen);
    body.style.setProperty('--bg-image-url', `url('${chosen}')`);
    body.classList.add('has-bg-image');
}

export function applyTheme(themeName, forceRerollBackground = false) {
    const theme = normalizeTheme(themeName);
    const root = document.documentElement;

    root.classList.remove(...PRESET_THEMES.map((name) => `theme-${name}`));
    if (PRESET_THEMES.includes(theme)) root.classList.add(`theme-${theme}`);

    applyThemeBackground(theme, forceRerollBackground);
}

export function setAccentColor(color) {
    const normalized = normalizeColor(color);
    const red = parseInt(normalized.slice(1, 3), 16);
    const green = parseInt(normalized.slice(3, 5), 16);
    const blue = parseInt(normalized.slice(5, 7), 16);
    const light = (0.299 * red + 0.587 * green + 0.114 * blue) / 255 > 0.6;
    const style = document.documentElement.style;

    style.setProperty('--color-bg-page', normalized);
    style.setProperty('--color-text-primary', light ? '#1a1a1a' : '#e8e8ea');
    style.setProperty('--color-text-secondary', light ? '#4b4b4b' : '#c9c9cf');
}

function clearAccentOverride() {
    const style = document.documentElement.style;

    for (const name of ['--color-bg-page', '--color-text-primary', '--color-text-secondary']) {
        style.removeProperty(name);
    }
}

function renderTheme(theme, accent, reroll = false) {
    applyTheme(theme, reroll);

    if (theme === 'custom') setAccentColor(accent);
    else clearAccentOverride();

    const select = document.getElementById('theme-select');
    const picker = document.getElementById('accent-picker');

    if (select) select.value = theme;
    if (picker) {
        picker.value = accent;
        picker.disabled = theme !== 'custom';
    }
}

export function loadUserTheme() {
    const body = document.body;
    if (loadedBodies.has(body)) return;

    loadedBodies.add(body);

    const authenticated = body.hasAttribute('data-user-theme');
    const theme = normalizeTheme(authenticated ? body.dataset.userTheme : readStorage('localStorage', 'user-theme'));
    const accent = normalizeColor(authenticated ? body.dataset.userAccent : readStorage('localStorage', 'user-accent'));

    writeStorage('localStorage', 'user-theme', theme);
    writeStorage('localStorage', 'user-accent', accent);
    renderTheme(theme, accent);
}

async function drainThemeSaves() {
    if (saving || saveBlocked) return;
    saving = true;

    try {
        while (pendingSave) {
            const { body, payload } = pendingSave;
            pendingSave = null;

            const response = await sessionClient.sessionFetch('/profile/theme', {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
                body: JSON.stringify(payload),
                retryAfterRefresh: true
            });

            if (isAuthenticationFailure(response) || response.status === 401) {
                throw new Error('Для сохранения темы нужно войти снова.');
            }

            if (!response.ok) throw new Error(`Сервер не подтвердил сохранение темы (${response.status}).`);

            const data = await response.json();
            if (data?.theme !== payload.theme) throw new Error('Сервер вернул неожиданный ответ при сохранении темы.');

            body.dataset.userTheme = payload.theme;
            if (payload.theme_color !== null) body.dataset.userAccent = payload.theme_color;
        }
    } catch (error) {
        pendingSave = null;
        saveBlocked = true;

        const message = error instanceof Error ? error.message : 'Сохранение не подтверждено.';
        showNotice(`${message} Тема применена в браузере, но сохранение в аккаунте не подтверждено. Обновите страницу перед новой записью.`, 'warning');
    } finally {
        saving = false;
    }
}

function persistChoice(theme, accent) {
    writeStorage('localStorage', 'user-theme', theme);
    writeStorage('localStorage', 'user-accent', accent);

    const body = document.body;
    if (!body.hasAttribute('data-user-theme') || saveBlocked) return;

    pendingSave = { body, payload: { theme, theme_color: theme === 'custom' ? accent : null } };
    void drainThemeSaves();
}

function bindThemeControls() {
    const select = document.getElementById('theme-select');
    const picker = document.getElementById('accent-picker');

    if (select && !boundControls.has(select)) {
        boundControls.add(select);
        select.addEventListener('change', () => {
            const theme = normalizeTheme(select.value);
            const accent = normalizeColor(picker?.value);

            renderTheme(theme, accent, true);
            persistChoice(theme, accent);
        });
    }

    if (picker && !boundControls.has(picker)) {
        boundControls.add(picker);

        picker.addEventListener('input', () => {
            if (document.getElementById('theme-select')?.value === 'custom') setAccentColor(picker.value);
        });

        picker.addEventListener('change', () => {
            if (document.getElementById('theme-select')?.value === 'custom') persistChoice('custom', normalizeColor(picker.value));
        });
    }
}

export function initThemeSwitcher() {
    loadUserTheme();
    bindThemeControls();

    const select = document.getElementById('theme-select');
    const picker = document.getElementById('accent-picker');

    if (picker && select) picker.disabled = select.value !== 'custom';
}