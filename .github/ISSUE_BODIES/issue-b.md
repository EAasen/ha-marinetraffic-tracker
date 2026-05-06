## Summary

`VesselData` is documented as an *"Immutable snapshot"* in its class docstring, but `coordinator.py` mutates the `last_seen` field directly on the live object. This creates a misleading contract and a potential source of subtle bugs if the dataclass is ever made `frozen=True` or if code assumes snapshots are safe to share without copying.

---

## Reproduction

**`client.py` — `VesselData` docstring (line ~78):**

```python
@dataclass
class VesselData:
    """Immutable snapshot of a single vessel's state.
    ...
    """
```

**`coordinator.py` — `_async_update_data` (line ~183):**

```python
for vessel in fresh:
    vessel.last_seen = now          # ← direct mutation of a "snapshot"
    self._vessels[vessel.mmsi] = vessel
```

The mutation happens *before* the object is stored in `self._vessels`, so at this exact moment the coordinator has already given the same object reference to the caller if `get_vessels_in_radius` returned it. In the current single-threaded async design this is harmless, but the docstring promise is broken.

---

## Options

### Option 1 — Remove the "Immutable" claim (minimal fix)

Update the `VesselData` docstring to say *"snapshot"* rather than *"immutable snapshot"* and add a note that `last_seen` is updated by the coordinator.

**Pros:** Smallest change, no functional impact.
**Cons:** Does not enforce the intended design; the field remains mutable.

### Option 2 — Use `dataclasses.replace()` to produce a fresh copy (preferred)

```python
from dataclasses import replace

for vessel in fresh:
    updated = replace(vessel, last_seen=now)
    self._vessels[updated.mmsi] = updated
```

This preserves the original snapshot from the client and stores a new object with the updated timestamp.

**Pros:** True snapshot semantics; safe to share references from `_parse_row`.
**Cons:** Minor extra allocation per vessel per poll cycle (negligible).

### Option 3 — Make the dataclass `frozen=True` and store timestamps separately

Store `last_seen` outside `VesselData` (e.g., in a parallel `dict[str, datetime]` in the coordinator).

**Pros:** Enforces immutability at the Python level.
**Cons:** More invasive refactor; separates logically related data.

---

## Recommendation

**Option 2** — `dataclasses.replace()` in `coordinator.py`. It is a one-line fix, preserves the intended immutability, and does not require any interface changes downstream.

---

## Acceptance criteria

- [ ] `VesselData` docstring accurately reflects its mutability contract.
- [ ] `coordinator.py` no longer directly mutates `vessel.last_seen` on an object returned by the client.
- [ ] All existing tests still pass.
- [ ] Ruff clean.

_Originated from the non-blocking items noted in PR #19._
