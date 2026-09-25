"""Host adapters.

An adapter's entire job is to normalize its host's tool-call event into a
`ToolEvent` and translate a `Decision` back into whatever that host understands.
Everything else lives in `gate.core`, which imports no host.

Hosts differ in what they can do with a decision, and the protocol degrades
honestly rather than pretending otherwise: a host that can block a call gets
`enforce`; a host that can only watch gets `observe` and is *reported as*
observe-only. Neither may masquerade as the other, because a containment number
that cannot say which one produced it is not a measurement.
"""
