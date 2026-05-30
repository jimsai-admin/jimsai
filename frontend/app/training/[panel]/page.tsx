import { notFound } from "next/navigation";

import TrainingPanelClient from "../TrainingPanelClient";
import { panelDefinitions } from "../panels";

export default async function TrainingPanelRoute({ params }: { params: Promise<{ panel: string }> }) {
  const { panel } = await params;
  if (!panelDefinitions.some((definition) => definition.id === panel)) {
    notFound();
  }
  return <TrainingPanelClient panelId={panel} />;
}
