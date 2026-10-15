# Desktop conversation recovery

This patch preserves the combined display, voice speed, commands and agent permissions.

- Unsupported or failed playback releases the audio lock and rearms conversation
  mode after the current turn completes. The reply stays on screen.
- Browser autoplay denial remains explicit and retries on a user gesture. It is
  not treated as a successful playback or bypassed.
- Late ended/error/rejected-play events from old audio cannot stop a newer reply.
- A suspended microphone AudioContext is resumed. The display says listening
  only when that context is running, and retries resume on a page gesture.
- A disconnected microphone rearms capture when conversation mode is enabled.
  Explicit pause, mic-off and ownership changes still take precedence.
- Failed microphone setup releases tracks and closes its context.

The lifecycle test runs the real controller with fake browser devices, promises,
timers and audio events, including failure and stale-callback cases. It does not
prove Safari behavior on the owner's Mac. There is no acoustic interruption or
faster speech recognizer in this change. The microphone remains paused during
Jarvis playback to prevent echo loops.

The installer accepts the last confirmed installed desktop, `155d060d`, and retains
the existing backup, conflict detection, health check and rollback behavior.
