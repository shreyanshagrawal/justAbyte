import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { GateThresholds, SimulationResult, ContributorEvaluation } from './types.js';
import { generateScenario } from './scenario.js';
import { evaluateScenario } from './evaluator.js';

export function loadThresholds(filePath?: string): GateThresholds {
  const candidatePaths = [
    filePath,
    path.resolve(process.cwd(), 'packages/simulation/gates.json'),
    path.resolve(process.cwd(), 'simulation/gates.json'),
    path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../gates.json'),
  ].filter(Boolean) as string[];

  for (const p of candidatePaths) {
    if (fs.existsSync(p)) {
      return JSON.parse(fs.readFileSync(p, 'utf8')) as GateThresholds;
    }
  }

  throw new Error(`Could not find gates.json. Searched in: ${candidatePaths.join(', ')}`);
}

export function checkGate(
  evaluations: ContributorEvaluation[],
  thresholds: GateThresholds,
): { violations: string[]; passed: boolean } {
  const violations: string[] = [];

  for (const c of evaluations) {
    // 1. Newcomer fairness checks
    if (c.role === 'newcomer') {
      if (c.reputation < thresholds.newcomer.minReputation) {
        violations.push(
          `Newcomer "${c.id}" received negative reputation ${c.reputation} (minimum allowed: ${thresholds.newcomer.minReputation})`,
        );
      }

      const isAllowedRisk =
        c.risk === thresholds.newcomer.allowedRiskState ||
        (typeof c.risk === 'number' && c.risk <= thresholds.newcomer.maxRisk);

      if (!isAllowedRisk) {
        violations.push(
          `Newcomer "${c.id}" received elevated risk "${c.risk}" (allowed: "${thresholds.newcomer.allowedRiskState}" or <= ${thresholds.newcomer.maxRisk})`,
        );
      }
    }

    // 2. Malicious denouncement ring suppression checks
    if (c.role === 'malicious_target') {
      if (c.reputation < thresholds.suppression.legitimateContributorFloor) {
        violations.push(
          `Malicious target "${c.id}" was suppressed below floor: reputation ${c.reputation} < floor ${thresholds.suppression.legitimateContributorFloor}`,
        );
      }

      if (
        c.suppressionDrop !== undefined &&
        c.suppressionDrop > thresholds.suppression.maxAllowedSuppressionDrop
      ) {
        violations.push(
          `Malicious target "${c.id}" suffered excessive suppression drop: ${c.suppressionDrop} > max allowed ${thresholds.suppression.maxAllowedSuppressionDrop}`,
        );
      }
    }

    // 3. AI contributor fairness checks
    if (c.role === 'ai_assisted') {
      if (c.reputation < thresholds.aiContributions.minReputation) {
        violations.push(
          `AI-assisted contributor "${c.id}" penalized with negative reputation: ${c.reputation}`,
        );
      }
      if (typeof c.risk === 'number' && c.risk > thresholds.aiContributions.maxRiskPenalty) {
        violations.push(
          `AI-assisted contributor "${c.id}" penalized with elevated risk: ${c.risk}`,
        );
      }
    }
  }

  return {
    violations,
    passed: violations.length === 0,
  };
}

export function generateMarkdownReport(result: SimulationResult): string {
  const lines: string[] = [
    `# OpenCred Simulation Gate Report`,
    ``,
    `**Scenario Seed**: \`${result.seed}\`  `,
    `**Overall Gate Status**: **${result.summary.allPassed ? '✅ PASSED' : '❌ FAILED'}**  `,
    ``,
    `## Fairness Summary`,
    `- **Newcomer Neutrality (Cold Start)**: ${result.summary.newcomersPassed ? '✅ PASS' : '❌ FAIL'}`,
    `- **Sybil Ring Suppression Resistance**: ${result.summary.suppressionResisted ? '✅ PASS' : '❌ FAIL'}`,
    `- **AI Contribution Neutrality**: ${result.summary.aiFairnessPassed ? '✅ PASS' : '❌ FAIL'}`,
    ``,
    `## Contributor Evaluations (Three-Way Output)`,
    `| Contributor | Role | Reputation [-1, +1] | Risk [0, 1] | Confidence [0, 1] | Suppression Drop | Status |`,
    `|-------------|------|---------------------|-------------|-------------------|------------------|--------|`,
  ];

  for (const c of result.contributors) {
    const hasViolation = result.violations.some((v) => v.includes(c.id));
    const status = hasViolation ? '❌ Fail' : '✅ Pass';
    const drop = c.suppressionDrop !== undefined ? c.suppressionDrop.toFixed(3) : '0.000';
    lines.push(
      `| \`${c.id}\` | ${c.role} | ${c.reputation.toFixed(3)} | \`${c.risk}\` | ${c.confidence.toFixed(3)} | ${drop} | ${status} |`,
    );
  }

  if (result.violations.length > 0) {
    lines.push(``, `## Violations Detected`);
    for (const v of result.violations) {
      lines.push(`- ❌ **Violation**: ${v}`);
    }
  }

  lines.push(``);
  return lines.join('\n');
}

export function runSimulationGate(customThresholdsPath?: string): SimulationResult {
  const thresholds = loadThresholds(customThresholdsPath);
  const scenario = generateScenario(thresholds.scenario.seed);
  const evaluations = evaluateScenario(scenario);
  const { violations, passed } = checkGate(evaluations, thresholds);

  const newcomersPassed = !violations.some((v) => v.includes('Newcomer'));
  const suppressionResisted = !violations.some((v) => v.includes('suppress'));
  const aiFairnessPassed = !violations.some((v) => v.includes('AI-assisted'));

  const result: SimulationResult = {
    seed: thresholds.scenario.seed,
    contributors: evaluations,
    summary: {
      totalEvaluated: evaluations.length,
      newcomersPassed,
      suppressionResisted,
      aiFairnessPassed,
      allPassed: passed,
    },
    violations,
  };

  // Ensure output directory exists
  const outputDirs = [
    path.resolve(process.cwd(), 'packages/simulation/output'),
    path.resolve(process.cwd(), 'simulation/output'),
  ];

  for (const dir of outputDirs) {
    try {
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(
        path.join(dir, 'simulation-report.json'),
        JSON.stringify(result, null, 2) + '\n',
      );
      fs.writeFileSync(path.join(dir, 'simulation-report.md'), generateMarkdownReport(result));
    } catch {
      // Continue to next directory if path is redundant
    }
  }

  return result;
}

export function runCli(): void {
  console.log('🔄 Running OpenCred Seed-42 Simulation Scenario & Three-Way Evaluation...');
  const result = runSimulationGate();

  console.log(
    `\nEvaluated ${result.summary.totalEvaluated} contributors with seed ${result.seed}:`,
  );
  for (const c of result.contributors) {
    console.log(
      `  • ${c.id.padEnd(25)} [${c.role.padEnd(16)}]: Rep=${c.reputation.toString().padStart(6)}, Risk=${c.risk.toString().padStart(22)}, Conf=${c.confidence}`,
    );
  }

  if (!result.summary.allPassed) {
    console.error('\n❌ SIMULATION GATE FAILED — Fairness metrics violated:');
    for (const v of result.violations) {
      console.error(`  - ${v}`);
    }
    process.exit(1);
  }

  console.log(
    '\n✅ SIMULATION GATE PASSED: All fairness & suppression resistance metrics satisfied.',
  );
  console.log('Reports written to: packages/simulation/output/simulation-report.{json,md}');
}

const currentFilePath = fileURLToPath(import.meta.url);
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(currentFilePath)) {
  runCli();
}
