import { useEffect, useReducer } from "react";
import type {
  AgentOpinion,
  CouncilCritique,
  CouncilRun,
  CouncilSynthesis,
  LeaderElection,
  OrchestrationPlan,
  SynthesisValidation
} from "../types";

export interface CouncilStreamState {
  plan: OrchestrationPlan | null;
  opinions: AgentOpinion[];
  opinionDrafts: Record<string, string>;
  critiques: CouncilCritique[];
  election: LeaderElection | null;
  synthesis: CouncilSynthesis | null;
  validation: SynthesisValidation | null;
  run: CouncilRun | null;
  isComplete: boolean;
  error: string | null;
}

type EventAction =
  | { type: "plan_ready"; payload: OrchestrationPlan }
  | { type: "agent_opinion"; payload: AgentOpinion }
  | { type: "opinion_token"; payload: { model_id: string; delta: string } }
  | { type: "critique_scored"; payload: CouncilCritique }
  | { type: "leader_elected"; payload: LeaderElection }
  | { type: "synthesis_ready"; payload: CouncilSynthesis }
  | { type: "validation_result"; payload: SynthesisValidation }
  | { type: "run_complete"; payload: CouncilRun }
  | { type: "error"; payload: string }
  | { type: "reset" };

const initialState: CouncilStreamState = {
  plan: null,
  opinions: [],
  opinionDrafts: {},
  critiques: [],
  election: null,
  synthesis: null,
  validation: null,
  run: null,
  isComplete: false,
  error: null
};

function reducer(state: CouncilStreamState, action: EventAction): CouncilStreamState {
  switch (action.type) {
    case "plan_ready":
      return { ...state, plan: action.payload };
    case "agent_opinion":
      return { ...state, opinions: [...state.opinions.filter((item) => item.model_id !== action.payload.model_id), action.payload] };
    case "opinion_token":
      return {
        ...state,
        opinionDrafts: {
          ...state.opinionDrafts,
          [action.payload.model_id]: (state.opinionDrafts[action.payload.model_id] ?? "") + action.payload.delta
        }
      };
    case "critique_scored":
      return { ...state, critiques: [...state.critiques, action.payload] };
    case "leader_elected":
      return { ...state, election: action.payload };
    case "synthesis_ready":
      return { ...state, synthesis: action.payload };
    case "validation_result":
      return { ...state, validation: action.payload };
    case "run_complete":
      return { ...state, run: action.payload, isComplete: true };
    case "error":
      return { ...state, error: action.payload };
    case "reset":
      return initialState;
    default:
      return state;
  }
}

export function useCouncilStream(runId: string | null): CouncilStreamState {
  const [state, dispatch] = useReducer(reducer, initialState);

  useEffect(() => {
    if (!runId) {
      dispatch({ type: "reset" });
      return;
    }

    const source = new EventSource(`/api/council/run/${runId}/stream`);
    const bind = <T,>(eventName: EventAction["type"]) => {
      source.addEventListener(eventName, (event) => {
        dispatch({ type: eventName, payload: JSON.parse((event as MessageEvent).data) } as EventAction);
      });
    };

    bind<OrchestrationPlan>("plan_ready");
    bind<AgentOpinion>("agent_opinion");
    bind<{ model_id: string; delta: string }>("opinion_token");
    bind<CouncilCritique>("critique_scored");
    bind<LeaderElection>("leader_elected");
    bind<CouncilSynthesis>("synthesis_ready");
    bind<SynthesisValidation>("validation_result");
    bind<CouncilRun>("run_complete");
    source.onerror = () => dispatch({ type: "error", payload: "Council stream connection failed" });

    return () => source.close();
  }, [runId]);

  return state;
}
