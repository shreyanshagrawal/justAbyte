import path from 'node:path';
import { describe, it, expect } from 'vitest';
import { validateWorkflow, checkCiWorkflows } from '../scripts/check-ci.js';

describe('CI Configuration Guard & Validator', () => {
  const validWorkflowYaml = `
name: Valid Workflow
on:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false
      - run: npm test
`;

  it('passes on valid workflow definitions', () => {
    const violations = validateWorkflow('valid.yml', validWorkflowYaml);
    expect(violations).toHaveLength(0);
  });

  it('fails when a job is missing timeout-minutes', () => {
    const invalidYaml = `
name: Missing Timeout
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - run: npm test
`;
    const violations = validateWorkflow('missing-timeout.yml', invalidYaml);
    expect(violations.some((v) => v.rule.includes('timeout-minutes'))).toBe(true);
  });

  it('fails when a job is missing explicit permissions', () => {
    const invalidYaml = `
name: Missing Permissions
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - run: npm test
`;
    const violations = validateWorkflow('missing-perms.yml', invalidYaml);
    expect(violations.some((v) => v.rule.includes('permissions'))).toBe(true);
  });

  it('fails when continue-on-error is used on a job or step', () => {
    const invalidYaml = `
name: Continue On Error
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      contents: read
    continue-on-error: true
    steps:
      - run: npm test
        continue-on-error: true
`;
    const violations = validateWorkflow('masked.yml', invalidYaml);
    expect(violations.filter((v) => v.rule === 'No continue-on-error')).toHaveLength(2);
  });

  it('fails when pull_request_target trigger is used', () => {
    const invalidYaml = `
name: Insecure Trigger
on:
  pull_request_target:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      contents: read
    steps:
      - run: echo "hello"
`;
    const violations = validateWorkflow('pr-target.yml', invalidYaml);
    expect(violations.some((v) => v.rule === 'No pull_request_target')).toBe(true);
  });

  it('fails when actions/checkout is missing persist-credentials: false without push step', () => {
    const invalidYaml = `
name: Checkout Creds Leaked
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4
      - run: npm test
`;
    const violations = validateWorkflow('insecure-checkout.yml', invalidYaml);
    expect(violations.some((v) => v.rule.includes('persist-credentials'))).toBe(true);
  });

  it('verifies that repository ci.yml satisfies all security and CI checks', () => {
    const ciFilePath = path.resolve(process.cwd(), '.github/workflows/ci.yml');
    const violations = checkCiWorkflows(ciFilePath);
    expect(violations).toHaveLength(0);
  });
});
