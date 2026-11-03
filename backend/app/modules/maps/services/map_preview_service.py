# backend/app/modules/maps/services/map_preview_service.py

"""Предпросмотр геометрической видимости без изменения сохранённой сетки."""

import asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.modules.maps.errors import InvalidMapOperation
from backend.app.modules.maps.geometry.hex_geometry import VisibilityCell, VisibilityViewer, calculate_visible_coordinates, offset_to_axial_oddr
from backend.app.modules.maps.schemas import MapPreviewIn, MapVisibilitySettings
from backend.app.modules.maps.services import map_hex_service as hexes
from backend.app.modules.maps.services import map_management_service as management

def _calculate(cells: list[dict], payload: MapPreviewIn, settings: MapVisibilitySettings) -> list[dict]:
	"""Рассчитать предпросмотр на независимых данных."""
	by_coordinate = {
		(cell["q"], cell["r"]): VisibilityCell(elevation=cell["elevation"], blocks_sight=cell["cover"])
		for cell in cells
	}

	if len(by_coordinate) != len(cells):
		raise InvalidMapOperation("В предпросмотре повторяются координаты гексов")

	viewers = []

	if payload.origin_q is not None:
		origin = (payload.origin_q, payload.origin_r)

		if origin not in by_coordinate:
			raise InvalidMapOperation("Наблюдатель находится вне сетки")

		viewers.append(VisibilityViewer(coordinate=origin, radius=payload.vision_radius))

	visible = calculate_visible_coordinates(
		by_coordinate,
		viewers,
		line_of_sight=settings.line_of_sight,
		use_elevation=settings.use_elevation,
	)
	return [{**cell, "visible": (cell["q"], cell["r"]) in visible} for cell in cells]

def _make_temporary_cells(rows: int, cols: int) -> list[dict]:
	cells = []

	for row in range(rows):
		for col in range(cols):
			q, r = offset_to_axial_oddr(col, row)
			cells.append(
				{
					"q": q,
					"r": r,
					"col": col,
					"row": row,
					"elevation": 0,
					"cover": False,
					"explored": False,
				}
			)

	return cells

async def preview(session: AsyncSession, user_id: UUID, payload: MapPreviewIn) -> dict:
	"""Проверить доступ и построить предпросмотр без завершения транзакции."""
	if not isinstance(payload, MapPreviewIn):
		raise InvalidMapOperation("Для предпросмотра требуется MapPreviewIn")

	rows = payload.rows
	cols = payload.cols
	persisted_grid = False
	show_grid = True
	settings = payload.visibility or MapVisibilitySettings()
	cells = []

	if payload.map_id is None:
		await management.require_maps_master(session, payload.game_id, user_id)
	else:
		campaign_map = await management.get_map(session, payload.map_id, user_id)

		if campaign_map.game_id != payload.game_id:
			raise InvalidMapOperation("Карта принадлежит другой игре")

		settings = payload.visibility or hexes.get_visibility_settings(campaign_map)
		show_grid = bool((campaign_map.grid_settings_json or {}).get("show_grid", True))
		state = await hexes.load_hex_grid(session, campaign_map.id)
		persisted_grid = state.layer is not None

		for cell in state.hexes:
			cells.append(
				{
					"q": cell.axial_q,
					"r": cell.axial_r,
					"col": cell.axial_q + (cell.axial_r - (cell.axial_r & 1)) // 2,
					"row": cell.axial_r,
					"elevation": cell.elevation,
					"cover": bool((cell.data_json or {}).get(settings.blocker_key)),
					"explored": cell.explored_by_players,
				}
			)

		if cells:
			rows = max(cell["row"] for cell in cells) + 1
			cols = max(cell["col"] for cell in cells) + 1

	if not persisted_grid:
		cells = _make_temporary_cells(rows, cols)

	calculated = await asyncio.to_thread(_calculate, cells, payload, settings)
	return {
		"rows": rows,
		"cols": cols,
		"show_grid": show_grid,
		"persisted_grid": persisted_grid,
		"hexes": calculated,
	}