export const panelDefinitions = [
  { id: "ingestion", number: "Panel 1", title: "Multimodal Data Ingestion" },
  { id: "review", number: "Panel 2", title: "Human Review Queue" },
  { id: "ambiguity", number: "Panel 3", title: "Ambiguity Resolution Queue" },
  { id: "memory", number: "Panel 4", title: "Memory Inspection and Management" },
  { id: "world-model", number: "Panel 5", title: "World Model Dashboard" },
  { id: "pipeline", number: "Panel 6", title: "Training Pipeline Monitor" },
  { id: "sessions", number: "Panel 7", title: "Canvas and Invention Management" },
  { id: "feedback", number: "Panel 8", title: "Model Inspection and Feedback" }
] as const;

export type TrainingPanelId = (typeof panelDefinitions)[number]["id"];

export function panelById(panelId: string) {
  return panelDefinitions.find((panel) => panel.id === panelId) ?? panelDefinitions[0];
}
