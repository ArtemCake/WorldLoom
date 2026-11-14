// frontend/src/js/features/rules/draft/draft-toc-panel.js

function element(document, tag, text = '') {
    const node = document.createElement(tag);
    node.textContent = text;
    return node;
}

function actionButton(document, action, title, key = null) {
    const button = element(document, 'button', title);
    button.type = 'button';
    button.className = 'btn btn-outline-primary';
    button.dataset.tocAction = action;
    if (key !== null) button.dataset.tocKey = key;
    return button;
}

export function createDraftTocPanel({ host, onCommand, onSectionCommand }) {
    const document = host.ownerDocument;
    const window = document.defaultView;
    const events = new AbortController();
    const section = element(document, 'section');
    const heading = element(document, 'h3', 'Структура черновика');
    const hint = element(document, 'p', 'Изменения глав сохраняются общей кнопкой «Сохранить черновик».');
    const list = element(document, 'div');
    const addRoot = actionButton(document, 'add-root', 'Добавить главу');
    let current = [];
    let locked = true;
    let signature = '';

    section.dataset.authorTocEditor = '';
    section.hidden = true;
    section.append(heading, hint, addRoot, list);
    host.after(section);

    function buildBranch(parent, groups) {
        const result = element(document, 'ul');
        const siblings = groups.get(parent) || [];

        for (const [index, node] of siblings.entries()) {
            const item = element(document, 'li');
            const fallback = 'Раздел: название берётся из закреплённой публикации';
            const label = node.kind === 'chapter' ? `Глава: ${node.title}` : node.title || fallback;
            item.append(element(document, 'span', label));

            if (node.kind === 'chapter') {
                const actions = element(document, 'div');
                actions.className = 'rules-catalog__actions';

                const add = actionButton(document, 'add-child', 'Подглава', node.key);
                const rename = actionButton(document, 'rename', 'Переименовать', node.key);
                const up = actionButton(document, 'up', 'Выше', node.key);
                const down = actionButton(document, 'down', 'Ниже', node.key);
                const remove = actionButton(document, 'remove', 'Удалить пустую главу', node.key);

                for (const button of [add, rename, up, down, remove]) {
                    button.disabled = locked;
                }

                up.disabled ||= index === 0;
                down.disabled ||= index === siblings.length - 1;
                remove.disabled ||= groups.has(node.key);

                actions.append(add, rename, up, down, remove);
                item.append(actions);
            }

            if (node.kind === 'article') {
                const actions = element(document, 'div');
                actions.className = 'rules-catalog__actions';

                const up = actionButton(document, 'section-up', 'Выше', node.key);
                const down = actionButton(document, 'section-down', 'Ниже', node.key);
                const remove = actionButton(document, 'section-remove', 'Убрать из книги', node.key);

                up.disabled = locked || index === 0;
                down.disabled = locked || index === siblings.length - 1;
                remove.disabled = locked;

                actions.append(up, down, remove);
                item.append(actions);
            }

            if (groups.has(node.key)) item.append(buildBranch(node.key, groups));
            result.append(item);
        }

        return result;
    }

    function requestCommand(action, key) {
        if (action === 'add-root' || action === 'add-child') {
            const title = window.prompt('Название новой главы:');
            if (title === null) return;

            onCommand({
                type: 'add',
                key: `chapter-${window.crypto.randomUUID()}`,
                parent_key: action === 'add-root' ? null : key,
                title
            });
            return;
        }

        if (['section-up', 'section-down', 'section-remove'].includes(action)) {
            const section = current.find((node) => node.key === key && node.kind === 'article');
            if (!section) return;

            if (action === 'section-remove') {
                const title = section.title || 'выбранный раздел';

                if (window.confirm(`Убрать «${title}» из книги? Исходная публикация не удаляется.`)) {
                    onSectionCommand({ type: 'remove', key });
                }
            } else {
                onSectionCommand({ type: 'move', key, delta: action === 'section-up' ? -1 : 1 });
            }

            return;
        }

        const chapter = current.find((node) => node.key === key && node.kind === 'chapter');
        if (!chapter) return;

        if (action === 'rename') {
            const title = window.prompt('Название главы:', chapter.title);
            if (title !== null) onCommand({ type: 'rename', key, title });
        } else if (action === 'up' || action === 'down') {
            onCommand({ type: 'move', key, delta: action === 'up' ? -1 : 1 });
        } else if (action === 'remove') {
            if (window.confirm(`Удалить пустую главу «${chapter.title}»?`)) {
                onCommand({ type: 'remove', key });
            }
        }
    }

    section.addEventListener('click', (event) => {
        const button = event.target.closest?.('[data-toc-action]');
        if (!button || !section.contains(button) || button.disabled || locked) return;
        requestCommand(button.dataset.tocAction, button.dataset.tocKey);
    }, { signal: events.signal });

    function render(state) {
        section.hidden = false;
        locked = Boolean(state.busy) || state.blocked;
        addRoot.disabled = locked;
        section.setAttribute('aria-busy', String(Boolean(state.busy)));

        const nextSignature = JSON.stringify([state.toc, locked]);
        if (nextSignature === signature) return;

        const active = document.activeElement;
        const focus = section.contains(active) ? { action: active.dataset.tocAction, key: active.dataset.tocKey } : null;

        signature = nextSignature;
        current = structuredClone(state.toc);
        const groups = new Map();

        for (const node of current) {
            const siblings = groups.get(node.parent_key) || [];
            siblings.push(node);
            groups.set(node.parent_key, siblings);
        }

        for (const siblings of groups.values()) {
            siblings.sort((left, right) => left.position - right.position);
        }

        list.replaceChildren();

        if (current.length) {
            list.append(buildBranch(null, groups));
        } else {
            list.append(element(document, 'p', 'В оглавлении пока нет пунктов.'));
        }

        if (focus?.action) {
            const buttons = [...section.querySelectorAll('[data-toc-action]')];
            const target = buttons.find((button) => {
                return button.dataset.tocAction === focus.action && button.dataset.tocKey === focus.key;
            });

            if (target && !target.disabled) target.focus();
        }
    }

    function clear() {
        current = [];
        locked = true;
        signature = '';
        list.replaceChildren();
        section.hidden = true;
    }

    function dispose() {
        events.abort();
        section.remove();
    }

    return Object.freeze({ render, clear, dispose });
}
