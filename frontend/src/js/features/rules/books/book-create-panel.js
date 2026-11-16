// frontend/src/js/features/rules/books/book-create-panel.js

import { NEW_BOOK_DEFAULTS } from './book-create-data.js';

function required(root, selector) {
    const node = root.querySelector(selector);
    if (!node) throw new Error('Не найден элемент формы создания книги.');
    return node;
}

export function createBookCreationPanel({ root, onOpen, onCancel, onInput, onSubmit }) {
    const events = new AbortController();
    const options = { signal: events.signal };
    const host = required(root, '[data-book-create]');
    const open = required(host, '[data-book-create-open]');
    const form = required(host, '[data-book-create-form]');
    const heading = required(form, '[data-book-create-heading]');
    const error = required(form, '[data-book-create-error]');
    const submit = required(form, '[data-book-create-submit]');
    const cancel = required(form, '[data-book-create-cancel]');
    const fields = new Map();
    let current = null;

    for (const name of Object.keys(NEW_BOOK_DEFAULTS)) {
        fields.set(name, required(form, `[name="${name}"]`));
    }

    const system = fields.get('system_id');
    const hasSystems = [...system.options].some((option) => Boolean(option.value));

    open.disabled = !hasSystems;
    open.addEventListener('click', onOpen, options);
    cancel.addEventListener('click', onCancel, options);

    form.addEventListener('input', (event) => {
        const input = fields.get(event.target.name);
        if (input !== event.target || !current || current.busy || current.blocked || current.bookId) return;
        onInput(input.name, input.value);
    }, options);

    form.addEventListener('submit', (event) => {
        event.preventDefault();
        if (!current || current.busy || current.blocked) return;
        if (!current.bookId && !form.reportValidity()) return;
        onSubmit();
    }, options);

    function render(state) {
        current = state;
        form.hidden = !state.opened;
        open.hidden = state.opened;
        open.disabled = !hasSystems || state.busy;
        cancel.disabled = state.busy;
        submit.disabled = state.busy || state.blocked;
        form.setAttribute('aria-busy', String(state.busy));

        const locked = state.busy || state.blocked || Boolean(state.bookId);

        for (const [name, input] of fields) {
            if (input.value !== state.values[name]) input.value = state.values[name];

            if (input.tagName === 'SELECT') {
                input.disabled = locked;
            } else {
                input.readOnly = locked;
            }
        }

        error.textContent = state.error;
        error.hidden = !state.error;

        if (state.busy) {
            submit.textContent = state.bookId ? 'Открытие черновика…' : 'Создание книги…';
        } else {
            submit.textContent = state.bookId ? 'Открыть созданную книгу' : 'Создать и открыть';
        }

        cancel.textContent = state.blocked || state.bookId ? 'К списку книг' : 'Отмена';
    }

    function focus() {
        heading.focus();
    }

    function focusOpen() {
        open.focus();
    }

    function dispose() {
        events.abort();
    }

    return Object.freeze({ render, focus, focusOpen, dispose });
}
