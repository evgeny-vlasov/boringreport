# Telegraph and Telegram publication

The owner authorized automatic weekly posting to **@dots_and_lines**. Existing Gmail delivery remains the first independent delivery step.

After sending email and pushing the issue archive, `server_runner.py` calls `publisher.py publish --scheduled` when `~/.config/boringreport/publishing.json` has `enabled: true` and `mode: "auto"`. It publishes Russian and English Telegraph articles, then sends exactly four separate channel posts in order:

1. Russian PNG only, captioned `Boring Report №NN — DD.MM.YYYY` using the issue date.
2. The complete prepared `telegram-ru.html` message, with paragraph breaks translated to Telegram-compatible HTML. Source text, emphasis and citation links are preserved; article links are not appended.
3. A bold linked report heading for the Russian Telegraph article, with a short Russian language label.
4. A bold linked report heading for the English Telegraph article, with a short English language label.

All text posts enable link previews. The English image is never uploaded as a separate channel photo, but it may appear in the automatic preview of the English article. No new channel messages are sent when generating a preview with `prepare`.

The images are ordinary R-generated PNGs. Telegraph embeds immutable, commit-pinned image URLs from the existing public GitHub report archive. The publisher checks that each public image is byte-identical to its local archived render. Telegram receives the Russian PNG directly through multipart upload, so the channel image does not depend on an external URL fetch. Telegram may recompress photo previews; the original PNG is available from the article image URL. GitHub raw asset availability and rate limits remain an external dependency for article images.

## Credentials and setup

Secrets remain outside Git in `~/.config/boringreport/`:

* `telegraph.json`: dedicated Telegraph account access token, created once by the publisher.
* `telegram.json`: bot token.
* `publishing.json`: approved channel, resolved immutable channel ID, enabled flag and publication mode. No bot token belongs here.

Credential files are `0600`. The Telegram setup helper binds only to loopback on port 8766, serves a nonce-protected form through an SSH tunnel, and verifies `getMe`, `getChat` and `getChatMember`. It requires a channel matching the approved destination and the bot's Post Messages permission before saving the token and enabling publication. It does not change webhook or update settings, so an existing bot can be reused. The helper can provide a private Telegraph account browser-login link for proofreading and editing published articles.

Copy `publisher.py` and `telegram_setup.py` into `~/.local/lib/boringreport/` when installing source changes. They require Python's standard library only. Run the setup helper with its directory on Python's import path (executing it directly does this automatically).

## Operator commands

```sh
# Publishes/updates articles and prints a channel-caption preview; sends no channel message.
python3 ~/.local/lib/boringreport/publisher.py prepare --issue YYYY-MM-DD

# Read-only bot and destination permission checks.
python3 ~/.local/lib/boringreport/publisher.py check

# Explicit manual publication to the configured channel.
python3 ~/.local/lib/boringreport/publisher.py publish --issue YYYY-MM-DD
```

## Retry and delivery records

Per-issue state is stored in `~/.local/state/boringreport/YYYY-MM-DD.publication.json`. Article paths are reused for updates rather than creating new copies. A lost createPage response is reconciled by exact title against the dedicated account's page list; ambiguity requires inspection.

All four posts, photo integrity and message lengths are checked before the first channel send. An oversized Russian message is rejected rather than truncated or split into extra posts. The research prompt should keep that publication view within Telegram's single-message limit.

Delivery is tracked per post in the `four-posts-v1` format. Before each send, the publisher persists `in_flight`. A successful response records that post's Telegram message ID; the entire issue is marked `sent` only after all four posts succeed. A definitive API rejection leaves the preceding posts recorded and permits retry of the rejected and remaining posts, without repeating the earlier ones. Short pacing between messages avoids bursting all four requests at once. If content or destination changes mid-publication, continuation stops for operator review.

Connection loss, timeout, server errors or an unreadable response produce an uncertain outcome. **Do not blindly clear `in_flight` or `uncertain`: inspect the channel first.** The Bot API has no general idempotency key for these operations. If the pending post exists, record its message ID and status `sent`; if conclusively absent, an operator can mark only that post `rejected` and set the overall status to `partial` before retrying. Completed older-format deliveries remain completed. Issues removed at the owner's request remain suppressed and are not reposted when the layout changes.

Publishing failures fail the delivery service and trigger its existing Gmail alert, while the email delivery record prevents repeat report emails on retries. When Gmail is unavailable, its alerts can fail too; consult the server journal.

## Verification

```sh
python3 ops/boringreport/test_publisher.py
python3 ops/boringreport/test_runner.py
```

Tests cover article sanitization, preservation of source text and links, harmless Telegraph-added markup, destination and permission checks, exact four-post order, Russian-only image upload, titled article links, enabled link previews, length checks, resuming a rejected post without duplicates, and suppression of blind retries after uncertain outcomes. Live preparation retrieves both saved article contents and checks their semantic content against the source.
