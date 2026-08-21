import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const FEATURE_DIR = join(import.meta.dirname, "features");

export function discoverFeatureFiles(): string[] {
  try {
    return readdirSync(FEATURE_DIR)
      .filter((name) => name.endsWith(".feature"))
      .map((name) => join(FEATURE_DIR, name))
      .sort();
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === "ENOENT") {
      return [];
    }
    throw error;
  }
}

export function countScenarios(featurePath: string): number {
  const source = readFileSync(featurePath, "utf8");
  return source.split("\n").filter((line) => /^\s*Scenario:/.test(line)).length;
}

export function loadFeatureCatalog(): { files: string[]; scenarioCount: number } {
  const files = discoverFeatureFiles();
  const scenarioCount = files.reduce((total, file) => total + countScenarios(file), 0);
  return { files, scenarioCount };
}
