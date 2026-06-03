"""Team aggregate root."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.value_objects import TeamId, TeamName, Version


@dataclass(kw_only=True, slots=True)
class Team:
    """チーム集約。

    監査用時刻と楽観ロック用のバージョンを持つ。
    更新管理はリポジトリ層が担当する。
    """

    _id: TeamId = field(
        init=False,
        default_factory=lambda: TeamId.generate().expect(
            "TeamId.generate should succeed"
        ),
    )
    _name: TeamName
    _version: Version = field(init=False, default_factory=lambda: Version(0))
    _created_at: datetime = field(init=False, default_factory=lambda: datetime.now(UTC))
    _updated_at: datetime = field(init=False, default_factory=lambda: datetime.now(UTC))

    @classmethod
    def form(cls, name: TeamName) -> Team:
        """新しいチームを生成する。"""
        return Team(_name=name)

    @property
    def id(self) -> TeamId:
        return self._id

    @property
    def name(self) -> TeamName:
        return self._name

    @property
    def version(self) -> Version:
        return self._version

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    def change_name(self, new_name: TeamName) -> Team:
        """チーム名を変更する。"""
        self._name = new_name

        return self
