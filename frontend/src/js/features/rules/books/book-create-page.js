// frontend/src/js/features/rules/books/book-create-page.js

import { booksApi } from './books-api.js';
import { createBookCreation } from './book-create-state.js';
import { createBookCreationPanel } from './book-create-panel.js';
import { createAuthoringNavigation } from '../authoring/authoring-navigation.js';

const instances = new Map();
let cleanupBound = false;

function destroy(root) {
    const instance = instances.get(root);
    if (!instance) return;

    instance.dispose();
    instances.delete(root);
}

function bindCleanup() {
    if (cleanupBound) return;
    cleanupBound = true;

    document.addEventListener('htmx:beforeCleanupElement', (event) => {
        const element = event.detail?.elt || event.target;

        for (const root of instances.keys()) {
            if (element === root || element?.contains?.(root)) destroy(root);
        }
    });
}

function mountCreationPage(root) {
    const window = root.ownerDocument.defaultView;
    const notice = root.querySelector('[data-book-create-notice]');
    if (!notice) throw new Error('Не найдено сообщение страницы создания книги.');

    let disposed = false;

    function notify(message) {
        notice.textContent = message;
        notice.hidden = !message;
    }

    function act(action) {
        notify('');

        void Promise.resolve().then(action).catch((failure) => {
            if (disposed) return;
            notify(failure?.message || 'Не удалось выполнить действие.');
        });
    }

    const panel = createBookCreationPanel({
        root,
        onCancel: () => act(cancel),
        onInput: (name, value) => creation.change(name, value),
        onSubmit: () => act(submit)
    });

    const creation = createBookCreation({
        api: booksApi,
        onChange: panel.render,
        openBook: async (bookId) => {
            const result = await booksApi.getWorkingEditor(bookId);

            if (result?.book?.id !== bookId || result?.draft?.book_id !== bookId) {
                throw new TypeError('Сервер не подтвердил открытие черновика созданной книги.');
            }
        }
    });

    const navigation = createAuthoringNavigation({
        root,
        getState: creation.getState,
        notify
    });

    async function submit() {
        const bookId = await creation.submit();
        if (disposed || !bookId) return;

        const destination = new URL('/rules/workspace', window.location.origin);
        destination.searchParams.set('book_id', bookId);
        window.location.assign(destination.href);
    }

    function cancel() {
        if (!navigation.allow()) return;
        if (!creation.close()) return;

        window.location.assign('/rules/workspace');
    }

    function dispose() {
        if (disposed) return;

        disposed = true;
        navigation.dispose();
        creation.dispose();
        panel.dispose();
    }

    creation.open();
    instances.set(root, { dispose });
}

export function initRulesBookCreation() {
    bindCleanup();

    for (const root of instances.keys()) {
        if (!root.isConnected) destroy(root);
    }

    for (const root of document.querySelectorAll('[data-rules-book-create-page]')) {
        if (!instances.has(root)) mountCreationPage(root);
    }
}
