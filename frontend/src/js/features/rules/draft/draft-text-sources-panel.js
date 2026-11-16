// frontend/src/js/features/rules/draft/draft-text-sources-panel.js

import { MAX_DRAFT_SOURCES } from './draft-source-data.js';

const FIELDS = [
    ['title', 'Название источника'],
    ['publisher', 'Издатель'],
    ['locator', 'Страница или раздел'],
    ['url', 'Адрес источника'],
    ['license_name', 'Название лицензии'],
    ['license_url', 'Адрес лицензии'],
    ['attribution', 'Атрибуция']
];

function element(document, tag, text = '') {
    const node = document.createElement(tag);
    node.textContent = text;
    return node;
}

function button(document, title) {
    const node = element(document, 'button', title);
    node.type = 'button';
    node.className = 'btn btn-outline-primary';
    return node;
}

export function createDraftSourcesPanel({ host, onCommand, title = 'Источники', hintText = 'Изменения сохраняются вместе с книгой.' }) {
    const document = host.ownerDocument;
    const events = new AbortController();
    const options = { signal: events.signal };
    const heading = element(document, 'h4', title);
    const list = element(document, 'div');
    const add = button(document, 'Добавить источник');
    const hint = element(document, 'p');
    let fields = [];
    let buttons = [];
    let current = null;
    let locked = true;
    let signature = '';

    host.replaceChildren(heading, list, add, hint);
    host.hidden = true;

    add.addEventListener('click', () => {
        if (!current || locked || current.length >= MAX_DRAFT_SOURCES) return;
        onCommand({ type: 'add' });
    }, options);

    list.addEventListener('input', (event) => {
        if (!current || locked) return;

        const input = event.target;
        if (!input.matches?.('[data-source-field]')) return;

        const index = Number(input.dataset.sourceIndex);
        onCommand({ type: 'input', index, field: input.dataset.sourceField, value: input.value });
    }, options);

    list.addEventListener('click', (event) => {
        if (!current || locked) return;

        const remove = event.target.closest?.('[data-source-remove]');
        if (!remove || !list.contains(remove) || remove.disabled) return;

        const index = Number(remove.dataset.sourceRemove);
        if (!Number.isSafeInteger(index) || !current[index]) return;

        const caption = current[index].title || `Источник ${index + 1}`;

        if (document.defaultView.confirm(`Убрать «${caption}» из списка источников?`)) {
            onCommand({ type: 'remove', index });
        }
    }, options);

    function build(sources) {
        fields = [];
        buttons = [];
        list.replaceChildren();

        for (let index = 0; index < sources.length; index += 1) {
            const group = element(document, 'fieldset');
            const legend = element(document, 'legend', `Источник ${index + 1}`);
            const remove = button(document, 'Убрать источник');

            group.append(legend);

            for (const [name, caption] of FIELDS) {
                const label = element(document, 'label', caption);
                const input = element(document, name === 'attribution' ? 'textarea' : 'input');

                input.dataset.sourceField = name;
                input.dataset.sourceIndex = String(index);

                if (name === 'attribution') {
                    input.rows = 3;
                } else {
                    input.type = 'text';
                }

                label.append(input);
                group.append(label);
                fields.push({ index, name, input });
            }

            remove.dataset.sourceRemove = String(index);
            group.append(remove);
            list.append(group);
            buttons.push(remove);
        }
    }

    function render(sources, disabled, scope = '') {
        current = sources;
        locked = Boolean(disabled);
        host.hidden = false;

        const nextSignature = JSON.stringify([scope, sources.length]);

        if (signature !== nextSignature) {
            signature = nextSignature;
            build(sources);
        }

        for (const { index, name, input } of fields) {
            const value = sources[index][name] ?? '';
            if (input.value !== value) input.value = value;
            input.readOnly = locked;
        }

        for (const remove of buttons) remove.disabled = locked;

        add.disabled = locked || sources.length >= MAX_DRAFT_SOURCES;
        hint.textContent = locked
            ? 'Изменение источников недоступно. Значения можно выделить и скопировать.'
            : `${hintText} Для адресов используйте HTTP или HTTPS.`;
    }

    function clear() {
        current = null;
        locked = true;
        signature = '';
        fields = [];
        buttons = [];
        list.replaceChildren();
        host.hidden = true;
    }

    function dispose() {
        events.abort();
        clear();
        host.replaceChildren();
    }

    return Object.freeze({ render, clear, dispose });
}

export function createDraftTextSourcesPanel({ host, onCommand }) {
    const panel = createDraftSourcesPanel({
        host,
        onCommand,
        title: 'Источники текста',
        hintText: 'Источники текста сохраняются вместе с книгой.'
    });

    function render(node, disabled) {
        panel.render(node.content.sources, disabled, node.key);
    }

    return Object.freeze({ render, clear: panel.clear, dispose: panel.dispose });
}