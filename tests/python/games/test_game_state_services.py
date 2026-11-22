# tests/python/games/test_game_state_services.py

"""Интеграционные тесты сервиса состояния игры (этап H).

Проверяет initiative (начало боя, очередь ходов, раунды), dice (броски)
и access (права мастера) через реальный PostgreSQL.
"""

from __future__ import annotations
import os
import unittest
from uuid import uuid4

from sqlalchemy import func, insert, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.app.infrastructure.database.model_registry import configure_models
from backend.app.modules.game_systems.models.game_systems import (
    GameSystem,
    GameSystemRulesDraft,
)
from backend.app.modules.games.models.lobby import (
    DiceRoll,
    Game,
    InitiativeTracker,
    Party,
    Session as GameSession,
)
from backend.app.modules.games.services.initiative_service import (
    get_combat_state,
    start_combat,
    next_turn,
    end_combat,
)
from backend.app.modules.games.services.dice_service import roll_dice, list_session_rolls
from backend.app.modules.games.errors import (
    GameNotFound,
    GameStateConflict,
    GameAccessDenied,
    InvalidGameInput,
)
from backend.app.modules.games.schemas.dice import DiceRollIn
from tests.python.rules.pg_support import (
    PostgresTestCase,
    apply_migrations,
    require_connection,
)


configure_models()

_GAME_SYSTEMS = GameSystem.__table__
_GAME_DRAFTS = GameSystemRulesDraft.__table__
_GAMES = Game.__table__
_PARTIES = Party.__table__
_SESSIONS = GameSession.__table__
_DICE_ROLLS = DiceRoll.__table__
_INITIATIVE = InitiativeTracker.__table__


class GameStateServicesTests(PostgresTestCase):
    """Тесты initiative, dice, access на PostgreSQL."""

    async def asyncSetUp(self):
        raw_url = os.environ.get("WORLDLOOM_RULES_TEST_URL")
        if not raw_url:
            raise unittest.SkipTest("Нет WORLDLOOM_RULES_TEST_URL")

        url = make_url(raw_url)
        if url.drivername != "postgresql+asyncpg":
            raise RuntimeError("Должен использоваться postgresql+asyncpg")
        if not url.database or not url.database.endswith(("_test", "_tests")):
            raise RuntimeError("Имя базы должно оканчиваться на _test или _tests")

        await require_connection(url)

        self.schema = f"wl_gamestate_{uuid4().hex}"
        self.user_id = uuid4()
        self.master_id = uuid4()
        self.member_id = uuid4()
        self.system_id = uuid4()
        self.game_id = uuid4()
        self.session_id = uuid4()

        self.admin_engine = create_async_engine(url, poolclass=NullPool, hide_parameters=True)
        self.engine = None

        async with self.admin_engine.begin() as connection:
            await connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))

        self.engine = create_async_engine(
            url,
            poolclass=NullPool,
            hide_parameters=True,
            isolation_level="READ COMMITTED",
            connect_args={
                "server_settings": {
                    "search_path": self.schema,
                    "lock_timeout": "5000",
                    "statement_timeout": "10000",
                }
            },
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

        async with self.engine.begin() as connection:
            await connection.run_sync(apply_migrations)

            # Пользователь
            await connection.execute(
                text(
                    "INSERT INTO users (id, email_encrypted, email_hash, nickname, "
                    "is_email_verified, is_active, is_2fa_enabled) "
                    "VALUES (:id, :email, :email_hash, :nickname, false, true, false)"
                ),
                {
                    "id": self.user_id,
                    "email": f"encrypted-{uuid4().hex}",
                    "email_hash": uuid4().hex,
                    "nickname": f"user-{uuid4().hex[:12]}",
                },
            )

            # Мастер
            await connection.execute(
                text(
                    "INSERT INTO users (id, email_encrypted, email_hash, nickname, "
                    "is_email_verified, is_active, is_2fa_enabled) "
                    "VALUES (:id, :email, :email_hash, :nickname, false, true, false)"
                ),
                {
                    "id": str(self.master_id),
                    "email": f"encrypted-{uuid4().hex}",
                    "email_hash": uuid4().hex,
                    "nickname": f"master-{uuid4().hex[:12]}",
                },
            )

            # Участник (не мастер)
            await connection.execute(
                text(
                    "INSERT INTO users (id, email_encrypted, email_hash, nickname, "
                    "is_email_verified, is_active, is_2fa_enabled) "
                    "VALUES (:id, :email, :email_hash, :nickname, false, true, false)"
                ),
                {
                    "id": str(self.member_id),
                    "email": f"encrypted-{uuid4().hex}",
                    "email_hash": uuid4().hex,
                    "nickname": f"member-{uuid4().hex[:12]}",
                },
            )

            # Система
            await connection.execute(
                insert(_GAME_SYSTEMS).values(
                    id=self.system_id,
                    name=f"Система {uuid4().hex[:8]}",
                    slug=f"sys-{uuid4().hex[:8]}",
                    rules_engine_version="1.0",
                    is_active=True,
                )
            )

            # Игра (master_id — владелец)
            await connection.execute(
                insert(_GAMES).values(
                    id=str(self.game_id),
                    system_id=str(self.system_id),
                    master_id=str(self.master_id),
                    title=f"Игра {uuid4().hex[:8]}",
                    status="active",
                    privacy_level="private",
                )
            )

            # Участник игры (не мастер) — нужен для чтения истории бросков
            await connection.execute(
                insert(_PARTIES).values(
                    id=str(uuid4()),
                    game_id=str(self.game_id),
                    user_id=str(self.member_id),
                    role_in_game="player",
                    is_active=True,
                )
            )

            # Сессия
            await connection.execute(
                insert(_SESSIONS).values(
                    id=self.session_id,
                    game_id=self.game_id,
                    title="Сессия теста",
                    is_active=True,
                )
            )

    async def asyncTearDown(self):
        if self.engine:
            await self.engine.dispose()
        try:
            async with self.admin_engine.begin() as connection:
                await connection.execute(text(f'DROP SCHEMA IF EXISTS "{self.schema}" CASCADE'))
        finally:
            await self.admin_engine.dispose()

    # ------------------------------------------------------------------ #
    # INITIATIVE TESTS
    # ------------------------------------------------------------------ #

    async def test_start_combat_creates_tracker(self):
        """Мастер начинает бой: создаётся очередь ходов."""
        combatants = [
            {"name": "Герой", "initiative": 15},
            {"name": "Орк", "initiative": 12},
            {"name": "Гоблин", "initiative": 8},
        ]

        async with self.sessions.begin() as session:
            tracker = await start_combat(
                session, self.session_id, self.master_id, combatants
            )
            await session.refresh(tracker)

        self.assertEqual(tracker.session_id, self.session_id)
        self.assertEqual(len(tracker.turn_order_json), 3)
        self.assertEqual(tracker.current_index, 0)
        self.assertEqual(tracker.round_number, 1)
        self.assertTrue(tracker.is_active)

    async def test_start_combat_rejected_by_non_master(self):
        """Не-мастер не может начать бой."""
        combatants = [{"name": "Герой", "initiative": 15}]

        async with self.sessions.begin() as session:
            with self.assertRaises(GameAccessDenied):
                await start_combat(
                    session, self.session_id, self.user_id, combatants
                )

    async def test_start_combat_empty_combatants(self):
        """Пустой список комбатантов отклоняется."""
        async with self.sessions.begin() as session:
            with self.assertRaises(InvalidGameInput):
                await start_combat(
                    session, self.session_id, self.master_id, []
                )

    async def test_start_combat_duplicate_tracker(self):
        """Повторный start_combat отклоняет существующую очередь."""
        combatants = [{"name": "Герой", "initiative": 15}]

        async with self.sessions.begin() as session:
            await start_combat(
                session, self.session_id, self.master_id, combatants
            )
            with self.assertRaises(GameStateConflict):
                await start_combat(
                    session, self.session_id, self.master_id, combatants
                )

    async def test_next_turn_advances_index_and_rounds(self):
        """next_turn увеличивает current_index; при переходе за лимит — раунд."""
        combatants = [
            {"name": "Герой", "initiative": 15},
            {"name": "Орк", "initiative": 12},
            {"name": "Гоблин", "initiative": 8},
        ]

        async with self.sessions.begin() as session:
            await start_combat(
                session, self.session_id, self.master_id, combatants
            )
            # Ход 0 -> 1
            t1 = await next_turn(session, self.session_id, self.master_id)
            await session.refresh(t1)
            self.assertEqual(t1.current_index, 1)
            self.assertEqual(t1.round_number, 1)

            # Ход 1 -> 2
            t2 = await next_turn(session, self.session_id, self.master_id)
            await session.refresh(t2)
            self.assertEqual(t2.current_index, 2)
            self.assertEqual(t2.round_number, 1)

            # Ход 2 -> 0, раунд 1 -> 2
            t3 = await next_turn(session, self.session_id, self.master_id)
            await session.refresh(t3)
            self.assertEqual(t3.current_index, 0)
            self.assertEqual(t3.round_number, 2)

    async def test_next_turn_rejected_when_no_combat(self):
        """next_turn без боя отклоняет GameNotFound."""
        async with self.sessions.begin() as session:
            with self.assertRaises(GameNotFound):
                await next_turn(session, self.session_id, self.master_id)

    async def test_end_combat_removes_tracker(self):
        """end_combat удаляет очередь ходов."""
        combatants = [{"name": "Герой", "initiative": 15}]

        async with self.sessions.begin() as session:
            await start_combat(
                session, self.session_id, self.master_id, combatants
            )
            # Проверить наличие
            tracker = (
                await session.execute(
                    select(InitiativeTracker)
                    .where(InitiativeTracker.session_id == self.session_id)
                )
            ).scalar_one_or_none()
            self.assertIsNotNone(tracker)

            # Удалить
            await end_combat(session, self.session_id, self.master_id)

        # Проверить удаление вне транзакции
        async with self.sessions() as session:
            tracker = (
                await session.execute(
                    select(InitiativeTracker)
                    .where(InitiativeTracker.session_id == self.session_id)
                )
            ).scalar_one_or_none()
            self.assertIsNone(tracker)

    async def test_get_combat_state_no_combat(self):
        """get_combat_state без боя возвращает пустую очередь."""
        async with self.sessions.begin() as session:
            state = await get_combat_state(
                session, self.session_id, self.master_id
            )

        self.assertEqual(state["combat_active"], False)
        self.assertEqual(state["turn_order"], [])
        self.assertIsNone(state["current_index"])
        self.assertIsNone(state["round_number"])

    async def test_get_combat_state_with_combat(self):
        """get_combat_state с боем возвращает очередь."""
        combatants = [
            {"name": "Герой", "initiative": 15},
            {"name": "Орк", "initiative": 12},
        ]

        async with self.sessions.begin() as session:
            await start_combat(
                session, self.session_id, self.master_id, combatants
            )

        async with self.sessions.begin() as session:
            state = await get_combat_state(
                session, self.session_id, self.master_id
            )

        self.assertEqual(state["combat_active"], True)
        self.assertEqual(len(state["turn_order"]), 2)
        self.assertEqual(state["round_number"], 1)

    async def test_get_combat_state_non_member(self):
        """Не-участник не видит состояние боя."""
        combatants = [{"name": "Герой", "initiative": 15}]

        async with self.sessions.begin() as session:
            await start_combat(
                session, self.session_id, self.master_id, combatants
            )

        async with self.sessions.begin() as session:
            with self.assertRaises(GameAccessDenied):
                await get_combat_state(
                    session, self.session_id, self.user_id
                )

    # ------------------------------------------------------------------ #
    # DICE TESTS
    # ------------------------------------------------------------------ #

    async def test_roll_dice_success(self):
        """Успешный бросок d20."""
        async with self.sessions.begin() as session:
            roll = await roll_dice(
                session,
                self.session_id,
                self.master_id,
                None,
                DiceRollIn(formula="1d20", is_gm_hidden=False),
            )
            await session.refresh(roll)

        self.assertEqual(roll.session_id, self.session_id)
        self.assertEqual(roll.roller_id, self.master_id)
        self.assertEqual(roll.formula, "1d20")
        self.assertGreaterEqual(roll.result_total, 1)
        self.assertLessEqual(roll.result_total, 20)

    async def test_roll_dice_hidden_by_non_master(self):
        """Скрытый бросок не-мастером отклоняется."""
        async with self.sessions.begin() as session:
            with self.assertRaises(GameAccessDenied):
                await roll_dice(
                    session,
                    self.session_id,
                    self.user_id,
                    None,
                    DiceRollIn(formula="1d20", is_gm_hidden=True),
                )

    async def test_roll_dice_invalid_formula(self):
        """Невалидная формула отклоняется."""
        async with self.sessions.begin() as session:
            with self.assertRaises(InvalidGameInput):
                await roll_dice(
                    session,
                    self.session_id,
                    self.master_id,
                    None,
                    DiceRollIn(formula="d!"),
                )

    async def test_list_rolls_filters_hidden_from_non_master(self):
        """Скрытые броски не видны не-мастеру."""
        async with self.sessions.begin() as session:
            # Мастер делает обычный и скрытый бросок
            await roll_dice(
                session,
                self.session_id,
                self.master_id,
                None,
                DiceRollIn(formula="1d6", is_gm_hidden=False),
            )
            await roll_dice(
                session,
                self.session_id,
                self.master_id,
                None,
                DiceRollIn(formula="1d8", is_gm_hidden=True),
            )

        # Мастер видит оба
        async with self.sessions() as session:
            rolls = await list_session_rolls(
                session, self.session_id, self.master_id
            )
            self.assertEqual(len(rolls), 2)

        # Не-мастер (участник) видит только открытый
        async with self.sessions() as session:
            rolls = await list_session_rolls(
                session, self.session_id, self.member_id
            )
            self.assertEqual(len(rolls), 1)
            self.assertFalse(rolls[0].is_gm_hidden)


if __name__ == "__main__":
    unittest.main()
