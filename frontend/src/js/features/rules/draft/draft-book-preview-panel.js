// frontend/src/js/features/rules/draft/draft-book-preview-panel.js

import { createBookContent } from '../books/book-content-view.js';

export function createDraftBookPreviewPanel({ host, onOpen, onClose }) {
    if (typeof onOpen !== 'function' || typeof onClose !== 'function') {
        throw new TypeError('Требуются обработчики открытия и закрытия предпросмотра.');
    }

    const document = host.ownerDocument;
    const events = new AbortController();
    const options = { signal: events.signal };
    const root = document.createElement('section');
    const openButton = document.createElement('button');
    const body = document.createElement('section');
    const heading = document.createElement('h2');
    const explanation = document.createElement('p');
    const status = document.createElement('p');
    const refreshButton = document.createElement('button');
    const closeButton = document.createElement('button');
    const actions = document.createElement('div');
    const content = document.createElement('div');

    let renderedGeneration = null;
    let disposed = false;

    root.hidden = true;
    body.hidden = true;

    heading.textContent = 'Предпросмотр черновика';
    heading.tabIndex = -1;

    explanation.textContent = 'Показан локальный снимок книги, включая несохранённые правки. Открытие ничего не сохраняет и не публикует.';

    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');

    openButton.type = 'button';
    openButton.className = 'btn btn-outline-primary';
    openButton.textContent = 'Предпросмотр всей книги';

    refreshButton.type = 'button';
    refreshButton.className = 'btn btn-outline-primary';
    refreshButton.textContent = 'Обновить предпросмотр';

    closeButton.type = 'button';
    closeButton.className = 'btn btn-outline-primary';
    closeButton.textContent = 'Закрыть предпросмотр';

    actions.className = 'rules-catalog__actions';
    actions.append(refreshButton, closeButton);
    body.append(heading, explanation, status, actions, content);
    root.append(openButton, body);
    host.append(root);

    openButton.addEventListener('click', () => {
        onOpen();
        if (!body.hidden) heading.focus();
    }, options);

    refreshButton.addEventListener('click', () => {
        onOpen();
    }, options);

    closeButton.addEventListener('click', () => {
        onClose();
        if (!root.hidden) openButton.focus();
    }, options);

    function render(state) {
        if (disposed) return;

        root.hidden = !state.available;
        body.hidden = !state.opened;
        openButton.hidden = state.opened;
        openButton.disabled = !state.available || state.busy;
        refreshButton.disabled = !state.available || state.busy;
        body.setAttribute('aria-busy', String(state.loading));

        refreshButton.textContent = state.loading
            ? 'Перезапустить сборку'
            : state.error ? 'Повторить сборку' : 'Обновить предпросмотр';

        const messages = [];

        if (state.loading) messages.push('Собираем снимок и загружаем закреплённые публикации.');
        if (state.error) messages.push(state.error);

        if (state.stale) {
            messages.push('Черновик изменился после открытия. Для актуального содержания обновите предпросмотр.');
        } else if (state.book) {
            messages.push('Снимок соответствует текущему локальному содержанию.');
        }

        status.textContent = messages.join(' ');

        if (!state.opened || !state.book) {
            content.replaceChildren();
            renderedGeneration = null;
            return;
        }

        if (renderedGeneration !== state.generation) {
            const view = createBookContent(document, state.book, { mode: 'draft' });
            content.replaceChildren(view);
            renderedGeneration = state.generation;
        }
    }

    function dispose() {
        if (disposed) return;

        disposed = true;
        events.abort();
        root.remove();
    }

    return Object.freeze({ render, dispose });
}
