// frontend/src/js/features/rules/draft/draft-editor-panel.js

const FIELDS = [
    { name: 'title', label: 'Название', limit: 200 },
    { name: 'summary', label: 'Описание', limit: 5000, multiline: true },
    { name: 'language', label: 'Код языка', limit: 20 },
    { name: 'edition_key', label: 'Код редакции', limit: 100 },
    { name: 'introduction', label: 'Введение', limit: 300000, multiline: true }
];

function button(document, title) {
    const node = document.createElement('button');
    node.type = 'button';
    node.className = 'btn btn-outline-primary';
    node.textContent = title;
    return node;
}

export function createDraftEditorPanel({ host, onInput, onSave, onReload }) {
    const document = host.ownerDocument;
    const events = new AbortController();
    const options = { signal: events.signal };
    const form = document.createElement('form');
    const fields = new Map();
    const heading = document.createElement('h3');
    const status = document.createElement('p');
    const error = document.createElement('p');
    const hint = document.createElement('p');
    const actions = document.createElement('div');
    const save = button(document, 'Сохранить черновик');
    const reload = button(document, 'Загрузить серверный черновик');

    form.className = 'rules-book__definition-form';
    form.dataset.authorEditForm = '';
    form.noValidate = true;
    heading.textContent = 'Сведения и введение книги';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    error.setAttribute('role', 'alert');
    actions.className = 'rules-catalog__actions';
    save.type = 'submit';
    save.className = 'btn btn-primary';
    hint.textContent = 'Кнопка сохраняет сведения, введение и оглавление. Список источников книги, категория и аудитория не изменяются.';
    form.append(heading, hint);

    for (const field of FIELDS) {
        const label = document.createElement('label');
        const title = document.createElement('span');
        const input = document.createElement(field.multiline ? 'textarea' : 'input');

        title.textContent = field.label;
        input.name = field.name;
        input.dataset.authorField = field.name;
        input.autocomplete = 'off';

        if (field.multiline) input.rows = field.name === 'introduction' ? 12 : 4;

        input.addEventListener('input', () => onInput(field.name, input.value), options);
        label.append(title, input);
        form.append(label);
        fields.set(field.name, input);
    }

    form.addEventListener('submit', (event) => {
        event.preventDefault();
        onSave();
    }, options);

    reload.addEventListener('click', onReload, options);
    actions.append(save, reload);
    form.append(status, error, actions);
    host.replaceChildren(form);
    host.hidden = true;

    function render(state) {
        host.hidden = false;

        for (const [name, input] of fields) {
            const value = state.values[name] ?? '';
            if (input.value !== value) input.value = value;
            input.readOnly = Boolean(state.busy) || state.blocked;
        }

        form.setAttribute('aria-busy', String(Boolean(state.busy)));
        save.disabled = !state.canSave;
        reload.disabled = Boolean(state.busy);

        if (state.busy) {
            status.textContent = state.busy === 'save' ? 'Ожидаем результат сохранения…' : 'Загружаем серверный черновик…';
        } else {
            status.textContent = state.message || (state.dirty ? 'Есть несохранённые изменения.' : `Ревизия ${state.revision}.`);
        }

        error.textContent = state.error;
        error.hidden = !state.error;
        hint.textContent = state.blocked
            ? 'Запись заблокирована. Текст можно выделить и скопировать. Загрузка с сервера заменит локальную форму.'
            : 'Кнопка сохраняет сведения, введение и оглавление. Список источников книги, категория и аудитория не изменяются.';
    }

    function clear() {
        host.hidden = true;
        for (const input of fields.values()) input.value = '';
        status.textContent = '';
        error.textContent = '';
    }

    function dispose() {
        events.abort();
        host.replaceChildren();
        host.hidden = true;
    }

    return Object.freeze({ render, clear, dispose });
}
