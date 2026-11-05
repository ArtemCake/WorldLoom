// frontend/src/js/features/game-systems/book/book-pagination.js

import {BOOK_CHAPTERS} from './book-state.js';

export function getBookChapterItems(document, chapter) {
	const rules = document.rules;

	if (!rules) return [];

	const collections = {
		attributes: rules.calculations?.attributes,
		derived: rules.calculations?.derived,
		resources: rules.resources
	};

	return Object.keys(collections[chapter] ?? {});
}

export function getBookTurn(document, chapter, selectedCode, direction) {
	if (direction !== -1 && direction !== 1) {
		throw new Error('Направление перелистывания должно быть -1 или 1.');
	}

	const chapterIndex = BOOK_CHAPTERS.findIndex((item) => item.code === chapter);

	if (chapterIndex < 0) {
		throw new Error('Неизвестная глава книги.');
	}

	const items = getBookChapterItems(document, chapter);
	const itemIndex = selectedCode === null ? -1 : items.indexOf(selectedCode);

	if (selectedCode !== null && itemIndex < 0) {
		throw new Error('Выбранный элемент отсутствует в главе.');
	}

	if (itemIndex >= 0) {
		const nextIndex = itemIndex + direction;

		if (nextIndex >= 0 && nextIndex < items.length) {
			return {chapter, itemCode: items[nextIndex]};
		}
	}

	// Форма нового элемента находится после существующих элементов главы.
	// Назад из неё открывается последний элемент, вперёд — следующая глава.
	if (selectedCode === null && items.length && direction === -1) {
		return {chapter, itemCode: items[items.length - 1]};
	}

	const adjacent = BOOK_CHAPTERS[chapterIndex + direction];

	if (!adjacent) return null;

	const adjacentItems = getBookChapterItems(document, adjacent.code);
	const targetIndex = direction === 1 ? 0 : adjacentItems.length - 1;

	return {
		chapter: adjacent.code,
		itemCode: adjacentItems[targetIndex] ?? null
	};
}