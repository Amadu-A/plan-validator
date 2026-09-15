# tests/architecture/test_context_runtime_contract.py

"""Architecture acceptance contract explicit Stage 10 Linux failure injection."""

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    """Читает UTF-8 project file."""
    return (_ROOT / relative_path).read_text(encoding="utf-8")


def _runtime_source() -> str:
    """Возвращает source Linux Context runtime E2E."""
    return _read("tests/runtime/context_service/test_context_runtime.py")


def _runtime_tree() -> ast.Module:
    """Парсит runtime E2E для format-independent architecture assertions."""
    return ast.parse(_runtime_source())


def _string_list(node: ast.AST) -> list[str] | None:
    """Возвращает literal string list либо None для dynamic выражения."""
    if not isinstance(node, (ast.List, ast.Tuple)):
        return None

    values: list[str] = []

    for element in node.elts:
        if not isinstance(element, ast.Constant):
            return None

        if not isinstance(element.value, str):
            return None

        values.append(element.value)

    return values


def _subprocess_commands() -> list[list[str]]:
    """Извлекает literal subprocess.run command vectors из runtime test."""
    commands: list[list[str]] = []

    for node in ast.walk(_runtime_tree()):
        if not isinstance(node, ast.Call):
            continue

        function = node.func

        if not (
            isinstance(function, ast.Attribute)
            and function.attr == "run"
            and isinstance(function.value, ast.Name)
            and function.value.id == "subprocess"
        ):
            continue

        if not node.args:
            continue

        command = _string_list(node.args[0])

        if command is not None:
            commands.append(command)

    return commands


def _has_wait_for_job_success_call(
    *,
    variable_name: str,
    minimum_attempt: int,
) -> bool:
    """Ищет semantic вызов success waiter независимо от форматирования."""
    for node in ast.walk(_runtime_tree()):
        if not isinstance(node, ast.Call):
            continue

        if not (isinstance(node.func, ast.Name) and node.func.id == "_wait_for_job_success"):
            continue

        if not node.args:
            continue

        first_argument = node.args[0]

        if not (isinstance(first_argument, ast.Name) and first_argument.id == variable_name):
            continue

        for keyword in node.keywords:
            if keyword.arg != "minimum_attempt":
                continue

            if isinstance(keyword.value, ast.Constant) and keyword.value.value == minimum_attempt:
                return True

    return False


def test_context_runtime_e2e_is_explicit_not_normal_startup() -> None:
    """Heavy SIGKILL/Qwen scenario запускается отдельным benchmark script."""
    startup = _read("scripts/up.sh")
    benchmark = _read("scripts/benchmark-context.sh")

    assert "benchmark-context.sh" not in startup

    assert "tests/runtime/context_service/test_context_runtime.py" in benchmark

    assert "PLAN_VALIDATOR_RUN_CONTEXT_RUNTIME_E2E=1" in benchmark


def test_context_runtime_fault_injection_kills_only_context_worker() -> None:
    """Failure injection не имеет права убивать shared GPU worker/RabbitMQ."""
    runtime = _runtime_source()
    commands = _subprocess_commands()

    expected_kill_command = [
        "docker",
        "compose",
        "kill",
        "-s",
        "KILL",
        "context-worker",
    ]

    assert expected_kill_command in commands

    forbidden_kill_commands = (
        [
            "docker",
            "compose",
            "kill",
            "-s",
            "KILL",
            "embedding-worker",
        ],
        [
            "docker",
            "compose",
            "kill",
            "-s",
            "KILL",
            "rabbitmq",
        ],
    )

    for command in forbidden_kill_commands:
        assert command not in commands

    assert "embedding_container_before" in runtime


def test_context_runtime_requires_retry_and_next_user_progress() -> None:
    """Фиксирует stale-lease retry и отсутствие блокировки следующего user job."""
    runtime = _runtime_source()

    assert "first_job_id" in runtime
    assert "second_email" in runtime
    assert "second_job_id" in runtime

    assert _has_wait_for_job_success_call(
        variable_name="first_job_id",
        minimum_attempt=2,
    )

    assert _has_wait_for_job_success_call(
        variable_name="second_job_id",
        minimum_attempt=1,
    )


def test_context_runtime_proves_non_normative_t_pz_isolation_and_cleanup() -> None:
    """Runtime acceptance включает semantic role, typed collections и cleanup."""
    runtime = _runtime_source()

    assert 'kind="T"' in runtime
    assert 'kind="PZ"' in runtime

    assert "project_context_non_normative" in runtime

    assert "_collection_vector_size" in runtime

    assert "== 4096" in runtime

    assert '"cleaned"' in runtime

    assert "_context_payload_rows" in runtime

    assert "_cleanup_qdrant_context" in runtime


def test_context_runtime_checks_t_and_pz_collection_dimensions() -> None:
    """Проверяет, что runtime E2E валидирует 4096 для обеих semantic collections."""
    tree = _runtime_tree()

    checked_kinds: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue

        if len(node.ops) != 1:
            continue

        if not isinstance(node.ops[0], ast.Eq):
            continue

        if len(node.comparators) != 1:
            continue

        comparator = node.comparators[0]

        if not (isinstance(comparator, ast.Constant) and comparator.value == 4096):
            continue

        call = node.left

        if not (
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "_collection_vector_size"
        ):
            continue

        if len(call.args) < 2:
            continue

        kind_argument = call.args[1]

        if isinstance(kind_argument, ast.Constant) and isinstance(kind_argument.value, str):
            checked_kinds.add(kind_argument.value)

    assert checked_kinds == {
        "t",
        "pz",
    }


def test_context_runtime_checks_both_queue_drain_contracts() -> None:
    """Фиксирует Ready/Unacked recovery и для Context, и для GPU queues."""
    runtime = _runtime_source()

    assert "plan-validator.context.index" in runtime

    assert "plan-validator.gpu.embedding" in runtime

    assert ".ready" in runtime
    assert ".unacked" in runtime
    assert ".consumers" in runtime


def test_context_runtime_recovery_never_uses_manual_queue_purge() -> None:
    """Stage 10 recovery acceptance запрещает purge как способ разблокировки."""
    runtime = _runtime_source().casefold()
    benchmark = _read("scripts/benchmark-context.sh").casefold()

    assert "purge_queue" not in runtime
    assert "purge_queue" not in benchmark

    assert "purge queue" not in runtime
    assert "purge queue" not in benchmark

    assert "messages_unacknowledged" in runtime

    assert "messages_unacknowledged" in benchmark
