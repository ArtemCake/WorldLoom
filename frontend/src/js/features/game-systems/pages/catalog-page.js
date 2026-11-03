// frontend/src/js/features/game-systems/pages/catalog-page.js

import { mountGameSystemsPage } from './page-controller.js';

export function initGameSystemsCatalog() {
    for (const root of document.querySelectorAll('[data-game-systems-page]')) {
        if (!['list', 'view'].includes(root.dataset.pageMode)) continue;

        mountGameSystemsPage(root);
    }
}