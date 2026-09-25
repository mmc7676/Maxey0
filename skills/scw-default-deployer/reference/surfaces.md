# Where the default SCW is created

The default deployer builds one contract, `maxey0_ss.scw_deployer.deploy_default_scw`,
and every surface below registers it through `ContextService.create_spec`.

| Surface | Call | Notes |
|---|---|---|
| MCP | `maxey0-ss.scw.create` (`scw_id`, `task`, `concept`, `parent_id`) | Needs the builder role. |
| REST | `POST /v1/scw/default-deploy` (`task`, optional `scw_id`, `parent_id`, `concept`) | `scw_id` defaults to `SCW0`. |
| REST | `POST /v1/context/scws` | Takes a full spec rather than the default contract. |

## The contract

- `constitution` is `DEFAULT_CONSTITUTION` plus the `task`: fail-closed isolation,
  explicit admission, addressed routing, events+provenance+replay observability,
  and a harness the host selects.
- `skills` is empty. `instantiate()` handles an empty skill list; the skill id the
  deployer used to name was registered in no context graph.
- `drift_threshold` is `0.15`. It is the default threshold for `maxey0-ss.scw.drift`.

## Refusals

A create is refused before anything is stored, so a refused id can be used again:

- the id already exists (MCP: error; REST: `409`);
- `parent_id` names a window that is not chartered (create the parent first);
- `concept` is not a string, or `skills` is not a list of strings.
