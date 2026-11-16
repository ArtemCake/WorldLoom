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
import { createDraftPublicationPanel } from '../draft/draft-publication-panel.js';
import { createSectionReplacement } from '../draft/draft-section-replacement-state.js';
import { createSectionReplacementPanel } from '../draft/draft-section-replacement-panel.js';
import { createDraftTextPanel } from '../draft/draft-text-panel.js';
import { createBookCreation } from '../books/book-create-state.js';
import { createBookCreationPanel } from '../books/book-create-panel.js';
import { createDraftPreviewSession } from '../draft/draft-book-preview-session.js';
import { createDraftBookPreviewPanel } from '../draft/draft-book-preview-panel.js';

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
        onReload: () => act(reloadDraft),
        onBookSource: (command) => act(() => editor?.bookSource(command))
    });

    const tocPanel = createDraftTocPanel({
        host,
        onCommand: (command) => act(() => editor?.chapter(command)),
        onSectionCommand: (command) => act(() => editor?.section(command)),
        onTextCommand: (command) => act(() => editor?.text(command))
    });

    const textPanel = createDraftTextPanel({
        host,
        onAdd: (parentKey) => act(() => addText(parentKey)),
        onInput: (key, field, value) => act(() => editor?.changeText(key, field, value)),
        onRemove: (key) => act(() => editor?.text({ type: 'remove', key })),
        onSource: (key, command) => act(() => editor?.textSource(key, command))
    });

    const pickerPanel = createSectionPickerPanel({
        host,
        onSearch: (query) => act(() => picker.search(query)),
        onNext: () => act(() => picker.next()),
        onSelect: (articleId) => act(() => picker.select(articleId)),
        onAttach: (parentKey) => act(() => attachSection(parentKey)),
        onClose: () => picker.close()
    });

    const replacementPanel = createSectionReplacementPanel({
        host,
        onCompare: (key) => act(() => compareSection(key)),
        onApply: () => act(applyReplacement),
        onClose: () => replacement.close()
    });

    const replacement = createSectionReplacement({
        api: articlesApi,
        onChange: replacementPanel.renderComparison
    });

    const picker = createSectionPicker({
        api: articlesApi,
        onChange: (state) => {
            pickerPanel.renderPicker(state);
            replacementPanel.renderPicker(state);
        }
    });
    const publicationPanel = createDraftPublicationPanel({ host, onPublish: () => act(publishDraft) });
    const previewPanel = createDraftBookPreviewPanel({
        host,
        onOpen: () => preview.open(),
        onClose: () => preview.close()
    });

    const preview = createDraftPreviewSession({
        loadVersion: (versionId, options) => articlesApi.getVersionById(versionId, options),
        onChange: previewPanel.render
    });

    previewPanel.render(preview.getState());

    function addText(parentKey) {
        if (!editor) return;

        const state = editor.getState();
        if (state.busy || state.blocked || state.schemaVersion !== 2) return;

        const siblings = state.toc.filter((node) => node.parent_key === parentKey);
        const position = siblings.reduce((maximum, node) => Math.max(maximum, node.position), -1) + 1;
        const key = `text-${root.ownerDocument.defaultView.crypto.randomUUID()}`;
        const node = {
            kind: 'text',
            key,
            parent_key: parentKey,
            position,
            title: null,
            content: {
                schema_version: 1,
                title: 'Новый раздел',
                summary: '',
                body: '',
                language: state.values.language,
                edition_key: state.values.edition_key,
                audience: 'both',
                rule_kind: 'base',
                sources: []
            }
        };

        if (!editor.text({ type: 'add', node })) return;

        textPanel.select(key);
        view.showNotice('Собственный текст добавлен в локальный черновик. Заполните содержание и сохраните книгу.');
    }

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

    async function compareSection(key) {
        if (!editor) return;

        const current = editor.getState();
        if (current.busy || current.blocked) return;

        const node = current.toc.find((item) => item.key === key && item.kind === 'article');
        const selected = picker.getState();

        if (!node || !selected.opened || selected.reading || !selected.publication) return;

        await replacement.compare({ node, publication: selected.publication });
    }

    function applyReplacement() {
        if (!editor) return;

        const current = editor.getState();
        if (current.busy || current.blocked) return;

        const command = replacement.getCommand();
        const selected = picker.getState();

        if (!selected.opened || selected.reading || selected.publication?.id !== command.publication.id) {
            throw new TypeError('Выбранный материал изменился. Откройте сравнение заново.');
        }

        const window = root.ownerDocument.defaultView;
        const question = 'Заменить публикацию только в выбранном пункте книги? Изменение потребуется сохранить.';
        if (!window.confirm(question)) return;

        if (!editor.section(command)) return;

        replacement.close();
        picker.close();
        view.showNotice('Публикация раздела заменена в локальном оглавлении. Сохраните черновик.');
    }

    function renderEditor(state) {
        panel.render(state);
        tocPanel.render(state);
        pickerPanel.renderEditor(state);
        publicationPanel.render(state);
        replacementPanel.renderEditor(state);
        textPanel.render(state);
        preview.update(state);
    }

    function renderWorkspace(state) {
        view.render(state);

        if (!state.editor) {
            preview.reset();
            editor?.dispose();
            editor = null;
            panel.clear();
            tocPanel.clear();
            picker.close();
            pickerPanel.clear();
            textPanel.clear();
            publicationPanel.clear();
            replacement.close();
            replacementPanel.clear();
            return;
        }

        if (!editor) {
            editor = createBookDraftEditor({
                draft: state.editor.draft,
                workingState: state.editor,
                api: booksApi,
                onChange: renderEditor
            });
        }

        renderEditor(editor.getState());
    }

    const workspaceApi = Object.freeze({
        list: (...args) => bookAuthoringApi.list(...args),
        getEditor: (...args) => booksApi.getWorkingEditor(...args)
    });
    const controller = createAuthoringController({ api: bookAuthoringApi, onChange: renderWorkspace });
    const creationPanel = createBookCreationPanel({
        root,
        onOpen: () => act(openCreation),
        onCancel: () => act(closeCreation),
        onInput: (name, value) => creation.change(name, value),
        onSubmit: () => act(() => creation.submit())
    });

    const creation = createBookCreation({
        api: booksApi,
        onChange: creationPanel.render,
        openBook: openCreatedBook
    });

    creationPanel.render(creation.getState());
    const navigation = createAuthoringNavigation({
        root,
        getState: () => creation.getState().opened ? creation.getState() : editor?.getState(),
        notify: view.showNotice
    });

    function openCreation() {
        if (!navigation.allow()) return;

        controller.close();
        if (creation.open(system.value)) creationPanel.focus();
    }

    function closeCreation() {
        if (!navigation.allow()) return;

        if (creation.close()) creationPanel.focusOpen();
    }

    async function openCreatedBook(bookId) {
        if (events.signal.aborted) return;

        await controller.open(bookId);
        if (events.signal.aborted) return;

        const state = controller.getState();

        if (state.selectedId !== bookId || !state.editor) {
            const message = state.draftError || 'Повторите открытие созданного черновика.';
            controller.close();
            throw new Error(message);
        }

        heading.focus();
    }

    async function saveDraft() {
        if (!editor) return;
        const saved = await editor.save();
        if (saved && !events.signal.aborted) controller.acceptDraft(saved);
    }

    async function publishDraft() {
        const current = editor;
        if (!current?.getState().canPublish) return;

        const window = root.ownerDocument.defaultView;
        const question = 'Выпустить новую неизменяемую версию сохранённой книги? Видимость книги не изменится.';
        if (!window.confirm(question)) return;

        picker.close();
        replacement.close();
        const result = await current.publish();

        if (!result || events.signal.aborted || editor !== current) return;
        if (result.draft) controller.acceptDraft(result.draft);

        await controller.reload();
    }

    async function reloadDraft() {
        if (!editor || !navigation.allow()) return;
        const loaded = await editor.reload();
        if (loaded && !events.signal.aborted) {
            replacement.close();
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
            creation.close();
            const pending = controller.open(button.dataset.authorOpen);
            heading.focus();
            return pending;
        });
    }, options);

    back.addEventListener('click', () => {
        if (!navigation.allow()) return;
        controller.close();
        act(() => controller.reload());
        search.focus();
    }, options);

    draftRetry.addEventListener('click', () => {
        const { selectedId } = controller.getState();
        if (selectedId) act(() => controller.open(selectedId));
    }, options);

    function dispose() {
        events.abort();
        preview.dispose();
        previewPanel.dispose();
        creation.dispose();
        creationPanel.dispose();
        navigation.dispose();
        editor?.dispose();
        controller.dispose();
        panel.dispose();
        tocPanel.dispose();
        picker.dispose();
        pickerPanel.dispose();
        publicationPanel.dispose();
        replacement.dispose();
        replacementPanel.dispose();
        textPanel.dispose();
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
