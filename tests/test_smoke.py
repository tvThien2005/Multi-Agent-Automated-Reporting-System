"""Fast import checks that require neither a database nor an LLM key."""


def test_project_packages_import() -> None:
    import src.agents.baseline_sql  # noqa: F401
    import src.eval.compare  # noqa: F401
    import src.safety.executor  # noqa: F401
