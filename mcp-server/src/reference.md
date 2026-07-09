# Strudel quick reference

A cheat sheet for writing patterns this MCP server can play via `eval_pattern`.
`evaluate()` here behaves like the Strudel REPL: **double-quoted strings are
mini-notation**, single-quoted strings are plain JS strings.

## Skeleton

```js
setcpm(120)          // tempo, cycles per minute (setcps(0.5) is the low-level form)
stack(               // layer independent voices — the "orchestra" model
  s("bd*4"),
  s("~ cp ~ cp"),
  s("hh*8").gain(0.4),
  note("c2 c2 eb2 g2").s("sawtooth").lpf(800)
)
```

`stack(...)` sums voices. Each agent/part owns one argument of the stack.

## Mini-notation (inside double quotes)

| Syntax | Meaning |
|---|---|
| `a b c` | sequence over one cycle |
| `a*4` | repeat 4× (faster) |
| `a/2` | stretch over 2 cycles (slower) |
| `~` | rest |
| `[a b]` | sub-group (nest to subdivide) |
| `<a b c>` | alternate one per cycle |
| `a,b` | parallel (polyphony within one string) |
| `a?` | 50% chance to play |
| `a!3` | replicate 3× (no speedup) |
| `a:2` | sample index 2 |
| `bd(3,8)` | euclidean: 3 hits over 8 steps |

## Sounds

- Drums: `bd sd hh oh cp rim lt mt ht cr rd` (add `.bank("tr808")`, `"tr909"`, `"RolandTR707"`).
- Synths: `s("sawtooth"|"square"|"triangle"|"sine")` with `note(...)`.
- GM instruments: `s("gm_acoustic_bass")`, `s("gm_epiano1")`, `s("piano")`, etc.
- `n("0 2 4").scale("C:major")` — scale degrees instead of raw notes.

## Notes & harmony

```js
note("c e g")                    // note names
note("c4 e4 g4")                 // with octave
n("0 1 2 3 4").scale("A:minor")  // degrees in a scale
chord("Cmaj7 Am7 Dm7 G7").voicing()   // chord symbols -> voiced notes
"c e g".add(note("12"))          // transpose up an octave
```

## Common effects (chain with `.`)

| Effect | Example |
|---|---|
| gain | `.gain(0.8)` |
| pan | `.pan(sine.range(-1,1))` |
| low/high-pass | `.lpf(800)` / `.hpf(200)` |
| resonance | `.lpq(10)` |
| reverb | `.room(0.5)` |
| delay | `.delay(0.4)` |
| distortion | `.distort(2)` |
| adsr | `.attack(0.1).release(0.4)` |
| speed / reverse | `.speed(2)` / `.rev` |
| swing | `.swing(0.1)` |

## Pattern transforms

```js
.fast(2) / .slow(2)          // time-scale
.jux(rev)                    // stereo: left normal, right reversed
.every(4, x => x.rev)        // every 4th cycle, reverse
.sometimes(x => x.fast(2))   // 50% of events
.rarely(x => x.speed(-1))
.mask("<1 1 0 0>")           // gate on/off over cycles
.struct("1 ~ 1 1")           // impose a rhythm onto a melody
.off(0.125, x => x.add(note("7")))  // echo, offset + transposed
```

## Signals (continuous modulators)

`sine cosine saw isaw tri square rand perlin` — use `.range(lo,hi)` and `.slow(n)`:

```js
.lpf(sine.range(200, 4000).slow(8))
.pan(perlin.range(-1, 1))
```

## Register allocation convention (for multi-part sessions)

To keep a multi-agent mix clean, assign frequency space per part:

- **Bass**: `note(...).lpf(...)` below ~200 Hz — one voice only.
- **Drums**: full-band but transient.
- **Pads/keys**: mids, `.lpf(2000).room(...)`.
- **Leads/perc**: highs, `.hpf(...)`.

Everyone shares `setcpm`, key, and bar count from the conductor spec.
