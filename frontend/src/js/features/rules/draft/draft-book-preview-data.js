// frontend/src/js/features/rules/draft/draft-book-preview-data.js

import { ruleId } from '../rules-http.js';
import { readBookSources, readBookTextContent, validateBookToc } from './draft-toc-data.js';
import { readSectionVersion } from './draft-section-data.js';

function ensure(condition, message) {
    if (!condition) throw new TypeError(message);
}

function previewContent(value) {
    ensure(value && typeof value === 'object', 'Не получено содержание предпросмотра.');
    ensure(typeof value.title === 'string' && value.title.trim(), 'Укажите название книги.');
    ensure([...value.title].length <= 200, 'Название книги слишком длинное.');
    ensure(typeof value.introduction === 'string', 'Введение должно быть строкой.');
    ensure([...value.introduction].length <= 300000, 'Введение слишком длинное.');

    return {
        title: value.title,
        introduction: value.introduction,
        sources: readBookSources(value.sources),
        toc: validateBookToc(value.toc)
    };
}

export function readDraftPreviewInput(state) {
    ensure(state && [1, 2].includes(state.schemaVersion), 'Неподдерживаемый формат черновика.');
    ensure(state.values && typeof state.values === 'object', 'Не получены поля редактора.');

    const result = previewContent({
        title: state.values.title,
        introduction: state.values.introduction,
        sources: state.sources,
        toc: state.toc
    });

    if (state.schemaVersion === 1) {
        ensure(result.toc.every((node) => node.kind !== 'text'), 'Собственный текст требует рабочего формата книги.');
    }

    return result;
}

export function draftPreviewVersionIds(input) {
    const checked = previewContent(input);
    return [...new Set(checked.toc.filter((node) => node.kind === 'article').map((node) => node.article_version_id))];
}

function publicationContent(value) {
    const checked = readSectionVersion(value, value?.article_id, value?.id);

    return {
        title: checked.content_json.title,
        body: checked.content_json.body,
        sources: readBookSources(checked.content_json.sources)
    };
}

export function buildDraftBookPreview(input, publications) {
    const checked = previewContent(input);
    ensure(Array.isArray(publications), 'Публикации должны быть списком.');

    const required = new Set(draftPreviewVersionIds(checked));
    const versions = new Map();

    for (const publication of publications) {
        ruleId(publication?.id);
        ensure(required.has(publication.id), 'Получена публикация, отсутствующая в оглавлении.');
        ensure(!versions.has(publication.id), 'Публикация передана повторно.');
        versions.set(publication.id, publicationContent(publication));
    }

    ensure(versions.size === required.size, 'Не получены все закреплённые публикации.');

    const groups = new Map();

    for (const node of checked.toc) {
        const siblings = groups.get(node.parent_key) ?? [];
        siblings.push(node);
        groups.set(node.parent_key, siblings);
    }

    for (const siblings of groups.values()) {
        siblings.sort((left, right) => left.position - right.position);
    }

    const sections = [];

    function appendBranch(parentKey, depth) {
        for (const node of groups.get(parentKey) ?? []) {
            let saved = { title: node.title, body: '', sources: [] };

            if (node.kind === 'article') {
                saved = versions.get(node.article_version_id);
            } else if (node.kind === 'text') {
                saved = readBookTextContent(node.content);
            }

            sections.push({
                key: node.key,
                parentKey,
                depth,
                title: node.title ?? saved.title,
                body: saved.body,
                sources: structuredClone(saved.sources)
            });

            if (node.kind === 'chapter') appendBranch(node.key, depth + 1);
        }
    }

    appendBranch(null, 0);

    return {
        title: checked.title,
        introduction: checked.introduction,
        sources: checked.sources,
        version: null,
        sections
    };
}
