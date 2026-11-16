// frontend/src/js/features/rules/books/book-content-view.js

import { createBookProse } from './book-prose-view.js';
import { createBookSources } from './book-sources-view.js';

let sequence = 0;

function element(document, tag, className, text = '') {
    const node = document.createElement(tag);
    node.className = className;
    node.textContent = text;
    return node;
}

function localLink(document, target, title) {
    const link = element(document, 'a', '', title);
    link.href = `#${target}`;
    link.setAttribute('hx-boost', 'false');
    return link;
}

function appendSources(document, host, sources, title) {
    const view = createBookSources(document, sources, title);
    if (view) host.append(view);
}

function appendSections(document, host, navigation, sections, prefix, tocId) {
    const rootList = document.createElement('ul');
    const parents = new Map();

    sections.forEach((section, index) => {
        const parent = section.parentKey === null ? null : parents.get(section.parentKey);

        if (section.parentKey !== null && !parent) {
            throw new TypeError('Родительский раздел должен предшествовать дочернему.');
        }

        const target = `${prefix}-section-${index}`;
        const headingLevel = Math.min(section.depth + 3, 6);
        const block = element(document, 'section', 'rules-catalog__section');
        const heading = element(document, `h${headingLevel}`, '', section.title);

        heading.id = target;
        heading.setAttribute('tabindex', '-1');
        block.setAttribute('aria-labelledby', target);
        block.append(heading);

        if (section.body) {
            const proseLevel = Math.min(headingLevel + 1, 6);
            block.append(createBookProse(document, section.body, { headingLevel: proseLevel }));
        }

        appendSources(document, block, section.sources, 'Источники раздела и условия использования');

        const back = element(document, 'p', '');
        back.append(localLink(document, tocId, 'К оглавлению'));
        block.append(back);

        const item = document.createElement('li');
        item.append(localLink(document, target, section.title));

        if (parent) {
            if (!parent.list) {
                parent.list = document.createElement('ul');
                parent.item.append(parent.list);
            }

            parent.list.append(item);
            parent.block.append(block);
        } else {
            rootList.append(item);
            host.append(block);
        }

        parents.set(section.key, { block, item, list: null });
    });

    if (sections.length) {
        navigation.append(rootList);
    } else {
        navigation.append(element(document, 'p', '', 'Оглавление пока пустое.'));
    }
}

export function createBookContent(document, book, { mode = 'published' } = {}) {
    if (!['published', 'draft'].includes(mode)) {
        throw new TypeError('Неизвестный режим представления книги.');
    }
    const prefix = `rules-book-content-${++sequence}`;
    const tocId = `${prefix}-toc`;
    const titleId = `${prefix}-title`;
    const host = element(document, 'article', 'rules-catalog__book');
    const title = element(document, 'h2', '', book.title);

    title.id = titleId;
    host.setAttribute('aria-labelledby', titleId);
    host.append(title);
    const caption = mode === 'draft'
        ? 'Предпросмотр локального черновика. Это не опубликованная версия.'
        : `Опубликованная версия ${book.version}`;

    host.append(element(document, 'p', 'rules-catalog__meta', caption));

    if (book.introduction) {
        host.append(element(document, 'h3', '', 'Введение'));
        host.append(createBookProse(document, book.introduction));
    }

    const navigation = element(document, 'nav', 'rules-catalog__toc');
    const tocHeading = element(document, 'h3', '', 'Оглавление');

    tocHeading.id = tocId;
    tocHeading.setAttribute('tabindex', '-1');
    navigation.setAttribute('aria-labelledby', tocId);
    navigation.append(tocHeading);
    host.append(navigation);

    appendSections(document, host, navigation, book.sections, prefix, tocId);
    appendSources(document, host, book.sources, 'Источники книги и условия использования');

    return host;
}
