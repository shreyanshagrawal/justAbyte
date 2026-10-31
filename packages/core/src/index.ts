/**
 * OpenCred Core Engine
 * Advisory decentralized trust and reputation model for GitHub contributors.
 */

export const CORE_VERSION = '0.1.0';

export function getEngineStatus(): { status: string; advisoryOnly: boolean } {
  return {
    status: 'initialized',
    advisoryOnly: true,
  };
}
