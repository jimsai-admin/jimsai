// Consolidated to the 8 panels backed by real pipeline data. The former
// autonomous / artifacts / evaluation panels had no backend builder (empty,
// durable-only) and overlapped these — runs, jobs and artifacts all live under
// "Runs & Artifacts" (sessions). Their routes still resolve; only the nav is trimmed.
export const panelDefinitions = [
  { id: "ingestion", number: "Panel 1", title: "Data Ingestion" },
  { id: "review", number: "Panel 2", title: "Human Review Queue" },
  { id: "ambiguity", number: "Panel 3", title: "Ambiguity Resolution" },
  { id: "memory", number: "Panel 4", title: "Memory Management" },
  { id: "world-model", number: "Panel 5", title: "World Model" },
  { id: "pipeline", number: "Panel 6", title: "Pipeline Monitor" },
  { id: "sessions", number: "Panel 7", title: "Runs & Artifacts" },
  { id: "feedback", number: "Panel 8", title: "Feedback & Inspection" }
] as const;

export type TrainingPanelId = (typeof panelDefinitions)[number]["id"];

export function panelById(panelId: string) {
  return panelDefinitions.find((panel) => panel.id === panelId) ?? panelDefinitions[0];
}
