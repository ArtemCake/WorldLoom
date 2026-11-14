// frontend/src/js/features/rules/authoring/authoring-page.js

import { booksApi } from '../books/books-api.js';
import { bookAuthoringApi } from '../books/book-authoring-api.js';
import { createAuthoringController } from './authoring-controller.js';
import { authorElement, createAuthoringView } from './authoring-view.js';
import { createBookDraftEditor } from '../draft/draft-editor-state.js';
import { createDraftEditorPanel } from '../draft/draft-editor-panel.js';
import { createAuthoringNavigation } from './authoring-navigation.js';
import { createDraftTocPanel } from '../draft/draft-toc-panel.js';
import { articlesApi } from '../articles-api.js';
import { createSectionPicker } from './section-picker-state.js';
import { createSectionPickerPanel } from './section-picker-panel.js';

const instances = new Map();
let cleanupBound = false;

function destroy(root) {
    const instance = instances.get(root);
    if (!instance) return;

    instance.dispose();
    instances.delete(root);
}

function bindCleanup() {
    if (cleanupBound) return;
    cleanupBound = true;

    document.addEventListener('htmx:beforeCleanupElement', (event) => {
        const element = event.detail?.elt || event.target;

        for (const root of instances.keys()) {
            if (element === root || element?.contains?.(root)) destroy(root);
        }
    });
}

function formFilters(form) {
    const values = new FormData(form);
    const filters = {};

    for (const key of ['system_id', 'q', 'edition_key', 'language']) {
        filters[key] = String(values.get(key) || '');
    }

    return filters;
}

function mountWorkspace(root) {
    const form = authorElement(root, '[data-author-filters]');
    const reload = authorElement(root, '[data-author-reload]');
    const more = authorElement(root, '[data-author-more]');
    const retry = authorElement(root, '[data-author-retry]');
    const back = authorElement(root, '[data-author-back]');
    const draftRetry = authorElement(root, '[data-author-draft-retry]');
    const heading = authorElement(root, '[data-author-heading]');
    const system = authorElement(form, '[name="system_id"]');
    const search = authorElement(form, '[name="q"]');
    const host = authorElement(root, '[data-author-edit]');
    const view = createAuthoringView(root);
    const events = new AbortController();
    const options = { signal: events.signal };
    let editor = null;

    function act(action) {
        view.showNotice('');

        void Promise.resolve().then(action).catch((failure) => {
            if (events.signal.aborted) return;
            view.showNotice(failure?.message || 'Не удалось выполнить действие.');
        });
    }

    const panel = createDraftEditorPanel({
        host,
        onInput: (field, value) => editor?.change(field, value),
        onSave: () => act(saveDraft),
        onReload: () => act(reloadDraft)
    });

    const tocPanel = createDraftTocPanel({
        host,
        onCommand: (command) => act(() => editor?.chapter(command)),
        onSectionCommand: (command) => act(() => editor?.section(command))
    });

    const pickerPanel = createSectionPickerPanel({
        host,
        onSearch: (query) => act(() => picker.search(query)),
        onNext: () => act(() => picker.next()),
        onSelect: (articleId) => act(() => picker.select(articleId)),
        onAttach: (parentKey) => act(() => attachSection(parentKey)),
        onClose: () => picker.close()
    });

    const picker = createSectionPicker({ api: articlesApi, onChange: pickerPanel.renderPicker });

    function attachSection(parentKey) {
        if (!editor) return;

        const selected = picker.getState();
        if (!selected.opened || selected.reading || !selected.publication) return;

        const added = editor.section({
            type: 'attach',
            key: `section-${root.ownerDocument.defaultView.crypto.randomUUID()}`,
            parent_key: parentKey,
            publication: selected.publication
        });

        if (!added) return;

        picker.close();
        view.showNotice('Раздел добавлен в локальное оглавление. Сохраните черновик, чтобы записать изменения.');
    }

    function renderEditor(state) {
        panel.render(state);
        tocPanel.render(state);
        pickerPanel.renderEditor(state);
    }

    function renderWorkspace(state) {
        view.render(state);

        if (!state.editor) {
            editor?.dispose();
            editor = null;
            panel.clear();
            tocPanel.clear();
            picker.close();
            pickerPanel.clear();
            return;
        }

        if (!editor) {
            editor = createBookDraftEditor({
                draft: state.editor.draft,
                api: booksApi,
                onChange: renderEditor
            });
        }

        renderEditor(editor.getState());
    }

    const controller = createAuthoringController({ api: bookAuthoringApi, onChange: renderWorkspace });
    const navigation = createAuthoringNavigation({
        root,
        getState: () => editor?.getState(),
        notify: view.showNotice
    });

    async function saveDraft() {
        if (!editor) return;
        const saved = await editor.save();
        if (saved && !events.signal.aborted) controller.acceptDraft(saved);
    }

    async function reloadDraft() {
        if (!editor || !navigation.allow()) return;
        const loaded = await editor.reload();
        if (loaded && !events.signal.aborted) {
            picker.close();
            controller.acceptDraft(loaded);
        }
    }

    function submit() {
        if (form.reportValidity()) act(() => controller.reload(formFilters(form)));
    }

    form.addEventListener('submit', (event) => {
        event.preventDefault();
        submit();
    }, options);

    system.addEventListener('change', submit, options);
    reload.addEventListener('click', submit, options);
    more.addEventListener('click', () => act(() => controller.next()), options);

    retry.addEventListener('click', () => {
        const state = controller.getState();
        act(() => state.nextAfter ? controller.next() : controller.reload());
    }, options);

    root.addEventListener('click', (event) => {
        const button = event.target.closest?.('[data-author-open]');
        if (!button || !root.contains(button)) return;

        act(() => {
            if (!navigation.allow()) return;
            const pending = controller.open(button.dataset.authorOpen);
            heading.focus();
            return pending;
        });
    }, options);

    back.addEventListener('click', () => {
        if (!navigation.allow()) return;
        controller.close();
        search.focus();
    }, options);

    draftRetry.addEventListener('click', () => {
        const { selectedId } = controller.getState();
        if (selectedId) act(() => controller.open(selectedId));
    }, options);

    function dispose() {
        events.abort();
        navigation.dispose();
        editor?.dispose();
        controller.dispose();
        panel.dispose();
        tocPanel.dispose();
        picker.dispose();
        pickerPanel.dispose();
    }

    instances.set(root, { dispose });
    submit();
}

export function initRulesWorkspace() {
    bindCleanup();

    for (const root of instances.keys()) {
        if (!root.isConnected) destroy(root);
    }

    for (const root of document.querySelectorAll('[data-rules-workspace]')) {
        if (!instances.has(root)) mountWorkspace(root);
    }
}
