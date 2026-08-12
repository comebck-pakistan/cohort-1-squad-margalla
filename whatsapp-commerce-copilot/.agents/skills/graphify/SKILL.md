---
name: graphify
description: Instructs the agent to use Graphify to build and query a knowledge graph of the codebase instead of brute-force file scanning.
---

# Graphify
When working in a codebase:
- Use the `graphify` CLI tool to map the project into a knowledge graph.
- If it is not installed, install it via `pip install graphifyy` or `uv tool install graphifyy` (Note the double 'y' in the package name).
- Use the knowledge graph to understand relationships, dependencies, and architecture instead of repeatedly reading raw files.
- Run `graphify --help` for usage instructions once installed.
