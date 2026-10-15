# Response processing and operational status

Claude calls mark the final allowed tool definition with an ephemeral cache
breakpoint. Channel tool scope, memory, model and response budget are unchanged.
The shared tool registry is not mutated. `AI_TOOL_CACHE_ENABLED=false` disables
this optimization. Only tool definitions are marked, not conversations or owner
records. Cache writes can cost more than ordinary input; reuse during repeated
turns can reduce repeated processing. No fixed speed improvement is promised.

The status panel reports the most recent completed model call duration and cache
read tokens. These are process-local metrics, not full voice latency or first
token time. Transcription, tool calls and audio playback remain separate.

`autonomy_status` and the status panel expose existing background/publication
gates and configured account/read-check state without credentials or network
requests. Configured does not mean verified; a stored read check does not verify
publishing permissions. They do not turn on flags or change approval policies.

Existing automatic organic publishing functions cover Facebook, Instagram,
YouTube and TikTok under their existing gates and daily cap. The latter can remain
private depending on app permissions. Purchases and Amazon listing publication
are not made autonomous by this patch. No account is connected by merely setting
a flag. No new purchases, listings, ads or messages are executed by diagnostics.

The background cycle now requests at most one original Facebook/Instagram post
when both existing publication flags are on, using the existing idempotent draft
publication tool. Missing credentials, daily caps and the owner's stop switch
remain enforced. Otherwise the cycle continues to prepare drafts only. This
does not add unattended Amazon purchases or supplier orders.

Reference: https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-use-with-prompt-caching
