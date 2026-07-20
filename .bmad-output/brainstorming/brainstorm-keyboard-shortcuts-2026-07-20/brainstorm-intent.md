# Keyboard Submit Shortcuts — Intent

## Goal
Speed issue creation and parked-issue replies with a predictable, additive keyboard submit path without weakening existing safeguards or fallback interaction.

## V1 behavior
- `Meta+Enter` and `Control+Enter` submit from the focused composer textarea in `NewIssueModal` and `ReplyComposer`.
- Plain `Enter` and `Shift+Enter` preserve multiline editing.
- Existing visible Create/Send buttons remain the universal touch, voice-control, mobile, and fallback path.

## Interaction and guard contract
- React only to exact Meta-or-Control plus Enter while the relevant textarea has focus; call `preventDefault` only for that chord.
- Ignore active IME composition (including key code 229), an open slash picker, and repeated keydown events.
- Keyboard and button must converge on the same existing create/reply action and preserve blank, pending, attachment-upload, run-state, staged-control, and comment-vs-reply checks.
- The existing disabled button state supplies blocked/pending feedback; do not add toast, confirmation, or animation.
- Do not intercept browser-wide shortcuts or install a global listener.

## Source-grounded seam
Extend the shared `SlashPickerTextarea` with one optional submit-shortcut callback. It already owns slash-picker state and Enter handling, so it can suppress the chord for picker selection, composition, and repeats before each composer delegates to its existing guarded submit path. Modify that component, the two composers, and their existing Playwright specs; add no shortcut manager, hook, or new file.

## Accessibility and discoverability
- Show a compact visible `⌘+Enter` / `Ctrl+Enter` submit hint near the button.
- Add `aria-keyshortcuts` so assistive technology can discover the binding.
- Keep the labeled button and current focus/tab behavior; the shortcut is never the only submission path.

## Verification
Extend existing Playwright coverage to prove:
- both modifier chords submit through the same action as the button;
- plain and Shift+Enter preserve multiline text;
- open slash picker and active IME do not submit;
- disabled, pending, and uploading states do not submit;
- repeated keydown cannot create duplicate requests.

## Explicit non-goals
No global shortcuts, OS-sniffing layer, command palette, shortcut customization, chords, analytics, confirmation UI, mobile gesture, voice binding, cancel shortcut, org overrides, or broader keyboard navigation.

## Key risks
- Accidental submission during IME composition or slash-picker selection.
- Duplicate requests from key repeat or bypassed pending state.
- Keyboard/button behavior drifting if guard logic is duplicated.
- Browser, OS, or assistive-technology collisions if handling escapes textarea scope or prevents unrelated keys.
- Reply mode choosing `/reply` instead of `/comment` if the shortcut bypasses existing run-state logic.
