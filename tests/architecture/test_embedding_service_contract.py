# tests/architecture/test_embedding_service_contract.py

"""Architecture tests Stage 8 Embedding Service/GPU coordination contract."""

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EMBEDDING_ROOT = PROJECT_ROOT / "services" / "embedding-service" / "src" / "embedding_service"


def read_project_file(relative_path: str) -> str:
    """Читает UTF-8 project file для architecture assertions."""
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def imported_root_modules(python_file: Path) -> set[str]:
    """Возвращает root modules Python imports одного source file."""
    tree = ast.parse(
        python_file.read_text(encoding="utf-8"),
        filename=str(python_file),
    )
    result: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module.split(".")[0])

    return result


def test_embedding_application_domain_have_no_framework_gpu_coupling() -> None:
    """Запрещает FastAPI/Rabbit/torch/transformers в business layers."""
    forbidden = {
        "fastapi",
        "starlette",
        "aio_pika",
        "torch",
        "transformers",
        "sentence_transformers",
        "qdrant_client",
        "sqlalchemy",
    }

    for layer in ("application", "domain"):
        for python_file in (EMBEDDING_ROOT / layer).rglob("*.py"):
            imports = imported_root_modules(python_file)
            assert imports.isdisjoint(forbidden), (
                f"{python_file} imports forbidden modules: {imports & forbidden}"
            )


def test_embedding_stage_does_not_own_qdrant_retrieval() -> None:
    """Не позволяет преждевременно смешать Stage 8 и Stage 9 retrieval."""
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in EMBEDDING_ROOT.rglob("*.py")
    ).casefold()

    assert "qdrant_client" not in source
    assert "collection_name" not in source
    assert "similarity_search" not in source


def test_embedding_compute_is_queue_only() -> None:
    """Фиксирует отсутствие direct HTTP inference endpoint."""
    routers = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (EMBEDDING_ROOT / "transport" / "routers").rglob("*.py")
    )
    worker = read_project_file(
        "services/embedding-service/src/embedding_service/infrastructure/messaging/worker.py"
    )

    assert 'prefix="/internal/v1/embedding"' in routers
    assert '"/runtime"' in routers
    assert '"/embed"' not in routers
    assert "settings.embedding_queue.name" in worker
    assert "declare_queue" in worker


def test_embedding_queue_and_gpu_policy_are_pydantic_first() -> None:
    """Фиксирует model/queue/lease/admission safe defaults в settings."""
    settings = read_project_file(
        "services/embedding-service/src/embedding_service/core/settings.py"
    )
    env_example = read_project_file(".env.example")

    required_markers = (
        "Qwen/Qwen3-VL-Embedding-8B",
        "output_dimension: int",
        "plan-validator.gpu.embedding",
        "prefetch_count: int",
        "/var/lock/plan-validator-gpu/gpu.lock",
        "min_free_ram_gib",
        "min_free_vram_gib",
    )

    for marker in required_markers:
        assert marker in settings

    assert "PLAN_VALIDATOR_EMBEDDING_MODEL__NAME=Qwen/Qwen3-VL-Embedding-8B" in env_example
    assert "PLAN_VALIDATOR_EMBEDDING_QUEUE__PREFETCH_COUNT=1" in env_example


def test_embedding_compose_uses_external_existing_model_cache() -> None:
    """Проверяет reuse PDRD model cache без model download/copy."""
    compose = read_project_file("compose.yaml")

    assert "embedding-model-cache:" in compose
    assert "external: true" in compose
    assert "pdrd-validation-ai_multimodal_model_cache" in compose
    assert "embedding-model-cache:/models/huggingface:ro" in compose


def test_embedding_worker_has_gpu_but_api_does_not() -> None:
    """GPU доступен только dedicated worker, а HTTP API остаётся лёгким."""
    compose = read_project_file("compose.yaml")
    api_start = compose.index("\n  embedding-service:\n")
    worker_start = compose.index("\n  embedding-worker:\n")
    benchmark_start = compose.index("\n  embedding-benchmark:\n")
    api_block = compose[api_start:worker_start]
    worker_block = compose[worker_start:benchmark_start]

    assert "gpus: all" not in api_block
    assert "gpus: all" in worker_block
    assert "target: gpu" in worker_block
    assert "./var/lock/plan-validator-gpu:/var/lock/plan-validator-gpu" in worker_block
    assert "read_only: true" in worker_block


def test_embedding_application_services_have_no_environment_block() -> None:
    """Не допускает Compose duplication Pydantic application settings."""
    compose = read_project_file("compose.yaml")

    for service, next_service in (
        ("embedding-service", "embedding-worker"),
        ("embedding-worker", "embedding-benchmark"),
        ("embedding-benchmark", "api-gateway"),
    ):
        start = compose.index(f"\n  {service}:\n")
        end = compose.index(f"\n  {next_service}:\n")
        block = compose[start:end]
        assert "\n    environment:" not in block


def test_embedding_gpu_image_is_offline_for_model_weights() -> None:
    """Фиксирует offline Hugging Face runtime и отсутствие COPY model weights."""
    dockerfile = read_project_file("services/embedding-service/Dockerfile")
    runtime = read_project_file(
        "services/embedding-service/src/embedding_service/infrastructure/gpu_runtime.py"
    )

    assert "HF_HUB_OFFLINE=1" in dockerfile
    assert "TRANSFORMERS_OFFLINE=1" in dockerfile
    assert "local_files_only=True" in runtime
    assert "COPY models" not in dockerfile


def test_embedding_worker_releases_model_inside_each_job() -> None:
    """Фиксирует lease/load/infer/release lifecycle вместо постоянной VRAM residency."""
    runtime = read_project_file(
        "services/embedding-service/src/embedding_service/infrastructure/gpu_runtime.py"
    )

    acquire_position = runtime.index("self._gpu_lease.acquire")
    ram_position = runtime.index("_require_system_ram")
    model_position = runtime.index("model_class(")
    release_position = runtime.index("self._gpu_lease.release()")

    assert acquire_position < ram_position < model_position < release_position
    assert "finally:" in runtime
    assert "empty_cache" in runtime


def test_up_and_stage_gate_include_embedding_stage() -> None:
    """Проверяет canonical startup и dedicated Stage 8 checks."""
    up_script = read_project_file("scripts/up.sh")
    check_script = read_project_file("scripts/check-embedding.sh")

    assert "./scripts/check-embedding.sh --fix" in up_script
    assert "./scripts/check-embedding.sh --check" in up_script
    assert "./scripts/check-catalog.sh --check" in check_script
    assert "tests/unit/embedding_service" in check_script
    assert "tests/transport/embedding_service" in check_script
    assert "tests/architecture" in check_script


def test_embedding_sources_have_docstrings() -> None:
    """Проверяет обязательную русскую documentation discipline нового service."""
    missing: list[str] = []

    for python_file in EMBEDDING_ROOT.rglob("*.py"):
        tree = ast.parse(
            python_file.read_text(encoding="utf-8"),
            filename=str(python_file),
        )

        if ast.get_docstring(tree) is None:
            missing.append(f"{python_file}:module")

        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if ast.get_docstring(node) is None:
                    missing.append(f"{python_file}:{node.lineno}:{node.name}")

    assert not missing, f"Missing Embedding docstrings: {missing}"
