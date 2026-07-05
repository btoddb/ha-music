# Agents

<!--

  This is the shared generic AGENTS config.  Paste this in your repo's AGENTS.md file.

  !!! DO NOT CHANGE ANYTHING BETWEEN THIS COMMENT AND THE END COMMENT !!!

 -->
# General Agent Rules

This file provides guidance to AI agents for working with code in this repository.

**constraint** Follow all the rules in all files in directory, [ai-rules](./ai-rules/).
**constraint** Add new general project rules to [PROJECT_CONTEXT.md](./ai-rules/PROJECT_CONTEXT.md).
**suggestion** If a new feature has a lot of new rules, create a new rule file in [ai-rules](./ai-rules/), purely for organization.  Otherwise add it to PROJECT_CONTEXT.md

- If you can't make a required change, give clear instructions on how I must manually change it.  Assume I'm a 5 year old that knows how to read and write, but I know nothing else.

## New Code

**constraint** With all new code written, a unit test case must also be added.  Old code in the same file that doesn't have coverage should be left untested, but produce a note in the plan or result.  Untested code in unrelated files should be left untested and without a note.

## Git

- Work on a fresh branch from `main`; never edit directly on `main`.

## Specs

- Keep the living spec in `requirements/spec/` synchronized with workflow
  behavior changes.

## Coding

- For new code, always create a unit test
  - For Typescript, use Vitest
  - For Java, use JUnit 6
  - For Python, use Pytest

<!-- end of shared AGENTS.md -->