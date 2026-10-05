from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from auditor.interfaces.aws_lambda._bootstrap import bootstrap_settings_from_aws

bootstrap_settings_from_aws()

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

from auditor.infrastructure.config.container import get_engine  # noqa: E402
from auditor.interfaces.cli.main import app  # noqa: E402

_TASK_ROOT = Path(os.environ.get("LAMBDA_TASK_ROOT", "."))


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    argv = event["argv"]
    try:
        if argv == ["migrate"]:
            cfg = Config(str(_TASK_ROOT / "alembic.ini"))
            cfg.set_main_option("script_location", str(_TASK_ROOT / "migrations"))
            command.upgrade(cfg, "head")
            return {"exit_code": 0, "output": "migrations aplicadas (head)\n"}
        result = CliRunner().invoke(app, argv)
        return {"exit_code": result.exit_code, "output": result.output}
    finally:
        # ponytail: get_engine() é lru_cache e cada comando CLI faz o próprio asyncio.run;
        # num warm start o pool ficaria preso ao loop fechado. dispose(close=False) só
        # descarta o pool. Upgrade: criar engine por invocação, se virar hot path.
        if get_engine.cache_info().currsize:
            get_engine().sync_engine.dispose(close=False)
