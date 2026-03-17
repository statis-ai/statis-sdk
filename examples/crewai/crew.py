"""Crew definition for the Coordinated Response demo.

Wires agents -> tasks into a sequential Crew and provides a simple run()
entry point.
"""
from __future__ import annotations

from crewai import Crew, Process


def build_crew(agents: dict, tasks: list, verbose: bool = True) -> Crew:
    """Build a sequential Crew from the given agents and tasks."""
    return Crew(
        agents=list(agents.values()),
        tasks=tasks,
        process=Process.sequential,
        verbose=verbose,
    )
