"""Tests that verification worker settling windows only
use vocabulary actions."""
from app.shared.healing_vocabulary import VALID_ACTIONS


def test_settling_windows_only_use_vocabulary_actions():
    """All keys in SETTLING_WINDOWS must be valid
    vocabulary actions."""
    import inspect
    import re
    from app.healing import verification_worker
    source = inspect.getsource(verification_worker)

    # Find SETTLING_WINDOWS dict definition
    match = re.search(
        r"SETTLING_WINDOWS\s*=\s*\{([^}]+)\}",
        source,
        re.DOTALL
    )
    assert match is not None, "SETTLING_WINDOWS not found"

    # Extract action name keys
    window_block = match.group(1)
    action_keys = re.findall(r'"([^"]+)"\s*:', window_block)

    invalid = [k for k in action_keys if k not in VALID_ACTIONS]
    assert len(invalid) == 0, (
        f"Non-vocabulary actions in SETTLING_WINDOWS: {invalid}"
    )


def test_all_vocabulary_actions_have_settling_window():
    """Every vocabulary action should have a defined
    settling window."""
    import inspect
    import re
    from app.healing import verification_worker
    source = inspect.getsource(verification_worker)

    match = re.search(
        r"SETTLING_WINDOWS\s*=\s*\{([^}]+)\}",
        source,
        re.DOTALL
    )
    assert match is not None
    window_block = match.group(1)
    action_keys = set(
        re.findall(r'"([^"]+)"\s*:', window_block)
    )

    missing = VALID_ACTIONS - action_keys
    assert len(missing) == 0, (
        f"Vocabulary actions missing from "
        f"SETTLING_WINDOWS: {missing}"
    )
