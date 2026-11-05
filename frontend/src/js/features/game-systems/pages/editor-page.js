// frontend/src/js/features/game-systems/pages/editor-page.js

import {mountGameSystemsPage} from './page-controller.js';
import {createRulesBookState} from '../book/book-state.js';
import {mountRulesBook} from '../book/book-view.js';

const initializedBooks = new WeakSet();

function mountNewBook(root) {
    if (initializedBooks.has(root)) return;

    const document = {
        system: {
            name: '',
            slug: '',
            description: '',
            is_active: true,
            rules_engine_version: '1.0'
        },
        rules: null,
        origin: null
    };

    const state = createRulesBookState({document, mode: 'create'});

    initializedBooks.add(root);

    try {
        mountRulesBook(root, {state});
    } catch (error) {
        initializedBooks.delete(root);

        const message = window.document.createElement('p');
        message.setAttribute('role', 'alert');
        message.textContent = error instanceof Error ? error.message : 'Не удалось открыть книгу правил.';

        root.replaceChildren(message);
    }
}

export function initGameSystemEditor() {
    const bookRequested = new URLSearchParams(window.location.search).get('book') === '1';

    for (const root of document.querySelectorAll('[data-game-systems-page]')) {
        const mode = root.dataset.pageMode;

        if (!['create', 'edit'].includes(mode)) continue;

        if (mode === 'create' && bookRequested) {
            mountNewBook(root);
            continue;
        }

        mountGameSystemsPage(root);
    }
}