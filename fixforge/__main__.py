import argparse
import os

import uvicorn

from .config import Settings, load_env
from .handoff import prepare_handoff
from .providers import check_ollama_model
from .publisher import publish_repair
from .sandbox import docker_available, resolve_docker_image
from .store import Store


def check_pilot(settings: Settings) -> bool:
    if settings.inference_provider == "ollama":
        try:
            check_ollama_model(settings.ollama_model)
        except ValueError as error:
            print(f"Ollama: {error}")
            provider_ready = False
        else:
            print(f"Ollama: local model ready ({settings.ollama_model})")
            provider_ready = True
    else:
        provider_ready = bool(settings.api_key)
        print("Provider key: configured" if provider_ready else "Provider key: set OPENAI_API_KEY locally")
    repositories = settings.repositories or {}
    ready_repositories = sum(path.is_dir() for path in repositories.values())
    print(f"Registered repository directories available: {ready_repositories}/{len(repositories)}")
    if not docker_available():
        print("Docker: Linux engine unavailable")
        return False
    try:
        image_id, architecture = resolve_docker_image(settings.image)
    except ValueError as error:
        print(f"Docker: {error}")
        return False
    print(f"Docker image: {image_id} ({architecture})")
    return provider_ready and ready_repositories > 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run FixForge, prepare an approved repair, or publish a GitHub draft.")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("serve", help="Start the local repair workbench")
    commands.add_parser("doctor", help="Check the local pilot prerequisites")
    handoff = commands.add_parser("handoff", help="Package an approved Git repair and its evidence")
    handoff.add_argument("run_id", help="ID of an approved repository repair")
    publish = commands.add_parser("publish", help="Push an approved repair branch and open a GitHub draft PR")
    publish.add_argument("run_id", help="ID of an approved repository repair")
    args = parser.parse_args()
    if args.command == "doctor":
        raise SystemExit(0 if check_pilot(Settings.from_env()) else 1)
    if args.command in {"handoff", "publish"}:
        settings = Settings.from_env()
        try:
            run = Store(settings.data_dir).get(args.run_id)
        except KeyError:
            raise SystemExit("Repair run not found") from None
        try:
            if args.command == "publish":
                result = publish_repair(settings, run)
                label = "Existing pull request" if result["reused"] else "Draft pull request"
                print(f"{label}: {result['url']}")
            else:
                path, receipt = prepare_handoff(settings, run)
                print(f"Git handoff: {path}")
                print(f"Base commit: {receipt['base_commit']}")
                print(f"Prepared commit: {receipt['prepared_commit']}")
                print(f"Branch: {receipt['branch']}")
        except (OSError, ValueError) as error:
            raise SystemExit(str(error)) from None
        return
    load_env()
    host = os.getenv("FIXFORGE_HOST", "127.0.0.1")
    if host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("FixForge only supports loopback hosts (127.0.0.1 / localhost)")
    uvicorn.run("fixforge.api:create_app", factory=True, host=host,
                port=int(os.getenv("FIXFORGE_PORT", "8000")), log_level="info")


if __name__ == "__main__":
    main()
