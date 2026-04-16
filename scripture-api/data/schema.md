# taxonomy.json Schema

## Top-level

```json
{
  "topics": [ <Topic> ]
}
```

---

## Topic

| Field             | Type              | Description |
|-------------------|-------------------|-------------|
| `id`              | string            | Unique snake_case identifier used in API responses and classifier output |
| `name`            | string            | Human-readable topic name |
| `cluster`         | string            | Grouping label for related topics (e.g. "Emotional Distress", "Faith & Belief") |
| `description`     | string            | Pastoral description of the topic; informs framing tone and scope |
| `intent_examples` | string[]          | Representative phrases a user might write; used in classifier prompt |
| `topic_variants`  | TopicVariant[]    | Sub-types within the topic that may call for different passage selection or framing |
| `passages`        | Passage[]         | Curated scripture passages for this topic |
| `caution_flags`   | string[]          | Pastoral cautions for this topic (e.g. clinical referral, avoid minimizing) |
| `editorial_notes` | string            | Curator notes on passage selection rationale and emphasis |

---

## TopicVariant

Variants capture meaningful sub-types within a topic where the pastoral situation, and therefore the appropriate passage selection or framing emphasis, differs. The classifier may identify a variant when the user's input contains clear signals; it returns `null` for `variant_id` when the variant is ambiguous.

| Field            | Type     | Description |
|------------------|----------|-------------|
| `id`             | string   | Unique snake_case identifier scoped within the topic (e.g. `intellectual_doubt`) |
| `label`          | string   | Human-readable variant name (e.g. `"Intellectual Doubt"`) |
| `description`    | string   | What distinguishes this variant pastorally — how the need differs from the general topic and from other variants. Should note which passages are most relevant to this variant. |
| `intent_signals` | string[] | Phrases that suggest this variant over others or over the general topic. Used in the classifier prompt alongside `intent_examples`. |

### Variant design guidelines

- A variant should represent a genuinely different pastoral situation, not just a different severity of the same situation.
- Each variant's `description` should note which existing passages in the topic are most relevant to it — variants do not have their own passage lists; they guide framing emphasis.
- `intent_signals` should be distinct from the parent topic's `intent_examples`. If a signal would trigger the general topic equally well, it belongs in `intent_examples`, not `intent_signals`.
- Aim for 2–3 variants per topic. More than 3 usually indicates the topic should be split.

---

## Passage

| Field          | Type   | Description |
|----------------|--------|-------------|
| `reference`    | string | Scripture reference in standard format (e.g. `"Philippians 4:6-7"`) |
| `weight`       | string | `"primary"` · `"supporting"` · `"contextual"` — controls which passages are fetched by default |
| `rationale`    | string | Why this passage fits this topic; informs Claude's pastoral framing |
| `context_note` | string | Hermeneutical caution or reading note; included in framing context |

### Weight semantics

| Value         | Meaning |
|---------------|---------|
| `primary`     | Fetched and framed in every response for this topic |
| `supporting`  | Available for richer responses or when a variant calls for it |
| `contextual`  | Background material; not fetched by default |
