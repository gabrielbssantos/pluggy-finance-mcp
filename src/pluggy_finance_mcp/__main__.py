import sys

import uvicorn
from pydantic import ValidationError

from pluggy_finance_mcp.asgi import create_app
from pluggy_finance_mcp.config import Settings
from pluggy_finance_mcp.server import build_server, configure_logging


def main() -> None:
    try:
        settings = Settings()
    except ValidationError:
        print(
            "CONFIGURATION_ERROR: verifique as variáveis de ambiente obrigatórias.", file=sys.stderr
        )
        raise SystemExit(2) from None
    configure_logging()
    if settings.mcp_transport == "stdio":
        server, _ = build_server(settings)
        server.run(transport="stdio")
    else:
        uvicorn.run(
            create_app(settings),
            host="0.0.0.0",
            port=settings.port,
            access_log=False,
            log_config=None,
        )


if __name__ == "__main__":
    main()
