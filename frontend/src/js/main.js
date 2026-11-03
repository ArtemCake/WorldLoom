// frontend/src/js/main.js

import { setupPageLifecycle } from './app/page-lifecycle.js';
import { setupAuthHandlers } from './features/auth/auth.js';
import { initNetworkErrorHandlers } from './shared/http/network-error-handler.js';
import { initGameDetails } from './features/games/game-details.js';
import { initLobby } from './features/games/lobby.js';
import { initSessionCombat } from './features/games/sessions/session-combat.js';
import { initSessionDice } from './features/games/sessions/session-dice.js';
import { initSessionManagement } from './features/games/sessions/session-management.js';
import { initMapDelete } from './features/maps/map-delete.js';
import { initMaps } from './features/maps/maps.js';
import { initMapEdit } from './features/maps/map-edit.js';
import { initMapManagement } from './features/maps/map-management.js';
import { initMapView } from './features/maps/map-view.js';
import { initGameMaps } from './features/maps/games/game-map-controller.js';
import { initSessionTokens } from './features/games/sessions/session-tokens.js';

setupAuthHandlers();
initNetworkErrorHandlers();
setupPageLifecycle();
initGameDetails();
initLobby();
initSessionCombat();
initSessionDice();
initSessionManagement();
initMapDelete();
initMaps();
initMapEdit();
initMapManagement();
initMapView();
initGameMaps();
initSessionTokens();