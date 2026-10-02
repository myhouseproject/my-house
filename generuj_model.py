#!/usr/bin/env python3
"""Compatibility entrypoint for the one canonical geometry generator.

Historical CAD logic is archived in docs/archive/generuj_model_legacy.py.
The current model is a mesh, and this command does not create or certify STEP.
"""
import sys
from generuj_geometrie import cli


if __name__ == '__main__':
    print('generuj_model.py: używam kanonicznego generuj_geometrie.py; aktualny STEP nie jest dostępny.', file=sys.stderr)
    cli()
