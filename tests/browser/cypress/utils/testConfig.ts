import process from "node:process";
import fs from "fs";

import YAML from 'yaml';

class TestConfig {
    ODH_DASHBOARD_URL?: string;
}

export const testConfig: TestConfig | undefined = process.env.CY_TEST_CONFIG
    ? YAML.parse(fs.readFileSync(process.env.CY_TEST_CONFIG).toString())
    : undefined;

export const BASE_URL = testConfig?.ODH_DASHBOARD_URL || process.env.BASE_URL || '';
