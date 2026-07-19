# Synthesis S-04 implementation started

Branch target: `agent/synthesis-s04-ui`

The public frontend implementation begins from the canonical S-04 documents on `agent/synthesis-s04-spec`.

Initial scope:

- replace the blueprint/profile browser with the intent-first S-04 workspace;
- make the centre prompt the first durable Ask turn;
- implement deterministic Explore, Design, Test, Build, Registered, failure, retry, and stale states;
- preserve the existing app shell and `Navigation | Centre | Detail / Ask` grammar;
- add Playwright coverage before live backend integration;
- keep all write/build behavior explicitly fixture-backed until the live runtime exists.

Control board: #33
