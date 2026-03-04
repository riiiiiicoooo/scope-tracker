"""
Scope Tracker - MCP Server
Model Context Protocol implementation for managing scope drift,
time tracking, change orders, and engagement metrics. Integrates with
project management and time tracking systems.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import logging
from decimal import Decimal

from mcp.server import Server, Tool
from mcp.types import TextContent

# Data access
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize MCP Server
server = Server("scope-tracker")


class ScopeDriftAnalyzer:
    """
    Analyzes scope drift by comparing planned vs. actual resource consumption.
    Tracks hours, budget variance, schedule variance, and unplanned scope additions.
    """
    
    DRIFT_THRESHOLDS = {
        "hours_variance_pct": 15,  # Alert if hours exceed budget by 15%+
        "budget_variance_pct": 10,  # Alert if budget variance > 10%
        "schedule_variance_days": 7,  # Alert if schedule slips 7+ days
    }
    
    def __init__(self, analytics_api_url: str, api_key: str):
        self.analytics_api_url = analytics_api_url
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {api_key}"}
        )
    
    async def check_scope_drift(self, engagement_id: str) -> Dict[str, Any]:
        """
        Analyze scope drift for engagement.
        
        Returns:
        - Actual vs planned hours by role/phase
        - Budget vs actual spend
        - Schedule variance
        - Unplanned scope items
        - Drift alerts
        """
        try:
            response = await self.client.get(
                f"{self.analytics_api_url}/engagements/{engagement_id}/scope_analysis"
            )
            response.raise_for_status()
            
            analysis = response.json()
            
            # Calculate drift metrics
            drift_metrics = self._calculate_drift(analysis)
            
            return {
                "engagement_id": engagement_id,
                "metrics": drift_metrics,
                "alerts": self._generate_alerts(drift_metrics),
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            logger.error(f"Scope drift analysis failed: {str(e)}")
            raise
    
    def _calculate_drift(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate drift metrics from engagement analysis."""
        planned_hours = analysis.get("planned_hours", 0)
        actual_hours = analysis.get("actual_hours", 0)
        
        hours_variance_pct = (
            ((actual_hours - planned_hours) / planned_hours * 100)
            if planned_hours > 0
            else 0
        )
        
        planned_budget = analysis.get("planned_budget", 0)
        actual_spend = analysis.get("actual_spend", 0)
        
        budget_variance_pct = (
            ((actual_spend - planned_budget) / planned_budget * 100)
            if planned_budget > 0
            else 0
        )
        
        planned_end = analysis.get("planned_end_date")
        actual_end = analysis.get("estimated_end_date")
        schedule_variance_days = 0
        if planned_end and actual_end:
            schedule_variance_days = (
                datetime.fromisoformat(actual_end) - datetime.fromisoformat(planned_end)
            ).days
        
        return {
            "hours_variance_pct": round(hours_variance_pct, 1),
            "hours_variance_absolute": actual_hours - planned_hours,
            "planned_hours": planned_hours,
            "actual_hours": actual_hours,
            "budget_variance_pct": round(budget_variance_pct, 1),
            "budget_variance_absolute": actual_spend - planned_budget,
            "planned_budget": planned_budget,
            "actual_spend": actual_spend,
            "schedule_variance_days": schedule_variance_days,
            "unplanned_scope_items": analysis.get("unplanned_items", []),
        }
    
    def _generate_alerts(self, metrics: Dict[str, Any]) -> List[Dict[str, str]]:
        """Generate drift alerts based on thresholds."""
        alerts = []
        
        if abs(metrics["hours_variance_pct"]) > self.DRIFT_THRESHOLDS["hours_variance_pct"]:
            alerts.append({
                "severity": "high" if metrics["hours_variance_pct"] > 30 else "medium",
                "type": "hours_drift",
                "message": f"Hours variance: {metrics['hours_variance_pct']}% over/under plan ({metrics['hours_variance_absolute']:.0f} hours)",
            })
        
        if abs(metrics["budget_variance_pct"]) > self.DRIFT_THRESHOLDS["budget_variance_pct"]:
            alerts.append({
                "severity": "high" if metrics["budget_variance_pct"] > 25 else "medium",
                "type": "budget_drift",
                "message": f"Budget variance: {metrics['budget_variance_pct']}% (${metrics['budget_variance_absolute']:.0f})",
            })
        
        if abs(metrics["schedule_variance_days"]) > self.DRIFT_THRESHOLDS["schedule_variance_days"]:
            alerts.append({
                "severity": "medium",
                "type": "schedule_drift",
                "message": f"Schedule slipping by {metrics['schedule_variance_days']} days",
            })
        
        if metrics["unplanned_scope_items"]:
            alerts.append({
                "severity": "info",
                "type": "unplanned_scope",
                "message": f"{len(metrics['unplanned_scope_items'])} unplanned scope items detected",
            })
        
        return sorted(alerts, key=lambda x: ["high", "medium", "low", "info"].index(x["severity"]))


class ChangeOrderGenerator:
    """
    Generates change order documents based on scope changes.
    Includes impact analysis (hours, budget, schedule).
    """
    
    def __init__(self, document_api_url: str, api_key: str):
        self.document_api_url = document_api_url
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {api_key}"}
        )
    
    async def generate_change_order(
        self,
        engagement_id: str,
        reason: str,
        impact_hours: Optional[int] = None,
        impact_budget: Optional[float] = None,
    ) -> str:
        """
        Generate change order document with impact analysis.
        
        Returns markdown-formatted change order ready for review/approval.
        """
        try:
            payload = {
                "engagement_id": engagement_id,
                "reason": reason,
                "impact_hours": impact_hours,
                "impact_budget": impact_budget,
            }
            
            response = await self.client.post(
                f"{self.document_api_url}/change_orders/generate",
                json=payload,
            )
            response.raise_for_status()
            
            return response.json().get("markdown_content", "")
        except Exception as e:
            logger.error(f"Change order generation failed: {str(e)}")
            raise


class TimeEntryTracker:
    """Track and query time entries with filtering and reporting."""
    
    def __init__(self, time_tracking_api_url: str, api_key: str):
        self.time_tracking_api_url = time_tracking_api_url
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {api_key}"}
        )
    
    async def get_time_entries(
        self,
        engagement_id: str,
        date_range: Optional[Dict[str, str]] = None,
        resource_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch time entries for engagement with optional filters.
        
        Returns list of time entries with resource, phase, and allocation info.
        """
        try:
            params = {"engagement_id": engagement_id}
            
            if date_range:
                params["start_date"] = date_range.get("start")
                params["end_date"] = date_range.get("end")
            
            if resource_id:
                params["resource_id"] = resource_id
            
            response = await self.client.get(
                f"{self.time_tracking_api_url}/time_entries",
                params=params,
            )
            response.raise_for_status()
            
            entries = response.json().get("entries", [])
            
            # Group by phase if requested
            grouped = {}
            for entry in entries:
                phase = entry.get("phase", "Unallocated")
                if phase not in grouped:
                    grouped[phase] = []
                grouped[phase].append(entry)
            
            return entries, grouped
        except Exception as e:
            logger.error(f"Time entry retrieval failed: {str(e)}")
            return [], {}


class EngagementManager:
    """Manage and list engagements with status and metrics."""
    
    def __init__(self, project_api_url: str, api_key: str):
        self.project_api_url = project_api_url
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {api_key}"}
        )
    
    async def list_engagements(
        self,
        tenant_id: str,
        status_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        List all engagements with status and key metrics.
        
        Returns engagement list with drift indicators.
        """
        try:
            params = {"tenant_id": tenant_id}
            if status_filter:
                params["status"] = status_filter
            
            response = await self.client.get(
                f"{self.project_api_url}/engagements",
                params=params,
            )
            response.raise_for_status()
            
            engagements = response.json().get("engagements", [])
            
            # Add drift indicators
            for eng in engagements:
                drift_pct = eng.get("hours_variance_pct", 0)
                if abs(drift_pct) > 15:
                    eng["drift_status"] = "high_drift" if drift_pct > 0 else "under_utilized"
                    eng["drift_indicator"] = "warning"
                elif abs(drift_pct) > 5:
                    eng["drift_status"] = "moderate_drift"
                    eng["drift_indicator"] = "caution"
                else:
                    eng["drift_status"] = "on_track"
                    eng["drift_indicator"] = "healthy"
            
            return engagements
        except Exception as e:
            logger.error(f"Engagement listing failed: {str(e)}")
            return []


# Global clients
drift_analyzer = None
change_order_gen = None
time_tracker = None
engagement_mgr = None


@server.list_tools()
def list_tools():
    """Register all scope tracking tools."""
    return [
        Tool(
            name="check_scope_drift",
            description=(
                "Check current scope drift status for an engagement. "
                "Compares planned vs actual hours, budget, schedule, and identifies "
                "unplanned scope items with alerts."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "engagement_id": {
                        "type": "string",
                        "description": "Engagement identifier",
                    },
                    "tenant_id": {
                        "type": "string",
                        "description": "Tenant identifier",
                    },
                },
                "required": ["engagement_id", "tenant_id"],
            },
        ),
        Tool(
            name="generate_change_order",
            description=(
                "Generate change order document for scope change. "
                "Includes impact analysis on hours, budget, and schedule. "
                "Returns markdown ready for client review."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "engagement_id": {
                        "type": "string",
                        "description": "Engagement identifier",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Description of scope change",
                    },
                    "impact_hours": {
                        "type": "integer",
                        "description": "Estimated additional hours required",
                    },
                    "impact_budget": {
                        "type": "number",
                        "description": "Estimated cost impact in USD",
                    },
                    "tenant_id": {
                        "type": "string",
                        "description": "Tenant identifier",
                    },
                },
                "required": ["engagement_id", "reason", "tenant_id"],
            },
        ),
        Tool(
            name="get_time_entries",
            description=(
                "Fetch time entries for engagement with optional filtering. "
                "Returns entries by date, resource, and project phase."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "engagement_id": {
                        "type": "string",
                        "description": "Engagement identifier",
                    },
                    "date_range": {
                        "type": "object",
                        "properties": {
                            "start": {
                                "type": "string",
                                "description": "Start date (YYYY-MM-DD)",
                            },
                            "end": {
                                "type": "string",
                                "description": "End date (YYYY-MM-DD)",
                            },
                        },
                        "description": "Optional: time range filter",
                    },
                    "resource_id": {
                        "type": "string",
                        "description": "Optional: filter to specific team member",
                    },
                    "tenant_id": {
                        "type": "string",
                        "description": "Tenant identifier",
                    },
                },
                "required": ["engagement_id", "tenant_id"],
            },
        ),
        Tool(
            name="list_engagements",
            description=(
                "List all engagements with status and scope drift indicators. "
                "Quick overview of portfolio with risk identification."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "tenant_id": {
                        "type": "string",
                        "description": "Tenant identifier",
                    },
                    "status_filter": {
                        "type": "string",
                        "enum": ["active", "planning", "closed", "on_hold"],
                        "description": "Optional: filter by engagement status",
                    },
                },
                "required": ["tenant_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle tool invocations."""
    
    if name == "check_scope_drift":
        return await _check_scope_drift(arguments)
    elif name == "generate_change_order":
        return await _generate_change_order(arguments)
    elif name == "get_time_entries":
        return await _get_time_entries(arguments)
    elif name == "list_engagements":
        return await _list_engagements(arguments)
    else:
        raise ValueError(f"Unknown tool: {name}")


async def _check_scope_drift(args: Dict[str, Any]) -> List[TextContent]:
    """Check scope drift status."""
    try:
        engagement_id = args["engagement_id"]
        
        drift_result = await drift_analyzer.check_scope_drift(engagement_id)
        
        return [TextContent(type="text", text=json.dumps(drift_result, indent=2))]
    except Exception as e:
        logger.error(f"Scope drift check failed: {str(e)}")
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def _generate_change_order(args: Dict[str, Any]) -> List[TextContent]:
    """Generate change order document."""
    try:
        engagement_id = args["engagement_id"]
        reason = args["reason"]
        impact_hours = args.get("impact_hours")
        impact_budget = args.get("impact_budget")
        
        markdown = await change_order_gen.generate_change_order(
            engagement_id, reason, impact_hours, impact_budget
        )
        
        return [
            TextContent(
                type="text",
                text=json.dumps({
                    "engagement_id": engagement_id,
                    "change_order_markdown": markdown,
                    "timestamp": datetime.utcnow().isoformat(),
                }, indent=2),
            )
        ]
    except Exception as e:
        logger.error(f"Change order generation failed: {str(e)}")
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def _get_time_entries(args: Dict[str, Any]) -> List[TextContent]:
    """Get time entries for engagement."""
    try:
        engagement_id = args["engagement_id"]
        
        entries, grouped = await time_tracker.get_time_entries(
            engagement_id,
            date_range=args.get("date_range"),
            resource_id=args.get("resource_id"),
        )
        
        return [
            TextContent(
                type="text",
                text=json.dumps({
                    "engagement_id": engagement_id,
                    "entry_count": len(entries),
                    "entries": entries,
                    "grouped_by_phase": grouped,
                    "timestamp": datetime.utcnow().isoformat(),
                }, indent=2, default=str),
            )
        ]
    except Exception as e:
        logger.error(f"Time entry retrieval failed: {str(e)}")
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def _list_engagements(args: Dict[str, Any]) -> List[TextContent]:
    """List engagements."""
    try:
        tenant_id = args["tenant_id"]
        status_filter = args.get("status_filter")
        
        engagements = await engagement_mgr.list_engagements(tenant_id, status_filter)
        
        return [
            TextContent(
                type="text",
                text=json.dumps({
                    "tenant_id": tenant_id,
                    "engagement_count": len(engagements),
                    "engagements": engagements,
                    "timestamp": datetime.utcnow().isoformat(),
                }, indent=2),
            )
        ]
    except Exception as e:
        logger.error(f"Engagement listing failed: {str(e)}")
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


def initialize_mcp_server():
    """Initialize scope tracking clients."""
    global drift_analyzer, change_order_gen, time_tracker, engagement_mgr
    
    api_url = os.getenv("ANALYTICS_API_URL", "http://localhost:8000")
    api_key = os.getenv("API_KEY", "")
    
    drift_analyzer = ScopeDriftAnalyzer(api_url, api_key)
    change_order_gen = ChangeOrderGenerator(api_url, api_key)
    time_tracker = TimeEntryTracker(api_url, api_key)
    engagement_mgr = EngagementManager(api_url, api_key)
    
    logger.info("Scope Tracker MCP server initialized")


if __name__ == "__main__":
    initialize_mcp_server()
    server.run()
