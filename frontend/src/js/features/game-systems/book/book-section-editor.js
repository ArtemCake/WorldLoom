// frontend/src/js/features/game-systems/book/book-section-editor.js

// Редактор одной главы механики. Глава — это технический тип параметра:
// attributes, derived, modifiers или resources. Текстовые главы книги
// этим модулем не обслуживаются.

import {mountBookAttributes} from './book-attributes.js';
import {mountBookDefinitions} from './book-definitions.js';
import {bookParameterLabel, findBookKindEntry, getBookKindEntries, isBookMechanicChapter} from './book-sections.js';
import {elementIn} from '../../../shared/dom/elements.js';

export function mountBookSection(host, options) {
    const {state, chapter, navigationHost = null, initialCode = null} = options;

    if (!isBookMechanicChapter(chapter) || chapter === 'basis') {
        throw new Error('Редактор параметров открывается только для главы механики.');
    }

    const ownerDocument = host.ownerDocument;

    let selected = initialCode;
    let child = null;
    let generation = 0;
    let destroyed = false;

    const navigation = elementIn(ownerDocument, 'div', '', 'rules-book__element-picker');
    const pickerLabel = elementIn(ownerDocument, 'label', '', 'rules-book__field');
    const picker = elementIn(ownerDocument, 'select');
    const add = elementIn(ownerDocument, 'button', 'Добавить параметр', 'btn btn-outline-primary');
    const editorHost = elementIn(ownerDocument, 'div');

    add.type = 'button';
    pickerLabel.append(elementIn(ownerDocument, 'span', 'Параметр'), picker);

    navigation.append(pickerLabel, add);
    host.replaceChildren(editorHost);

    if (navigationHost) {
        navigationHost.replaceChildren(navigation);
    } else {
        host.prepend(navigation);
    }

    function entries() {
        return getBookKindEntries(state.read().document.rules, chapter);
    }

    function selectedEntry() {
        return findBookKindEntry(state.read().document.rules, chapter, selected);
    }

    function canDiscard() {
        return !child?.isDirty() || window.confirm('Перейти без применения правок открытого параметра?');
    }

    function notifySelection() {
        options.onSelectionChange?.(selected);
    }

    function syncNavigation() {
        const snapshot = state.read();
        const writable = snapshot.mode !== 'view' && !snapshot.blocked && snapshot.writePending === null;
        const empty = elementIn(ownerDocument, 'option', 'Новый параметр');

        empty.value = '';
        picker.replaceChildren(empty);

        for (const entry of entries()) {
            const option = elementIn(ownerDocument, 'option', bookParameterLabel(entry));

            option.value = entry.id;
            picker.append(option);
        }

        picker.value = selected ?? '';
        add.disabled = !writable || !snapshot.document.rules;
    }

    function mountSelected() {
        const currentGeneration = ++generation;
        const snapshot = state.read();

        child = null;

        if (!snapshot.document.rules) {
            editorHost.replaceChildren(elementIn(ownerDocument, 'p', 'Сначала загрузите правила в главе «Основа правил».'));
            syncNavigation();
            return;
        }

        const entry = selectedEntry();

        if (selected !== null && !entry) selected = null;

        const hiddenNavigation = elementIn(ownerDocument, 'div');
        const mountEditor = chapter === 'attributes' ? mountBookAttributes : mountBookDefinitions;

        const childOptions = {
            state,
            chapter,
            initialCode: entry?.code ?? null,
            navigationHost: hiddenNavigation,
            defaultSection: options.defaultSection ?? '',

            onTitleChange(title) {
                if (destroyed || generation !== currentGeneration) return;

                options.onTitleChange?.(title);
            },

            onSelectionChange(code) {
                if (destroyed || generation !== currentGeneration) return;

                const rules = state.read().document.rules;
                const candidate = code === null ? null : `${chapter}:${code}`;
                const current = findBookKindEntry(rules, chapter, candidate);

                selected = current?.id ?? null;

                syncNavigation();
                notifySelection();

                // После переноса параметра в другую главу текста открываем
                // новую форму только после завершения render() внутреннего редактора.
                if (candidate !== null && current === null) {
                    queueMicrotask(() => {
                        if (destroyed || generation !== currentGeneration) return;

                        mountSelected();
                    });
                }
            },

            onCommit() {
                if (destroyed || generation !== currentGeneration) return;

                options.onCommit?.();
            }
        };

        syncNavigation();
        child = mountEditor(editorHost, childOptions);
        options.onTitleChange?.(entry?.definition.label || 'Новый параметр');
    }

    function open(id) {
        if (destroyed) return false;

        const rules = state.read().document.rules;

        if (id !== null && !findBookKindEntry(rules, chapter, id)) {
            throw new Error('Параметр отсутствует в выбранной главе.');
        }

        if (!canDiscard()) return false;

        selected = id;
        mountSelected();

        return true;
    }

    picker.addEventListener('change', () => {
        if (!open(picker.value || null)) picker.value = selected ?? '';
    });

    add.addEventListener('click', () => {
        if (!open(null)) return;

        options.onCreate?.();
    });

    mountSelected();

    return {
        isDirty: () => child?.isDirty() === true,
        getSelectedCode: () => selected,
        selectItem: open,

        destroy() {
            destroyed = true;
            generation += 1;
            child = null;
        }
    };
}
