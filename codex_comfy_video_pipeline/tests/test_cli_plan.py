from codex_video_pipeline.cli import build_plan


def test_build_plan_scene_count():
    config = {"render": {"scene_seconds": 4, "aspect_ratio": "9:16"}}
    plan = build_plan(config, "未来城市", "cinematic", 2)
    assert len(plan["scenes"]) == 2
    assert plan["scenes"][0]["scene_id"] == "scene_001"
