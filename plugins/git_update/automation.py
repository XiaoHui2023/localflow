from __future__ import annotations

import logging
from pathlib import Path

from automation import Automation
from pydantic import Field, PrivateAttr

from .last_update import get_head_hash, get_last_update
from .models import GitRepoUpdatePayload

logger = logging.getLogger(__name__)


class GitUpdateAutomation(Automation[GitRepoUpdatePayload]):
    """按间隔轮询 Git 仓库 HEAD，发现变更时触发 GitRepoUpdatePayload 事件。"""

    repo_path: Path = Field(..., description="本地 Git 仓库目录")
    interval: float = Field(default=60.0, gt=0, description="轮询间隔（秒）")

    _last_head: str | None = PrivateAttr(default=None)

    async def on_tick(self) -> None:
        try:
            head = get_head_hash(self.repo_path)
        except (ValueError, RuntimeError):
            logger.exception("读取 Git HEAD 失败: %s", self.repo_path)
            return

        if self._last_head is None:
            self._last_head = head
            return
        if head == self._last_head:
            return

        previous = self._last_head
        self._last_head = head
        try:
            update = get_last_update(self.repo_path)
        except (ValueError, RuntimeError):
            logger.exception("读取 Git 更新详情失败: %s", self.repo_path)
            self._last_head = previous
            return

        await self.run(
            GitRepoUpdatePayload(previous_hash=previous, update=update),
        )
