// frontend/src/js/features/rules/draft/draft-text-panel.js

import { createDraftTextSourcesPanel } from './draft-text-sources-panel.js';

const FIELDS = [
    { name: 'title', label: 'Название текста' },
    { name: 'summary', label: 'Описание', rows: 3 },
    { name: 'body', label: 'Содержание', rows: 16 },
    { name: 'language', label: 'Код языка' },
    { name: 'edition_key', label: 'Код редакции' },
    {
        name: 'audience',
        label: 'Аудитория',
        choices: [['both', 'Все'], ['players', 'Игроки'], ['gm', 'Ведущий']]
    },
    {
        name: 'rule_kind',
        label: 'Вид правила',
        choices: [
            ['base', 'Основное'],
            ['optional', 'Дополнительное правило'],
            ['supplement', 'Дополнение'],
            ['homebrew', 'Авторское']
        ]
    }
];

function element(document, tag, text = '') {
    const node = document.createElement(tag);
    node.textContent = text;
    return node;
}

function option(document, value, title) {
    const node = element(document, 'option', title);
    node.value = value;
    return node;
}

function button(document, title) {
    const node = element(document, 'button', title);
    node.type = 'button';
    node.className = 'btn btn-outline-primary';
    return node;
}

export function createDraftTextPanel({ host, onAdd, onInput, onRemove, onSource }) {
    const document = host.ownerDocument;
    const events = new AbortController();
    const options = { signal: events.signal };
    const section = element(document, 'section');
    const heading = element(document, 'h3', 'Собственные тексты книги');
    const hint = element(document, 'p');
    const parentLabel = element(document, 'label', 'Куда добавить текст');
    const parent = element(document, 'select');
    const add = button(document, 'Добавить собственный текст');
    const selectedLabel = element(document, 'label', 'Редактируемый текст');
    const selected = element(document, 'select');
    const editor = element(document, 'div');
    const sources = element(document, 'div');
    const remove = button(document, 'Убрать собственный текст');
    const fields = new Map();
    let current = null;
    let selectedKey = '';
    let listSignature = '';
    let parentSignature = '';

    const sourcePanel = createDraftTextSourcesPanel({
        host: sources,
        onCommand: (command) => {
            if (!current || current.busy || current.blocked || !selectedKey) return;
            onSource(selectedKey, command);
        }
    });

    section.dataset.authorTextEditor = '';
    section.hidden = true;
    parent.dataset.textParent = '';
    selected.dataset.textSelected = '';
    parentLabel.append(parent);
    selectedLabel.append(selected);

    for (const field of FIELDS) {
        const label = element(document, 'label');
        const title = element(document, 'span', field.label);
        const tag = field.choices ? 'select' : field.rows ? 'textarea' : 'input';
        const input = element(document, tag);

        input.dataset.textField = field.name;
        input.autocomplete = 'off';

        if (tag === 'input') input.type = 'text';
        if (field.rows) input.rows = field.rows;

        for (const [value, caption] of field.choices || []) {
            input.append(option(document, value, caption));
        }

        input.addEventListener(field.choices ? 'change' : 'input', () => {
            if (!current || current.busy || current.blocked || !selectedKey) return;
            onInput(selectedKey, field.name, input.value);
        }, options);

        label.append(title, input);
        editor.append(label);
        fields.set(field.name, input);
    }

    editor.append(sources, remove);
    section.append(heading, hint, parentLabel, add, selectedLabel, editor);
    host.after(section);

    add.addEventListener('click', () => {
        if (!current || current.busy || current.blocked) return;
        onAdd(parent.value || null);
    }, options);

    selected.addEventListener('change', () => {
        selectedKey = selected.value;
        if (current) render(current);
    }, options);

    remove.addEventListener('click', () => {
        if (!current || current.busy || current.blocked) return;

        const node = current.toc.find((item) => item.key === selectedKey && item.kind === 'text');
        if (!node) return;

        const question = `Убрать собственный текст «${node.content.title || 'Без названия'}»? Изменение потребуется сохранить.`;

        if (document.defaultView.confirm(question)) onRemove(node.key);
    }, options);

    function renderParents(state) {
        const chapters = state.toc.filter((node) => node.kind === 'chapter');
        const signature = JSON.stringify(chapters.map((node) => [node.key, node.title]));

        if (signature === parentSignature) return;

        parentSignature = signature;
        const previous = parent.value;
        parent.replaceChildren(option(document, '', 'В корень книги'));

        for (const chapter of chapters) {
            parent.append(option(document, chapter.key, `${chapter.title} (${chapter.key})`));
        }

        parent.value = chapters.some((node) => node.key === previous) ? previous : '';
    }

    function renderChoices(texts) {
        const signature = JSON.stringify(texts.map((node) => [node.key, node.content.title]));

        if (signature !== listSignature) {
            listSignature = signature;
            selected.replaceChildren();

            for (const node of texts) {
                selected.append(option(document, node.key, node.content.title || 'Без названия'));
            }
        }

        if (!texts.some((node) => node.key === selectedKey)) {
            selectedKey = texts[0]?.key || '';
        }

        selected.value = selectedKey;
    }

    function render(state) {
        current = state;
        section.hidden = state.schemaVersion !== 2;
        if (section.hidden) return;

        const locked = Boolean(state.busy) || state.blocked;
        const texts = state.toc.filter((node) => node.kind === 'text');

        renderParents(state);
        renderChoices(texts);
        parent.disabled = locked;
        add.disabled = locked;
        selected.disabled = Boolean(state.busy) || !texts.length;
        section.setAttribute('aria-busy', String(Boolean(state.busy)));

        hint.textContent = state.blocked
            ? 'Запись заблокирована. Можно выбрать текст и скопировать его из полей.'
            : 'Все изменения записываются общей кнопкой «Сохранить черновик».';

        const node = texts.find((item) => item.key === selectedKey);
        editor.hidden = !node;
        selectedLabel.hidden = !texts.length;
        if (!node) {
            sourcePanel.clear();
            return;
        }

        for (const [name, input] of fields) {
            const value = node.content[name] ?? '';
            if (input.value !== value) input.value = value;

            if (input.tagName === 'SELECT') {
                input.disabled = locked;
            } else {
                input.readOnly = locked;
            }
        }

        remove.disabled = locked;
        sourcePanel.render(node, locked);
    }

    function select(key) {
        selectedKey = key;
        if (current) render(current);
    }

    function clear() {
        current = null;
        selectedKey = '';
        listSignature = '';
        parentSignature = '';
        parent.replaceChildren();
        selected.replaceChildren();
        sourcePanel.clear();
        for (const input of fields.values()) input.value = '';
        section.hidden = true;
    }

    function dispose() {
        events.abort();
        sourcePanel.dispose();
        section.remove();
    }

    return Object.freeze({ render, select, clear, dispose });
}
