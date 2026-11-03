# backend/app/modules/maps/services/map_hex_service.py

from uuid import UUID, uuid4
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
from dataclasses import dataclass
from sqlalchemy import select
from backend.app.modules.games.models.lobby import Session as GameSession
from backend.app.modules.maps.errors import InvalidMapOperation, MapStateConflict
from backend.app.modules.maps.geometry.hex_geometry import VisibilityCell, VisibilityViewer, calculate_visible_coordinates, offset_to_axial_oddr
from backend.app.modules.maps.models import CampaignMap, MapHex, MapLayer, Token
from backend.app.modules.maps.schemas import MapVisibilitySettings


async def add_hex_grid(session: AsyncSession, campaign_map: CampaignMap, rows: int, cols: int) -> MapLayer:
	"""Add the initial grid within the current transaction without committing."""
	if not isinstance(campaign_map.id, UUID):
		raise InvalidMapOperation("Adding a grid requires a map UUID")

	for label, value in (("Row count", rows), ("Column count", cols)):
		if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 200:
			raise InvalidMapOperation(f"{label} must be an integer between 1 and 200")

	if not isinstance(campaign_map.fog_of_war_enabled, bool):
		raise InvalidMapOperation("Fog of war must be a boolean")

	layer = MapLayer(
		id=uuid4(),
		map_id=campaign_map.id,
		name="Hex Grid",
		layer_type="vector_tiles",
		z_index=1,
	)
	session.add(layer)
	await session.flush()
	batch = []

	for row in range(rows):
		for col in range(cols):
			q, r = offset_to_axial_oddr(col, row)
			batch.append(
				MapHex(
					id=uuid4(),
					layer_id=layer.id,
					axial_q=q,
					axial_r=r,
					h3_index=f"{row}:{col}",
					is_visible_to_players=not campaign_map.fog_of_war_enabled,
					explored_by_players=False,
				)
			)

			if len(batch) == 500:
				session.add_all(batch)
				await session.flush()
				batch = []

	if batch:
		session.add_all(batch)
		await session.flush()

	campaign_map.grid_settings_json = {
		**(campaign_map.grid_settings_json or {}),
		"rows": rows,
		"cols": cols,
		"orientation": "pointy-top",
		"offset": "odd-r",
	}
	return layer

@dataclass
class HexGridState:
	layer: MapLayer | None
	hexes: list[MapHex]

async def load_hex_grid(session: AsyncSession, map_id: UUID) -> HexGridState:
	"""Прочитать единственный слой сетки; права и блокировку карты обеспечивает вызывающий код."""
	statement = (
		select(MapLayer)
		.where(MapLayer.map_id == map_id, MapLayer.layer_type == "vector_tiles")
		.order_by(MapLayer.id)
		.limit(2)
		.execution_options(populate_existing=True)
	)
	layers = list((await session.execute(statement)).scalars().all())

	if len(layers) > 1:
		raise MapStateConflict("На карте несколько слоёв гексов; требуется выбрать или исправить сетку")

	if not layers:
		return HexGridState(layer=None, hexes=[])

	statement = (
		select(MapHex)
		.where(MapHex.layer_id == layers[0].id)
		.order_by(MapHex.id)
		.execution_options(populate_existing=True)
	)
	rows = list((await session.execute(statement)).scalars().all())
	return HexGridState(layer=layers[0], hexes=rows)

def get_visibility_settings(campaign_map: CampaignMap) -> MapVisibilitySettings:
	"""Прочитать параметры геометрии из данных карты."""
	settings = campaign_map.grid_settings_json or {}
	return MapVisibilitySettings.model_validate(settings.get("visibility", {}))

def make_visibility_cells(rows: list[MapHex], settings: MapVisibilitySettings) -> dict[tuple[int, int], VisibilityCell]:
	"""Создать независимый снимок геометрии без передачи ORM в поток."""
	result = {}

	for row in rows:
		coordinate = (row.axial_q, row.axial_r)

		if coordinate in result:
			raise MapStateConflict("В слое повторяются координаты гексов")

		result[coordinate] = VisibilityCell(
			elevation=row.elevation,
			blocks_sight=bool((row.data_json or {}).get(settings.blocker_key)),
		)

	return result

async def recalculate_visibility(session: AsyncSession, campaign_map: CampaignMap, viewer_token_ids: list[UUID]) -> set[UUID]:
	"""Изменить видимость гексов в текущей транзакции без commit и rollback."""
	settings = get_visibility_settings(campaign_map)
	state = await load_hex_grid(session, campaign_map.id)

	if state.layer is None:
		raise InvalidMapOperation("На карте нет слоя гексов — туман войны недоступен")

	cells = make_visibility_cells(state.hexes, settings)
	hex_by_id = {row.id: row for row in state.hexes}
	viewers = []

	if viewer_token_ids and hex_by_id:
		statement = (
			select(Token)
			.join(GameSession, Token.session_id == GameSession.id)
			.where(
				Token.id.in_(viewer_token_ids),
				Token.current_map_id == campaign_map.id,
				Token.current_hex_id.in_(list(hex_by_id)),
				GameSession.game_id == campaign_map.game_id,
				)
			.order_by(Token.id)
			.execution_options(populate_existing=True)
		)
		tokens = list((await session.execute(statement)).scalars().all())

		for token in tokens:
			origin = hex_by_id.get(token.current_hex_id)

			if origin is None:
				continue

			radius = token.vision_radius_cells

			if isinstance(radius, bool) or not isinstance(radius, int) or radius < 0:
				raise InvalidMapOperation("У наблюдателя некорректная дальность обзора")

			viewers.append(VisibilityViewer(coordinate=(origin.axial_q, origin.axial_r), radius=radius))

	visible = await asyncio.to_thread(
		calculate_visible_coordinates,
		cells,
		tuple(viewers),
		line_of_sight=settings.line_of_sight,
		use_elevation=settings.use_elevation,
	)
	visible_ids = set()

	for row in state.hexes:
		row.is_visible_to_players = (row.axial_q, row.axial_r) in visible

		if row.is_visible_to_players:
			row.explored_by_players = True
			visible_ids.add(row.id)

	return visible_ids