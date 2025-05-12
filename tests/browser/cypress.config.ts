// https://docs.cypress.io/app/references/configuration

import { defineConfig } from "cypress";
import * as testConfig from "./cypress/utils/testConfig.js";

export default defineConfig({
  e2e: {
    env: {
        LOGIN: !!process.env.LOGIN,
    },
    baseUrl: testConfig.BASE_URL,
    // this helps with browser crashes
    experimentalMemoryManagement: true,
    numTestsKeptInMemory: 1,

    // cross-origin testing

    // disable webSecurity
    chromeWebSecurity: false,
    // Using require() or import() within the cy.origin() callback is not supported.
    // Use Cypress.require() to include dependencies instead,
    // but note that it currently requires enabling the experimentalOriginDependencies flag.
    experimentalOriginDependencies: true,
    // https://docs.cypress.io/app/guides/cypress-studio
    experimentalStudio: false,
    // https://docs.cypress.io/app/plugins/plugins-guide
    setupNodeEvents(on, config) {
      // implement node event listeners here
    },
  },
});
