import { logger, task, wait } from "@trigger.dev/sdk/v3";
import { createClient } from "@supabase/supabase-js";
import type { Database } from "../types/database";

interface DriftDetectionPayload {
  engagement_id: string;
  trigger_event: "time_entry_created" | "scheduled_check";
  time_entry_id?: string;
  is_unscoped?: boolean;
  hours?: number;
}

interface TimeEntry {
  id: string;
  engagement_id: string;
  deliverable_id: string | null;
  hours: number;
  entry_date: string;
  description: string;
  category: string;
  created_at: string;
}

interface Deliverable {
  id: string;
  title: string;
  estimated_hours: number;
  status: string;
}

interface DriftMetrics {
  total_hours: number;
  scoped_hours: number;
  unscoped_hours: number;
  unscoped_entries: TimeEntry[];
  budget_consumed_percent: number;
  drift_percentage: number;
  deliverable_overruns: Array<{
    deliverable_id: string;
    title: string;
    estimated_hours: number;
    actual_hours: number;
    percent_over: number;
  }>;
  trend_acceleration: boolean;
}

interface DriftEvent {
  engagement_id: string;
  drift_type: string;
  severity: "info" | "warning" | "critical";
  unscoped_hours: number;
  budget_consumed_percent: number;
  related_time_entries: string[];
  notes: string;
}

const supabase = createClient<Database>(
  process.env.SUPABASE_URL!,
  process.env.SUPABASE_ANON_KEY!
);

export const driftDetectionJob = task({
  id: "drift-detection",
  run: async (payload: DriftDetectionPayload, { ctx }) => {
    logger.info("Starting drift detection", {
      engagement_id: payload.engagement_id,
      trigger_event: payload.trigger_event,
    });

    try {
      // Fetch engagement and time entries
      const { data: engagement, error: engError } = await supabase
        .from("engagements")
        .select("id, total_budget, estimated_hours, start_date, owner_id")
        .eq("id", payload.engagement_id)
        .single();

      if (engError || !engagement) {
        throw new Error(`Failed to fetch engagement: ${engError?.message}`);
      }

      // Fetch all time entries for engagement
      const { data: timeEntries, error: entriesError } = await supabase
        .from("time_entries")
        .select("*")
        .eq("engagement_id", payload.engagement_id);

      if (entriesError) {
        throw new Error(`Failed to fetch time entries: ${entriesError.message}`);
      }

      // Fetch deliverables
      const { data: deliverables, error: delError } = await supabase
        .from("scoped_deliverables")
        .select("id, title, estimated_hours, status")
        .eq("engagement_id", payload.engagement_id);

      if (delError) {
        throw new Error(`Failed to fetch deliverables: ${delError.message}`);
      }

      // Calculate drift metrics
      const metrics = calculateDriftMetrics(
        timeEntries || [],
        deliverables || [],
        engagement
      );

      logger.info("Drift metrics calculated", {
        unscoped_hours: metrics.unscoped_hours,
        drift_percentage: metrics.drift_percentage,
        budget_consumed_percent: metrics.budget_consumed_percent,
      });

      // Detect drift events
      const driftEvents = detectDriftEvents(metrics, engagement);

      // Save drift events to database
      for (const event of driftEvents) {
        const { error: saveError } = await supabase
          .from("drift_events")
          .insert({
            engagement_id: payload.engagement_id,
            drift_type: event.drift_type,
            severity: event.severity,
            unscoped_hours: event.unscoped_hours,
            budget_consumed_percent: event.budget_consumed_percent,
            related_time_entries: event.related_time_entries,
            notes: event.notes,
          } as any);

        if (saveError) {
          logger.error("Failed to save drift event", { error: saveError });
        }
      }

      // Trigger alerts if needed
      if (driftEvents.length > 0) {
        await triggerAlerts(
          engagement,
          driftEvents,
          metrics.unscoped_entries
        );
      }

      // Check if change order should be auto-generated (critical drift)
      const criticalEvent = driftEvents.find((e) => e.severity === "critical");
      if (criticalEvent) {
        logger.info("Critical drift detected, queuing change order generation", {
          engagement_id: payload.engagement_id,
        });

        // Queue change order generation job
        await wait.for({
          delay: 5 * 60, // 5 minute delay to allow manual intervention
        });

        // Note: This would trigger the change-order-generation job
        // await trigger.changeOrderGeneration({
        //   engagement_id: payload.engagement_id,
        //   drift_event_id: criticalEvent.id,
        // });
      }

      return {
        success: true,
        engagement_id: payload.engagement_id,
        drift_events_detected: driftEvents.length,
        unscoped_hours: metrics.unscoped_hours,
        drift_percentage: metrics.drift_percentage,
      };
    } catch (error) {
      logger.error("Drift detection failed", {
        engagement_id: payload.engagement_id,
        error: error instanceof Error ? error.message : String(error),
      });

      throw error;
    }
  },
});

function calculateDriftMetrics(
  timeEntries: TimeEntry[],
  deliverables: Deliverable[],
  engagement: {
    total_budget: number;
    estimated_hours: number;
    start_date: string;
  }
): DriftMetrics {
  const totalHours = timeEntries.reduce((sum, entry) => sum + entry.hours, 0);
  const unscopedEntries = timeEntries.filter((e) => !e.deliverable_id);
  const unscopedHours = unscopedEntries.reduce(
    (sum, entry) => sum + entry.hours,
    0
  );
  const scopedHours = totalHours - unscopedHours;

  // Calculate budget consumed (using blended rate)
  const blendedRate = engagement.total_budget / engagement.estimated_hours;
  const budgetConsumed = totalHours * blendedRate;
  const budgetConsumedPercent = (budgetConsumed / engagement.total_budget) * 100;
  const driftPercentage = (unscopedHours / totalHours) * 100 || 0;

  // Find deliverable overruns
  const deliverableOverruns = deliverables
    .map((del) => {
      const delEntries = timeEntries.filter((e) => e.deliverable_id === del.id);
      const actualHours = delEntries.reduce((sum, e) => sum + e.hours, 0);
      const percentOver = ((actualHours - del.estimated_hours) / del.estimated_hours) * 100;

      return {
        deliverable_id: del.id,
        title: del.title,
        estimated_hours: del.estimated_hours,
        actual_hours: actualHours,
        percent_over: percentOver > 0 ? percentOver : 0,
      };
    })
    .filter((d) => d.percent_over > 0);

  // Detect trend acceleration (simple: comparing early vs late entries)
  const trendAcceleration = detectTrendAcceleration(timeEntries);

  return {
    total_hours: totalHours,
    scoped_hours: scopedHours,
    unscoped_hours: unscopedHours,
    unscoped_entries: unscopedEntries,
    budget_consumed_percent: budgetConsumedPercent,
    drift_percentage: driftPercentage,
    deliverable_overruns,
    trend_acceleration: trendAcceleration,
  };
}

function detectDriftEvents(
  metrics: DriftMetrics,
  engagement: {
    estimated_hours: number;
  }
): DriftEvent[] {
  const events: DriftEvent[] = [];

  // Unscoped work detection
  if (metrics.unscoped_hours > 2) {
    const severity =
      metrics.unscoped_hours > engagement.estimated_hours * 0.1
        ? "critical"
        : "warning";

    events.push({
      engagement_id: "",
      drift_type: "unscoped_work",
      severity,
      unscoped_hours: metrics.unscoped_hours,
      budget_consumed_percent: metrics.budget_consumed_percent,
      related_time_entries: metrics.unscoped_entries.map((e) => e.id),
      notes: `${metrics.unscoped_hours.toFixed(1)} hours of unscoped work detected (${metrics.drift_percentage.toFixed(1)}% of total time)`,
    });
  }

  // Budget overrun detection
  if (metrics.budget_consumed_percent > 90) {
    events.push({
      engagement_id: "",
      drift_type: "budget_overrun",
      severity: "critical",
      unscoped_hours: metrics.unscoped_hours,
      budget_consumed_percent: metrics.budget_consumed_percent,
      related_time_entries: [],
      notes: `Budget ${metrics.budget_consumed_percent.toFixed(1)}% consumed`,
    });
  } else if (metrics.budget_consumed_percent > 75) {
    events.push({
      engagement_id: "",
      drift_type: "budget_overrun",
      severity: "warning",
      unscoped_hours: metrics.unscoped_hours,
      budget_consumed_percent: metrics.budget_consumed_percent,
      related_time_entries: [],
      notes: `Budget ${metrics.budget_consumed_percent.toFixed(1)}% consumed`,
    });
  }

  // Deliverable overrun detection
  for (const overrun of metrics.deliverable_overruns) {
    if (overrun.percent_over > 25) {
      events.push({
        engagement_id: "",
        drift_type: "budget_overrun",
        severity: overrun.percent_over > 50 ? "critical" : "warning",
        unscoped_hours: 0,
        budget_consumed_percent: metrics.budget_consumed_percent,
        related_time_entries: [],
        notes: `Deliverable "${overrun.title}" ${overrun.percent_over.toFixed(1)}% over budget (${overrun.actual_hours}/${overrun.estimated_hours} hours)`,
      });
    }
  }

  // Trend acceleration detection
  if (metrics.trend_acceleration) {
    events.push({
      engagement_id: "",
      drift_type: "trend_acceleration",
      severity: "warning",
      unscoped_hours: metrics.unscoped_hours,
      budget_consumed_percent: metrics.budget_consumed_percent,
      related_time_entries: [],
      notes: "Drift rate accelerating - unscoped hours growing faster than early engagement",
    });
  }

  return events;
}

function detectTrendAcceleration(timeEntries: TimeEntry[]): boolean {
  if (timeEntries.length < 4) return false;

  // Split entries into early and late periods
  const sorted = [...timeEntries].sort(
    (a, b) =>
      new Date(a.entry_date).getTime() - new Date(b.entry_date).getTime()
  );

  const midpoint = Math.floor(sorted.length / 2);
  const earlyEntries = sorted.slice(0, midpoint);
  const lateEntries = sorted.slice(midpoint);

  const earlyUnscoped = earlyEntries.filter((e) => !e.deliverable_id).length;
  const lateUnscoped = lateEntries.filter((e) => !e.deliverable_id).length;

  const earlyRate = earlyUnscoped / earlyEntries.length;
  const lateRate = lateUnscoped / lateEntries.length;

  // If late period has 50% more unscoped work rate, flag as acceleration
  return lateRate > earlyRate * 1.5;
}

async function triggerAlerts(
  engagement: {
    id: string;
    owner_id: string;
  },
  driftEvents: DriftEvent[],
  unscopedEntries: TimeEntry[]
) {
  logger.info("Triggering alerts for engagement", {
    engagement_id: engagement.id,
    event_count: driftEvents.length,
  });

  // In production, this would trigger an email job via Resend or similar
  // For now, log the alert
  const alertPayload = {
    engagement_id: engagement.id,
    owner_id: engagement.owner_id,
    events: driftEvents,
    unscoped_entries: unscopedEntries.slice(0, 10), // Top 10 entries
    timestamp: new Date().toISOString(),
  };

  logger.info("Alert payload prepared", alertPayload);
}
