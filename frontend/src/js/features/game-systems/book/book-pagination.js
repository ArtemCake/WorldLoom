// frontend/src/js/features/game-systems/book/book-pagination.js

import {BOOK_TEXT_CHAPTERS, BOOK_MECHANIC_CHAPTERS} from './book-state.js';
import {isBookMechanicChapter, getBookKindEntries} from './book-sections.js';

// Список элементов главы.
// Текстовые главы элементов не имеют: их содержание — поля rulebook.
// Главы механики перечисляют параметры технического типа.
export function getBookChapterItems(document, chapter) {
    const rules = document.rules;

    if (!rules) return [];

    if (isBookMechanicChapter(chapter)) {
        return getBookKindEntries(rules, chapter).map((entry) => entry.id);
    }

    return [];
}

// Порядок глав зависит от раздела редактора: перелистывание не переносит
// читателя из текста в механику и обратно.
function chapterOrder(chapter) {
    return isBookMechanicChapter(chapter) ? BOOK_MECHANIC_CHAPTERS : BOOK_TEXT_CHAPTERS;
}

export function getBookTurn(document, chapter, selectedCode, direction) {
	if (direction !== -1 && direction !== 1) {
		throw new Error('Направление перелистывания должно быть -1 или 1.');
	}

	const order = chapterOrder(chapter);
	const chapterIndex = order.findIndex((item) => item.code === chapter);

	if (chapterIndex < 0) {
		throw new Error('Неизвестная страница книги.');
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

	// Форма нового элемента находится после существующих элементов страницы.
	// Назад из неё открывается последний элемент, вперёд — следующая страница.
	if (selectedCode === null && items.length && direction === -1) {
		return {chapter, itemCode: items[items.length - 1]};
	}

	const adjacent = order[chapterIndex + direction];

	if (!adjacent) return null;

	const adjacentItems = getBookChapterItems(document, adjacent.code);
	const targetIndex = direction === 1 ? 0 : adjacentItems.length - 1;

	return {
		chapter: adjacent.code,
		itemCode: adjacentItems[targetIndex] ?? null
	};
}
