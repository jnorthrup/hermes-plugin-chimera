# Hermes Chimera Plugin

Observable key→model array for Hermes — tracks draft keys, context limits, and syncs kanban concurrency.

## What it does

- **Loads keys** from `~/.hermes/auth.json` credential pool
- **Tracks per-key state**: provider, model, last_used timestamp, draft/exhausted/dead status
- **Context-aware**: each key knows its model's context limit (min across all draft keys = virtual LLM context)
- **600s timeout**: keys idle >10min treated as fresh
- **Takeover**: on plugin load, sets `kanban.max_in_progress` = draft key count

## Install

```bash
# As user plugin
mkdir -p ~/.hermes/plugins
cd ~/.hermes/plugins
git clone https://github.com/jnorthrup/hermes-plugin-chimera.git chimera
```

Enable in your profile's `config.yaml`:
```yaml
plugins:
  enabled: '["chimera"]'
```

## API

```python
from chimera import get_chimera, takeover

c = get_chimera()

# All draft keys with context limits
c.drafts()  # → [KeyState(id, provider, model, last_used, status, context_limit)]

# Count
c.count()  # → int

# Virtual LLM: min context across ALL draft keys
c.virtual_llm()  
# → {'provider': 'zai', 'model': 'glm-5', 'context_limit': 128000, 'key_id': '8def58'}

# Record usage (persists to auth.json)
c.record_use('key_id', 'model_name')

# Force kanban config sync
takeover()
```

## KeyState fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | Key ID from auth.json |
| `provider` | str | Provider name (zai, copilot, minimax, etc.) |
| `model` | str | Last used model |
| `last_used` | int | Unix timestamp |
| `status` | str | `draft` \| `exhausted` \| `dead` |
| `context_limit` | int | Effective context for this key's model |

## How virtual LLM works

```
Draft keys:
  zai          → glm-5        → 128k
  copilot      → gpt-4o       → 128k  
  openai-codex → gpt-5        → 272k
  nvidia       → nemotron-3   → 128k
  nous         → hermes-3-70b → 256k

virtual_llm() → context_limit: 128000 (MINIMUM of all)
```

Any draft key can handle the virtual LLM's context.

## Auto-takeover

On plugin register (Hermes startup or `hermes plugins list`):
```
Chimera takeover: max_in_progress=5, max_spawn=5
Chimera: 5 drafts ready, takeover complete
```

## Context limits table (built-in)

```python
CONTEXT_LIMITS = {
    "zai":           {"glm-5": 128_000, "default": 128_000},
    "copilot":       {"gpt-4o": 128_000, "default": 128_000},
    "minimax":       {"minimax-01": 256_000, "default": 256_000},
    "openai-codex":  {"gpt-5": 272_000, "default": 272_000},
    "nous":          {"hermes-3-70b": 256_000, "default": 256_000},
    "nvidia":        {"nemotron-3-ultra": 128_000, "default": 128_000},
}
```

## License

MIT