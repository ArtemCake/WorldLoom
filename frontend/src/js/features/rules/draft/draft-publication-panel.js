// frontend/src/js/features/rules/draft/draft-publication-panel.js

function element(document, tag, text = '') {
    const node = document.createElement(tag);
    node.textContent = text;
    return node;
}

export function createDraftPublicationPanel({ host, onPublish }) {
    const document = host.ownerDocument;
    const events = new AbortController();
    const section = element(document, 'section');
    const heading = element(document, 'h3', 'Публикация книги');
    const hint = element(document, 'p');
    const last = element(document, 'p');
    const publish = element(document, 'button', 'Выпустить новую версию книги');
    let allowed = false;

    section.hidden = true;
    section.dataset.authorPublication = '';
    publish.type = 'button';
    publish.className = 'btn btn-primary';
    last.setAttribute('role', 'status');
    last.setAttribute('aria-live', 'polite');
    section.append(heading, hint, last, publish);
    host.after(section);

    publish.addEventListener('click', () => {
        if (allowed) onPublish();
    }, { signal: events.signal });

    function render(state) {
        section.hidden = false;
        allowed = Boolean(state.canPublish);
        publish.disabled = !allowed;
        section.setAttribute('aria-busy', String(state.busy === 'publish'));

        last.hidden = !state.lastPublication;
        last.textContent = state.lastPublication
            ? `Последний подтверждённый здесь выпуск: ${state.lastPublication.version_number}.`
            : '';

        if (state.busy === 'publish') {
            hint.textContent = 'Ожидаем результат публикации и проверяем состояние черновика.';
        } else if (state.busy) {
            hint.textContent = 'Завершите текущую операцию перед публикацией.';
        } else if (state.blocked) {
            hint.textContent = 'Перед публикацией необходимо загрузить актуальный серверный черновик.';
        } else if (state.dirty) {
            hint.textContent = 'Сначала сохраните изменения. Публикация выпускает только сохранённое содержание.';
        } else if (!state.toc.some((node) => node.kind === 'article')) {
            hint.textContent = 'Добавьте в книгу хотя бы один опубликованный раздел и сохраните черновик.';
        } else if (!allowed) {
            hint.textContent = 'Это состояние уже опубликовано в текущем сеансе редактирования.';
        } else {
            hint.textContent = 'Будет создана неизменяемая версия книги. Видимость и закреплённые материалы не меняются.';
        }
    }

    function clear() {
        allowed = false;
        section.hidden = true;
        publish.disabled = true;
        last.textContent = '';
    }

    function dispose() {
        events.abort();
        section.remove();
    }

    return Object.freeze({ render, clear, dispose });
}