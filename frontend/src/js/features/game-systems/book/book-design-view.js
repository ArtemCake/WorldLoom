// frontend/src/js/features/game-systems/book/book-design-view.js

import {BOOK_CHAPTER_STATUS, findDesignChapter} from './book-design-catalog.js';
import {elementIn} from '../../../shared/dom/elements.js';

export function renderBookDesign(host, rules, chapter) {
    const specification = findDesignChapter(chapter);

    if (!specification || !rules) return;

    const ownerDocument = host.ownerDocument;
    const saved = rules.rulebook?.[chapter];

    const section = elementIn(ownerDocument, 'section', '', 'rules-book__design-reading');
    const status = saved?.status ?? 'draft';

    section.append(elementIn(ownerDocument, 'h4', 'Правила раздела'));
    section.append(elementIn(ownerDocument, 'p', BOOK_CHAPTER_STATUS[status] ?? status, 'rules-book__muted'));

    let count = 0;

    for (const [code, text] of Object.entries(saved?.fields ?? {})) {
        if (!text.trim()) continue;

        const title = specification.fields[code] ?? code;

        section.append(elementIn(ownerDocument, 'h5', title), elementIn(ownerDocument, 'p', text, 'rules-book__design-text'));
        count += 1;
    }

    if (!count) {
        const message = status === 'unused'
            ? 'Автор отметил, что эта механика не используется.'
            : 'Описание правил раздела пока не заполнено.';

        section.append(elementIn(ownerDocument, 'p', message));
    }

    host.append(section);
}