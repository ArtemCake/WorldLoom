// frontend/src/js/app/page-lifecycle.js

import { initAdminPanel } from '../features/admin/admin.js';
import { initAuthPage } from '../features/auth/auth.js';
import { initMfaSetup } from '../features/auth/mfa-setup.js';
import { initCookieBanner } from '../features/legal/cookie-banner.js';
import { initDeleteAccountModal } from '../features/users/delete-account.js';
import { initProfile } from '../features/users/profile.js';
import { initGlobalUI } from '../shared/ui/ui.js';
import { initGameSystemsCatalog } from '../features/game-systems/pages/catalog-page.js';
import { initGameSystemEditor } from '../features/game-systems/pages/editor-page.js';
import { initRulesCatalog } from '../features/rules/catalog/catalog-page.js';

let lifecycleBound = false;

export function initPage() {
    initGlobalUI();
    initCookieBanner();
    initAuthPage();
    initProfile();
    initMfaSetup();
    initDeleteAccountModal();
    initAdminPanel();
    initGameSystemsCatalog();
    initRulesCatalog();
    initGameSystemEditor();
}

export function setupPageLifecycle() {
    if (lifecycleBound) return;
    lifecycleBound = true;

    document.addEventListener('htmx:afterSettle', initPage);
    document.addEventListener('htmx:historyRestore', initPage);

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initPage, { once: true });
    } else {
        initPage();
    }
}