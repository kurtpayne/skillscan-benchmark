# About — why this exists

I set out to answer a narrow, practical question: **how far can you get detecting malicious AI-agent
skills *cheaply* — without shipping the skill off to a commercial API (privacy / third-party disclosure),
without burning tokens, and without needing a GPU?** If a defender could catch bad skills with local,
free, static analysis, that's the answer everyone wants.

So I built the whole local stack — free and open-source, to answer the question, never to sell — a
detection-rule engine, a fine-tuned small local classifier, intel databases, a daily threat-research
cadence — and then measured it honestly. The answer was
uncomfortable, and it's the opposite of what I hoped: **the cheap, local, private approach doesn't work
— and the only thing that *does* is the exact expensive option the question was trying to avoid.**
Measured on attacks I did **not** write, static rules are unusable either way — they miss most of it
(13–32% recall for the signature scanners) or, in the one case that fires, block almost everything
(a free static tool hits 98% recall at a 97% false-positive rate). The cheap small models barely beat
the signature scanners. A *flagship* frontier model reading the skill catches **81%** at a low
false-positive rate (recall measured on the independent set; the false-positive rate on our in-house
benign set, since the independent set ships no benign cases) — but that means GPUs or a commercial API,
burned tokens, and shipping your files
to a company. Detection is real. **Capability is the price**, and it's sold by the token.

The scanner I built was **free and open-source — never a product, never for sale.** It didn't clear the
bar, so I retired it. This scoreboard is what I built instead.

## Where the static-rule road runs out

**It barely sees novel attacks.** A signature only fires on behavior it already has a pattern for.
Disguised or never-before-seen skills sail through — static scanners, including the ones big vendors
ship, catch single digits to low double digits on disguised malicious skills. Not because they're badly
built; because pattern-matching can't read *intent*.

**It punishes legitimate-but-scary skills.** The flip side of "match risky-looking patterns" is firing
on dual-use ones — a real auth tool that reads a token and calls an API looks a lot like exfiltration
to a rule. So you pay in false-positives on exactly the legitimate skills people actually run.

**And the thing that *works* isn't cheap, local, or private.** Having a model read the skill beats
static rules — but "use an LLM" is not advice until you say *which* one. On an independent benchmark I
didn't author, the same 84 attacks score **23% to 81%** depending on the model: cheap/small models
(gpt-4o-mini 23%, claude-haiku 26%) barely beat static, mid-tier gpt-4o hits 38%, and only the flagship
(claude-sonnet 81%, opus ties it in the headline run) actually clears bar. (The models score higher on my *own* corpus — dramatically so
for the cheap ones, which is the tell — because an LLM recognizes LLM-written test cases, and I helped
write that corpus with these models, so I don't headline it; the independent numbers are the honest
ones.)

Detection quality climbs with model capability, then plateaus — and there's no cheap
/ local / private way to buy that capability: managed gateways block the requests as "prompt injection,"
self-hosting hits structured-output and throughput limits, and the direct frontier APIs that work mean
feeding malware to a commercial account. The accuracy and the cost are the same coin — which is the
whole point, and the part that "just use an LLM" advice usually leaves out.

So I stopped — not to ship a better scanner, but because I won't keep a project that objectively doesn't
work. And I'd come to suspect the approach itself is the mismatch: this is **antivirus tactics —
signatures, IOC matching, pattern-scanning — pointed at what are really *knowledge documents*,**
natural-language instructions whose harm depends on intent and context, not a matchable pattern. You
can't virus-scan a sentence for bad intent. So I measured the field instead.

## What this is

An independent scoreboard that grades AI-skill security **scanners** — not skills, and not a
certification. I have **nothing to sell**: the scanner I built was free and open-source (never a
product), now retired — so there's no tool to push and no vendor to protect. **Disclosure:** I still maintain some open-source skill tooling under `skillscan-*` (now
retired); none of my own tools are graded against the products here.

**Full disclosure on the *who*:** I'm not a security researcher — I'm a curious software engineer. I saw
a gap in how much trust we hand an agent the moment we install a skill; it happened to be security-shaped,
so I built something, measured it, and followed the result. The turn at the end — that this is a *trust*
problem, not a *detection* one — is just what falls out of measuring it honestly.

**Scope:** this measures **read-time** detection — static rules and one-shot LLM reads of a skill
*before* it runs. **Dynamic runtime analysis** (sandboxing, syscall/eBPF monitoring) is a different,
complementary category and deliberately out of scope; "static vs. LLM reading" is the read-time
comparison, not a claim that read-time is the only way to catch a bad skill.

- **Corpus private** (so nobody can train to the test); **method, code, and aggregate results
  public**; anyone can reproduce the pipeline on their own data (see Reproduce).
- Pre-specified-then-frozen method, reviewed before publishing.
- Numbers are **directional** — the real-wild sample set is small and we say so loudly.

## What the data says

The field is filling with skill scanners making strong claims. Held to a measured, reviewed test, the
shape is clear and a little uncomfortable: **the approach most of them ship — static rules — can't find
novel attacks and false-positives on legitimate ones; and the approach that *works* (a top frontier
model reading the skill) only works at the top of the model-cost ladder — cheap and local variants fail,
and the one that clears 80% runs only if you pay in tokens, GPUs, and shipping content to a commercial
API.** Detection is achievable; you just can't get it cheaply, locally, or privately. Others are walking
the same road I did. The numbers here are what they find at the end of it.

This isn't "give up" — it's "stop looking here." The one thing that works isn't a control you can *own*:
you transmit every skill to a third-party commercial API, pay per scan forever, depend on a model that
can be deprecated or repriced, get verdicts whose reproducibility the provider controls, and can't
independently own, pin, or audit it the way you could a local artifact.

The ceiling isn't
an implementation bug — it follows from the information available at read time: a scanner sees text and
code, not future intent, runtime context, network behavior, or credential use, so it can't reliably tell
a benignly-used capability from a maliciously-used one.

So read-time review should be a **linting and
triage layer, not the security boundary**. The boundary needs to move closer to execution — capability
isolation, runtime permissioning, provenance / signed identity, behavioral monitoring, constrained tool
APIs. That's a direction the data motivates, not a finding this board measures — but it's where I'd look
next.

Built solo and independent. Spot a factual or method error? Corrections welcome from anyone.
