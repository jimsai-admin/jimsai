from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from typing import Any

import httpx

try:
    from dotenv import load_dotenv

    load_dotenv(".env")
except ImportError:
    pass


API_BASE = "https://console.vast.ai/api/v0"


def api_key() -> str:
    value = os.getenv("VAST_API") or os.getenv("VAST_API_KEY")
    if not value:
        raise SystemExit("Set VAST_API or VAST_API_KEY before using this script.")
    return value


def headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"}


def search(args: argparse.Namespace) -> None:
    payload: dict[str, Any] = {
        "limit": args.limit,
        "type": "ondemand",
        "verified": {"eq": True},
        "rentable": {"eq": True},
        "rented": {"eq": False},
        "num_gpus": {"eq": 1},
        "gpu_ram": {"gte": args.min_gpu_ram},
        "dph_total": {"lte": args.max_price},
        "direct_port_count": {"gte": 1},
        "order": [["dph_total", "asc"]],
    }
    if args.gpu_name:
        payload["gpu_name"] = {"in": args.gpu_name}
    response = httpx.post(f"{API_BASE}/bundles/", headers=headers(), json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    offers = data.get("offers", [])
    if isinstance(offers, dict):
        offers = [offers]
    for offer in offers[: args.limit]:
        print(
            json.dumps(
                {
                    "id": offer.get("id") or offer.get("ask_contract_id"),
                    "gpu_name": offer.get("gpu_name"),
                    "gpu_ram_mb": offer.get("gpu_ram"),
                    "dph_total": offer.get("dph_total"),
                    "reliability": offer.get("reliability"),
                    "direct_port_count": offer.get("direct_port_count"),
                    "inet_down": offer.get("inet_down"),
                    "inet_up": offer.get("inet_up"),
                },
                separators=(",", ":"),
            )
        )


def launch(args: argparse.Namespace) -> None:
    if not args.confirm_launch:
        raise SystemExit("Refusing to launch a paid Vast.ai instance without --confirm-launch.")
    encoder_key = args.encoder_api_key or os.getenv("JIMS_MULTIMODAL_ENCODER_API_KEY") or secrets.token_urlsafe(32)
    docker_env = (
        f"-p 8000:8000 "
        f"-e JIMS_MULTIMODAL_ENCODER_API_KEY={encoder_key} "
        f"-e ENCODER_TEXT_MODEL={args.text_model} "
        f"-e ENCODER_CODE_MODEL={args.code_model} "
        f"-e ENCODER_IMAGE_MODEL={args.image_model} "
        f"-e ENCODER_WHISPER_MODEL={args.whisper_model}"
    )
    payload = {
        "image": args.image,
        "label": "jimsai-multimodal-encoder",
        "disk": args.disk,
        "runtype": "args",
        "env": docker_env,
        "args": ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
        "target_state": "running",
        "cancel_unavail": True,
    }
    response = httpx.put(f"{API_BASE}/asks/{args.offer_id}/", headers=headers(), json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    print(json.dumps({"vast_response": data, "encoder_api_key": encoder_key}, indent=2))
    print("After Vast assigns the public mapped port, set JIMS_MULTIMODAL_ENCODER_URL to http://<host>:<mapped-port>.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Search and launch a Vast.ai JIMS-AI encoder instance.")
    subparsers = parser.add_subparsers(required=True)

    search_parser = subparsers.add_parser("search", help="Find encoder-capable Vast.ai offers.")
    search_parser.add_argument("--max-price", type=float, default=float(os.getenv("VAST_ENCODER_MAX_PRICE", "0.40")))
    search_parser.add_argument("--min-gpu-ram", type=int, default=int(os.getenv("VAST_ENCODER_MIN_GPU_RAM", "16000")))
    search_parser.add_argument("--gpu-name", action="append", default=[])
    search_parser.add_argument("--limit", type=int, default=10)
    search_parser.set_defaults(func=search)

    launch_parser = subparsers.add_parser("launch", help="Launch a paid encoder instance from an offer id.")
    launch_parser.add_argument("--offer-id", required=True)
    launch_parser.add_argument("--image", default=os.getenv("VAST_ENCODER_IMAGE", "ghcr.io/YOUR_ORG/jimsai-multimodal-encoder:latest"))
    launch_parser.add_argument("--disk", type=float, default=float(os.getenv("VAST_ENCODER_DISK_GB", "50")))
    launch_parser.add_argument("--encoder-api-key", default="")
    launch_parser.add_argument("--text-model", default=os.getenv("ENCODER_TEXT_MODEL", "nomic-ai/nomic-embed-text-v1.5"))
    launch_parser.add_argument("--code-model", default=os.getenv("ENCODER_CODE_MODEL", "nomic-ai/nomic-embed-code"))
    launch_parser.add_argument("--image-model", default=os.getenv("ENCODER_IMAGE_MODEL", "google/siglip-so400m-patch14-384"))
    launch_parser.add_argument("--whisper-model", default=os.getenv("ENCODER_WHISPER_MODEL", "base"))
    launch_parser.add_argument("--confirm-launch", action="store_true")
    launch_parser.set_defaults(func=launch)

    args = parser.parse_args()
    try:
        args.func(args)
    except httpx.HTTPStatusError as exc:
        print(exc.response.text, file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
