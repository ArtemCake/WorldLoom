// frontend/src/js/features/rules/catalog/catalog-page.js

import { booksApi } from './../books/books-api.js';
import { createRulesCatalogController } from './catalog-controller.js';
import { createRulesCatalogView } from './catalog-view.js';
import { createBookReader } from './../books/book-reader.js';

const instances = new Map();
let cleanupBound = false;

function destroy(root) {
    const instance = instances.get(root);

    if (!instance) return;

    instance.events.abort();
    instance.controller.dispose();
    instance.reader.dispose();
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

function formFilters(form) {
    const values = new FormData(form);

    return {
        kind: 'books',
        system_id: String(values.get('system_id') || ''),
        scope: String(values.get('scope') || 'available'),
        q: String(values.get('q') || ''),
        edition_key: String(values.get('edition_key') || ''),
        language: String(values.get('language') || '')
    };
}

export function initRulesCatalog() {
    bindCleanup();

    for (const root of instances.keys()) {
        if (!root.isConnected) destroy(root);
    }

    for (const root of document.querySelectorAll('[data-rules-catalog]')) {
        if (instances.has(root)) continue;
        const system = root.querySelector('[data-rules-system]');
        const form = root.querySelector('[data-rules-filters]');
        const reload = root.querySelector('[data-rules-reload]');
        const more = root.querySelector('[data-rules-more]');
        const retry = root.querySelector('[data-rules-retry]');
        const back = root.querySelector('[data-rules-reader-back]');
        const readerRetry = root.querySelector('[data-rules-reader-retry]');

        if (!form || !system || !reload || !more || !retry || !back || !readerRetry) {
            throw new Error('Разметка раздела правил неполна.');
        }

        const events = new AbortController();
        const options = { signal: events.signal };
        let selected = null;
        let reader;

        function openBook(bookId, versionId) {
            selected = { bookId, versionId };
            void reader.open(bookId, versionId);
            back.focus();
        }

        const view = createRulesCatalogView(root, { onOpen: openBook });
        const loadPage = (_kind, filters, requestOptions) => booksApi.list(filters, requestOptions);
        const controller = createRulesCatalogController({ loadPage, onChange: view.render });
        const loadBook = (bookId, versionId, requestOptions) => booksApi.read(bookId, versionId, requestOptions);

        reader = createBookReader({ loadBook, onChange: view.renderReader });

        function submitFilters() {
            if (!form.reportValidity()) return;

            void controller.reload(formFilters(form));
        }

        form.addEventListener('submit', (event) => {
            event.preventDefault();
            submitFilters();
        }, options);
        system.addEventListener('change', submitFilters, options);

        reload.addEventListener('click', submitFilters, options);
        more.addEventListener('click', () => { void controller.next(); }, options);

        retry.addEventListener('click', () => {
            const state = controller.getState();

            if (state.nextAfter) {
                void controller.next();
            } else {
                void controller.reload();
            }
        }, options);

        back.addEventListener('click', () => {
            reader.close();
            reload.focus();
        }, options);

        readerRetry.addEventListener('click', () => {
            if (selected) void reader.open(selected.bookId, selected.versionId);
        }, options);

        instances.set(root, { controller, reader, events });
        submitFilters();
    }
}
