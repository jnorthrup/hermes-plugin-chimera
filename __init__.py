"""
Chimera - Observable key->model array for Hermes.

Simple brainless module: loads keys from auth.json, tracks last_used,
provides array of draft keys with timeout logic.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

AUTH_PATH = Path.home() / ".hermes" / "auth.json"
AGENT_TIMEOUT = 600  # seconds


@dataclass
class KeyState:
    """Observable key state."""
    id: str
    provider: str
    model: str = ""
    last_used: int = 0
    status: str = "draft"  # draft, exhausted, dead


@dataclass
class Chimera:
    """Observable key->model array."""
    
    keys: list[KeyState] = field(default_factory=list)
    _loaded_at: int = 0
    
    def load(self) -> None:
        """Load keys from auth.json."""
        if not AUTH_PATH.exists():
            self.keys = []
            return
            
        pool = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
        cred_pool = pool.get("credential_pool", {})
        
        self.keys.clear()
        now = time.time()
        
        for provider, creds in cred_pool.items():
            if not isinstance(creds, list):
                continue
            for cred in creds:
                key_id = cred.get("id", "")
                if not key_id:
                    continue
                    
                last_status = cred.get("last_status")
                if last_status in (None, "ok", ""):
                    last_status = "draft"
                reset_at = cred.get("last_error_reset_at", 0)
                
                if last_status == "dead":
                    continue
                    
                if last_status == "exhausted" and reset_at and reset_at < now:
                    last_status = "draft"
                
                # Check timeout - key too old?
                last_used = cred.get("last_used_at", 0)
                if last_used > 0 and (now - last_used) > AGENT_TIMEOUT:
                    # Key timed out, treat as available
                    last_used = 0
                
                self.keys.append(KeyState(
                    id=key_id,
                    provider=provider,
                    model=cred.get("last_model", ""),
                    last_used=last_used,
                    status=last_status,
                ))
        
        self._loaded_at = int(now)
    
    def drafts(self) -> list[KeyState]:
        """Get all draft keys."""
        return [k for k in self.keys if k.status == "draft"]
    
    def count(self) -> int:
        """Count of draft keys."""
        return len(self.drafts())
    
    def get(self, key_id: str) -> Optional[KeyState]:
        """Get key by id."""
        for k in self.keys:
            if k.id == key_id:
                return k
        return None
    
    def record_use(self, key_id: str, model: str) -> None:
        """Record key usage. Persists to auth.json."""
        now = int(time.time())
        
        # Update local state
        for k in self.keys:
            if k.id == key_id:
                k.last_used = now
                k.model = model
                break
        
        # Persist to auth.json
        pool = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
        for provider, creds in pool.get("credential_pool", {}).items():
            if not isinstance(creds, list):
                continue
            for cred in creds:
                if cred.get("id") == key_id:
                    cred["last_model"] = model
                    cred["last_used_at"] = now
                    break
        
        AUTH_PATH.write_text(json.dumps(pool, indent=2), encoding="utf-8")
    
    def most_recent(self) -> Optional[KeyState]:
        """Most recently used draft key."""
        candidates = [k for k in self.drafts() if k.last_used > 0]
        if not candidates:
            return None
        return max(candidates, key=lambda k: k.last_used)
    
    def oldest(self) -> Optional[KeyState]:
        """Oldest used draft key (or most recent if none used)."""
        candidates = self.drafts()
        if not candidates:
            return None
        # Prefer keys with last_used > 0, sorted oldest first
        used = [k for k in candidates if k.last_used > 0]
        if used:
            return min(used, key=lambda k: k.last_used)
        # All fresh, return any
        return candidates[0]


# Singleton instance
_chimera: Optional[Chimera] = None


def get_chimera() -> Chimera:
    """Get chimera instance."""
    global _chimera
    if _chimera is None:
        _chimera = Chimera()
        _chimera.load()
    return _chimera


def register(ctx) -> None:
    """Plugin register hook - runs takeover on setup."""
    c = get_chimera()
    takeover()
    print(f"Chimera: {c.count()} drafts ready, takeover complete")


def takeover() -> None:
    """Take over kanban: repopulate agents with chimera keys.
    
    Updates kanban config to use chimera draft count.
    """
    c = get_chimera()
    c.load()
    
    drafts = c.count()
    if drafts == 0:
        print("Chimera: no draft keys available")
        return
    
    # Update kanban config
    config = {
        "kanban.max_in_progress": drafts,
        "kanban.max_spawn": drafts,
    }
    
    import subprocess
    for key, value in config.items():
        subprocess.run(
            ["hermes", "config", "set", key, str(value)],
            capture_output=True,
            check=False,
        )
    
    print(f"Chimera takeover: max_in_progress={drafts}, max_spawn={drafts}")


def unregister() -> None:
    """Plugin unregister hook."""
    global _chimera
    _chimera = None
