// frontend/src/js/features/games/lobby-view.js

import {element} from '../../shared/dom/elements.js';

const STATUS_LABELS = {
    draft: 'Черновик',
    active: 'Идёт',
    archived: 'Архив'
};

const PRIVACY_LABELS = {
    public: 'Публичная',
    friends_only: 'Только друзья',
    invite_only: 'По приглашению',
    private: 'Приватная'
};

function link(text, href) {
    const node = element('a', text, 'btn btn-outline-primary');
    node.href = href;
    return node;
}

function actionButton(text, action, gameId) {
    const button = element('button', text, 'btn btn-outline-primary');
    button.type = 'button';
    button.dataset.lobbyAction = action;
    button.dataset.gameId = gameId;
    return button;
}

function gameCard(game, currentUserId) {
    const isMaster = game.master_id === currentUserId;
    const gamePath = `/games/${encodeURIComponent(game.id)}`;
    const card = element('article', '', 'lobby-card');
    const header = element('header', '', 'lobby-card__header');
    const heading = element('h3');
    const title = element('a', game.title);

    title.href = `${gamePath}/details`;
    heading.append(title);
    header.append(heading);

    if (isMaster) {
        header.append(element('span', 'Вы — ведущий', 'lobby-badge lobby-badge--master'));
    }

    card.append(header);

    if (game.description) {
        card.append(element('p', game.description, 'lobby-card__description'));
    }

    const badges = element('div', '', 'lobby-card__badges');
    const status = STATUS_LABELS[game.status] || game.status;
    const privacy = PRIVACY_LABELS[game.privacy_level] || game.privacy_level;

    badges.append(
        element('span', `Статус: ${status}`, 'lobby-badge'),
        element('span', privacy, 'lobby-badge')
    );

    const actions = element('div', '', 'lobby-card__actions');

    actions.append(
        link(isMaster ? 'Открыть и настроить' : 'Открыть игру', `${gamePath}/details`),
        link('К игровым сессиям', `${gamePath}/play`),
        actionButton(isMaster ? 'Пригласить' : 'Покинуть', isMaster ? 'invite-open' : 'leave-game', game.id)
    );

    card.append(badges, actions);
    return card;
}

export function renderGames(root, games, currentUserId) {
    const list = root.querySelector('[data-games-list]');
    const fragment = document.createDocumentFragment();

    for (const game of games) {
        fragment.append(gameCard(game, currentUserId));
    }

    list.replaceChildren(fragment);
    root.querySelector('[data-games-empty]').hidden = games.length !== 0;
}

export function renderSystems(select, systems) {
    select.replaceChildren(new Option('Выберите игровую систему', ''));

    for (const system of systems) {
        select.add(new Option(system.name, system.id));
    }

    select.disabled = systems.length === 0;

    if (!systems.length) {
        select.replaceChildren(new Option('Нет доступных игровых систем', ''));
    }
}
