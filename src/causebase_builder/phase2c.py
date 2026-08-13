"""Backward-compatible entry point for the generic RC4 projection."""

from .phase2d import project_phase2d


def project_phase2c(*args, **kwargs):
    return project_phase2d(*args, **kwargs)
