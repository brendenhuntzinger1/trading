# Setting up an Alpaca paper key safely

**Never paste a key or secret into chat, a file, a commit or an issue.** If one ever appears in a message, treat
it as leaked (see the last section).

**Alpaca does not document a read-only or data-only scope for personal API keys** (docs/ALPACA_DATA_AUDIT.md,
sources G and H). The safest available option is a key belonging to a **Paper Only** account. It cannot move real
money, because paper orders are simulated and not routed, but it *can* place simulated orders. The project's
paper processes never send orders to Alpaca. They only read market data.

## 1. Create the key (your browser, not this chat)

1. Sign up at alpaca.markets as a **Paper Only** account. Do not open or fund a live brokerage account for this project.
2. In the Paper dashboard, generate an API key. Alpaca shows the secret once.
3. Don't store it in a text file, a note app, or this repository.

## 2. Store it as an environment secret for the cloud session

In the Claude Code environment settings (the cloud environment menu in the session's title bar → **Edit**), add
these under **Network secrets** (shown as **API credentials** in older app versions). If that section isn't
offered, add them as environment variables:

| Variable | Value |
|---|---|
| `TRADELAB_PAPER_APCA_API_KEY_ID` | the paper key ID |
| `TRADELAB_PAPER_APCA_API_SECRET_KEY` | the paper secret |
| `TRADELAB_PAPER_APCA_BASE_URL` | `https://paper-api.alpaca.markets` |

A new session picks them up. The names start with `TRADELAB_PAPER_` on purpose:
`tradelab/execution/secrets.py` refuses to start a paper process if any `TRADELAB_LIVE_*KEY`/`*SECRET` variable
is present. Never create `TRADELAB_LIVE_*` variables.

## 2b. Later only: GitHub repository secrets (for scheduled stock paper runs)

Not needed for research. Only when a stock paper workflow is approved and merged:

1. On GitHub: repository **Settings → Secrets and variables → Actions → New repository secret**.
2. Add `TRADELAB_PAPER_APCA_API_KEY_ID` and `TRADELAB_PAPER_APCA_API_SECRET_KEY` with the same paper values.
3. Workflows read them as `${{ secrets.TRADELAB_PAPER_APCA_API_KEY_ID }}`. GitHub masks them in logs and does
   not pass them to workflows triggered from forks.

Never add `TRADELAB_LIVE_*` secrets. Use the same rotation steps (§4) for both places.

## 2c. Run the checks (in a new session, after the secrets exist)

    .venv/bin/python scripts/pit_verify_alpaca.py --quick    # is it a paper key? historical SIP or IEX only?
    .venv/bin/python scripts/pit_verify_alpaca.py            # data gates B7.1-B7.5 (about 15-40 minutes at 200 calls/min)
    .venv/bin/python research/orb/study.py gates             # read the gate report; the study runs only if B7.1-B7.3 pass

Without the secrets, the script prints a message and exits with code 2. It runs nothing and writes nothing.
The full run writes:
- `data/stocks/verify_<date>.json` (gitignored);
- a summary table appended to `docs/ALPACA_DATA_AUDIT.md`.

Neither contains the key.

## 3. How I will verify it is a paper key, without revealing it

- I will call `GET https://paper-api.alpaca.markets/v2/account` and `GET https://api.alpaca.markets/v2/account`
  with the key in request headers, and report only:
  - the two HTTP statuses;
  - the paper account's status field.

  A paper key must authenticate on the paper host and be rejected by the live host
  (`verify_paper_key`). If it is not confirmed as a paper key, the data gates stop before any other request.
- The client refuses, in code and before any request, every endpoint except market data (bars, quotes,
  trades), the asset master, the calendar and the account status check. Orders, positions, watchlists and
  account configuration are unreachable (`tradelab/pit/alpaca_sip.py`, `check_endpoint`; tested).
- Alpaca states that paper and live keys are separate. I *expect* a live key to fail authentication on the
  paper host, but no official page I read says so. I will treat "authenticates on `paper-api`" as supporting
  evidence, not proof. The decisive control is that you create only a Paper Only account.
- I will then make one historical-data request with `feed=sip`, `end` more than 15 minutes ago, and report
  whether it is permitted. That settles the IEX-only question.
- Logs pass through `RedactingFilter`; keys are never printed, written to disk, or included in errors.

## 4. Rotation and revocation

- Rotate every 90 days, or immediately after any suspected exposure:
  1. In the Alpaca dashboard, regenerate the key; the old key stops working.
  2. Update the environment secrets, and the GitHub secrets if they exist.
  3. Start a new session.
- Resetting a paper account also requires regenerating credentials (Alpaca FAQ).
- To revoke permanently, delete the key in the dashboard, then remove both secrets.

## 5. If a key leaks

1. Regenerate it in the Alpaca dashboard at once, which invalidates the old key.
2. Check the paper account's order history for activity you didn't cause.
3. Replace the environment secrets, then search the repository history and chat for the leaked string.
4. Because the key is paper-only, no real money is at risk. Treat it as a rehearsal for the live-key procedure,
   which this project does not use.
