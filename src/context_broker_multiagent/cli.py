"""Interface CLI inicial para demonstrar a orquestracao multiagentes."""

from __future__ import annotations

import argparse
import json

from context_broker_multiagent.agents import MultiAgentOrchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="context-broker-agent",
        description="CLI inicial do sistema multiagentes para Orion Context Broker.",
    )
    parser.add_argument(
        "request",
        nargs="?",
        default="consultar sensores do Context Broker",
        help="Solicitacao em linguagem natural para os agentes processarem.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    orchestrator = MultiAgentOrchestrator()
    response = orchestrator.handle(args.request)
    print(json.dumps(response, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
