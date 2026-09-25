# I/O Contract — agents

The 13 registry agent(s) that appear in loops tagged `io-contract`, ordered by how often.

These are library entries, not shipped Claude Code agents. A loop stage names one of these; the subagent it is dispatched as is one of the four role agents this plugin ships — `maxey0-maker`, `maxey0-checker`, `maxey0-judge`, `maxey0-role`.

| agent | stages | specialization |
|---|---|---|
| Memory API Keeper (`Maxey30`) | 8 | FastAPI memory service |
| MCP Bridge (`Maxey32`) | 5 | MCP endpoints |
| Runner API Keeper (`Maxey31`) | 4 | Runner service |
| QA Agent (`Maxey71`) | 4 | Quality assurance |
| Retrieval Orchestrator (`Maxey14`) | 3 | High-quality retrieval |
| Code Interpreter Agent (`Maxey187`) | 3 | Code execution |
| Context Window Architect (`Maxey10`) | 2 | SCW construction & packing |
| API Gateway Agent (`Maxey66`) | 2 | API gateway |
| Frames Steward (`Maxey15`) | 1 | ReasoningFrames |
| Anchor Miner (`Maxey16`) | 1 | Anchor extraction |
| Anchor Metrics (`Maxey17`) | 1 | Anchor evaluation |
| SCW Packing Schema Agent (`Maxey180`) | 1 | Packing schema |
| SCW ReasoningFrame Schema Agent (`Maxey364`) | 1 | Schema mgmt |
