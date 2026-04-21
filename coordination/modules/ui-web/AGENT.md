# AGENT — ui-web module (FROZEN)

This module is **frozen in v1** per D-004. Read before touching.

## Status

**Frozen**. No new features. Bug fixes only if a bug makes the current
gh-pages deployment unusable.

## Purpose

2D HTML/CSS/Canvas front-end. Built with Vite + TS. Deployed to GitHub
Pages for iPad/phone browser play.

## Scope — what you own

- `packages/ui-web/`
- Static build artifacts on the `gh-pages` branch

## Why frozen

- v1 focuses on UE plugin (D-004). Adding new mechanics to this module
  would double the work and slow v1 shipping.

## When to unfreeze

- After v1 UE ships, a v1.5 task will port the new mechanics (heat, morale,
  bluff, tells) back to this UI. Until then, don't.

## Allowed tasks

1. Fix a broken build (e.g. dep vulnerability).
2. Fix a broken API call if `dealer-ai` schema field names change (which
   shouldn't happen — see dealer-ai AGENT.md).
3. Update the startup modal text strings if copy changes.

## Escalation triggers

- Any request that would add a new mechanic → PM decides whether to
  unfreeze early (probably not in v1).
