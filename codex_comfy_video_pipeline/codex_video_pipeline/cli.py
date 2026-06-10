from __future__ import annotations

import argparse
import json
import random
import shutil
import time
import urllib.request
from pathlib import Path


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def check(config: dict) -> dict:
    base_url = config["comfyui"]["base_url"].rstrip("/")
    try:
        with urllib.request.urlopen(f"{base_url}/system_stats", timeout=5) as response:
            comfy_ok = response.status == 200
            comfy_message = f"HTTP {response.status}"
    except Exception as exc:  # noqa: BLE001
        comfy_ok = False
        comfy_message = str(exc)
    paths = config["paths"]
    workflow_dir = Path(paths["workflow_dir"])
    return {
        "comfyui_models_exists": Path(paths["comfyui_models"]).exists(),
        "comfyui_api_ok": comfy_ok,
        "comfyui_api_message": comfy_message,
        "workflow_dir_exists": workflow_dir.exists(),
        "text_to_image_workflow_exists": (workflow_dir / config["comfyui"]["text_to_image_workflow"]).exists(),
        "image_to_video_workflow_exists": (workflow_dir / config["comfyui"]["image_to_video_workflow"]).exists(),
        "ffmpeg_exists": Path(paths["ffmpeg"]).exists(),
        "ffmpeg": paths["ffmpeg"],
        "hyperframes_mode": config["hyperframes"]["mode"],
    }


def build_plan(config: dict, topic: str, style: str, scene_count: int) -> dict:
    scenes = []
    moves = ["slow push in", "pan right", "low angle reveal", "overhead drift", "close-up"]
    for index in range(1, scene_count + 1):
        visual = f"{topic} shot {index}, cinematic composition, clear subject"
        scenes.append(
            {
                "scene_id": f"scene_{index:03d}",
                "duration": config["render"]["scene_seconds"],
                "visual": visual,
                "camera": moves[(index - 1) % len(moves)],
                "voiceover": f"{topic}，第 {index} 个镜头。",
                "prompt": f"{visual}, {style}, {moves[(index - 1) % len(moves)]}, safe lower subtitle area",
                "negative_prompt": "low quality, blurry, bad anatomy, watermark, unreadable text",
            }
        )
    return {"topic": topic, "style": style, "aspect_ratio": config["render"]["aspect_ratio"], "scenes": scenes}


def dry_run(config: dict, topic: str, style: str, scene_count: int) -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    run_dir = Path(config["paths"]["runs_dir"]) / f"{stamp}_{topic[:32]}"
    plan = build_plan(config, topic, style, scene_count)
    write_json(run_dir / "plan.json", plan)
    write_json(run_dir / "environment_check.json", check(config))
    for scene in plan["scenes"]:
        task = {
            "scene_id": scene["scene_id"],
            "target": {
                "duration": scene["duration"],
                "visual": scene["visual"],
                "camera": scene["camera"],
                "aspect_ratio": config["render"]["aspect_ratio"],
            },
            "issues": [
                {"type": "composition", "description": "reserve subtitle safe area", "action": "reframe_center_subject"}
            ],
            "hyperframes_tasks": [
                {"operation": "reframe", "params": {"subject_position": "center", "safe_area": "subtitle_bottom"}},
                {"operation": "style_match", "params": {"reference_scene": "previous_accepted_scene"}},
            ],
        }
        write_json(run_dir / "dry_run" / f"{scene['scene_id']}_hyperframes_task.json", task)
    return run_dir


def queue_one_image(config: dict, topic: str, style: str) -> dict:
    workflow_path = Path(config["paths"]["workflow_dir"]) / config["comfyui"]["text_to_image_workflow"]
    workflow = read_json(workflow_path)
    scene = build_plan(config, topic, style, 1)["scenes"][0]
    workflow[config["comfyui"]["prompt_node_id"]]["inputs"]["text"] = scene["prompt"]
    workflow[config["comfyui"]["negative_prompt_node_id"]]["inputs"]["text"] = scene["negative_prompt"]
    workflow[config["comfyui"]["seed_node_id"]]["inputs"]["seed"] = random.randint(1, 2_147_483_647)
    workflow[config["comfyui"]["width_node_id"]]["inputs"]["width"] = config["comfyui"]["width"]
    workflow[config["comfyui"]["width_node_id"]]["inputs"]["height"] = config["comfyui"]["height"]
    payload = {"prompt": workflow, "client_id": config["comfyui"]["client_id"]}
    request = urllib.request.Request(
        config["comfyui"]["base_url"].rstrip("/") + "/prompt",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    for command_name in ("check", "run", "queue-image"):
        command = sub.add_parser(command_name)
        command.add_argument("--config", default="config.json")
        if command_name in {"run", "queue-image"}:
            command.add_argument("--topic", required=True)
            command.add_argument("--style", default="cinematic, polished, consistent")
        if command_name == "run":
            command.add_argument("--scene-count", type=int, default=6)
            command.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    config = read_json(Path(args.config))
    if args.command == "check":
        for key, value in check(config).items():
            print(f"{key}: {value}")
        return 0
    if args.command == "run":
        if not args.dry_run:
            raise SystemExit("Only --dry-run is enabled until Hyperframes real adapter is configured.")
        print(dry_run(config, args.topic, args.style, args.scene_count))
        return 0
    if args.command == "queue-image":
        print(json.dumps(queue_one_image(config, args.topic, args.style), ensure_ascii=False, indent=2))
        return 0
    return 1
