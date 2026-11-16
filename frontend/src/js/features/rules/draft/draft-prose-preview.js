// frontend/src/js/features/rules/draft/draft-prose-preview.js

import { createBookProse } from '../books/book-prose-view.js';

export function createDraftProsePreview({ document, title = 'Предпросмотр текста' }) {
    const events = new AbortController();
    const root = document.createElement('details');
    const summary = document.createElement('summary');
    const hint = document.createElement('p');
    const content = document.createElement('div');
    let current = '';
    let rendered = null;
    let disposed = false;

    summary.textContent = title;
    hint.textContent = 'Локальный предпросмотр. Открытие не сохраняет и не публикует изменения.';
    root.append(summary, hint, content);

    function draw() {
        if (disposed || !root.open || rendered === current) return;

        const next = current.trim()
            ? createBookProse(document, current)
            : document.createElement('p');

        if (!current.trim()) next.textContent = 'Текст пока не добавлен.';

        content.replaceChildren(next);
        rendered = current;
    }

    root.addEventListener('toggle', draw, { signal: events.signal });

    function render(value) {
        if (disposed) return;
        if (typeof value !== 'string') throw new TypeError('Текст предпросмотра должен быть строкой.');

        current = value;
        draw();
    }

    function clear() {
        current = '';
        rendered = null;
        root.open = false;
        content.replaceChildren();
    }

    function dispose() {
        disposed = true;
        events.abort();
        clear();
        root.remove();
    }

    return Object.freeze({ root, render, clear, dispose });
}
