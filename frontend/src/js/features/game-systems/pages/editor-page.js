// frontend/src/js/features/game-systems/pages/editor-page.js

import {requestGameSystem} from '../api/game-system-api.js';
import {createRulesBookState} from '../book/book-state.js';
import {mountRulesBook} from '../book/book-view.js';
import {publishBookRules} from '../book/book-publication.js';
import * as publicationSource from '../book/book-publication-source.js';
import {createTextApi} from '../api/text-api.js';
import {createMechanicApi} from '../api/mechanic-api.js';
import {createVersionApi} from '../api/version-api.js';
import {createSplitEditorSession} from '../editor/split-editor-session.js';

const initializedRoots = new WeakSet();
const MODES = new Set(['create', 'edit', 'view']);

const textApi = createTextApi(requestGameSystem);
const mechanicApi = createMechanicApi(requestGameSystem);
const versionApi = createVersionApi(requestGameSystem);

// Пустой валидный профиль правил для начального создания системы.
function emptyRules() {
    return Object.freeze({
        schema_version: 4,
        rulebook: {},
        calculations: {attributes: {}, derived: {}},
        initial_attributes: {},
        resources: {}
    });
}

function ensure(condition, message) {
    if (!condition) throw new Error(message);
}

function cardValues(system) {
    ensure(system && typeof system.name === 'string', 'Не удалось прочитать карточку системы.');
    ensure(typeof system.slug === 'string', 'В карточке отсутствует код системы.');
    ensure(typeof system.rules_engine_version === 'string', 'В карточке отсутствует версия исполнителя.');
    ensure(typeof system.is_active === 'boolean', 'В карточке отсутствует состояние активности.');

    return {
        name: system.name,
        slug: system.slug,
        description: system.description ?? '',
        rules_engine_version: system.rules_engine_version,
        is_active: system.is_active
    };
}

function validateCard(system) {
    const values = cardValues(system);

    values.name = values.name.trim();
    values.slug = values.slug.trim();
    values.description = values.description.trim() || null;
    values.rules_engine_version = values.rules_engine_version.trim();

    ensure(values.name && [...values.name].length <= 100, 'Укажите название системы длиной до 100 символов.');
    ensure(values.slug.length <= 100 && /^[a-z0-9]+([_-][a-z0-9]+)*$/.test(values.slug), 'Проверьте код системы.');
    ensure(values.rules_engine_version.length > 0, 'Не указана версия исполнителя.');

    return values;
}

function mustReload(error) {
    const status = Number(error?.status) || 0;

    return error?.uncertain === true || !status || status >= 500 || [401, 403, 409].includes(status);
}

function mountBookPage(root) {
    if (initializedRoots.has(root)) return;
    initializedRoots.add(root);

    let mode = root.dataset.pageMode;
    const host = root.querySelector('[data-book-host]');
    const message = root.querySelector('[data-book-message]');
    const login = root.querySelector('[data-book-login]');
    const reload = root.querySelector('[data-book-reload]');
    const save = root.querySelector('[data-book-save]');
    const edit = root.querySelector('[data-book-edit]');
    const sourceField = root.querySelector('[data-book-source-field]');
    const source = root.querySelector('[data-book-source]');
    const publish = root.querySelector('[data-book-publish]');
    const published = root.querySelector('[data-book-published]');
    const required = [host, message, login, reload, save, edit, sourceField, source, publish, published];

    if (required.some((item) => !item)) {
        initializedRoots.delete(root);
        return;
    }

    let systemId = root.dataset.systemId || null;
    let access = null;
    let state = null;
    let book = null;
    let session = null;
    let revisions = {text: null, mechanic: null};
    let busy = false;
    let sourceInitialized = false;

    const controller = new AbortController();
    const {signal} = controller;

    function openSession(id) {
        if (!id) throw new Error('Не указан идентификатор системы.');
        return createSplitEditorSession({
            systemId: id,
            textApi,
            mechanicApi,
            versionApi
        });
    }

    function sync() {
        const snapshot = state?.read();

        host.inert = busy;
        host.setAttribute('aria-busy', String(busy));
        reload.disabled = busy;
        source.disabled = busy;

        save.hidden = mode === 'view' || !(access?.can_create === true || access?.can_edit === true);
        save.disabled = busy || !snapshot || snapshot.blocked || snapshot.writePending !== null;

        if (snapshot?.mode === 'create' && access?.can_create !== true) save.disabled = true;
        if (snapshot?.mode === 'edit' && access?.can_edit !== true) save.disabled = true;

        save.textContent = snapshot?.mode === 'create' ? 'Создать систему и черновик' : 'Сохранить изменения';

        edit.hidden = mode !== 'view' || access?.can_edit !== true || !systemId;
        const pinnedPublication = mode === 'view'
        && new URLSearchParams(window.location.search).has('version');

        edit.textContent = pinnedPublication ? 'Редактировать текущий черновик' : 'Редактировать';

        if (systemId) {
            edit.href = `/game-systems/catalog/${encodeURIComponent(systemId)}/edit`;
        }
        publish.hidden = mode !== 'edit' || access?.can_edit !== true;
        publish.disabled = busy || !snapshot?.canPublish || book?.hasPendingChanges() === true;

        published.hidden = !systemId || busy;

        if (systemId) {
            const id = encodeURIComponent(systemId);
            published.href = `/game-systems/catalog/${id}?source=published`;
        }
    }

    async function publishBook() {
        if (busy || !state || !book || !session) return;

        const snapshot = state.read();

        if (access?.can_edit !== true || snapshot.mode !== 'edit') {
            message.textContent = 'Публикация недоступна.';
            return;
        }

        if (book.hasPendingChanges()) {
            message.textContent = 'Сначала примените к книге или отмените правки открытого элемента.';
            return;
        }

        if (snapshot.document.system.is_active !== true) {
            message.textContent = 'Перед публикацией активируйте и сохраните систему.';
            return;
        }

        if (!snapshot.canPublish) {
            message.textContent = 'Сохраните изменения. Если это состояние уже опубликовано, повторная публикация не нужна.';
            return;
        }

        const question = `Опубликовать сохранённую ревизию ${snapshot.revision}? Опубликованный снимок нельзя изменить.`;

        if (!window.confirm(question)) return;

        busy = true;
        login.hidden = true;
        sync();
        message.textContent = 'Публикация комплекта…';

        try {
            const version = await publishBookRules({
                state,
                systemId,
                session,
                allowed: access.can_edit === true,
                hasPendingChanges: () => book.hasPendingChanges()
            });

            book.refresh();

            // Ревизии обоих черновиков увеличились на 1.
            const newRev = state.read().revision;
            revisions = {text: newRev, mechanic: newRev};

            message.textContent = `Опубликован комплект №${version.version_number}. Текущая ревизия: ${newRev}.`;
            const link = document.createElement('a');
            link.href = publicationSource.bookPublicationHref(systemId, version.id);
            link.textContent = `Открыть опубликованный комплект №${version.version_number}`;
            link.setAttribute('hx-boost', 'false');
            message.append(document.createTextNode(' '), link);
        } catch (error) {
            message.textContent = error instanceof Error ? error.message : 'Не удалось выполнить действие.';
            login.hidden = error?.status !== 401;
        } finally {
            busy = false;
            sync();
        }
    }

    function replaceBook(document, revision) {
        const nextState = createRulesBookState({document, mode, revision});
        const chapter = state?.read().chapter ?? 'main';

        nextState.selectChapter(chapter);
        book?.destroy();
        state = nextState;
        book = mountRulesBook(host, {
            state,
            request: requestGameSystem,
            systemId,
            manager: access?.can_edit === true,
            getSystemId: () => systemId
        });
    }

    async function load() {
        if (busy) return;

        if (book?.hasChanges() && !window.confirm('Загрузить данные заново? Несохранённые изменения будут потеряны.')) {
            return;
        }

        busy = true;
        login.hidden = true;
        sync();
        message.textContent = 'Загрузка…';

        try {
            access = await requestGameSystem('/game-systems/access');
            const selectedVersion = publicationSource.selectedBookPublication(window.location.search, mode);

            if (mode === 'create') {
                ensure(access.can_create === true, 'Создание игровых систем недоступно.');

                const system = {
                    name: '',
                    slug: `system-${crypto.randomUUID()}`,
                    description: '',
                    is_active: true,
                    rules_engine_version: '1.0'
                };

                session = null;
                revisions = {text: null, mechanic: null};

                replaceBook({system, rules: emptyRules(), origin: null}, null);
                message.textContent = 'Новая книга. Запись на сервер выполняется кнопкой сохранения.';
                return;
            }

            if (mode === 'edit') {
                ensure(access.can_edit === true, 'Редактирование игровых систем недоступно.');
            }

            ensure(systemId, 'Не указана игровая система.');

            const id = encodeURIComponent(systemId);
            const adminPath = `/admin/game-systems/${id}`;
            const manager = access.can_edit === true;
            const systemPath = manager ? adminPath : `/game-systems/items/${id}`;
            const system = await requestGameSystem(systemPath);

            ensure(system?.id === systemId, 'Сервер вернул другую игровую систему.');

            if (!sourceInitialized) {
                const requestedSource = new URLSearchParams(window.location.search).get('source');
                const publishedRequested = mode === 'view'
                && (requestedSource === 'published' || selectedVersion !== null);

                source.value = manager && !publishedRequested ? 'draft' : 'published';
                sourceInitialized = true;
            }

            if (selectedVersion !== null) {
                source.value = 'published';
            }

            sourceField.hidden = mode !== 'view' || !manager || selectedVersion !== null;

            const draftMode = mode === 'edit'
            && selectedVersion === null
            && manager && source.value === 'draft';

            if (draftMode) {
                session = openSession(systemId);
                const loaded = await session.load();
                revisions = {...loaded.revisions};

                if (!loaded.hasDraft) {
                    replaceBook({system: cardValues(system), rules: emptyRules(), origin: null}, null);
                    message.textContent = 'Сохранённого черновика нет.';
                    return;
                }

                const revision = revisions.mechanic ?? revisions.text;
                replaceBook({system: cardValues(system), rules: loaded.document, origin: null}, revision);
                message.textContent = loaded.hasDraft
                ? `Сохранённый черновик · ревизия механики ${revisions.mechanic}, текста ${revisions.text}.`
                : 'Нет черновиков.';
            } else {
                const result = await publicationSource.loadBookPublishedRules({
                    request: requestGameSystem,
                    systemId,
                    manager,
                    versionId: selectedVersion
                });

                if (result.version === null) {
                    replaceBook({system: cardValues(system), rules: emptyRules(), origin: null}, null);
                    message.textContent = 'Правила ещё не опубликованы.';
                    return;
                }

                session = null;
                const card = cardValues(system);
                card.rules_engine_version = result.version.rules_engine_version;

                replaceBook({system: card, rules: result.version.rules, origin: null, publication: result.version}, null);
                message.textContent = `Опубликованная версия №${result.version.version_number}. Карточка системы показана в текущем состоянии.`;
            }
        } catch (error) {
            message.textContent = error instanceof Error ? error.message : 'Не удалось выполнить действие.';
            login.hidden = error?.status !== 401;
        } finally {
            busy = false;
            sync();
        }
    }

    async function saveBook() {
        if (busy || !state || !book) return;

        login.hidden = true;

        if (book.hasPendingChanges()) {
            message.textContent = 'Сначала нажмите «Применить к книге» или отмените правки открытого элемента.';
            return;
        }

        let ticket = null;

        try {
            const snapshot = state.read();
            const creating = snapshot.mode === 'create';

            ensure(!snapshot.blocked, 'Сначала загрузите и сверьте сохранённые данные.');
            ensure(creating ? access?.can_create === true : access?.can_edit === true, 'Сохранение недоступно.');

            const card = validateCard(snapshot.document.system);
            const rules = snapshot.document.rules;

            ensure(rules && typeof rules === 'object', 'Сначала заполните правила.');

            ticket = state.beginSave();
            busy = true;
            sync();
            message.textContent = creating ? 'Создание системы…' : 'Сохранение…';

            let savedCard;

            if (creating) {
                // Шаг 1: создать карточку системы без правил.
                const created = await requestGameSystem('/admin/game-systems', 'POST', card);
                const savedId = created?.id;

                ensure(typeof savedId === 'string' && savedId.length > 0, 'Не удалось создать карточку системы.');

                systemId = savedId;
                root.dataset.systemId = savedId;
                session = openSession(savedId);
                savedCard = cardValues(created);
            } else {
                // Шаг 1: обновить карточку системы без правил.
                const updated = await requestGameSystem(`/admin/game-systems/${encodeURIComponent(systemId)}`, 'PATCH', card);

                ensure(updated?.id === systemId, 'Ответ обновления относится к другой системе.');
                savedCard = cardValues(updated);
            }

            // Шаг 2: сохранить раздельные черновики механики и текста.
            revisions = await session.save(snapshot.document.rules, revisions);

            const savedDocument = {
                system: savedCard,
                rules: snapshot.document.rules,
                origin: null
            };

            state.acceptSave(ticket, savedDocument, revisions.mechanic ?? revisions.text);
            ticket = null;
            book.refresh();

            if (creating) {
                mode = 'edit';
                const path = `/game-systems/catalog/${encodeURIComponent(systemId)}/edit`;
                history.replaceState(null, '', path);
                root.dataset.pageMode = 'edit';
                message.textContent = `Система создана. Черновик · ревизия механики ${revisions.mechanic}, текста ${revisions.text}.`;
                return;
            }

            message.textContent = 'Система и черновик сохранены. Публикация не выполнялась.';
        } catch (error) {
            if (ticket) {
                state.failWrite(ticket, {mustReload: mustReload(error)});
                book.refresh();
            }

            message.textContent = error instanceof Error ? error.message : 'Не удалось выполнить действие.';
            login.hidden = error?.status !== 401;
        } finally {
            busy = false;
            sync();
        }
    }

    save.addEventListener('click', () => void saveBook(), {signal});
    reload.addEventListener('click', () => void load(), {signal});
    source.addEventListener('change', () => void load(), {signal});
    publish.addEventListener('click', () => void publishBook(), {signal});

    root.addEventListener('input', sync, {signal});
    root.addEventListener('change', sync, {signal});

    document.addEventListener('htmx:beforeCleanupElement', (event) => {
        if (event.detail?.elt !== root && !event.detail?.elt?.contains(root)) return;

        book?.destroy();
        controller.abort();
    }, {signal});

    void load();
}

export function initGameSystemEditor() {
    for (const root of document.querySelectorAll('[data-game-systems-page]')) {
        if (MODES.has(root.dataset.pageMode)) mountBookPage(root);
    }
}
