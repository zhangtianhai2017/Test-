/**
 * Protocol barrel — re-exports every schema and inferred type. Consumers
 * (server, tests, UE mirror generator) should import exclusively from here
 * so that moving schemas between files stays a zero-churn refactor.
 */

export * from "./frames.js";
export * from "./client.js";
export * from "./server.js";
