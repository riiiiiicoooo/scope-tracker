"""
CSV Time Entry Importer — Load time entries from external timekeeping systems.

Supports multiple format variations from common legal timekeeping platforms:
- Clio (cloud-based practice management)
- PracticePanther (cloud practice management)
- Bill4Time (time and expense tracking)

The importer does three things:
1. Reads CSV files and maps columns to a canonical format
2. Parses descriptions to extract work categories and keywords
3. Matches entries to scoped deliverables or flags as potential scope drift

Design constraint: No dependencies beyond stdlib. Designed for small firms
running on shared drives with minimal IT support.
"""

import csv
import re
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional, Dict, List, Callable
from enum import Enum
import difflib


# ---------------------------------------------------------------------------
# Enums and Data Models
# ---------------------------------------------------------------------------

class TaskCategory(Enum):
    """Inferred category of work from time entry description."""
    RESEARCH = "research"
    DRAFTING = "drafting"
    NEGOTIATION = "negotiation"
    REVIEW = "review"
    COMMUNICATION = "communication"
    COORDINATION = "coordination"
    CLOSING = "closing"
    DUE_DILIGENCE = "due_diligence"
    OTHER = "other"


class TimeEntrySource(Enum):
    """Where the time entry came from."""
    CLIO = "clio"
    PRACTICEPANTHER = "practicepanther"
    BILL4TIME = "bill4time"
    MANUAL = "manual"


@dataclass
class ParsedTimeEntry:
    """A time entry as parsed from CSV, before matching to deliverables."""
    date: date
    team_member: str
    hours: float
    description: str
    matter_id: Optional[str]
    task_category: TaskCategory
    keywords: List[str]
    confidence_score: float  # 0.0-1.0 for category match
    raw_source: Dict  # Original CSV row
    source_system: TimeEntrySource

    @property
    def is_ambiguous(self) -> bool:
        """Flag entries where category is unclear or keywords suggest scope creep."""
        return self.confidence_score < 0.7


@dataclass
class MatchResult:
    """Result of matching a parsed entry to a deliverable."""
    parsed_entry: ParsedTimeEntry
    matched_deliverable_id: Optional[str]
    match_score: float  # 0.0-1.0
    is_unscoped: bool
    reasoning: str
    suggested_category: str


# ---------------------------------------------------------------------------
# CSV Column Mapping
# ---------------------------------------------------------------------------

@dataclass
class ColumnMapping:
    """Maps CSV columns from external system to canonical format."""
    date_col: str
    team_member_col: str
    hours_col: str
    description_col: str
    matter_id_col: Optional[str] = None
    task_type_col: Optional[str] = None
    date_format: str = "%Y-%m-%d"

    @staticmethod
    def clio() -> "ColumnMapping":
        """Standard Clio export format."""
        return ColumnMapping(
            date_col="Date",
            team_member_col="Timekeeper",
            hours_col="Duration (hours)",
            description_col="Description",
            matter_id_col="Matter ID",
            task_type_col="Task",
            date_format="%m/%d/%Y",
        )

    @staticmethod
    def practicepanther() -> "ColumnMapping":
        """Standard PracticePanther export format."""
        return ColumnMapping(
            date_col="Entry Date",
            team_member_col="User",
            hours_col="Hours",
            description_col="Note",
            matter_id_col="Matter Name",
            task_type_col="Task Category",
            date_format="%m/%d/%Y",
        )

    @staticmethod
    def bill4time() -> "ColumnMapping":
        """Standard Bill4Time export format."""
        return ColumnMapping(
            date_col="Date",
            team_member_col="Employee",
            hours_col="Hours",
            description_col="Description",
            matter_id_col="Project",
            date_format="%Y-%m-%d",
        )


# ---------------------------------------------------------------------------
# Description Parser
# ---------------------------------------------------------------------------

class DescriptionParser:
    """Extracts work category and keywords from time entry descriptions."""

    # Keyword mappings for category detection
    CATEGORY_KEYWORDS = {
        TaskCategory.RESEARCH: [
            "research", "review literature", "review case law", "legal authority",
            "prior transactions", "market analysis", "precedent", "investigate",
        ],
        TaskCategory.DRAFTING: [
            "draft", "prepare", "compose", "write", "create", "form", "template",
            "redline", "revise document",
        ],
        TaskCategory.NEGOTIATION: [
            "negotiate", "discuss terms", "clarify language", "push back",
            "settlement", "bargain", "terms", "language discussion",
        ],
        TaskCategory.REVIEW: [
            "review", "analyze", "examine", "check", "verify", "audit",
            "read through", "examine", "assess", "approve", "comment on",
        ],
        TaskCategory.COMMUNICATION: [
            "call", "email", "phone", "meeting", "conference", "client call",
            "team meeting", "party call", "discussion with", "update client",
        ],
        TaskCategory.COORDINATION: [
            "coordinate", "arrange", "schedule", "organize", "confirm",
            "liaise", "manage schedule", "align parties",
        ],
        TaskCategory.CLOSING: [
            "closing", "close", "finalize", "execution", "closing documents",
            "closing statement", "final", "wiring", "fund", "disburse",
        ],
        TaskCategory.DUE_DILIGENCE: [
            "due diligence", "diligence", "dd review", "audit", "dataroom",
            "disclosure", "certificate", "representation", "warrant",
        ],
    }

    # Keywords that suggest out-of-scope or drift work
    DRIFT_KEYWORDS = [
        "additional", "extra", "beyond scope", "client requested", "new request",
        "side letter", "earnout", "contingency", "indemnity", "expanded",
        "landlord", "tenant", "third party", "external", "unexpected",
    ]

    @staticmethod
    def parse(description: str) -> tuple[TaskCategory, List[str], float]:
        """Parse description and return (category, keywords, confidence).

        Returns:
            Tuple of (primary_category, extracted_keywords, confidence_score)
            confidence_score ranges from 0.0 (no clear match) to 1.0 (high confidence)
        """
        desc_lower = description.lower()
        words = desc_lower.split()

        # Score each category
        category_scores = {}
        for category, keywords in DescriptionParser.CATEGORY_KEYWORDS.items():
            matches = sum(1 for kw in keywords if kw in desc_lower)
            score = min(1.0, matches / max(1, len(keywords) / 2))  # Normalize
            if score > 0:
                category_scores[category] = score

        # Determine primary category
        if category_scores:
            primary = max(category_scores, key=category_scores.get)
            confidence = category_scores[primary]
        else:
            primary = TaskCategory.OTHER
            confidence = 0.3  # Low confidence fallback

        # Extract keywords
        extracted = []
        for kw in DescriptionParser.DRIFT_KEYWORDS:
            if kw in desc_lower:
                extracted.append(kw)

        return primary, extracted, confidence

    @staticmethod
    def extract_scope_references(description: str) -> List[str]:
        """Extract references to common legal deliverables from description."""
        references = []
        patterns = {
            "purchase_agreement": r"(purchase|pa|psa|agreement)",
            "due_diligence": r"(due\s?diligence|dd|audit|disclosure)",
            "lease": r"(lease|assignment)",
            "closing": r"(closing|close|execution)",
            "earnout": r"(earnout|earn\-out)",
            "title": r"(title\s?(commitment|insurance|report)|title_review)",
            "survey": r"(survey|alta|as-built)",
            "environmental": r"(environmental|phase\s?\d|epa|contamination)",
            "financing": r"(financing|loan|lender|mortgage)",
            "insurance": r"(insurance|coverage|policy)",
        }

        for doc_type, pattern in patterns.items():
            if re.search(pattern, description, re.IGNORECASE):
                references.append(doc_type)

        return references


# ---------------------------------------------------------------------------
# Deliverable Matcher
# ---------------------------------------------------------------------------

class DeliverableMatcher:
    """Matches time entries to scoped deliverables using keyword and fuzzy matching."""

    def __init__(self, deliverables: List[Dict]):
        """Initialize with list of deliverables from engagement.

        Args:
            deliverables: List of dicts with keys: id, name, description
        """
        self.deliverables = deliverables

    def match(
        self,
        parsed_entry: ParsedTimeEntry,
        threshold: float = 0.6,
    ) -> MatchResult:
        """Match a parsed entry to a deliverable.

        Uses three matching strategies:
        1. Exact keyword match (description contains deliverable keywords)
        2. Fuzzy string similarity (name/description similarity)
        3. Task category heuristics

        Args:
            parsed_entry: Parsed time entry
            threshold: Minimum match score to consider it a match (0.0-1.0)

        Returns:
            MatchResult with matched_deliverable_id and reasoning
        """
        if not self.deliverables:
            return MatchResult(
                parsed_entry=parsed_entry,
                matched_deliverable_id=None,
                match_score=0.0,
                is_unscoped=True,
                reasoning="No deliverables configured for this engagement",
                suggested_category="",
            )

        # Score each deliverable
        scores = {}
        for del_id, deliverable in enumerate(self.deliverables):
            score = self._score_match(parsed_entry, deliverable)
            scores[del_id] = score

        # Find best match
        best_idx = max(scores, key=scores.get)
        best_score = scores[best_idx]

        if best_score >= threshold:
            matched_id = self.deliverables[best_idx]["id"]
            reasoning = f"Matched to '{self.deliverables[best_idx]['name']}' (score: {best_score:.2f})"
            is_unscoped = False
        else:
            matched_id = None
            reasoning = f"No strong match. Best score: {best_score:.2f} (threshold: {threshold})"
            is_unscoped = True

        return MatchResult(
            parsed_entry=parsed_entry,
            matched_deliverable_id=matched_id,
            match_score=best_score,
            is_unscoped=is_unscoped,
            reasoning=reasoning,
            suggested_category=parsed_entry.task_category.value,
        )

    def _score_match(
        self,
        entry: ParsedTimeEntry,
        deliverable: Dict,
    ) -> float:
        """Calculate match score between entry and deliverable."""
        score = 0.0
        weights = {
            "keyword_match": 0.4,
            "name_similarity": 0.3,
            "description_similarity": 0.2,
            "category_heuristic": 0.1,
        }

        # 1. Keyword match: check if entry description mentions deliverable topics
        entry_refs = DescriptionParser.extract_scope_references(entry.description)
        deliverable_keywords = set(
            deliverable.get("name", "").lower().split() +
            deliverable.get("description", "").lower().split()
        )

        keyword_hits = sum(
            1 for ref in entry_refs
            if any(ref_word in kw for ref_word in ref.split("_"))
            for kw in deliverable_keywords
        )
        keyword_score = min(1.0, keyword_hits / max(1, len(entry_refs)))
        score += keyword_score * weights["keyword_match"]

        # 2. Name similarity: fuzzy match on deliverable name
        name_similarity = difflib.SequenceMatcher(
            None,
            entry.description.lower(),
            deliverable.get("name", "").lower(),
        ).ratio()
        score += name_similarity * weights["name_similarity"]

        # 3. Description similarity: fuzzy match on deliverable description
        desc_similarity = difflib.SequenceMatcher(
            None,
            entry.description.lower(),
            deliverable.get("description", "").lower(),
        ).ratio()
        score += desc_similarity * weights["description_similarity"]

        # 4. Category heuristics
        category_match = self._category_matches_deliverable(
            entry.task_category, deliverable
        )
        score += (1.0 if category_match else 0.2) * weights["category_heuristic"]

        return min(1.0, score)

    @staticmethod
    def _category_matches_deliverable(
        category: TaskCategory,
        deliverable: Dict,
    ) -> bool:
        """Check if entry category logically matches deliverable type."""
        del_name_lower = deliverable.get("name", "").lower()

        # Heuristic mappings
        heuristics = {
            TaskCategory.DRAFTING: ["draft", "prepare", "create"],
            TaskCategory.REVIEW: ["review", "analyze", "audit"],
            TaskCategory.NEGOTIATION: ["negoti", "discuss"],
            TaskCategory.CLOSING: ["closing", "final", "execution"],
            TaskCategory.DUE_DILIGENCE: ["due diligence", "review", "audit"],
        }

        if category not in heuristics:
            return False

        keywords = heuristics[category]
        return any(kw in del_name_lower for kw in keywords)


# ---------------------------------------------------------------------------
# CSV Importer
# ---------------------------------------------------------------------------

class TimeEntryImporter:
    """Imports time entries from CSV files."""

    def __init__(self, mapping: ColumnMapping, engagement_deliverables: List[Dict] = None):
        """Initialize importer with column mapping.

        Args:
            mapping: ColumnMapping specifying CSV format
            engagement_deliverables: List of dicts with id, name, description
        """
        self.mapping = mapping
        self.matcher = DeliverableMatcher(engagement_deliverables or [])
        self.parsed_entries: List[ParsedTimeEntry] = []
        self.match_results: List[MatchResult] = []

    def import_csv(
        self,
        file_path: str,
        source_system: TimeEntrySource = TimeEntrySource.MANUAL,
        match_threshold: float = 0.6,
    ) -> tuple[List[ParsedTimeEntry], List[MatchResult]]:
        """Import and parse time entries from a CSV file.

        Args:
            file_path: Path to CSV file
            source_system: Which system this came from (for context)
            match_threshold: Minimum score to match to deliverable

        Returns:
            Tuple of (parsed_entries, match_results)
        """
        self.parsed_entries = []
        self.match_results = []

        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row_idx, row in enumerate(reader, start=2):  # Start at 2 (headers are 1)
                try:
                    entry = self._parse_row(row, source_system)
                    self.parsed_entries.append(entry)

                    # Match to deliverable
                    match = self.matcher.match(entry, threshold=match_threshold)
                    self.match_results.append(match)

                except ValueError as e:
                    print(f"Warning: Skipping row {row_idx}: {e}")

        return self.parsed_entries, self.match_results

    def _parse_row(
        self,
        row: Dict[str, str],
        source_system: TimeEntrySource,
    ) -> ParsedTimeEntry:
        """Parse a single CSV row into a ParsedTimeEntry."""
        # Extract and validate fields
        date_str = row.get(self.mapping.date_col, "").strip()
        hours_str = row.get(self.mapping.hours_col, "").strip()
        description = row.get(self.mapping.description_col, "").strip()
        team_member = row.get(self.mapping.team_member_col, "").strip()
        matter_id = row.get(self.mapping.matter_id_col, "").strip() if self.mapping.matter_id_col else None

        if not all([date_str, hours_str, description, team_member]):
            raise ValueError("Missing required fields")

        # Parse date
        try:
            entry_date = datetime.strptime(date_str, self.mapping.date_format).date()
        except ValueError as e:
            raise ValueError(f"Invalid date format '{date_str}': {e}")

        # Parse hours
        try:
            hours = float(hours_str)
        except ValueError:
            raise ValueError(f"Invalid hours value '{hours_str}'")

        # Parse description
        category, keywords, confidence = DescriptionParser.parse(description)

        return ParsedTimeEntry(
            date=entry_date,
            team_member=team_member,
            hours=hours,
            description=description,
            matter_id=matter_id,
            task_category=category,
            keywords=keywords,
            confidence_score=confidence,
            raw_source=row,
            source_system=source_system,
        )

    def get_summary(self) -> Dict:
        """Summary of import results."""
        total_entries = len(self.parsed_entries)
        total_hours = sum(e.hours for e in self.parsed_entries)

        unscoped = [m for m in self.match_results if m.is_unscoped]
        unscoped_hours = sum(m.parsed_entry.hours for m in unscoped)

        ambiguous = [p for p in self.parsed_entries if p.is_ambiguous]

        by_category = {}
        for entry in self.parsed_entries:
            cat = entry.task_category.value
            by_category[cat] = by_category.get(cat, 0) + entry.hours

        by_team_member = {}
        for entry in self.parsed_entries:
            tm = entry.team_member
            by_team_member[tm] = by_team_member.get(tm, 0) + entry.hours

        return {
            "total_entries": total_entries,
            "total_hours": round(total_hours, 1),
            "unscoped_entries": len(unscoped),
            "unscoped_hours": round(unscoped_hours, 1),
            "unscoped_pct": round(unscoped_hours / total_hours * 100, 1) if total_hours > 0 else 0,
            "ambiguous_entries": len(ambiguous),
            "by_category": by_category,
            "by_team_member": by_team_member,
        }

    def print_summary(self) -> None:
        """Print import summary to stdout."""
        summary = self.get_summary()
        print("\n" + "=" * 70)
        print("TIME ENTRY IMPORT SUMMARY")
        print("=" * 70)
        print(f"Total entries:      {summary['total_entries']}")
        print(f"Total hours:        {summary['total_hours']:.1f}")
        print(f"Unscoped entries:   {summary['unscoped_entries']} ({summary['unscoped_pct']:.1f}% of hours)")
        print(f"Ambiguous entries:  {summary['ambiguous_entries']}")
        print()

        if summary["by_category"]:
            print("By Category:")
            for cat, hours in sorted(summary["by_category"].items(), key=lambda x: -x[1]):
                print(f"  {cat:<20} {hours:>6.1f} hours")
            print()

        if summary["by_team_member"]:
            print("By Team Member:")
            for member, hours in sorted(summary["by_team_member"].items(), key=lambda x: -x[1]):
                print(f"  {member:<30} {hours:>6.1f} hours")
            print()
