// frontend/src/js/shared/ui/ui.js

import { initPasswordToggles } from '../../features/auth/password-toggle.js';
import { initStickyNavigation } from './sticky-navigation.js';
import { initThemeSwitcher } from './theme-switcher.js';

export function initGlobalUI() {
    if (window.htmx) window.htmx.config.scrollIntoViewOnBoost = false;

    initPasswordToggles();
    initThemeSwitcher();
    initStickyNavigation();
}