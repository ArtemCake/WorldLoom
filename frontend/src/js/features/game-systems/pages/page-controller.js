// frontend/src/js/features/game-systems/pages/page-controller.js

import { requestGameSystem } from '../api/game-system-api.js';
import { createRulesEditor } from '../editor/game-system-rules-editor.js';
import { mountRuleEngineManager } from '../editor/rule-engine-manager.js';
import { mountRulesView } from '../view/game-system-rules-view.js';

const initializedRoots = new WeakSet();

export function mountGameSystemsPage(root) {
    if (!root || initializedRoots.has(root)) return;
	const mode = root.dataset.pageMode;
	const systemId = root.dataset.systemId;
	const message = root.querySelector('[data-page-message]');
	const login = root.querySelector('[data-page-login]');
	const reload = root.querySelector('[data-page-reload]');
	const content = root.querySelector('[data-page-content]');
	const list = root.querySelector('[data-systems-list]');
	const create = root.querySelector('[data-system-create]');
	const edit = root.querySelector('[data-system-edit]');
	const form = root.querySelector('[data-system-form]');
	const fields = root.querySelector('[data-system-fields]');

	if (!message || !login || !reload || !content) return;

	initializedRoots.add(root);

	let access = null;
	let ready = false;
	let busy = false;
	let systems = [];
	let loadedSystem = null;
    const deleteBlocked = new Set();

    function syncDeleteButtons() {
        root.querySelectorAll('[data-system-delete]').forEach((button) => {
            const allowed = access?.can_delete === true;
            button.hidden = !allowed;
            button.disabled = !allowed || busy ||  !ready ||  deleteBlocked.has(button.dataset.systemDelete);
        });
    }
    const editorPages = [
        ['basis', 'Основа'],
        ['main', 'Основное'],
        ['attributes', 'Характеристики'],
        ['derived', 'Показатели'],
        ['preview', 'Проверка и сохранение']
    ];

        let editorPage = 0;
        let metadataDirty = false;
        let saveBlocked = false;
        let leaving = false;

        const nextButton = root.querySelector('[data-editor-next]');
        const backButton = root.querySelector('[data-editor-back]');
        const saveButton = root.querySelector('[data-editor-save]');
        const editorState = root.querySelector('[data-editor-state]');
        const editorProgress = root.querySelector('[data-editor-progress]');

        const rulesEditor = ['create', 'edit'].includes(mode)
            ? createRulesEditor(root.querySelector('[data-rules-editor]'), {
                request,
                systemId: mode === 'edit' ? systemId : null,
                getExecutorVersion: () =>
                                    form.elements.namedItem(
                                        'rules_engine_version'
                                    ).value.trim(),
                onBusy: setBusy,
                onChange: updateEditorState,
                onInvalid: revealControl
            })
            : null;

	    const engineHost = root.querySelector('[data-rule-engine-manager]');

	    const engineManager = mode === 'list'
	        ? mountRuleEngineManager(engineHost, {
	            request,
	            isAllowed: () =>
	                ready &&
	                access?.can_create === true &&
	                engineHost?.hidden === false
	        })
	        : null;

        function hasUnsaved() {
            return metadataDirty || Boolean(rulesEditor?.hasUnsaved());
        }

        function updateEditorState() {
            if (!form) return;

            let saveReason = '';

            if (saveBlocked) {
                saveReason =
                    'Повторное сохранение заблокировано после ошибки. ' +
                    'Сверьте данные на сервере перед повторной попыткой.';

                editorState.textContent =
                    saveReason + ' Введённые данные оставлены в форме.';
            } else if (busy) {
                saveReason = 'Дождитесь завершения текущего запроса.';
                editorState.textContent = saveReason;
            } else if (!ready) {
                saveReason =
                    'Конструктор ещё не загружен или загрузка завершилась ошибкой.';

                editorState.textContent = saveReason;
            } else {
                editorState.textContent = hasUnsaved()
                    ? 'Есть несохранённые изменения.'
                    : 'Несохранённых изменений нет.';
            }

            nextButton.disabled = busy || !ready;
            backButton.disabled = busy || !ready || editorPage === 0;
            saveButton.disabled = busy || !ready || saveBlocked;

            saveButton.title = saveReason;
            saveButton.setAttribute(
                'aria-disabled',
                String(saveButton.disabled)
            );
        }

        function openEditorPage(index, focus = false) {
            if (!form || index < 0 || index >= editorPages.length) return;

            editorPage = index;
            const [name, title] = editorPages[index];

            root.querySelectorAll('[data-editor-panel]').forEach((panel) => {
                panel.hidden = panel.dataset.editorPanel !== name;
            });

            rulesEditor?.showPage(name);

            root.querySelectorAll('[data-editor-tab]').forEach((tab) => {
                const current = tab.dataset.editorTab === name;

                if (current) tab.setAttribute('aria-current', 'step');
                else tab.removeAttribute('aria-current');

                tab.disabled = busy || !ready;
            });

            const last = index === editorPages.length - 1;
            nextButton.hidden = last;
            saveButton.hidden = !last;

            if (!last) {
                nextButton.textContent =
                    `Далее: ${editorPages[index + 1][1].toLocaleLowerCase('ru')} →`;
            }

            editorProgress.textContent =
                `Страница ${index + 1} из ${editorPages.length}: ${title}`;

            updateEditorState();

            if (focus) {
                const panel = root.querySelector(
                    `[data-editor-panel="${name}"]`
                );
                const heading = panel?.querySelector('h2');

                if (heading) {
                    heading.tabIndex = -1;
                    heading.focus();
                }
            }
        }

        function revealControl(control) {
            const panel = control.closest('[data-editor-panel]');

            if (panel) {
                const index = editorPages.findIndex(
                    ([name]) => name === panel.dataset.editorPanel
                );
                if (index >= 0) openEditorPage(index);
            }

            let parent = control.parentElement;

            while (parent && parent !== form) {
                if (parent instanceof HTMLDetailsElement) parent.open = true;
                parent = parent.parentElement;
            }
        }

        function validateMetadata() {
            const names = [
                'name',
                'slug',
                'description',
                'rules_engine_version',
                'is_active'
            ];

            for (const name of names) {
                const control = form.elements.namedItem(name);

                if (
                    !(control instanceof HTMLInputElement) &&
                    !(control instanceof HTMLTextAreaElement) &&
                    !(control instanceof HTMLSelectElement)
                ) {
                    message.textContent =
                        'Не удалось найти одно из полей основных сведений. ' +
                        'Обновите страницу после сборки фронтенда.';
                    return false;
                }

                if (!control.checkValidity()) {
                    revealControl(control);
                    control.reportValidity();
                    message.textContent =
                        'Проверьте выделенное поле основных сведений.';
                    return false;
                }
            }

            const name = form.elements.namedItem('name');
            const slug = form.elements.namedItem('slug');

            if (!name.value.trim() || !slug.value.trim()) {
                const invalid = !name.value.trim() ? name : slug;

                revealControl(invalid);
                invalid.focus();

                message.textContent =
                    'Название и код не должны состоять из пробелов.';

                return false;
            }

            return true;
        }

	function pageUrl(id) {
		return `/game-systems/catalog/${encodeURIComponent(id)}`;
	}

	function adminUrl(id) {
		return `/admin/game-systems/${encodeURIComponent(id)}`;
	}

	function makeError(text, status = 0) {
		const error = new Error(text);
		error.status = status;
		return error;
	}

	function setBusy(value) {
		busy = value;
		reload.disabled = value;
		root.setAttribute('aria-busy', String(value));

		if (fields) {
			fields.disabled = value || !ready;
		}

		list?.querySelectorAll('button').forEach((button) => {
			button.disabled = value || !ready;
		});
		rulesEditor?.setParentBusy(value || !ready);
		if (form) {
            root.querySelectorAll('[data-editor-tab]').forEach((tab) => {
                tab.disabled = value || !ready;
            });
            updateEditorState();
        }
        syncDeleteButtons();
	}

	function showError(error) {
		message.textContent = error.message
			|| 'Не удалось выполнить действие.';

		login.hidden = error.status !== 401;

		if (
            (error.status === 401 || error.status === 403) &&
            !(form && ready)
        ) {
			ready = false;
			content.hidden = true;
		}
	}

	function request(path, method = 'GET', payload, options = {}) {
        return requestGameSystem(path, method, payload, options);
    }

	function details(system) {
		return [
			system.slug,
			system.rules_engine_version
				? `Движок: ${system.rules_engine_version}`
				: null,
			typeof system.is_active === 'boolean'
				? (system.is_active ? 'Активна' : 'Неактивна')
				: null
		].filter(Boolean).join(' · ');
	}

	function link(text, href) {
		const node = document.createElement('a');
		node.className = 'btn btn-outline-primary';
		node.textContent = text;
		node.href = href;
		return node;
	}

	function renderList() {
		const fragment = document.createDocumentFragment();

		for (const system of systems) {
			const card = document.createElement('article');
			card.className = 'admin-card';

			const title = document.createElement('h2');
			title.textContent = system.name;

			const info = document.createElement('p');
			info.textContent = details(system);

			const description = document.createElement('p');
			description.textContent = system.description || 'Без описания';

			card.append(
				title,
				info,
				description,
				link('Просмотр', pageUrl(system.id))
			);

			if (access.can_edit === true) {
				card.append(
					link('Редактировать', `${pageUrl(system.id)}/edit`)
				);
			}

			if (access.can_toggle === true) {
				const toggle = document.createElement('button');
				toggle.type = 'button';
				toggle.className = 'btn btn-outline-primary';
				toggle.textContent = system.is_active
					? 'Деактивировать'
					: 'Активировать';
				toggle.dataset.systemToggle = system.id;
				card.append(toggle);
			}

			if (access.can_delete === true) {
                const remove = document.createElement('button');
                remove.type = 'button';
                remove.className = 'btn btn-outline-primary';
                remove.textContent = 'Удалить';
                remove.dataset.systemDelete = system.id;
                card.append(remove);
            }
			fragment.append(card);
		}

		list.replaceChildren(fragment);
		create.hidden = access.can_create !== true;
		syncDeleteButtons();
	}

	async function renderView(system) {
        root.querySelector('[data-system-name]').textContent =
            system.name;

        root.querySelector('[data-system-details]').textContent =
            details(system);

        root.querySelector('[data-system-description]').textContent =
            system.description || 'Описание пока не добавлено.';

        edit.href = `${pageUrl(system.id)}/edit`;
        edit.hidden = access.can_edit !== true;

        const host = root.querySelector('[data-system-rules-view]');

        if (!host) {
            throw makeError(
                'В шаблоне страницы отсутствует блок просмотра правил.'
            );
        }

        await mountRulesView(host, {
            systemId: system.id,
            canEdit: access.can_edit === true,
            request
        });
    }

	function fillForm(system) {

		loadedSystem = { ...system };
        const deleteButton = root.querySelector('button[data-system-delete]');

        if (deleteButton) {
            deleteButton.dataset.systemDelete = system.id;
        }
		for (const name of [
			'name', 'slug', 'description', 'rules_engine_version'
		]) {
			form.elements.namedItem(name).value = system[name] ?? '';
		}

		form.elements.namedItem('is_active').checked =
			system.is_active === true;
	}

	async function loadPage() {
        if (
            busy ||
            rulesEditor?.isBusy() ||
            engineManager?.isBusy()
        ) {
            return;
        }
        if (engineHost) engineHost.hidden = true;

		ready = false;
		access = null;
		content.hidden = true;
		login.hidden = true;
		list?.replaceChildren();
		message.textContent = 'Загрузка…';
		setBusy(true);

		try {
			access = await request('/game-systems/access');

			const expectedListUrl = access.can_edit === true
				? '/admin/game-systems/list'
				: '/game-systems';

			if (access.list_url !== expectedListUrl) {
				throw makeError(
					'Сервер вернул несогласованные настройки доступа.'
				);
			}

			if (mode === 'list') {
				systems = await request(expectedListUrl);

				if (!Array.isArray(systems)) {
					throw makeError('Сервер вернул некорректный список.');
				}

				renderList();
			} else if (mode === 'create') {
				if (access.can_create !== true) {
					throw makeError('Создание систем недоступно.', 403);
				}

				form.reset();
				form.elements.namedItem('slug').value =
                    `system-${Date.now().toString(36)}-` +
                     Math.random().toString(36).slice(2, 8);

                await rulesEditor.load();
			} else if (mode === 'view' || mode === 'edit') {
				if (mode === 'edit' && access.can_edit !== true) {
					throw makeError('Редактирование системы недоступно.', 403);
				}

				const path = access.can_edit === true
					? adminUrl(systemId)
					: `/game-systems/items/${encodeURIComponent(systemId)}`;

				const system = await request(path);

				if (mode === 'view') {
                    await renderView(system);
                } else {
                	fillForm(system);
                	await rulesEditor?.load();
                }
			} else {
				throw makeError('Неизвестный режим страницы.');
			}

			ready = true;

            if (engineHost) {
                engineHost.hidden =
                    mode !== 'list' || access.can_create !== true;
            }

            engineManager?.sync();

			deleteBlocked.clear();
            syncDeleteButtons();
			content.hidden = false;
			if (form) {
                metadataDirty = false;
                saveBlocked = false;
                openEditorPage(0);
            }
			message.textContent = mode === 'list'
				? (
					systems.length
						? `Загружено систем: ${systems.length}.`
						: 'Доступных игровых систем пока нет.'
				)
				: '';
		} catch (error) {
			showError(error);
		} finally {
			setBusy(false);
		}
	}

	    form?.addEventListener('submit', async (event) => {
            event.preventDefault();

            if (
                busy || !ready || saveBlocked ||
                rulesEditor?.isBusy()
            ) {
                return;
            }

            // Enter на промежуточной странице означает продолжение,
            // а не неожиданное создание системы.
            if (editorPage < editorPages.length - 1) {
                nextButton.click();
                return;
            }

            const isEditing = mode === 'edit';
            const allowed = isEditing
                ? access.can_edit === true
                : access.can_create === true;

            if (!allowed || !validateMetadata()) return;

            let payload;

            try {
                const values = new FormData(form);

                payload = {
                    system: {
                        name: String(values.get('name') || '').trim(),
                        slug: String(values.get('slug') || '').trim(),
                        description:
                            String(values.get('description') || '').trim() || null,
                        rules_engine_version: String(
                            values.get('rules_engine_version') || ''
                        ).trim(),
                        is_active: values.has('is_active')
                    },
                    ...rulesEditor.collectSubmission()
                };

                if (isEditing) {
                    payload.expected_revision = rulesEditor.getRevision();
                }
            } catch (error) {
                message.textContent =
                    error.message || 'Проверьте заполнение конструктора.';
                return;
            }

            const linked = Object.prototype.hasOwnProperty.call(
                payload,
                'engine_version_id'
            );

            const savePath = linked
                ? (
                    isEditing
                        ? `${adminUrl(systemId)}/editor/engine`
                        : '/admin/game-systems/from-engine'
                )
                : (
                    isEditing
                        ? `${adminUrl(systemId)}/editor`
                        : '/admin/game-systems/editor/create'
                );

            setBusy(true);
            login.hidden = true;
            message.textContent = 'Сохранение системы и черновика…';

            try {
                const saved = await request(
                    savePath,
                    isEditing ? 'PUT' : 'POST',
                    payload
                );

                if (
                    typeof saved?.system?.id !== 'string' ||
                    !saved.system.id ||
                    saved.draft?.system_id !== saved.system.id ||
                    (isEditing && saved.system.id !== systemId)
                ) {
                    throw makeError(
                        'Ответ сохранения не удалось проверить. ' +
                        'Проверьте данные на сервере перед повторной попыткой.'
                    );
                }

                rulesEditor.acceptSaved(saved.draft);
                fillForm(saved.system);
                metadataDirty = false;

                message.textContent =
                    'Система и черновик сохранены. Публикация не выполнялась.';

                if (!isEditing) {
                    leaving = true;
                    window.location.assign(`${pageUrl(saved.system.id)}/edit`);
                }
            } catch (error) {
                if (
                    !error.status ||
                    error.status >= 500 ||
                    error.status === 401 ||
                    error.status === 403 ||
                    (isEditing && error.status === 409)
                ) {
                    saveBlocked = true;
                }

                showError(error);
            } finally {
                setBusy(false);
            }
        });

	list?.addEventListener('click', async (event) => {
		if (!(event.target instanceof Element)) return;

		const button = event.target.closest('[data-system-toggle]');

		if (
			!button || !list.contains(button) ||
			busy || !ready || access.can_toggle !== true
		) {
			return;
		}

		const system = systems.find(
			(item) => item.id === button.dataset.systemToggle
		);

		if (!system) return;

		setBusy(true);
		message.textContent = 'Сохранение…';

		try {
			const updated = await request(
				adminUrl(system.id),
				'PATCH',
				{ is_active: !system.is_active }
			);

			const index = systems.findIndex(
				(item) => item.id === system.id
			);

			systems[index] = updated;
			systems.sort((a, b) => {
				return Number(b.is_active) - Number(a.is_active)
					|| a.name.localeCompare(b.name, 'ru');
			});

			renderList();
			message.textContent = updated.is_active
				? 'Система активирована.'
				: 'Система деактивирована.';
		} catch (error) {
			showError(error);
		} finally {
			setBusy(false);
		}
	});

	reload.addEventListener('click', () => {
        if (
            busy ||
            rulesEditor?.isBusy() ||
            engineManager?.isBusy()
        ) {
            return;
        }

		if (
			form && ready &&
			!window.confirm(
				'Загрузить данные заново? Несохранённые изменения будут потеряны.'
			)
		) {
			return;
		}

		void loadPage();
	});

	    form?.addEventListener('input', (event) => {
            if (!(event.target instanceof HTMLElement)) return;
            if (event.target.dataset.sample === 'true') return;

            metadataDirty = true;
            updateEditorState();
        });

        form?.addEventListener('change', (event) => {
            if (!(event.target instanceof HTMLElement)) return;
            if (event.target.dataset.sample === 'true') return;

            metadataDirty = true;
            updateEditorState();
        });

        root.querySelectorAll('[data-editor-tab]').forEach((tab) => {
            tab.addEventListener('click', () => {
                if (busy || !ready) return;

                const index = editorPages.findIndex(
                    ([name]) => name === tab.dataset.editorTab
                );

                openEditorPage(index, true);
            });
        });

        backButton?.addEventListener('click', () => {
            if (busy || !ready) return;
            openEditorPage(editorPage - 1, true);
        });

        nextButton?.addEventListener('click', () => {
            if (busy || !ready) return;

            try {
                const page = editorPages[editorPage][0];

                if (page === 'main' && !validateMetadata()) {
                    return;
                }

                if (
                    ['basis', 'main', 'attributes', 'derived'].includes(page)
                ) {
                    rulesEditor.collectSubmission();
                }

                message.textContent = '';
                openEditorPage(editorPage + 1, true);
            } catch (error) {
                message.textContent =
                    error.message || 'Проверьте настройки текущей страницы.';
            }
        });

        root.addEventListener('click', (event) => {
            if (!(event.target instanceof Element)) return;

            const link = event.target.closest('a[href]');

            if (
                !link || !form || leaving ||
                event.button !== 0 ||
                event.ctrlKey || event.metaKey || event.shiftKey || event.altKey
            ) {
                return;
            }

            if (busy) {
                event.preventDefault();
                message.textContent = 'Дождитесь завершения запроса.';
                return;
            }

            if (
                hasUnsaved() &&
                !window.confirm(
                    'Покинуть конструктор? Несохранённые изменения будут потеряны.'
                )
            ) {
                event.preventDefault();
            }
        });

        window.addEventListener('beforeunload', (event) => {
            if (!root.isConnected) return;
            if (leaving || (!hasUnsaved() && !busy)) return;
            event.preventDefault();
            event.returnValue = '';
        });

		root.addEventListener('click', async (event) => {
        if (!(event.target instanceof Element)) return;

        const button = event.target.closest(
            'button[data-system-delete]'
        );

        if (
            !button ||
            !root.contains(button) ||
            busy ||
            !ready ||
            rulesEditor?.isBusy() ||
            access?.can_delete !== true
        ) {
            return;
        }

        const id = button.dataset.systemDelete;

        if (!id || deleteBlocked.has(id)) return;

        const system = mode === 'list'
            ? systems.find((item) => item.id === id)
            : loadedSystem;

        if (!system || system.id !== id) return;

        const unsavedWarning = form && hasUnsaved()
            ? '\nНесохранённые изменения формы также будут потеряны.\n'
            : '\n';

        const confirmation = window.prompt(
            `Удалить систему «${system.name}» и её черновик?\n` +
            'Действие нельзя отменить.\n' +
            'При наличии игр, контента или опубликованных правил ' +
            'сервер запретит удаление.\n' +
            unsavedWarning +
            '\nДля подтверждения введите название системы:',
            ''
        );

        if (confirmation === null) return;

        if (confirmation !== system.name) {
            message.textContent =
                'Название не совпало. Удаление не выполнялось.';
            return;
        }

        setBusy(true);
        message.textContent = 'Удаление системы…';

        try {
            const result = await request(adminUrl(id), 'DELETE');

            if (
                result?.deleted !== true ||
                result.system_id !== id
            ) {
                throw makeError(
                    'Ответ удаления не удалось проверить. ' +
                    'Загрузите актуальное состояние перед повторной попыткой.'
                );
            }

            if (mode === 'list') {
                systems = systems.filter((item) => item.id !== id);
                renderList();
                message.textContent =
                    `Система «${system.name}» и её черновик удалены.`;
            } else {
                // Не показываем предупреждение о потере изменений
                // после уже подтверждённого удаления.
                leaving = true;
                ready = false;
                content.hidden = true;
                message.textContent = 'Система и её черновик удалены.';
                window.location.assign('/game-systems/catalog');
            }
        } catch (error) {
            // Нет надёжного подтверждения результата:
            // повторный DELETE до обновления данных не предлагаем.
            if (!error.status || error.status >= 500) {
                deleteBlocked.add(id);
                message.textContent =
                    'Результат удаления не подтверждён. ' +
                    'Загрузите страницу заново, чтобы проверить, ' +
                    'осталась ли система. Повторное удаление пока заблокировано.';
            } else {
                showError(error);
            }
        } finally {
            setBusy(false);
        }
    });

	void loadPage();
}