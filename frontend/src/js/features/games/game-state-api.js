// frontend/src/js/features/games/game-state-api.js

import { GameRequestError, requestGameJson } from './game-http.js';

export { GameRequestError as GameStateApiError };

function encodeId(value) {
    if (typeof value !== 'string' || !value.trim()) {
        throw new GameRequestError('Не указан идентификатор объекта.');
    }

    return encodeURIComponent(value.trim());
}

function sessionPath(sessionId, suffix) {
    return `/sessions/${encodeId(sessionId)}/${suffix}`;
}

export const gameStateApi = Object.freeze({
    listTokens(sessionId) {
        return requestGameJson(sessionPath(sessionId, 'tokens'));
    },

    createToken(payload) {
        return requestGameJson('/sessions/tokens', { method: 'POST', body: payload });
    },

    updateToken(tokenId, payload) {
        return requestGameJson(`/sessions/tokens/${encodeId(tokenId)}`, { method: 'PATCH', body: payload });
    },

    moveToken(tokenId, payload) {
        return requestGameJson(`/sessions/tokens/${encodeId(tokenId)}/move`, { method: 'POST', body: payload });
    },

    deleteToken(tokenId) {
        return requestGameJson(`/sessions/tokens/${encodeId(tokenId)}`, { method: 'DELETE' });
    },

    getCombatState(sessionId) {
        return requestGameJson(sessionPath(sessionId, 'combat'));
    },

    startCombat(sessionId, combatants) {
        if (!Array.isArray(combatants)) {
            throw new GameRequestError('Участники боя должны передаваться списком.');
        }

        return requestGameJson(sessionPath(sessionId, 'combat/start'), { method: 'POST', body: combatants });
    },

    nextTurn(sessionId) {
        return requestGameJson(sessionPath(sessionId, 'combat/next-turn'), { method: 'POST' });
    },

    endCombat(sessionId) {
        return requestGameJson(sessionPath(sessionId, 'combat/end'), { method: 'POST' });
    },

    rollDice(sessionId, payload, partyId = null) {
        const query = new URLSearchParams();

        if (partyId !== null) {
            encodeId(partyId);
            query.set('party_id', partyId.trim());
        }

        const suffix = query.size ? `?${query.toString()}` : '';
        return requestGameJson(sessionPath(sessionId, `roll${suffix}`), { method: 'POST', body: payload });
    },

    listRolls(sessionId, { limit = 100, offset = 0 } = {}) {
        if (!Number.isInteger(limit) || limit < 1 || limit > 500 || !Number.isInteger(offset) || offset < 0 || offset > 1000000) {
            throw new GameRequestError('Недопустимые параметры страницы журнала бросков.');
        }

        const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
        return requestGameJson(sessionPath(sessionId, `rolls?${query.toString()}`));
    }
});
