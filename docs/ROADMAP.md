# Roadmap

Capabilities, and what having them would let you do. Deliberately no file
paths, no interfaces, and no partial implementations left in the tree to hint
at shape — an unbuilt thing described precisely enough to build is either a
specification somebody else can ship first, or a promise this repository has
not earned yet.

Nothing in the shipped code says TODO, stub, not-implemented or coming-soon. A
provider socket reporting `implemented: false` is a runtime fact about this
build, not a hint about the next one.

---

## Shipped

Everything below is installable today and exercised by the suite. It is here
because a roadmap that does not say where the line is drawn is a wish list.

- An explicit, enforceable window address space carried between stateless
  requests.
- A gate at every tool call and every model egress, with a configured-but-
  unimplemented provider failing **closed**.
- A hash-chained containment record, and a verifier a third party can run
  against records they hold without trusting the system that produced them.
- Three model providers, each admitted and attested, prompts digested.
- Semantic drift measurement against a declared per-window threshold.
- Eighteen installable targets across nine platforms, every manifest generated
  from one declaration.
- Replay of a public agent-intrusion corpus, and the findings the reconstructed
  record supports.

---

## Next

**Enforcement that holds across a process boundary.** Today the record is
complete within one deployment. The interesting case is a formation whose parts
run in different processes, on different machines, under different operators —
and a claim about containment that only holds inside one of them is not a claim
about the formation.

**A semantic provider worth configuring.** The gate's provider interface is
real and the null-object default is honest, but structural address validation
is the floor. What sits above it is the part that decides whether a request is
*the kind of thing* this window should be making, rather than whether it is
well-formed.

**Evidence that survives the system that produced it.** The chain is verifiable
and it is also local. Evidence an operator can publish, and a third party can
check years later against a system neither of them still runs, is a different
problem from evidence an operator can read today.

**Formation-level questions.** The record answers "what did this window reach".
It does not yet answer "was this formation the right shape for this task, and
did it stay that shape" — which is the question an operator actually has at
3 a.m.

**More surfaces than one team can watch.** Every platform that gains an agent
surface gains a boundary. The work is keeping one declaration authoritative as
that number grows, rather than acquiring a second list.

**Client libraries beyond Python.** A caller in another language should be able
to open a window and make an attributed, gated call without hand-writing the
JSON-RPC envelope and the routing headers. Reaching that means a library a
reader can install and import and have working — built, typechecked and
exercised against the endpoint by the suite — which is a higher bar than a
transport fixture that demonstrates the wire format, and the bar a client has
to clear before it earns a distribution row.

---

## Not planned

Stated because absence reads as oversight otherwise.

- **A model.** This is the plane around execution, not execution. The model and
  the harness stay external, and every provider SDK stays optional.
- **A hosted control plane.** The evidence belongs to whoever ran the system.
- **Motive inference.** The incident capability reports
  `answerable_from_the_record: false` for "why", and that is a permanent answer
  rather than a gap. Motive is not an observable; a system that produced one
  from a ledger would be inventing exactly what a careful investigation refuses
  to invent.
