// frontend/src/js/features/game-systems/book/book-state.js

export const BOOK_CHAPTERS = Object.freeze([
	Object.freeze({code: 'main', title: 'Об игровой системе'}),
	Object.freeze({code: 'basis', title: 'Основа правил'}),
	Object.freeze({code: 'attributes', title: 'Характеристики'}),
	Object.freeze({code: 'modifiers', title: 'Модификаторы'}),
	Object.freeze({code: 'derived', title: 'Вычисляемые показатели'}),
	Object.freeze({code: 'resources', title: 'Ресурсы'}),
	Object.freeze({code: 'preview', title: 'Проверка правил'}),
	Object.freeze({code: 'publications', title: 'Публикации'}),
	Object.freeze({code: 'access', title: 'Доступ и управление'})
]);

const MODES = new Set(['create', 'edit', 'view']);
const CHAPTER_CODES = new Set(BOOK_CHAPTERS.map((chapter) => chapter.code));

function record(value) {
	if (value === null || typeof value !== 'object' || Array.isArray(value)) return false;

	const prototype = Object.getPrototypeOf(value);
	return prototype === Object.prototype || prototype === null;
}

// Копируем только JSON-данные. Неподдерживаемые значения не удаляются молча.
function copyJson(value, ancestors = new Set()) {
	if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;

	if (typeof value === 'number' && Number.isFinite(value)) return value;

	if (!Array.isArray(value) && !record(value)) {
		throw new Error('Документ должен содержать только JSON-данные.');
	}

	if (ancestors.has(value)) {
		throw new Error('В документе обнаружена циклическая ссылка.');
	}

	ancestors.add(value);

	try {
		if (Array.isArray(value)) {
			const result = [];

			for (let index = 0; index < value.length; index += 1) {
				if (!Object.hasOwn(value, index)) {
					throw new Error('В массиве документа обнаружен пропущенный элемент.');
				}

				result.push(copyJson(value[index], ancestors));
			}

			return result;
		}

		const result = {};

		for (const key of Reflect.ownKeys(value)) {
			const descriptor = Object.getOwnPropertyDescriptor(value, key);

			if (typeof key !== 'string' || !descriptor.enumerable || !Object.hasOwn(descriptor, 'value')) {
				throw new Error('Документ содержит неподдерживаемое свойство.');
			}

			const copied = copyJson(descriptor.value, ancestors);
			const property = {value: copied, enumerable: true, configurable: true, writable: true};

			Object.defineProperty(result, key, property);
		}

		return result;
	} finally {
		ancestors.delete(value);
	}
}

function fingerprint(value) {
	if (Array.isArray(value)) {
		return `[${value.map(fingerprint).join(',')}]`;
	}

	if (record(value)) {
		const fields = Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${fingerprint(value[key])}`);
		return `{${fields.join(',')}}`;
	}

	return JSON.stringify(value);
}

function copyDocument(value) {
	const result = copyJson(value);

	if (!record(result) || !record(result.system)) {
		throw new Error('В документе книги отсутствуют сведения об игровой системе.');
	}

	if (result.rules !== null && !record(result.rules)) {
		throw new Error('Правила книги должны быть объектом либо явно отсутствовать.');
	}

	if (result.origin !== null && !record(result.origin)) {
		throw new Error('Источник правил должен быть объектом либо явно отсутствовать.');
	}

	return result;
}

function checkRevision(value, required = false) {
	if (value === null && !required) return;

	if (!Number.isSafeInteger(value) || value < 1) {
		throw new Error('Некорректная ревизия черновика.');
	}
}

export function createRulesBookState(options) {
	const {document, mode = 'edit', revision = null, saved = mode !== 'create'} = options;

	if (!MODES.has(mode)) throw new Error('Неизвестный режим книги правил.');
	if (typeof saved !== 'boolean') throw new Error('Не указано корректное состояние сохранения.');

	checkRevision(revision);

	if (mode === 'create' && revision !== null) {
		throw new Error('У новой книги не может быть сохранённой ревизии.');
	}

	let current = copyDocument(document);
	let baseline = saved ? fingerprint(current) : null;
	let currentMode = mode;
	let currentRevision = revision;
	let chapter = 'main';
	let sample = {};
	let preview = null;
	let pendingPreview = null;
	let pendingWrite = null;
	let blocked = false;

	function dirty() {
		return baseline === null || fingerprint(current) !== baseline;
	}

	function invalidatePreview() {
		pendingPreview = null;
		preview = null;
	}

	function assertWritable() {
		if (currentMode === 'view') {
			throw new Error('Книга открыта только для просмотра.');
		}

		if (blocked) {
			throw new Error('Сначала загрузите и сверьте сохранённые данные.');
		}

		if (pendingWrite) {
			throw new Error('Дождитесь результата текущей записи.');
		}
	}

	function assertRules() {
		if (current.rules === null) {
			throw new Error('Сначала создайте или загрузите правила книги.');
		}
	}

	function assertTicket(ticket, kind) {
		if (!pendingWrite || pendingWrite !== ticket || pendingWrite.kind !== kind) {
			throw new Error('Ответ не относится к текущей операции записи.');
		}
	}

	function canPublish() {
		const writable = currentMode !== 'view' && !blocked && pendingWrite === null;
		return writable && currentRevision !== null && current.rules !== null && !dirty();
	}

	function beginWrite(kind) {
		assertWritable();
		assertRules();

		if (kind === 'publish' && !canPublish()) {
			throw new Error('Перед публикацией сохраните актуальный черновик.');
		}

		const ticket = Object.freeze({
			kind,
			document: copyDocument(current),
			expectedRevision: currentRevision
		});

		pendingWrite = ticket;
		return ticket;
	}

	return Object.freeze({
		read() {
			return {
				document: copyDocument(current),
				mode: currentMode,
				revision: currentRevision,
				chapter,
				sample: copyJson(sample),
				preview: copyJson(preview),
				previewPending: pendingPreview !== null,
				writePending: pendingWrite?.kind ?? null,
				blocked,
				dirty: dirty(),
				canPublish: canPublish()
			};
		},

		selectChapter(code) {
			if (!CHAPTER_CODES.has(code)) {
				throw new Error('Неизвестная страница книги правил.');
			}

			chapter = code;
		},

		update(change) {
			assertWritable();

			if (typeof change !== 'function') {
				throw new Error('Изменение документа должно быть функцией.');
			}

			const next = copyDocument(current);
			const returned = change(next);

			if (returned && typeof returned.then === 'function') {
				throw new Error('Изменяйте документ синхронно, вне сетевого запроса.');
			}

			const checked = copyDocument(next);

			if (fingerprint(checked) === fingerprint(current)) return false;

			current = checked;
			invalidatePreview();
			return true;
		},

		setSample(value) {
			const next = copyJson(value);

			if (!record(next)) {
				throw new Error('Пример персонажа должен быть объектом.');
			}

			if (fingerprint(next) === fingerprint(sample)) return false;

			sample = next;
			invalidatePreview();
			return true;
		},

		beginPreview() {
			assertRules();

			const ticket = Object.freeze({
				document: copyDocument(current),
				sample: copyJson(sample)
			});

			pendingPreview = ticket;
			preview = null;

			return ticket;
		},

		acceptPreview(ticket, result) {
			if (!pendingPreview || pendingPreview !== ticket) return false;

			if (!record(result)) {
				throw new Error('Результат проверки должен быть объектом.');
			}

			const checked = copyJson(result);

			preview = checked;
			pendingPreview = null;

			return true;
		},

		failPreview(ticket) {
			if (!pendingPreview || pendingPreview !== ticket) return false;

			pendingPreview = null;
			return true;
		},

		beginSave() {
			return beginWrite('save');
		},

		acceptSave(ticket, document, revision) {
			assertTicket(ticket, 'save');
			checkRevision(revision, true);

			if (currentRevision !== null && revision <= currentRevision) {
				throw new Error('Ответ сохранения не содержит новой ревизии.');
			}

			const checked = copyDocument(document);

			current = checked;
			baseline = fingerprint(checked);
			currentRevision = revision;
			currentMode = 'edit';
			pendingWrite = null;

			invalidatePreview();
		},

		beginPublish() {
			return beginWrite('publish');
		},

		acceptPublish(ticket) {
			assertTicket(ticket, 'publish');
			pendingWrite = null;
		},

		failWrite(ticket, {mustReload = false} = {}) {
			if (!pendingWrite || pendingWrite !== ticket) {
				throw new Error('Ошибка не относится к текущей операции записи.');
			}

			if (typeof mustReload !== 'boolean') {
				throw new Error('Некорректное состояние проверки сохранённых данных.');
			}

			pendingWrite = null;
			blocked = mustReload;
		}
	});
}
