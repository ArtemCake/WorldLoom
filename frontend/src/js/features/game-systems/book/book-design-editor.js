// frontend/src/js/features/game-systems/book/book-design-editor.js

import {BOOK_CHAPTER_STATUS, findDesignChapter} from './book-design-catalog.js';
import {writeDesignChapter} from './book-design-data.js';
import {elementIn} from '../../../shared/dom/elements.js';

export function mountBookDesign(host, {state, chapter, onChange = () => {}}) {
    const specification = findDesignChapter(chapter);

    if (!specification) return;

    const snapshot = state.read();

    if (!snapshot.document.rules) return;

    const ownerDocument = host.ownerDocument;
    const saved = snapshot.document.rules.rulebook?.[chapter];
    const current = saved ?? {label: specification.title, status: 'draft', fields: {}};

    const details = elementIn(ownerDocument, 'details', '', 'rules-book__design');
    const summary = elementIn(ownerDocument, 'summary', 'Описание и проектирование правил');
    const form = elementIn(ownerDocument, 'fieldset', '', 'rules-book__definition-form');
    const error = elementIn(ownerDocument, 'p', '', 'rules-book__error');
    const status = elementIn(ownerDocument, 'select');
    const controls = new Map();

    form.disabled = snapshot.mode === 'view' || snapshot.blocked || snapshot.writePending !== null;
    error.hidden = true;
    error.setAttribute('role', 'alert');

    for (const [code, title] of Object.entries(BOOK_CHAPTER_STATUS)) {
        const option = elementIn(ownerDocument, 'option', title);

        option.value = code;
        status.append(option);
    }

    status.value = current.status ?? 'draft';

    const statusLabel = elementIn(ownerDocument, 'label', '', 'rules-book__field');

    statusLabel.append(elementIn(ownerDocument, 'span', 'Состояние описания'), status);
    form.append(statusLabel);

    const fields = {
        ...specification.fields,
        ...Object.fromEntries(Object.keys(current.fields ?? {}).map((code) => [code, specification.fields[code] ?? code]))
    };

    for (const [code, prompt] of Object.entries(fields)) {
        const label = elementIn(ownerDocument, 'label', '', 'rules-book__field');
        const input = elementIn(ownerDocument, 'textarea');

        input.rows = 4;
        input.maxLength = 10000;
        input.value = current.fields?.[code] ?? '';

        label.append(elementIn(ownerDocument, 'span', prompt), input);
        controls.set(code, input);
        form.append(label);
    }

    function apply() {
        error.hidden = true;
        error.textContent = '';

        try {
            const before = state.read().document.rules.rulebook?.[chapter];
            const values = {...(before?.fields ?? {})};

            for (const [code, input] of controls) {
                if (input.value.length || Object.hasOwn(values, code)) {
                    values[code] = input.value;
                }
            }

            const changed = state.update((draft) => {
                writeDesignChapter(draft, chapter, {
                    label: before?.label ?? specification.title,
                    status: status.value,
                    fields: values
                });
            });

            if (changed) onChange();
        } catch (failure) {
            error.textContent = failure instanceof Error ? failure.message : 'Не удалось изменить описание.';
            error.hidden = false;
        }
    }

    form.addEventListener('input', apply);
    form.addEventListener('change', apply);

    const note = elementIn(ownerDocument, 'p', 'Правки входят в черновик книги. Для записи на сервер используйте «Сохранить».');
    const warning = elementIn(ownerDocument, 'p', 'Описание не выполняет игровые действия автоматически.', 'rules-book__muted');

    details.append(summary, note, warning, error, form);
    host.replaceChildren(details);
}