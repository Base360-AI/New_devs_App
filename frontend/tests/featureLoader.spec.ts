import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { loadFeatureCatalog } from "./featureLoader";

const FEATURE_DIR = join(import.meta.dirname, "features");

describe("feature discovery", () => {
  it("discovers Gherkin files under tests/features", () => {
    mkdirSync(FEATURE_DIR, { recursive: true });
    const catalog = loadFeatureCatalog();
    expect(catalog.files.every((file) => file.endsWith(".feature"))).toBe(true);
    expect(catalog.files).toHaveLength(2);
    expect(catalog.scenarioCount).toBe(9);
  });
});
