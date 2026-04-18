Check that GitHub Action inputs defined in action.yml are properly wired to the entrypoint.

When a new input is added to action.yml, it must be:
1. Forwarded as an environment variable in the action's runs.steps[].env block
2. Read by the entrypoint code (via os.environ or _require_env)

When an input is removed from action.yml, the corresponding environment variable
read and any CLI flag that referenced it must also be removed.

An input that exists in action.yml but is never forwarded to the entrypoint is
silently ignored — the user sets it thinking it does something, but nothing reads it.
This is a high severity gap because it creates a false sense of configuration.
