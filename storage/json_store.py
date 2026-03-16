"""
JSON Persistence Layer — Save and load engagement state to JSON files.

Designed for small firms using shared drives. No database, no complex ORM.
Just files on a shared drive that teams can version control and backup.

Structure:
  data/
    engagements/
      {engagement_id}/
        engagement.json      — Main engagement definition and metadata
        time_entries.json    — All time entries logged
        drift_history.json   — Weekly snapshots of drift alerts
        change_orders/
          {co_id}.json       — Formal change order document

Features:
- Auto-save on any changes (engagement.json updated whenever state changes)
- Simple file-based locking for shared drive support
- load_engagement() and list_engagements() functions
- Backup/export to ZIP with single function call
- Human-readable JSON (for manual editing if needed)
"""

import json
import os
import shutil
import zipfile
from pathlib import Path
from datetime import datetime, date
from typing import Optional, Dict, List, Any
from dataclasses import asdict, dataclass, field
from collections import defaultdict
import time

# Import data models from src
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.engagement_tracker import (
    Engagement, EngagementStatus, Deliverable, DeliverableStatus,
    TeamMember, TimeEntry, ChangeOrder, PracticeArea, TeamRole,
)
from src.drift_detector import DriftAlert, DriftType, AlertSeverity, AlertStatus


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

class JSONEncoder(json.JSONEncoder):
    """Custom encoder that handles enums and date objects."""

    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if hasattr(obj, "value"):  # Enum
            return obj.value
        if hasattr(obj, "__dataclass_fields__"):  # Dataclass
            return asdict(obj)
        return super().default(obj)


def custom_decoder(obj: Dict) -> Dict:
    """Custom decoder for common patterns."""
    # Try to detect and convert ISO date strings
    for key, value in obj.items():
        if isinstance(value, str):
            # Try parsing as date
            for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"]:
                try:
                    parsed = datetime.strptime(value, fmt)
                    obj[key] = parsed.date() if fmt == "%Y-%m-%d" else parsed
                    break
                except ValueError:
                    continue
    return obj


def _ensure_json_serializable(obj: Any) -> Any:
    """Recursively convert objects to JSON-serializable types."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if hasattr(obj, "value"):  # Enum
        return obj.value
    if isinstance(obj, dict):
        return {k: _ensure_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_ensure_json_serializable(v) for v in obj]
    if hasattr(obj, "__dataclass_fields__"):  # Dataclass
        return {k: _ensure_json_serializable(v)
                for k, v in asdict(obj).items()}
    return obj


# ---------------------------------------------------------------------------
# File Locking
# ---------------------------------------------------------------------------

class FileLock:
    """Simple file-based lock for shared drive support."""

    def __init__(self, lock_path: str, timeout: float = 30.0):
        self.lock_path = lock_path
        self.timeout = timeout
        self.acquired = False

    def acquire(self) -> bool:
        """Try to acquire lock. Returns True if successful."""
        start_time = time.time()
        while time.time() - start_time < self.timeout:
            try:
                # Create lock file atomically
                fd = os.open(
                    self.lock_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o644,
                )
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                self.acquired = True
                return True
            except FileExistsError:
                time.sleep(0.1)
        return False

    def release(self) -> None:
        """Release the lock."""
        try:
            if os.path.exists(self.lock_path):
                os.remove(self.lock_path)
            self.acquired = False
        except OSError:
            pass

    def __enter__(self):
        if not self.acquire():
            raise TimeoutError(f"Could not acquire lock: {self.lock_path}")
        return self

    def __exit__(self, *args):
        self.release()


# ---------------------------------------------------------------------------
# JSON Store
# ---------------------------------------------------------------------------

class JSONStore:
    """Persistence layer using JSON files on shared drive."""

    def __init__(self, data_dir: str = "data"):
        """Initialize store with base data directory.

        Args:
            data_dir: Base directory for all engagement data
        """
        self.base_dir = Path(data_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _engagement_dir(self, engagement_id: str) -> Path:
        """Get directory path for an engagement."""
        path = self.base_dir / "engagements" / engagement_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _lock_path(self, engagement_id: str) -> Path:
        """Get lock file path for an engagement."""
        return self._engagement_dir(engagement_id) / ".lock"

    # -- Load Operations -------------------------------------------------------

    def load_engagement(self, engagement_id: str) -> Optional[Engagement]:
        """Load a complete engagement with all associated data.

        Returns None if engagement doesn't exist.
        """
        eng_file = self._engagement_dir(engagement_id) / "engagement.json"
        if not eng_file.exists():
            return None

        try:
            with open(eng_file, "r") as f:
                data = json.load(f, object_hook=custom_decoder)

            # Reconstruct Engagement object with all relationships
            eng = self._deserialize_engagement(data)

            # Load time entries
            time_entries = self.load_time_entries(engagement_id)
            eng.time_entries = time_entries

            # Load change orders
            change_orders = self.load_change_orders(engagement_id)
            eng.change_orders = change_orders

            return eng

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print(f"Error loading engagement {engagement_id}: {e}")
            return None

    def load_time_entries(self, engagement_id: str) -> List[TimeEntry]:
        """Load all time entries for an engagement."""
        entries_file = self._engagement_dir(engagement_id) / "time_entries.json"
        if not entries_file.exists():
            return []

        try:
            with open(entries_file, "r") as f:
                data = json.load(f, object_hook=custom_decoder)

            entries = []
            for entry_data in data.get("entries", []):
                entry = TimeEntry(
                    id=entry_data["id"],
                    engagement_id=entry_data["engagement_id"],
                    team_member=entry_data["team_member"],
                    date=entry_data["date"],
                    hours=entry_data["hours"],
                    description=entry_data["description"],
                    deliverable_id=entry_data.get("deliverable_id"),
                    is_scoped=entry_data.get("is_scoped", True),
                    flagged=entry_data.get("flagged", False),
                    flag_reason=entry_data.get("flag_reason"),
                )
                entries.append(entry)
            return entries
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error loading time entries for {engagement_id}: {e}")
            return []

    def load_change_orders(self, engagement_id: str) -> List[ChangeOrder]:
        """Load all change orders for an engagement."""
        co_dir = self._engagement_dir(engagement_id) / "change_orders"
        if not co_dir.exists():
            return []

        change_orders = []
        for co_file in co_dir.glob("*.json"):
            try:
                with open(co_file, "r") as f:
                    data = json.load(f, object_hook=custom_decoder)

                co = ChangeOrder(
                    id=data["id"],
                    engagement_id=data["engagement_id"],
                    created_at=data["created_at"],
                    created_by=data["created_by"],
                    status=data["status"],
                    new_deliverables=data["new_deliverables"],
                    additional_hours=data["additional_hours"],
                    additional_cost=data["additional_cost"],
                    reason=data["reason"],
                    client_request_description=data["client_request_description"],
                    original_fee=data["original_fee"],
                    revised_fee=data["revised_fee"],
                    approved_at=data.get("approved_at"),
                    approved_by=data.get("approved_by"),
                    notes=data.get("notes", ""),
                )
                change_orders.append(co)
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Error loading change order {co_file}: {e}")

        return change_orders

    def load_drift_history(self, engagement_id: str) -> List[Dict]:
        """Load drift history (weekly snapshots)."""
        history_file = self._engagement_dir(engagement_id) / "drift_history.json"
        if not history_file.exists():
            return []

        try:
            with open(history_file, "r") as f:
                data = json.load(f, object_hook=custom_decoder)
            return data.get("history", [])
        except json.JSONDecodeError:
            return []

    def list_engagements(
        self, limit: int = 50, offset: int = 0
    ) -> List[str]:
        """List engagement IDs in the store with pagination.

        Args:
            limit: Maximum number of results to return (default 50, max 200).
            offset: Number of results to skip (default 0).

        Returns:
            List of engagement IDs, paginated.
        """
        limit = min(limit, 200)  # Cap at 200
        eng_dir = self.base_dir / "engagements"
        if not eng_dir.exists():
            return []

        all_ids = sorted([
            d.name for d in eng_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ])
        return all_ids[offset : offset + limit]

    # -- Save Operations -------------------------------------------------------

    def save_engagement(self, engagement: Engagement) -> bool:
        """Save engagement metadata to JSON.

        Returns True if successful, False otherwise.
        """
        try:
            lock = FileLock(str(self._lock_path(engagement.id)))
            with lock:
                eng_dir = self._engagement_dir(engagement.id)

                # Serialize engagement
                eng_data = self._serialize_engagement(engagement)

                eng_file = eng_dir / "engagement.json"
                with open(eng_file, "w") as f:
                    json.dump(eng_data, f, indent=2, cls=JSONEncoder)

                return True
        except Exception as e:
            print(f"Error saving engagement {engagement.id}: {e}")
            return False

    def save_time_entries(
        self,
        engagement_id: str,
        time_entries: List[TimeEntry],
    ) -> bool:
        """Save all time entries for an engagement."""
        try:
            lock = FileLock(str(self._lock_path(engagement_id)))
            with lock:
                eng_dir = self._engagement_dir(engagement_id)
                entries_file = eng_dir / "time_entries.json"

                entries_data = []
                for entry in time_entries:
                    entries_data.append({
                        "id": entry.id,
                        "engagement_id": entry.engagement_id,
                        "team_member": entry.team_member,
                        "date": entry.date.isoformat(),
                        "hours": entry.hours,
                        "description": entry.description,
                        "deliverable_id": entry.deliverable_id,
                        "is_scoped": entry.is_scoped,
                        "flagged": entry.flagged,
                        "flag_reason": entry.flag_reason,
                    })

                with open(entries_file, "w") as f:
                    json.dump({"entries": entries_data}, f, indent=2)

                return True
        except Exception as e:
            print(f"Error saving time entries for {engagement_id}: {e}")
            return False

    def save_change_order(
        self,
        engagement_id: str,
        change_order: ChangeOrder,
    ) -> bool:
        """Save a change order to JSON."""
        try:
            lock = FileLock(str(self._lock_path(engagement_id)))
            with lock:
                co_dir = self._engagement_dir(engagement_id) / "change_orders"
                co_dir.mkdir(exist_ok=True)

                co_file = co_dir / f"{change_order.id}.json"

                co_data = {
                    "id": change_order.id,
                    "engagement_id": change_order.engagement_id,
                    "created_at": change_order.created_at.isoformat(),
                    "created_by": change_order.created_by,
                    "status": change_order.status,
                    "new_deliverables": change_order.new_deliverables,
                    "additional_hours": change_order.additional_hours,
                    "additional_cost": change_order.additional_cost,
                    "reason": change_order.reason,
                    "client_request_description": change_order.client_request_description,
                    "original_fee": change_order.original_fee,
                    "revised_fee": change_order.revised_fee,
                    "approved_at": change_order.approved_at.isoformat() if change_order.approved_at else None,
                    "approved_by": change_order.approved_by,
                    "notes": change_order.notes,
                }

                with open(co_file, "w") as f:
                    json.dump(co_data, f, indent=2)

                return True
        except Exception as e:
            print(f"Error saving change order {change_order.id}: {e}")
            return False

    def append_drift_history(
        self,
        engagement_id: str,
        snapshot: Dict,
    ) -> bool:
        """Append a weekly drift detection snapshot to history."""
        try:
            lock = FileLock(str(self._lock_path(engagement_id)))
            with lock:
                eng_dir = self._engagement_dir(engagement_id)
                history_file = eng_dir / "drift_history.json"

                # Load existing history
                history = []
                if history_file.exists():
                    with open(history_file, "r") as f:
                        data = json.load(f)
                        history = data.get("history", [])

                # Add new snapshot
                snapshot["timestamp"] = datetime.now().isoformat()
                history.append(_ensure_json_serializable(snapshot))

                # Save updated history
                with open(history_file, "w") as f:
                    json.dump({"history": history}, f, indent=2)

                return True
        except Exception as e:
            print(f"Error appending drift history for {engagement_id}: {e}")
            return False

    # -- Deserialization -------------------------------------------------------

    def _deserialize_engagement(self, data: Dict) -> Engagement:
        """Reconstruct Engagement object from JSON data."""
        # Reconstruct enums
        status = EngagementStatus(data["status"])
        practice_area = PracticeArea(data["practice_area"])

        # Reconstruct team
        team = []
        for member_data in data.get("team", []):
            role = TeamRole(member_data["role"])
            member = TeamMember(
                name=member_data["name"],
                role=role,
                hourly_rate=member_data["hourly_rate"],
                budgeted_hours=member_data["budgeted_hours"],
                actual_hours=member_data.get("actual_hours", 0.0),
            )
            team.append(member)

        # Reconstruct deliverables
        deliverables = []
        for del_data in data.get("deliverables", []):
            del_status = DeliverableStatus(del_data["status"])
            deliverable = Deliverable(
                id=del_data["id"],
                name=del_data["name"],
                description=del_data["description"],
                budgeted_hours=del_data["budgeted_hours"],
                assigned_to=del_data["assigned_to"],
                planned_start=del_data["planned_start"],
                planned_end=del_data["planned_end"],
                status=del_status,
                actual_hours=del_data.get("actual_hours", 0.0),
                actual_start=del_data.get("actual_start"),
                actual_end=del_data.get("actual_end"),
                is_original_scope=del_data.get("is_original_scope", True),
                change_order_id=del_data.get("change_order_id"),
            )
            deliverables.append(deliverable)

        # Reconstruct engagement
        engagement = Engagement(
            id=data["id"],
            client_name=data["client_name"],
            matter_name=data["matter_name"],
            practice_area=practice_area,
            responsible_partner=data["responsible_partner"],
            status=status,
            fixed_fee=data["fixed_fee"],
            total_budgeted_hours=data["total_budgeted_hours"],
            effective_rate=data.get("effective_rate", 0.0),
            engagement_start=data["engagement_start"],
            planned_close=data["planned_close"],
            actual_close=data.get("actual_close"),
            deliverables=deliverables,
            team=team,
            created_at=data["created_at"],
            notes=data.get("notes", ""),
        )

        return engagement

    def _serialize_engagement(self, engagement: Engagement) -> Dict:
        """Convert Engagement object to JSON-serializable dict."""
        return {
            "id": engagement.id,
            "client_name": engagement.client_name,
            "matter_name": engagement.matter_name,
            "practice_area": engagement.practice_area.value,
            "responsible_partner": engagement.responsible_partner,
            "status": engagement.status.value,
            "fixed_fee": engagement.fixed_fee,
            "total_budgeted_hours": engagement.total_budgeted_hours,
            "effective_rate": engagement.effective_rate,
            "engagement_start": engagement.engagement_start.isoformat(),
            "planned_close": engagement.planned_close.isoformat(),
            "actual_close": engagement.actual_close.isoformat() if engagement.actual_close else None,
            "team": [
                {
                    "name": m.name,
                    "role": m.role.value,
                    "hourly_rate": m.hourly_rate,
                    "budgeted_hours": m.budgeted_hours,
                    "actual_hours": m.actual_hours,
                }
                for m in engagement.team
            ],
            "deliverables": [
                {
                    "id": d.id,
                    "name": d.name,
                    "description": d.description,
                    "budgeted_hours": d.budgeted_hours,
                    "assigned_to": d.assigned_to,
                    "planned_start": d.planned_start.isoformat(),
                    "planned_end": d.planned_end.isoformat(),
                    "status": d.status.value,
                    "actual_hours": d.actual_hours,
                    "actual_start": d.actual_start.isoformat() if d.actual_start else None,
                    "actual_end": d.actual_end.isoformat() if d.actual_end else None,
                    "is_original_scope": d.is_original_scope,
                    "change_order_id": d.change_order_id,
                }
                for d in engagement.deliverables
            ],
            "created_at": engagement.created_at.isoformat(),
            "notes": engagement.notes,
        }

    # -- Backup ----------------------------------------------------------------

    def backup(self, backup_path: str) -> bool:
        """Create a ZIP backup of all engagement data.

        Args:
            backup_path: Path to create ZIP file at

        Returns:
            True if successful, False otherwise
        """
        try:
            with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(self.base_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, self.base_dir)
                        zf.write(file_path, arcname)
            print(f"Backup created: {backup_path}")
            return True
        except Exception as e:
            print(f"Error creating backup: {e}")
            return False


# ---------------------------------------------------------------------------
# Usage Example
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from datetime import timedelta

    # Create a sample engagement
    today = date.today = date.fromisoformat("2024-02-15")

    eng = Engagement(
        id="TEST-ENG-001",
        client_name="Meridian Properties LLC",
        matter_name="Acquisition of 450 Commerce Street",
        practice_area=PracticeArea.COMMERCIAL_REAL_ESTATE,
        responsible_partner="David Park",
        status=EngagementStatus.ACTIVE,
        fixed_fee=35000,
        total_budgeted_hours=95,
        engagement_start=today - timedelta(weeks=5),
        planned_close=today + timedelta(weeks=3),
        deliverables=[
            Deliverable(
                id="del_001", name="Purchase Agreement",
                description="Draft and negotiate PSA",
                budgeted_hours=28,
                assigned_to=["Rachel Torres", "Kevin Liu"],
                planned_start=today - timedelta(weeks=5),
                planned_end=today - timedelta(weeks=2),
                status=DeliverableStatus.DELIVERED, actual_hours=31.5,
            ),
        ],
        team=[
            TeamMember("David Park", TeamRole.PARTNER, 550, 8),
            TeamMember("Rachel Torres", TeamRole.SENIOR_ASSOCIATE, 350, 38),
        ],
    )

    # Save engagement
    store = JSONStore()
    if store.save_engagement(eng):
        print("✓ Engagement saved successfully")

    # Load engagement
    loaded = store.load_engagement(eng.id)
    if loaded:
        print(f"✓ Engagement loaded: {loaded.matter_name}")

    # List all engagements
    all_eng = store.list_engagements()
    print(f"✓ Total engagements: {len(all_eng)}")
