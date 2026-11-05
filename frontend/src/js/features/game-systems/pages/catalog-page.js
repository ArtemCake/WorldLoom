// frontend/src/js/features/game-systems/pages/catalog-page.js

import {mountSystemsCatalog} from './catalog-controller.js';

export function initGameSystemsCatalog() {
    for (const root of document.querySelectorAll('[data-game-systems-page]')) {
        if (root.dataset.pageMode === 'list') mountSystemsCatalog(root);
    }
}
