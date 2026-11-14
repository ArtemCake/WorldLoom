// frontend/src/js/features/rules/draft/draft-section-replacement-data.js

import { readSectionVersion } from './draft-section-data.js';
import { validateBookToc } from './draft-toc-data.js';

function ensure(condition, message) {
    if (!condition) throw new TypeError(message);
}

export function applySectionReplacement(value, command) {
    const toc = validateBookToc(value);
    ensure(command && typeof command === 'object', 'Не задана замена публикации.');

    const node = toc.find((item) => item.key === command.key);
    ensure(node?.kind === 'article', 'Раздел для обновления не найден.');
    ensure(node.article_version_id === command.expected_version_id, 'Закреплённая публикация уже изменилась.');

    const candidate = command.publication;
    const next = readSectionVersion(candidate, candidate?.article_id, candidate?.id);
    const current = readSectionVersion(command.current, next.article_id, node.article_version_id);

    ensure(current.id !== next.id, 'Эта публикация уже закреплена в выбранном пункте.');
    ensure(current.version_number !== next.version_number, 'Разные публикации имеют одинаковый номер версии.');

    node.article_version_id = next.id;

    return validateBookToc(toc);
}
