// frontend/src/js/features/game-systems/pages/editor-page.js

import { mountGameSystemsPage } from './page-controller.js';

export function initGameSystemEditor() {
    for (const root of document.querySelectorAll('[data-game-systems-page]')) {
        if (!['create', 'edit'].includes(root.dataset.pageMode)) continue;

        mountGameSystemsPage(root);
    }
}