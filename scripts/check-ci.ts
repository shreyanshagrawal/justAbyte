import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parse } from 'yaml';

export interface WorkflowViolation {
  file: string;
  job?: string;
  step?: string;
  rule: string;
  details: string;
}

export interface WorkflowStep {
  name?: string;
  uses?: string;
  run?: string;
  with?: Record<string, unknown>;
  'continue-on-error'?: boolean;
}

export interface WorkflowJob {
  name?: string;
  'runs-on'?: string;
  'timeout-minutes'?: number;
  permissions?: Record<string, string> | string;
  'continue-on-error'?: boolean;
  steps?: WorkflowStep[];
  uses?: string;
}

export interface WorkflowDocument {
  name?: string;
  on?: string | string[] | Record<string, unknown>;
  permissions?: Record<string, string> | string;
  jobs?: Record<string, WorkflowJob>;
}

export function validateWorkflow(filePath: string, content?: string): WorkflowViolation[] {
  const violations: WorkflowViolation[] = [];
  const fileName = path.basename(filePath);
  const rawYaml = content ?? fs.readFileSync(filePath, 'utf8');
  const doc = parse(rawYaml) as WorkflowDocument | null;

  if (!doc) {
    return [
      {
        file: fileName,
        rule: 'Valid YAML',
        details: 'Failed to parse YAML or document is empty.',
      },
    ];
  }

  // Rule 4: No workflow uses pull_request_target
  if (doc.on) {
    let usesPrTarget = false;
    if (typeof doc.on === 'string') {
      usesPrTarget = doc.on === 'pull_request_target';
    } else if (Array.isArray(doc.on)) {
      usesPrTarget = doc.on.includes('pull_request_target');
    } else if (typeof doc.on === 'object') {
      usesPrTarget = 'pull_request_target' in doc.on;
    }

    if (usesPrTarget) {
      violations.push({
        file: fileName,
        rule: 'No pull_request_target',
        details: 'Workflow uses forbidden pull_request_target trigger.',
      });
    }
  }

  if (!doc.jobs || typeof doc.jobs !== 'object') {
    return violations;
  }

  for (const [jobId, job] of Object.entries(doc.jobs)) {
    // Rule 1: Every job has timeout-minutes set
    // Note: Standard jobs with steps must have timeout-minutes set
    if (!job.uses) {
      if (
        job['timeout-minutes'] === undefined ||
        typeof job['timeout-minutes'] !== 'number' ||
        job['timeout-minutes'] <= 0
      ) {
        violations.push({
          file: fileName,
          job: jobId,
          rule: 'timeout-minutes required',
          details: `Job "${jobId}" must specify a positive numeric timeout-minutes (found ${job['timeout-minutes']}).`,
        });
      }
    }

    // Rule 2: Every job sets explicit permissions
    if (job.permissions === undefined) {
      violations.push({
        file: fileName,
        job: jobId,
        rule: 'Explicit permissions required',
        details: `Job "${jobId}" must set explicit permissions at the job level.`,
      });
    }

    // Rule 3: No job uses continue-on-error
    if (job['continue-on-error'] === true) {
      violations.push({
        file: fileName,
        job: jobId,
        rule: 'No continue-on-error',
        details: `Job "${jobId}" sets continue-on-error: true, which masks failures.`,
      });
    }

    // Check steps within standard jobs
    if (Array.isArray(job.steps)) {
      const laterStepsPush = job.steps.some(
        (s) => typeof s.run === 'string' && /git\s+push\b/.test(s.run),
      );

      for (let i = 0; i < job.steps.length; i++) {
        const step = job.steps[i];
        if (!step) continue;
        const stepName = step.name ?? `Step #${i + 1}`;

        // Rule 3 (step level): No step uses continue-on-error
        if (step['continue-on-error'] === true) {
          violations.push({
            file: fileName,
            job: jobId,
            step: stepName,
            rule: 'No continue-on-error',
            details: `Step "${stepName}" in job "${jobId}" sets continue-on-error: true.`,
          });
        }

        // Rule 5: Every checkout step uses persist-credentials: false unless later step pushes
        if (step.uses && /^actions\/checkout(?:@|$)/.test(step.uses)) {
          const persistCreds = step.with?.['persist-credentials'];
          const isPersistDisabled = persistCreds === false || persistCreds === 'false';

          if (!isPersistDisabled && !laterStepsPush) {
            violations.push({
              file: fileName,
              job: jobId,
              step: stepName,
              rule: 'persist-credentials: false required',
              details: `Checkout step in job "${jobId}" must specify "persist-credentials: false" when push access is not needed.`,
            });
          }
        }
      }
    }
  }

  return violations;
}

export function checkCiWorkflows(
  targetFile = path.resolve(process.cwd(), '.github/workflows/ci.yml'),
): WorkflowViolation[] {
  return validateWorkflow(targetFile);
}

export function runCli(): void {
  console.log('🔄 Validating .github/workflows/ci.yml against security & CI standards...');
  const violations = checkCiWorkflows();

  if (violations.length > 0) {
    console.error('\n❌ CI WORKFLOW VALIDATION FAILED:');
    for (const v of violations) {
      const location = [v.file, v.job, v.step].filter(Boolean).join(' > ');
      console.error(`- [${v.rule}] at ${location}`);
      console.error(`  ${v.details}`);
    }
    process.exit(1);
  }

  console.log(
    '✅ CI WORKFLOW VALIDATION PASSED: All jobs meet security, timeout, and permission rules.',
  );
}

const currentFilePath = fileURLToPath(import.meta.url);
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(currentFilePath)) {
  runCli();
}
