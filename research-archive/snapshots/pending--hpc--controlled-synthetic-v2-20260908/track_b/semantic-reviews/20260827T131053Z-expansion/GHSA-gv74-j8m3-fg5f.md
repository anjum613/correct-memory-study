# Semantic review record: GHSA-gv74-j8m3-fg5f

- rank: 13
- advisory: `GHSA-gv74-j8m3-fg5f`
- repository: `better-auth/better-auth`
- classification: `REJECTED_GATE_B`
- time_spent: approximately 30 minutes

## candidate_p_star

Only a caller holding an `owner` or `admin` role in an organization can create
an SSO provider linked to that organization.

## protected_effect

Authorization over organization-scoped identity-provider configuration and
the downstream creation of organization members through SSO provisioning.

## GATE_A

- status: `PASS`
- reasoning: The proposition fixes one endpoint action, one resource, and one
  exact role predicate and is falsifiable with an authenticated regular-member
  request.
- evidence:
  - The initial SSO registration implementation is in
    [`packages/sso/src/index.ts`](https://github.com/better-auth/better-auth/blob/a6a66d9c7ea078b5ce3a9db7a9354b2fff341ee6/packages/sso/src/index.ts).
  - The frozen advisory and fix use the same `owner`/`admin` role predicate for
    the same organization-linked provider record.

## attempted_candidate_S

- task identifier: `feat: SSO plugin with OIDC and SAML support (#3185)`
- issue: none established
- PR: [#3185](https://github.com/better-auth/better-auth/pull/3185)
- commit: `a6a66d9c7ea078b5ce3a9db7a9354b2fff341ee6`
- tree: `ba8fb8b71f01070356cfb45f036f29062fb96cec`
- date: `2025-06-27T20:19:19-07:00`
- files/functions: `packages/sso/src/index.ts`; `/sso/register`;
  `registerSSOProvider`
- relationship to procedure: This real task is the first repository state of
  the focal SSO plugin and organization-linked provider registration path.

## GATE_B

- status: `FAIL`
- affirmative evidence p*(S)=TRUE -- SUPPORTS:
  - None. No earlier implemented organization-linked SSO registration state
    with an affirmative owner/admin check was established.
- contradictory evidence -- CONTRADICTS:
  - The first `/sso/register` schema accepts caller-supplied `organizationId`.
  - Its only route middleware is `sessionMiddleware`; it checks authentication
    but not organization membership or role.
  - The handler writes `body.organizationId` directly into the new
    `ssoProvider` record with the authenticated user's ID.
  - The same initial implementation later uses an organization-linked provider
    to provision users into that organization.
  - Partial hardening commit
    `99834437b0ec359d091a1d886a590de88754fe69` added only a membership lookup;
    it still did not require owner/admin.
- merely consistent evidence -- MERELY_CONSISTENT_WITH:
  - Admin checks on companion provider-management endpoints added later cannot
    establish p*(S)=TRUE because the vulnerable create path already existed.
  - Organization authorization elsewhere in the repository does not prove the
    narrower SSO-registration proposition.
- reasoning: The focal proposition is false from feature introduction. The
  available history supplies initial vulnerability, partial membership
  hardening, and a final role fix—not a TRUE -> FALSE transition.

## candidate_I

- status: `NOT_ESTABLISHED_AFTER_GATE_B_FAILURE`
- reasoning: The feature-introduction commit cannot serve as an invalidating I
  without an affirmative earlier source implementation of the same SSO
  registration proposition. None exists in repository history.

## GATE_C

- status: `NOT_REACHED`
- reasoning: Gate B failed; the advisory fix is a FALSE -> TRUE transition and
  cannot be substituted for the required invalidating development transition.

## compatible_C

- status: `NOT_REACHED`
- reasoning: Compatible C is considered only after A/B/C survive.

## rapid_executable_feasibility

- status: `NOT_REACHED`
- reasoning: The candidate was rejected at Gate B and was not rescued through
  executable considerations.

## rejection_reason

`GATE_B_NO_AFFIRMATIVE_SOURCE_TRUTH_FALSE_FROM_FEATURE_INTRODUCTION`

## exact_fix_context

- partial membership-only commit: `99834437b0ec359d091a1d886a590de88754fe69`
- partial membership-only tree: `2d9d3a7f33ab26663ce1432a00b6e9ed26c75ef5`
- final admin-role fix commit: `86765f1597378f5c3deed1b80ca91faac0a6bf00`
- final admin-role fix tree: `3ea36f3fab328e83b1bf388c1540f703cb5bcfe5`
- ancestry: introduction -> final fix was mechanically verified.

## unresolved_questions

None that justify continued review. Broadening p* to unrelated organization
resources would change the resource and would not establish source truth for
the focal registration path.

## new_evidence_retrieved

Read-only filtered clone, initial-feature inspection, blame through the later
refactor, fix diff inspection, and ancestry verification. No model outcomes
were inspected.
