import { logger, task } from "@trigger.dev/sdk/v3";
import { createClient } from "@supabase/supabase-js";
import type { Database } from "../types/database";

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

const supabase = createClient<Database>(
  process.env.SUPABASE_URL!,
  process.env.SUPABASE_ANON_KEY!
);

export const changeOrderGenerationJob = task({
  id: "change-order-generation",
  run: async (payload: ChangeOrderPayload, { ctx }) => {
    logger.info("Starting change order generation", {
      engagement_id: payload.engagement_id,
      trigger: payload.trigger,
    });

    try {
      // Fetch engagement
      const { data: engagement, error: engError } = await supabase
        .from("engagements")
        .select("*")
        .eq("id", payload.engagement_id)
        .single();

      if (engError || !engagement) {
        throw new Error(`Failed to fetch engagement: ${engError?.message}`);
      }

      // Fetch client
      const { data: client, error: clientError } = await supabase
        .from("clients")
        .select("*")
        .eq("id", engagement.client_id)
        .single();

      if (clientError || !client) {
        throw new Error(`Failed to fetch client: ${clientError?.message}`);
      }

      // Fetch drift event if available
      let driftData: DriftData | null = null;
      if (payload.drift_event_id) {
        const { data: driftEvent, error: driftError } = await supabase
          .from("drift_events")
          .select("*")
          .eq("id", payload.drift_event_id)
          .single();

        if (!driftError && driftEvent) {
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
        engagement as EngagementData,
        client as ClientData,
        driftData
      );

      // Save change order to database
      const { data: savedOrder, error: saveError } = await supabase
        .from("change_orders")
        .insert({
          engagement_id: payload.engagement_id,
          drift_event_id: payload.drift_event_id,
          created_by_id: engagement.owner_id,
          status: "draft",
          title: changeOrderDraft.title,
          description: changeOrderDraft.description,
          scope_additions: changeOrderDraft.scope_additions,
          estimated_additional_hours: changeOrderDraft.estimated_additional_hours,
          estimated_additional_cost: changeOrderDraft.estimated_additional_cost,
          revised_total_budget: changeOrderDraft.revised_total_budget,
          revised_completion_date: changeOrderDraft.revised_completion_date,
          notes: `Generated automatically on ${new Date().toISOString()}`,
        } as any)
        .select();

      if (saveError) {
        throw new Error(`Failed to save change order: ${saveError.message}`);
      }

      logger.info("Change order draft generated", {
        change_order_id: savedOrder?.[0]?.id,
        additional_cost: changeOrderDraft.estimated_additional_cost,
      });

      // Create line items
      if (savedOrder && savedOrder.length > 0) {
        const lineItems = generateLineItems(
          savedOrder[0].id,
          changeOrderDraft.scope_additions_details,
          engagement as EngagementData
        );

        const { error: itemsError } = await supabase
          .from("change_order_items")
          .insert(lineItems);

        if (itemsError) {
          logger.error("Failed to save line items", { error: itemsError });
        }
      }

      return {
        success: true,
        change_order_id: savedOrder?.[0]?.id,
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
) {
  return items.map((item) => ({
    change_order_id: changeOrderId,
    description: item.description,
    quantity: item.hours,
    unit_cost: item.unit_rate,
    amount: item.hours * item.unit_rate,
  }));
}
