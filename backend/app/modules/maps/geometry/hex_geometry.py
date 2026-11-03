# backend/app/modules/maps/geometry/hex_geometry.py

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


"""Геометрия гекс-сетки без зависимости от БД и игровых систем."""

AXIAL_DIRECTIONS = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]

def axial_to_cube(q: int, r: int) -> tuple[int, int, int]:
	return q, -q - r, r

def cube_to_axial(cube: tuple[float, float, float]) -> tuple[int, int]:
	return round(cube[0]), round(cube[2])

def cube_distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> int:
	return int((abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])) / 2)

def axial_distance(a: tuple[int, int], b: tuple[int, int]) -> int:
	return cube_distance(axial_to_cube(*a), axial_to_cube(*b))

def axial_neighbors(q: int, r: int) -> list[tuple[int, int]]:
	return [(q + dq, r + dr) for dq, dr in AXIAL_DIRECTIONS]

def offset_to_axial_oddr(col: int, row: int) -> tuple[int, int]:
	"""Перевести координаты нечётных смещённых строк в axial."""
	q = col - (row - (row & 1)) // 2
	return q, row

def _cube_round(cube: tuple[float, float, float]) -> tuple[int, int, int]:
	rx, ry, rz = round(cube[0]), round(cube[1]), round(cube[2])
	dx, dy, dz = abs(rx - cube[0]), abs(ry - cube[1]), abs(rz - cube[2])

	if dx > dy and dx > dz:
		rx = -ry - rz
	elif dy > dz:
		ry = -rx - rz
	else:
		rz = -rx - ry

	return rx, ry, rz

def hex_line_draw(a: tuple[int, int], b: tuple[int, int]) -> list[tuple[int, int]]:
	"""Вернуть гексы на линии, включая обе конечные точки."""
	cube_a = axial_to_cube(*a)
	cube_b = axial_to_cube(*b)
	distance = cube_distance(cube_a, cube_b)

	if distance == 0:
		return [a]

	points = []

	for step in range(distance + 1):
		fraction = step / distance
		interpolated = tuple(cube_a[index] + (cube_b[index] - cube_a[index]) * fraction for index in range(3))
		points.append(cube_to_axial(_cube_round(interpolated)))

	return points

@dataclass(frozen=True)
class VisibilityCell:
	elevation: int
	blocks_sight: bool

@dataclass(frozen=True)
class VisibilityViewer:
	coordinate: tuple[int, int]
	radius: int

def has_line_of_sight(origin: tuple[int, int], target: tuple[int, int], cells: Mapping[tuple[int, int], VisibilityCell], *, use_elevation: bool = True) -> bool:
	"""Проверить промежуточные препятствия между двумя существующими гексами."""
	if origin not in cells or target not in cells:
		return False

	threshold = max(cells[origin].elevation, cells[target].elevation)

	for coordinate in hex_line_draw(origin, target):
		if coordinate == origin or coordinate == target:
			continue

		cell = cells.get(coordinate)

		if cell is None or not cell.blocks_sight:
			continue

		if not use_elevation or cell.elevation >= threshold:
			return False

	return True

def calculate_visible_coordinates(cells: Mapping[tuple[int, int], VisibilityCell], viewers: Iterable[VisibilityViewer], *,
		line_of_sight: bool = True, use_elevation: bool = True) -> set[tuple[int, int]]:
	"""Вычислить объединение видимых координат без изменения входных данных."""
	visible = set()

	for viewer in viewers:
		if isinstance(viewer.radius, bool) or not isinstance(viewer.radius, int) or viewer.radius < 0:
			raise ValueError("Дальность обзора должна быть неотрицательным целым числом")

		if viewer.coordinate not in cells:
			continue

		for target in cells:
			if target in visible:
				continue

			if axial_distance(viewer.coordinate, target) > viewer.radius:
				continue

			if not line_of_sight or has_line_of_sight(viewer.coordinate, target, cells, use_elevation=use_elevation):
				visible.add(target)

	return visible