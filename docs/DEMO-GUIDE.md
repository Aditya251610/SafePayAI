# Run the demo

A ten minute path through every role. The same guide is on the running site at `/guide`.

## What you are looking at

A buyer signs a spending mandate that sets what may be bought, and an AI agent drafts carts inside
it but never pays. When an order is late or lost, plain rules decide the refund, and a person
handles anything unusual. PayPal's sandbox takes the payment and sends the refund.

## Before you start

- **Sandbox only.** No real money moves. Every payment and refund is a PayPal sandbox test.
- **Slow first request.** The backend sleeps when idle, so the first request can take 30 to 45
  seconds. The app shows a waking-up notice. Do not stop; it continues on its own.
- **To pay you need a PayPal sandbox personal (buyer) account.** In developer.paypal.com go to
  Apps & Credentials, Sandbox, Testing Tools, Sandbox Accounts, Personal. A business account cannot
  be the buyer. Use those sandbox details only on PayPal's own page. Never put them in this repo or
  on this site.

## The walkthrough

Each account has one role. To change role, sign out from the top bar, then sign in as the next
account. Seeded accounts need the deployment to have them switched on
(`PS_APIGATEWAY_DEMO_PERSONA_LOGIN=true`); otherwise use Create account or Try the demo for the
buyer steps. On the site, each step has a button that opens the sign-in page with that account
already chosen.

### 1. A buyer signs a mandate

- **Sign in as:** `buyer-alex` (Explore a seeded account on `/login`)
- **Open:** `/mandate/new`
- **Do:**
  1. Fill in the cap, the per-cart limit, the shops in scope and the end date.
  2. Choose **Preview terms** and read the terms back.
  3. Choose **Sign mandate** before the signing window runs out. If it expires, preview again.
- **You see:** a signed mandate with its terms. Nothing can be bought outside it.
- **Notice:** a person signs. No one else can authorise spending.

### 2. State what you need, in words

- **Sign in as:** stay signed in as the buyer
- **Open:** `/intent`
- **Do:**
  1. Type what you want, for example a pair of headphones under a price you set.
  2. Choose **Propose cart**.
- **You see:** a draft cart from the seeded catalog, with every rule check listed. If the agent
  fails or is unsure you get a form instead.
- **Notice (AI):** the AI drafts. Rules check the draft against your mandate. The AI cannot approve
  or pay.

### 3. Approve the cart and pay at PayPal sandbox

- **Sign in as:** stay signed in as the buyer
- **Open:** `/cart/<id>`, opened from your draft
- **Do:**
  1. On the cart, choose **Approve cart**. You are sent to the PayPal sandbox.
  2. Sign in there with your own sandbox personal (buyer) account and approve the payment.
  3. You land on the **Back from PayPal** page. Choose **Check payment** if it still says pending,
     then **Track order**.
- **You see:** a captured order with its PayPal sandbox order and capture ids on the receipt.
- **Notice (PayPal):** PayPal's sandbox creates and captures the order. Test funds only.

### 4. The merchant ships it

- **Sign in as:** `merchant-trailhead`, `merchant-hearth` or `merchant-pixelwire`, whichever owns
  the item in your cart. Sign out of the buyer first.
- **Open:** `/merchant`
- **Do:**
  1. Paste the buyer's mandate id (it is in the address of `/mandate/<id>`) and choose **Show
     orders**.
  2. Choose **Ship this** on the order. Set the outcome profile to **late**, then choose **Mark
     shipped**.
- **You see:** a shipment labelled SIMULATED CARRIER, with a promised date.
- **Notice (Rules):** the carrier is our own simulated clock, not real carrier or PayPal data.

### 5. The operator makes it late

- **Sign in as:** `operator`
- **Open:** `/ops`
- **Do:**
  1. In the Demo clock panel choose **+7 days** (use **+1 day** to go in steps).
  2. Watch the cases list below fill in.
- **You see:** the simulated clock moves past the promised date. The late-order detector opens a
  case.
- **Notice (Rules):** a deterministic detector opens the case, not a person and not the AI.

### 6. The buyer accepts the refund offer

- **Sign in as:** `buyer-alex`
- **Open:** `/home`
- **Do:**
  1. Open the active case from your home page.
  2. Read why the rules made the offer, then choose **Accept offer**.
  3. If the refund is held, sign in as the operator, open `/ops`, choose **Unfreeze refunds** and
     confirm.
  4. If the app asks for your approval, follow the approve link it shows.
- **You see:** the case moves to a refund. It goes out through PayPal's refund API and is
  merchant-funded.
- **Notice (PayPal):** the rules set the amount. PayPal's refund API sends it, in the sandbox.

### 7. A reviewer decides what the rules could not

- **Sign in as:** `reviewer-demo`
- **Open:** `/review`
- **Do:**
  1. Open a case from the queue, if there is one.
  2. Choose a decision (propose a refund, propose a reship, decline or close), add a note and
     submit.
- **You see:** the case leaves the queue with your note attached. An empty queue means the rules
  decided everything so far.
- **Notice (A person):** a person decides unusual cases. A refund the reviewer proposes still needs
  the buyer's approval.

### 8. Read the hash-chained log

- **Sign in as:** any signed-in role
- **Open:** `/audit`
- **Do:** open the audit log and run the chain check.
- **You see:** every money action in order, each entry carrying the hash of the one before it.
- **Notice (Rules):** the log is append-only. The check re-reads the chain.

## Who is who

| Account              | Role     | What it can do                                                                  |
| -------------------- | -------- | ------------------------------------------------------------------------------- |
| `buyer-persona`      | Buyer    | Has a signed mandate, four orders, a refund and open cases to look through.     |
| `buyer-alex`         | Buyer    | Starts empty. Sign a mandate, state a need, pay, report a problem.              |
| `merchant-trailhead` | Merchant | Ships that shop's orders on the simulated carrier.                              |
| `merchant-hearth`    | Merchant | Ships that shop's orders on the simulated carrier.                              |
| `merchant-pixelwire` | Merchant | Ships that shop's orders on the simulated carrier.                              |
| `operator`           | Operator | Moves the simulated carrier clock and holds or releases the refund kill switch. |
| `reviewer-demo`      | Reviewer | Decides cases the rules hand to a person.                                       |

## Run it yourself

Whole stack with Docker:

```bash
cp .env.example .env
# edit .env: add your PayPal sandbox client id and secret
docker compose up
```

- Put your PayPal sandbox client id and secret in `.env`. Never commit that file.
- Optional: add a Gemini or Groq key so the AI can draft carts. Without one the app falls back to
  the plain form.
- Create the seeded accounts with `services/api-gateway/scripts/seed.py`. It reads the `SEED_*`
  password variables that you set yourself.
- To show the seeded-account picker set `PS_APIGATEWAY_DEMO_PERSONA_LOGIN=true` on the gateway.
- Open `http://localhost:3000`.

Web app only:

```bash
cd services/web
pnpm install
pnpm dev
```

Copy `.env.example` to `.env.local` and point `PS_WEB_GATEWAY_INTERNAL_URL` at a running gateway.
The app is at `http://localhost:3000`.

## Honest limits

- Sandbox only. No real money moves and no real PayPal account is used.
- The catalog is seeded, not a live marketplace.
- Carrier and delivery status is simulated by our own clock. It is not real carrier or PayPal data.
- The AI classifies and drafts only. On any error or low confidence it hands the case to a person.
- Refunds are merchant-funded, via PayPal's refund API.
- Not affiliated with or endorsed by PayPal.
