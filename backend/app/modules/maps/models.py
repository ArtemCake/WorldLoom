# backend/app/modules/maps/models.py

"""ORM-модели карт, слоёв, гексов и размещённых объектов."""

from __future__ import annotations
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, inspect, text)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.infrastructure.database.base import Base


def _identity_repr(instance: object, *, label: str) -> str:
	"""Не загружать атрибуты и не выводить содержимое карты."""
	state = inspect(instance)
	identifier = (
		state.identity[0]
		if state.identity is not None
		else state.dict.get("id")
	)
	return f"<{label}(id={identifier!r})>"

class CampaignMap(Base):
	"""Карта кампании с необязательной привязкой к игровой встрече."""

	__tablename__ = "campaign_maps"
	__table_args__ = (
		UniqueConstraint(
			"game_id",
			"map_number",
			name="uq_campaign_maps_game_number",
		),
	)

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	game_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("games.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	session_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("sessions.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	title: Mapped[str] = mapped_column(String(255), nullable=False)
	map_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
	background_storage_path: Mapped[str | None] = mapped_column(
		String(512), nullable=True,
	)
	map_type: Mapped[str] = mapped_column(String(20), nullable=False)
	background_image_url: Mapped[str | None] = mapped_column(
		String(1000), nullable=True,
	)
	grid_settings_json: Mapped[dict] = mapped_column(
		JSONB, nullable=False, server_default="{}",
	)
	fog_of_war_enabled: Mapped[bool] = mapped_column(
		Boolean, default=True, nullable=False,
	)
	lighting_model: Mapped[str] = mapped_column(
		String(20), nullable=False, server_default="basic",
	)
	is_active_in_session: Mapped[bool] = mapped_column(
		Boolean, default=False, nullable=False,
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=text("now()"),
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		onupdate=text("now()"),
		server_default=text("now()"),
	)

	game: Mapped["Game"] = relationship(
		"Game", back_populates="campaign_maps",
	)
	session: Mapped["Session | None"] = relationship(
		"Session", back_populates="maps",
	)
	layers: Mapped[list["MapLayer"]] = relationship(
		"MapLayer", back_populates="map", cascade="all, delete-orphan",
	)
	tokens: Mapped[list["Token"]] = relationship(
		"Token", back_populates="current_map", lazy="selectin",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="CampaignMap")

class MapLayer(Base):
	"""Визуальный слой карты."""

	__tablename__ = "map_layers"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	map_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("campaign_maps.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	name: Mapped[str] = mapped_column(String(100), nullable=False)
	z_index: Mapped[int] = mapped_column(
		Integer, nullable=False, server_default="0",
	)
	opacity: Mapped[float] = mapped_column(
		Float, nullable=False, server_default="1.0",
	)
	is_visible: Mapped[bool] = mapped_column(
		Boolean, default=True, nullable=False,
	)
	layer_type: Mapped[str] = mapped_column(String(20), nullable=False)
	data_json: Mapped[dict | None] = mapped_column(
		JSONB, nullable=True, server_default="{}",
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=text("now()"),
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		onupdate=text("now()"),
		server_default=text("now()"),
	)

	map: Mapped["CampaignMap"] = relationship(
		"CampaignMap", back_populates="layers",
	)
	hexes: Mapped[list["MapHex"]] = relationship(
		"MapHex", back_populates="layer", cascade="all, delete-orphan",
	)
	objects: Mapped[list["MapObject"]] = relationship(
		"MapObject", back_populates="layer", cascade="all, delete-orphan",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="MapLayer")

class MapHex(Base):
	"""Гекс с осевыми координатами; h3_index сохраняется как метка."""

	__tablename__ = "map_hexes"
	__table_args__ = (
		UniqueConstraint(
			"layer_id",
			"axial_q",
			"axial_r",
			name="uq_map_hexes_layer_axial",
		),
	)

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	layer_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("map_layers.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	axial_q: Mapped[int] = mapped_column(Integer, nullable=False)
	axial_r: Mapped[int] = mapped_column(Integer, nullable=False)
	h3_index: Mapped[str] = mapped_column(String(40), nullable=False)
	terrain_type_id: Mapped[int | None] = mapped_column(
		Integer,
		ForeignKey("item_types.id"),
		nullable=True,
		index=True,
	)
	elevation: Mapped[int] = mapped_column(
		Integer, default=0, nullable=False,
	)
	is_visible_to_players: Mapped[bool] = mapped_column(
		Boolean, default=True, nullable=False,
	)
	explored_by_players: Mapped[bool] = mapped_column(
		Boolean, default=False, nullable=False,
	)
	data_json: Mapped[dict | None] = mapped_column(
		JSONB, nullable=True, server_default="{}",
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=text("now()"),
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		onupdate=text("now()"),
		server_default=text("now()"),
	)

	layer: Mapped["MapLayer"] = relationship(
		"MapLayer", back_populates="hexes",
	)
	terrain_type: Mapped["ItemType | None"] = relationship("ItemType")

	def __repr__(self) -> str:
		return _identity_repr(self, label="MapHex")

class MapObject(Base):
	"""Объект, размещённый на слое карты."""

	__tablename__ = "map_objects"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	layer_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("map_layers.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	object_template_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("equipment.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	owner_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	position_x: Mapped[float] = mapped_column(Float, nullable=False)
	position_y: Mapped[float] = mapped_column(Float, nullable=False)
	z_order: Mapped[int] = mapped_column(
		Integer, default=0, nullable=False,
	)
	rotation_deg: Mapped[float] = mapped_column(
		Float, default=0.0, nullable=False,
	)
	scale: Mapped[float] = mapped_column(
		Float, default=1.0, nullable=False,
	)
	is_locked: Mapped[bool] = mapped_column(
		Boolean, default=False, nullable=False,
	)
	is_visible_to_players: Mapped[bool] = mapped_column(
		Boolean, default=True, nullable=False,
	)
	metadata_json: Mapped[dict | None] = mapped_column(
		JSONB, nullable=True, server_default="{}",
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=text("now()"),
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		onupdate=text("now()"),
		server_default=text("now()"),
	)

	layer: Mapped["MapLayer"] = relationship(
		"MapLayer", back_populates="objects",
	)
	template: Mapped["Equipment | None"] = relationship("Equipment")
	owner: Mapped["User | None"] = relationship(
		"User", back_populates="created_map_objects", lazy="selectin",
	)

	def __repr__(self) -> str:
		return _identity_repr(self, label="MapObject")

class Token(Base):
	"""Игровая фишка со снимком состояния для отображения на карте."""

	__tablename__ = "tokens"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	session_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("sessions.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	current_map_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("campaign_maps.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	character_sheet_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("character_sheets.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	npc_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("npcs.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	owner_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	image_url: Mapped[str] = mapped_column(String(1000), nullable=False)
	display_name: Mapped[str | None] = mapped_column(
		String(100), nullable=True,
	)
	grid_x: Mapped[int] = mapped_column(Integer, nullable=False)
	grid_y: Mapped[int] = mapped_column(Integer, nullable=False)
	elevation: Mapped[int] = mapped_column(
		Integer, default=0, nullable=False,
	)
	rotation_deg: Mapped[float] = mapped_column(
		Float, default=0.0, nullable=False,
	)
	hp_current: Mapped[int] = mapped_column(Integer, nullable=False)
	hp_max: Mapped[int] = mapped_column(Integer, nullable=False)
	conditions_json: Mapped[dict | None] = mapped_column(
		JSONB, nullable=True, server_default="{}",
	)
	is_visible_to_players: Mapped[bool] = mapped_column(
		Boolean, default=True, nullable=False,
	)
	controlled_by_ids: Mapped[list[UUID] | None] = mapped_column(
		ARRAY(PG_UUID(as_uuid=True)), nullable=True,
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=text("now()"),
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		onupdate=text("now()"),
		server_default=text("now()"),
	)
	current_hex_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("map_hexes.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	vision_radius_cells: Mapped[int] = mapped_column(
		Integer, default=6, nullable=False,
	)

	session: Mapped["Session"] = relationship(
		"Session", back_populates="tokens",
	)
	owner: Mapped["User"] = relationship("User")
	character_sheet: Mapped["CharacterSheet | None"] = relationship(
		"CharacterSheet",
	)
	npc: Mapped["NPC | None"] = relationship("NPC")
	current_map: Mapped["CampaignMap | None"] = relationship(
		"CampaignMap", back_populates="tokens", lazy="selectin",
	)
	current_hex: Mapped["MapHex | None"] = relationship("MapHex")

	def __repr__(self) -> str:
		return _identity_repr(self, label="Token")

class SpatialAudioZone(Base):
	"""Данные аудиозоны; расчёт слышимости выполняется вне модели."""

	__tablename__ = "spatial_audio_zones"

	id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True), primary_key=True, default=uuid4,
	)
	map_id: Mapped[UUID] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("campaign_maps.id", ondelete="CASCADE"),
		nullable=False,
		index=True,
	)
	creator_id: Mapped[UUID | None] = mapped_column(
		PG_UUID(as_uuid=True),
		ForeignKey("users.id", ondelete="SET NULL"),
		nullable=True,
		index=True,
	)
	geometry_geojson: Mapped[dict] = mapped_column(
		JSONB, nullable=False,
	)
	sound_source_url: Mapped[str] = mapped_column(
		String(1000), nullable=False,
	)
	volume_db: Mapped[float] = mapped_column(
		Float, default=0.0, nullable=False,
	)
	falloff_curve: Mapped[str] = mapped_column(
		String(20), nullable=False, server_default="logarithmic",
	)
	max_distance: Mapped[int] = mapped_column(Integer, nullable=False)
	acoustic_material: Mapped[str | None] = mapped_column(
		String(50), nullable=True,
	)
	is_looping: Mapped[bool] = mapped_column(
		Boolean, default=True, nullable=False,
	)
	is_muted_by_default: Mapped[bool] = mapped_column(
		Boolean, default=False, nullable=False,
	)
	created_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True), server_default=text("now()"),
	)
	updated_at: Mapped[datetime] = mapped_column(
		DateTime(timezone=True),
		onupdate=text("now()"),
		server_default=text("now()"),
	)

	map: Mapped["CampaignMap"] = relationship("CampaignMap")
	creator: Mapped["User | None"] = relationship("User")

	def __repr__(self) -> str:
		return _identity_repr(self, label="SpatialAudioZone")

class MapDeletionJob(Base):
	"""Сохранённое задание очистки файлов уже удалённой карты."""

	__tablename__ = "map_deletion_jobs"

	map_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
	game_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
	master_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
	cleanup_plan: Mapped[dict] = mapped_column(JSONB, nullable=False)
	cleanup_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
	created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))