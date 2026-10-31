export interface GateThresholds {
  scenario: {
    seed: number;
  };
  newcomer: {
    minReputation: number;
    maxRisk: number;
    allowedRiskState: string;
  };
  suppression: {
    legitimateContributorFloor: number;
    maxAllowedSuppressionDrop: number;
  };
  aiContributions: {
    minReputation: number;
    maxRiskPenalty: number;
  };
}

export type RiskValue = number | 'insufficient_evidence';

export interface ContributorEvaluation {
  id: string;
  role: 'newcomer' | 'legitimate' | 'malicious_target' | 'ai_assisted' | 'sybil';
  reputation: number;
  risk: RiskValue;
  confidence: number;
  baselineReputation?: number;
  suppressionDrop?: number;
}

export interface SimulationResult {
  seed: number;
  contributors: ContributorEvaluation[];
  summary: {
    totalEvaluated: number;
    newcomersPassed: boolean;
    suppressionResisted: boolean;
    aiFairnessPassed: boolean;
    allPassed: boolean;
  };
  violations: string[];
}
