import { logger, task } from "@trigger.dev/sdk/v3";
import { Pool } from "pg";

interface ChangeOrderPayload {
  engagement_id: string;
  drift_event_id?: string;
  unscoped_hours: number;
  trigger: "drift_alert" | "manual_request";
}

interface EngagementData {
  id: string;
  client_id: string;
  matter_name: string;
  owner_id: string;
  total_budget: number;
  estimated_hours: number;
  estimated_completion_date: string;
}

interface ClientData {
  name: string;
  contact_email: string;
  contact_phone: string;
}

interface DriftData {
  unscoped_hours: number;
  unscoped_amount: number;
  related_time_entries: string[];
  notes: string;
}

const pool = new Pool({
  connectionString: process.env.DATABASE_URL!,
});

export const changeOrderGenerationJob = task({
  id: "change-order-generation",
  run: async (payload: ChangeOrderPayload, { ctx }) => {
    const pgClient = await pool.connect();

    logger.info("Starting change order generation", {
      engagement_id: payload.engagement_id,
      trigger: payload.trigger,
    });

    try {
      // Fetch engagement
      const engResult = await pgClient.query(
        "SELECT * FROM engagements WHERE id = $1",
        [payload.engagement_id]
      );

      if (engResult.rows.length === 0) {
        throw new Error(`Engagement ${payload.engagement_id} not found`);
      }

      const engagement = engResult.rows[0] as EngagementData;

      // Fetch client
      const clientResult = await pgClient.query(
        "SELECT * FROM clients WHERE id = $1",
        [engagement.client_id]
      );

      if (clientResult.rows.length === 0) {
        throw new Error(`Client ${engagement.client_id} not found`);
      }

      const client = clientResult.rows[0] as ClientData;

      // Fetch drift event if available
      let driftData: DriftData | null = null;
      if (payload.drift_event_id) {
        const driftResult = await pgClient.query(
          "SELECT * FROM drift_events WHERE id = $1",
          [payload.drift_event_id]
        );

        if (driftResult.rows.length > 0) {
          const driftEvent = driftResult.rows[0];
          driftData = {
            unscoped_hours: driftEvent.unscoped_hours || payload.unscoped_hours,
            unscoped_amount: driftEvent.unscoped_amount || 0,
            related_time_entries: driftEvent.related_time_entries || [],
            notes: driftEvent.notes || "",
          };
        }
      }

      // If no drift data, calculate from payload
      if (!driftData) {
        const blendedRate = engagement.total_budget / engagement.estimated_hours;
        driftData = {
          unscoped_hours: payload.unscoped_hours,
          unscoped_amount: payload.unscoped_hours * blendedRate,
          related_time_entries: [],
          notes: `${payload.unscoped_hours} unscoped hours detected`,
        };
      }

      // Generate change order draft
      const changeOrderDraft = generateChangeOrderDraft(
        engagement,
        client,
        driftData
      );

      // Save change order to database
      const coResult = await pgClient.query(
        `INSERT INTO change_orders
         (engagement_id, drift_event_id, created_by_id, status, title, description, scope_additions,
          estimated_additional_hours, estimated_additional_cost, revised_total_budget, revised_completion_date, notes)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
         RETURNING id`,
        [
          payload.engagement_id,
          payload.drift_event_id || null,
          engagement.owner_id,
          "draft",
          changeOrderDraft.title,
          changeOrderDraft.description,
          changeOrderDraft.scope_additions,
          changeOrderDraft.estimated_additional_hours,
          changeOrderDraft.estimated_additional_cost,
          changeOrderDraft.revised_total_budget,
          changeOrderDraft.revised_completion_date,
          `Generated automatically on ${new Date().toISOString()}`,
        ]
      );

      const changeOrderId = coResult.rows[0]?.id;

      if (!changeOrderId) {
        throw new Error("Failed to create change order");
      }

      logger.info("Change order draft generated", {
        change_order_id: changeOrderId,
        additional_cost: changeOrderDraft.estimated_additional_cost,
      });

      // Create line items
      const lineItems = generateLineItems(
        changeOrderId,
        changeOrderDraft.scope_additions_details,
        engagement
      );

      for (const item of lineItems) {
        try {
          await pgClient.query(
            `INSERT INTO change_order_items
             (change_order_id, description, quantity, unit_cost, amount)
             VALUES ($1, $2, $3, $4, $5)`,
            [
              item.change_order_id,
              item.description,
              item.quantity,
              item.unit_cost,
              item.amount,
            ]
          );
        } catch (error) {
          logger.error("Failed to save line item", { error });
        }
      }

      return {
        success: true,
        change_order_id: changeOrderId,
        engagement_id: payload.engagement_id,
        additional_cost: changeOrderDraft.estimated_additional_cost,
        additional_hours: changeOrderDraft.estimated_additional_hours,
        status: "draft",
      };
    } catch (error) {
      logger.error("Change order generation failed", {
        engagement_id: payload.engagement_id,
        error: error instanceof Error ? error.message : String(error),
      });

      throw error;
    } finally {
      pgClient.release();
    }
  },
});

interface ChangeOrderDraft {
  title: string;
  description: string;
  scope_additions: string;
  scope_additions_details: Array<{
    description: string;
    hours: number;
    unit_rate: number;
  }>;
  estimated_additional_hours: number;
  estimated_additional_cost: number;
  revised_total_budget: number;
  revised_completion_date: string;
}

function generateChangeOrderDraft(
  engagement: EngagementData,
  client: ClientData,
  drift: DriftData
): ChangeOrderDraft {
  const blendedRate = engagement.total_budget / engagement.estimated_hours;
  const additionalHours = Math.ceil(drift.unscoped_hours);
  const additionalCost = additionalHours * blendedRate;

  // Parse scope additions from drift notes
  const scopeItems = [
    {
      description: "Unscoped work - client-requested additions",
      hours: additionalHours,
      unit_rate: blendedRate,
    },
  ];

  const scopeText = `
## Scope Additions

The following work was requested by the client but was not included in the original engagement scope:

${scopeItems.map((item) => `- ${item.description}: ~${item.hours} hours`).join("\n")}

**Total Additional Hours:** ${additionalHours}
**Blended Rate:** $${blendedRate.toFixed(2)}/hour
**Total Additional Cost:** $${additionalCost.toFixed(2)}
`;

  // Estimate revised completion date (add days based on hours)
  const daysToAdd = Math.ceil(additionalHours / 8); // Assuming 8 hour workdays
  const revisedDate = new Date(engagement.estimated_completion_date);
  revisedDate.setDate(revisedDate.getDate() + daysToAdd);

  return {
    title: `Change Order - ${client.name} | ${engagement.matter_name}`,
    description: `This change order documents scope additions to the engagement and establishes revised terms.`,
    scope_additions: scopeText,
    scope_additions_details: scopeItems,
    estimated_additional_hours: additionalHours,
    estimated_additional_cost: additionalCost,
    revised_total_budget: engagement.total_budget + additionalCost,
    revised_completion_date: revisedDate.toISOString().split("T")[0],
  };
}

function generateLineItems(
  changeOrderId: string,
  items: Array<{
    description: string;
    hours: number;
    unit_rate: number;
  }>,
  engagement: EngagementData
): Array<{
  change_order_id: string;
  description: string;
  quantity: number;
  unit_cost: number;
  amount: number;
}> {
  return items.map((item) => ({
    change_order_id: changeOrderId,
    description: item.description,
    quantity: item.hours,
    unit_cost: item.unit_rate,
    amount: item.hours * item.unit_rate,
  }));
}
