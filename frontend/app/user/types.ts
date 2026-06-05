// frontend/app/user/types.ts

export type TraceEvent = {
  stage: string;
  message: string;
  data: Record<string, unknown>;
};

export type LayerResult = {
  layer: string;
  activated: boolean;
  deterministic: boolean;
  summary: string;
  data: Record<string, unknown>;
};

export type CapabilityPlan = {
  kind: string;
  route: string;
  confidence: number;
  reason: string;
  energy_profile: string;
  context_strategy: string;
  requires_external_adapter: boolean;
};

export type CapabilityResult = {
  adapter: string;
  status: string;
  summary: string;
  confidence: number;
};

export type SimulationResult = {
  scenario: string;
  passed: boolean;
  confidence: number;
  outcomes: string[];
};

export type ApiResponse = {
  response: string;
  confidence: number;
  gaps: string[];
  sources: string[];
  suggestions: string[];
  used_groq: boolean;
  ir: {
    trace_id: string;
    target_ir: string;
    confidence: number;
    transformer_interface_used: boolean;
  };
  activation?: { route: string; reason: string; confidence: number };
  canvas_result?: { activated: boolean; patterns: string[]; used_groq: boolean };
  invention_result?: {
    activated: boolean;
    candidate_steps: string[];
    simulation_notes: string[];
    used_groq: boolean;
  };
  abstraction_result?: { concepts: string[]; analogies: string[]; confidence: number };
  capability_plan?: CapabilityPlan;
  capability_results?: CapabilityResult[];
  world_model_activations: Array<{ rule: string; confidence: number; source: string }>;
  simulation_results: SimulationResult[];
  trace: TraceEvent[];
  layer_results: LayerResult[];
};

export type Message = {
  role: "user" | "assistant";
  content: string;
  apiResponse?: ApiResponse;
};

export type Thread = {
  id: string;
  title: string;
  updated_at: string;
  created_at?: string;
};
