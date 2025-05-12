/// <reference types="cypress" />
/// <reference types="@testing-library/cypress" />
// ***********************************************
// This example commands.ts shows you how to
// create various custom commands and overwrite
// existing commands.
//
// For more comprehensive examples of custom
// commands please read more here:
// https://on.cypress.io/custom-commands
// ***********************************************
//
//
// -- This is a parent command --
// Cypress.Commands.add('login', (email, password) => { ... })
//
//
// -- This is a child command --
// Cypress.Commands.add('drag', { prevSubject: 'element'}, (subject, options) => { ... })
//
//
// -- This is a dual command --
// Cypress.Commands.add('dismiss', { prevSubject: 'optional'}, (subject, options) => { ... })
//
//
// -- This will overwrite an existing command --
// Cypress.Commands.overwrite('visit', (originalFn, url, options) => { ... })
//
// declare global {
//   namespace Cypress {
//     interface Chainable {
//       login(email: string, password: string): Chainable<void>
//       drag(subject: string, options?: Partial<TypeOptions>): Chainable<Element>
//       dismiss(subject: string, options?: Partial<TypeOptions>): Chainable<Element>
//       visit(originalFn: CommandOriginalFn, url: string, options: Partial<VisitOptions>): Chainable<Element>
//     }
//   }
// }

// https://youtrack.jetbrains.com/issue/AQUA-3175/Command-click-expects-element-as-a-previous-subject-but-any-is-passed-from-wrap-command

// https://docs.cypress.io/api/cypress-api/custom-commands

Cypress.Commands.add('establishOrigin', (url: string) => {
    // https://stackoverflow.com/questions/72197730/removing-an-intercept-in-cypress
    // https://github.com/cypress-io/cypress/issues/23192#issuecomment-2401901751
    cy.intercept(
            {
                method: 'GET',
                url: url,
                times: 1
            },
            {
                body: '<html lang="en"></html>',
                headers: {
                    'content-type': 'text/html'
                },
            })
        .as('establishOrigin');
    cy.visit(url);
    cy.wait('@establishOrigin');
})

Cypress.Commands.add('fill',
    { prevSubject: 'element' }, (subject, text, options) => {
    cy.wrap(subject).clear();
    return cy.wrap(subject).type(text, options);
});

Cypress.Commands.add('visitWithLogin', (relativeUrl, credentials = {USERNAME: 'admin-user', PASSWORD: 'xxx'}) => {
    if (Cypress.env('MOCK')) {
        cy.visit(relativeUrl);
    } else {
        let fullUrl: string;
        // if (relativeUrl.replace(/\//g, '')) {
        //     fullUrl = new URL(relativeUrl, Cypress.config('baseUrl') || '').href;
        // } else {
        //     fullUrl = new URL(Cypress.config('baseUrl') || '').href;
        // }
        fullUrl = relativeUrl;
        cy.step(`Navigate to: ${fullUrl}`);
        cy.intercept('GET', fullUrl, { log: false }).as('page');
        cy.visit(fullUrl, { failOnStatusCode: false });
        cy.wait('@page', { log: false }).then((interception) => {
            const statusCode = interception.response?.statusCode;
            if (statusCode === 403 || statusCode === 302) {
                cy.log('Log in');
                // cy.get('form[action="/oauth/start"]').submit();

                cy.intercept('GET', fullUrl, { log: false }).as('otherpage');
                cy.get('form').submit();
                cy.wait('@otherpage', { log: false }).then((interception) => {
                    const statusCode = interception.response?.statusCode;
                    if (statusCode === 403 || statusCode === 302) {
                        cy.visit(fullUrl, {failOnStatusCode: false});
                    } else if (!interception.response || statusCode !== 200) {
                        console.log("aaaa")
                        console.log(interception.response);
                        throw new Error(`Failed to visit '${fullUrl}'. Status code: ${statusCode || 'unknown'}`);
                    }
                });
            } else if (!interception.response || statusCode !== 200) {
                console.log("aaaa")
                console.log(interception.response);
                throw new Error(`Failed to visit '${fullUrl}'. Status code: ${statusCode || 'unknown'}`);
            }
        });
    }
});

declare global {
    namespace Cypress {
        interface Chainable<Subject = any> {
            /**
             * `clear()`s the current contents and then `type()`s in the given `text`
             */
            fill(text: string, options?: Partial<TypeOptions>): Cypress.Chainable<JQueryWithSelector>

            /**
             * Sets the default origin for the test to `url`.
             *
             * Workbenches reply to unauthed requests with a 302 redirect to oauth page on a different origin.
             * Therefore, a test will end up with the origin of oauth as its main origin.
             * Every interaction with the workbench after logging in would have to be wrapped in a `cy.origin()` block.
             *
             * This can be overcome if we mock the initial visit to return 200 and establish the origin.
             */
            establishOrigin(url: string): void
        }
    }
}
