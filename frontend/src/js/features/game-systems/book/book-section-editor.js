// frontend/src/js/features/game-systems/book/book-section-editor.js

import {mountBookAttributes} from './book-attributes.js';
import {mountBookDefinitions} from './book-definitions.js';
import {isBookModifierCode} from './book-definition-data.js';
import {bookParameterId, bookParameterLabel, bookRuleSectionTitle} from './book-sections.js';
import {findBookSectionEntry, getBookSectionEntries} from './book-sections.js';

const creationTypes = [
    ['attributes', 'Исходное значение'],
    ['derived', 'Вычисляемый показатель'],
    ['modifiers', 'Вычисляемый модификатор'],
    ['resources', 'Ресурс']
];

export function mountBookSection(host, options) {
    const {state, chapter, navigationHost = null, initialCode = null} = options;
    const ownerDocument = host.ownerDocument;
    const defaultSection = bookRuleSectionTitle(chapter);

    let selected = initialCode;
    let creationType = 'attributes';
    let child = null;
    let generation = 0;
    let destroyed = false;

    function node(tag, text = '', className = '') {
        const result = ownerDocument.createElement(tag);

        result.textContent = text;
        if (className) result.className = className;

        return result;
    }

    const navigation = node('div', '', 'rules-book__element-picker');
    const pickerLabel = node('label', '', 'rules-book__field');
    const picker = node('select');
    const typeLabel = node('label', '', 'rules-book__field');
    const type = node('select');
    const add = node('button', 'Добавить параметр', 'btn btn-outline-primary');
    const editorHost = node('div');

    add.type = 'button';
    pickerLabel.append(node('span', 'Параметр раздела'), picker);
    typeLabel.append(node('span', 'Тип нового параметра'), type);

    for (const [value, title] of creationTypes) {
        const option = node('option', title);

        option.value = value;
        type.append(option);
    }

    navigation.append(pickerLabel, typeLabel, add);
    host.replaceChildren(editorHost);

    if (navigationHost) {
        navigationHost.replaceChildren(navigation);
    } else {
        host.prepend(navigation);
    }

    function entries() {
        return getBookSectionEntries(state.read().document.rules, chapter);
    }

    function selectedEntry() {
        return findBookSectionEntry(state.read().document.rules, chapter, selected);
    }

    function technicalChapter(entry) {
        if (entry.kind !== 'derived') return entry.kind;

        return isBookModifierCode(entry.code) ? 'modifiers' : 'derived';
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
        const empty = node('option', 'Новый параметр');

        empty.value = '';
        picker.replaceChildren(empty);

        for (const entry of entries()) {
            const option = node('option', bookParameterLabel(entry));

            option.value = entry.id;
            picker.append(option);
        }

        picker.value = selected ?? '';
        type.value = creationType;
        type.disabled = !writable || !snapshot.document.rules;
        add.disabled = !writable || !snapshot.document.rules;
    }

    function mountSelected() {
        const currentGeneration = ++generation;
        const snapshot = state.read();

        child = null;

        if (!snapshot.document.rules) {
            editorHost.replaceChildren(node('p', 'Сначала загрузите правила в главе «Основа правил».'));
            syncNavigation();
            return;
        }

        const entry = selectedEntry();

        if (selected !== null && !entry) selected = null;
        if (entry) creationType = technicalChapter(entry);

        const childChapter = entry ? technicalChapter(entry) : creationType;
        const hiddenNavigation = node('div');
        const mountEditor = childChapter === 'attributes' ? mountBookAttributes : mountBookDefinitions;

        const childOptions = {
            state,
            chapter: childChapter,
            initialCode: entry?.code ?? null,
            navigationHost: hiddenNavigation,
            defaultSection,

            onTitleChange(title) {
                if (destroyed || generation !== currentGeneration) return;

                options.onTitleChange?.(title);
            },

            onSelectionChange(code) {
                if (destroyed || generation !== currentGeneration) return;

                const kind = childChapter === 'modifiers' ? 'derived' : childChapter;
                const candidate = code === null ? null : bookParameterId(kind, code);
                const rules = state.read().document.rules;
                const current = findBookSectionEntry(rules, chapter, candidate);

                selected = current?.id ?? null;

                syncNavigation();
                notifySelection();

                // После переноса параметра в другой раздел открываем новую форму
                // только после завершения render() внутреннего редактора.
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

        if (id !== null && !findBookSectionEntry(rules, chapter, id)) {
            throw new Error('Параметр отсутствует в выбранном разделе.');
        }

        if (!canDiscard()) return false;

        selected = id;
        mountSelected();

        return true;
    }

    picker.addEventListener('change', () => {
        if (!open(picker.value || null)) picker.value = selected ?? '';
    });

    type.addEventListener('change', () => {
        const previous = creationType;

        if (!canDiscard()) {
            type.value = previous;
            return;
        }

        creationType = type.value;
        selected = null;
        mountSelected();
        options.onCreate?.();
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
