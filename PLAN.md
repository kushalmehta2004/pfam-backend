<!-- Read PLAN.md and CURSORRULES.md before we start. We are on Phase X. -->

Phase 1 — Foundation (Weeks 1–2) (COMPLETE)
Goal: Skeleton app running locally and on cloud. Auth working. DB connected.
1.1 Project Setup

 Create two GitHub repos: pfam-frontend and pfam-backend
 pfam-frontend: npx create-next-app@latest --typescript --tailwind --eslint --app
 pfam-backend: mkdir pfam-backend && cd pfam-backend && python -m venv venv
 Install backend deps: pip install fastapi uvicorn sqlalchemy alembic psycopg2-binary celery redis python-dotenv cryptography
 Create Neon project → copy DATABASE_URL to .env
 Create Clerk app → copy keys to .env
 Create Upstash Redis → copy URL to .env
 Deploy frontend to Vercel (connect GitHub repo)
 Deploy backend to Railway (connect GitHub repo, set env vars)

Cursor prompt for this phase:

"Set up a FastAPI project with this folder structure: app/main.py, app/db.py, app/models/, app/routers/, app/services/, app/workers/. Configure SQLAlchemy 2.0 with async engine using this DATABASE_URL env var. Configure Alembic. Create a health check endpoint at GET /health."

1.2 Database Schema — Core Tables
Write migrations for these tables in order:
organizations (id, name, billing_plan, stripe_customer_id, base_currency, data_region, created_at)
users (id, org_id, clerk_user_id, email, name, role [owner/admin/analyst/readonly], created_at)
stores (id, org_id, shopify_store_id, access_token_enc, access_token_iv, region, last_sync_at, sync_status)
ad_accounts (id, org_id, platform [meta/google/tiktok], account_id, account_name, access_token_enc, access_token_iv, currency, last_sync_at)
Cursor prompt:

"Create SQLAlchemy 2.0 models and Alembic migrations for these tables [paste above]. Use UUID primary keys. All tokens must have separate _enc and _iv columns for AES-256 encryption. Add org_id to every table. Generate the migration file."

1.3 Auth Integration

 Install @clerk/nextjs in frontend
 Wrap app/layout.tsx in <ClerkProvider>
 Create middleware.ts to protect all /dashboard routes
 In FastAPI: create app/auth.py that verifies Clerk JWT on every protected route
 On first login: create org + user row in DB (Clerk webhook → FastAPI)

Cursor prompt:

"Create a FastAPI dependency get_current_user that verifies a Clerk JWT from the Authorization header. Extract org_id from the JWT claims. Raise 401 if invalid. Every protected router must use this dependency."

✅ Phase 1 done when: You can log in, your org row exists in Neon, and /health returns 200 on Railway.











Phase 2 — Shopify Connector (Weeks 3–4)
Goal: Connect a Shopify store, import 90 days of orders, products, and COGS.
2.1 Shopify OAuth Flow

 Create a Shopify Partner account at partners.shopify.com (do this on Day 1 — free)
 Create a Custom App in Partner dashboard, set redirect URL to your Railway backend
 Implement OAuth: GET /connect/shopify/init → redirect to Shopify → GET /connect/shopify/callback → save encrypted token

Cursor prompt:

"Implement Shopify OAuth in FastAPI. Route 1: GET /connect/shopify/init — takes shop domain from query param, redirects to Shopify OAuth with scopes: read_orders,read_products,read_inventory,read_reports,read_fulfillments. Route 2: GET /connect/shopify/callback — exchanges code for access token, encrypts token with AES-256 (key from env AES_KEY), stores enc+iv in stores table. Use org_id from the authenticated user."

2.2 Shopify Data Ingestion — Celery Worker
Tables needed first (add migrations):
orders (id, org_id, store_id, shopify_order_id, created_at, total_amount_cents, total_discounts_cents, currency, customer_id, financial_status, fulfillment_status)
line_items (id, org_id, order_id, product_id, variant_id, sku, quantity, unit_price_cents, unit_cogs_cents, unit_cogs_source [shopify/csv/manual/estimated])
returns (id, org_id, order_id, line_item_id, refund_amount_cents, quantity_returned, reason_category [defective/wrong/change_mind/sizing/other], created_at)
Cursor prompt:

"Create a Celery task sync_shopify_store(store_id, org_id, days_back=90). It must: 1) decrypt the store access token from DB, 2) call Shopify Orders API paginated with created_at_min = now-days_back, 3) upsert orders by shopify_order_id+store_id (idempotent), 4) upsert line_items, 5) sync refunds into returns table, 6) pull cost_per_item from Shopify variants into unit_cogs_cents, 7) update stores.last_sync_at on completion, 8) handle Shopify rate limit (2 req/sec) with token bucket. All amounts stored in cents."

2.3 COGS Management

 POST /cogs — create/update COGS setting (sku/category/global scope)
 POST /cogs/import — CSV upload, parse SKU + value, bulk upsert
 Add cogs_settings table: (id, org_id, scope, scope_value, cogs_type [absolute/percentage], cogs_value_cents, source)

✅ Phase 2 done when: You connect your own Shopify dev store, trigger a sync, and see orders + line items + COGS in Neon.












Phase 3 — Ad Platform Connectors (Weeks 5–7)
Goal: Meta and Google ad data flowing into DB.
3.1 Meta Ads Connector
Manual step (do on Week 1, not Week 5): Go to developers.facebook.com → create Business app → apply for ads_read + ads_management permissions. App Review takes 2–6 weeks. Submit a screen recording of your app even if basic.
Tables needed:
campaigns (id, org_id, ad_account_id, platform_campaign_id, name, status, objective, daily_budget_cents, start_date, end_date)
ad_sets (id, org_id, campaign_id, platform_adset_id, name, status, daily_budget_cents)
ads (id, org_id, ad_set_id, platform_ad_id, name, status, creative_thumbnail_url)
ad_insights (id, org_id, ad_set_id, date, spend_cents, impressions, clicks, reach, conversions, conversion_value_cents, cpm_cents, cpc_cents, ctr)
Cursor prompt:

"Create a Celery task sync_meta_account(ad_account_id, org_id). It must: 1) decrypt Meta access token, 2) call Meta Marketing API v18.0 to get all campaigns, ad sets, ads for the account, 3) upsert each by platform ID + org_id, 4) for each ad set call the Insights endpoint for the last 90 days with fields: spend, impressions, clicks, reach, actions, action_values, 5) upsert ad_insights by (adset_id, date), 6) handle rate limit error code 17 with exponential backoff (5min, 15min, 60min), 7) store spend and monetary values in cents. Use the official Meta Marketing API Python SDK."

3.2 Google Ads Connector
Manual step: Go to ads.google.com/aw/apidevelopers → apply for developer token → Basic access is auto-approved.
Cursor prompt:

"Create a Celery task sync_google_account(ad_account_id, org_id). Use the google-ads-python library. It must: 1) decrypt Google OAuth tokens, 2) pull campaigns, ad groups (map to ad_sets table), ads using GAQL queries, 3) pull daily metrics (cost, impressions, clicks, conversions, conversion_value) per ad group for last 90 days, 4) upsert into campaigns/ad_sets/ads/ad_insights tables using same schema as Meta, 5) map gclid from Shopify order UTM params to Google campaign IDs, 6) handle quota limits with daily budget tracking. Store platform='google' on all records."

3.3 Sync Scheduler
Cursor prompt:

"Create a Celery Beat schedule that runs: sync_all_shopify_stores every 60 minutes, sync_all_meta_accounts every 60 minutes, sync_all_google_accounts every 60 minutes. Each master task queries active stores/ad_accounts and fans out individual sync tasks. Add a manual trigger endpoint POST /connectors/{id}/sync that queues an immediate sync with a 5-minute cooldown enforced via Redis."

✅ Phase 3 done when: You connect a real (or test) Meta/Google ad account and see campaigns + daily spend in your DB.














Phase 4 — Attribution Engine (Weeks 8–11)
Goal: Every Shopify order is attributed to a campaign. This is the core of PFAM.
Table needed:
attributed_orders (id, org_id, order_id, ad_set_id, attribution_tier [1-5], confidence_score, attribution_method, matched_click_id, attributed_revenue_cents, window_start, window_end)
4.1 Tiers 1 & 2 — Click ID Matching
Cursor prompt:

"Create app/services/attribution/tier1_tier2.py. Function: match_click_ids(org_id, window_start, window_end). Tier 1: Query orders where UTM params contain fbclid or gclid. Join to ad_insights to find which ad set ran that click ID on that date. Insert attributed_order with tier=1, confidence=0.95, matched_click_id. Tier 2: For unmatched orders, check if Meta Pixel / Google Tag conversion events (stored in ad_insights.conversions) match by conversion timestamp within 1 hour of order created_at. Insert with tier=2, confidence=0.85. Both tiers must be idempotent — skip orders already in attributed_orders."

4.2 Tier 3 — SKU-Weighted Attribution
Cursor prompt:

"Create app/services/attribution/tier3.py. For orders not matched in Tiers 1-2: 1) get all SKUs in the order, 2) find all ad sets that ran in the attribution window (from ad_insights), 3) for each ad set, calculate what % of its spend was on campaigns that historically drove sales of those SKUs (use last 30 days of Tier 1/2 data as the signal), 4) distribute attribution proportionally — the ad set with highest SKU-weighted spend share gets the attribution, 5) insert with tier=3, confidence=0.70. If no SKU overlap found, fall through to Tier 4."

4.3 Tier 4 — Blended Attribution
Cursor prompt:

"Create app/services/attribution/tier4.py. For orders not matched in Tiers 1-3: 1) get all active ad sets in the attribution window, 2) distribute attribution proportionally to their share of total spend, 3) the ad set with the highest spend share gets the attribution, 4) insert with tier=4, confidence=0.50."

4.4 Tier 5 — ML Model
Note: Build this in Phase 7 after you have real data. Skip for now, mark orders as tier=4 as fallback.
4.5 Attribution Orchestrator
Cursor prompt:

"Create app/services/attribution/engine.py. Function: run_attribution(org_id, window_start, window_end). It must run Tiers 1→2→3→4 in sequence. Each tier only processes orders not yet in attributed_orders for this window. After all tiers: calculate attribution_coverage_rate = attributed_orders / total_orders. Log this metric. This function is called by a Celery task after every sync completes."

✅ Phase 4 done when: You run attribution on real sync data and see attributed_orders rows with tier distribution — expect ~60-70% Tier 1/2, rest in 3/4.














Phase 5 — Profit Engine (Weeks 12–13)
Goal: Net profit calculated per ad set per time window. Stored and queryable.
Table needed:
profit_metrics (id, org_id, ad_set_id, window_type [daily/7d/14d/30d], window_start, window_end, spend_cents, attributed_revenue_cents, attributed_cogs_cents, estimated_returns_cents, platform_fees_cents, net_profit_cents, net_profit_pct, true_roas, order_count, attribution_coverage_pct, computed_at)
Also needed:
sku_return_rates (id, org_id, sku, trailing_90d_rate, trailing_180d_rate, manual_override_rate, last_computed_at)
Cursor prompt:

"Create app/services/profit/engine.py. Function: calculate_profit_metrics(org_id, ad_set_id, window_start, window_end). Steps:

Ad Spend: sum ad_insights.spend_cents for this ad_set in window
Attributed Revenue: sum attributed_orders.attributed_revenue_cents for this ad_set in window
Attributed COGS: for each attributed order, sum (line_items.unit_cogs_cents * quantity). If cogs missing, use cogs_settings percentage fallback
Estimated Returns: for each attributed order, sum (order.total_amount_cents * sku_return_rates.trailing_180d_rate). For orders < 45 days old use trailing rate. For orders > 45 days use actual returns from returns table
Platform Fees: attributed_revenue_cents * 0.029 + (order_count * 30) [configurable]
Net Profit = Revenue - Spend - COGS - Returns - Fees (all in cents)
Net Profit % = net_profit / attributed_revenue * 100
True ROAS = attributed_revenue / spend
Upsert into profit_metrics by (ad_set_id, window_type, window_start, window_end)
All values stay in cents throughout. Never convert to float for calculation."


SKU return rates worker:
Cursor prompt:

"Create a Celery task compute_sku_return_rates(org_id) that runs nightly. For each SKU: trailing_90d_rate = refunded_units / sold_units over last 90 days. trailing_180d_rate = same over 180 days. Upsert into sku_return_rates. Skip if manual_override_rate is set."

Profit recalculation trigger:
Cursor prompt:

"When COGS data is updated (POST /cogs), queue a Celery task to recalculate profit_metrics for all affected ad sets for the last 90 days. When sku_return_rates are updated, do the same."

✅ Phase 5 done when: You can query profit_metrics and see net_profit_cents per ad set per window with real numbers.
















Phase 6 — Automation Rules Engine (Weeks 14–16)
Goal: Rules evaluate after every sync. Actions execute via platform APIs. Everything logged.
Tables needed:
automation_rules (id, org_id, name, platform, scope [campaign/adset/ad], conditions_json, action_type [pause/reduce_budget/increase_budget/alert], action_params_json, guardrails_json, is_active, created_by, created_at)
rule_executions (id, org_id, rule_id, evaluated_at, entities_evaluated, entities_triggered, entities_blocked_by_guardrail, action_queued)
audit_log (id, org_id, actor_user_id, actor_type [user/system], action_type, entity_type, entity_id, platform, rule_id, metric_snapshot_json, api_request_json, api_response_code, api_response_json, created_at)
6.1 Rules Evaluator
Cursor prompt:

"Create app/services/rules/evaluator.py. Function: evaluate_rules_for_org(org_id). Steps:

Fetch all active rules for org
For each rule, determine scope (account/campaign/adset)
For each entity in scope, fetch relevant profit_metrics for the rule's rolling window
Evaluate condition: compare metric value to threshold using operator
Check guardrails: min_orders (from profit_metrics.order_count), min_spend, max_actions_per_day (check audit_log count for today)
If condition met AND guardrails pass: emit action to Celery queue
If condition met BUT guardrail blocks: log to rule_executions with blocked=true, no action
Insert rule_executions row regardless of outcome
Conditions supported: net_profit_cents, net_profit_pct, true_roas, spend_cents. Operators: lt, gt, lte, gte."


6.2 Action Executor
Cursor prompt:

"Create app/services/rules/executor.py. Celery task: execute_rule_action(rule_id, entity_id, entity_type, platform, action_type, action_params, metric_snapshot). Steps:

Idempotency check: if same rule+entity+window already executed in last 24h (check audit_log), skip
For action_type=pause: call Meta/Google API to pause the entity

Meta: PATCH /{adset_id}?status=PAUSED using requests with access token
Google: use google-ads-python to set ad group status to PAUSED


Record API request + response (status code + body) in audit_log
On API error: retry up to 3 times with backoff. After 3 failures: log failure, queue notification to admin
On success: queue notification event
audit_log rows are INSERT ONLY. Never update or delete them."


6.3 Action Reversal
Cursor prompt:

"Create POST /actions/{audit_log_id}/reverse. It reads the original action from audit_log, calls the platform API to reverse it (unpause, restore budget), and inserts a new audit_log row with actor_type=user. Show a confirmation dialog in the UI before calling this endpoint."

✅ Phase 6 done when: You create a rule, trigger a sync that meets the condition, and see the ad set paused in Meta/Google with a full audit log entry.
















Phase 7 — API Layer + Dashboard UI (Weeks 17–20)
Goal: Full frontend dashboard consuming real data.
7.1 FastAPI Endpoints
Build these in order — data before UI:
Cursor prompt:

"Create these FastAPI endpoints. All require auth (get_current_user dependency). All queries must include WHERE org_id = current_user.org_id:

GET /dashboard/overview — totals: spend, revenue, COGS, returns, net_profit for date range across all platforms
GET /campaigns — paginated list with profit_metrics joined. Params: platform, date_range, sort_by, status
GET /campaigns/{id} — campaign detail with ad sets and metrics
GET /campaigns/{id}/attributed-orders — paginated attributed orders for this campaign
GET /adsets/{id}/profit-metrics — profit metrics for ad set across all window types
GET /rules — list org's automation rules
POST /rules — create rule (validate conditions_json schema)
PUT /rules/{id} — update rule
POST /rules/{id}/toggle — flip is_active
GET /audit-log — paginated, filterable by date/platform/action_type
GET /reports/export — generate CSV, upload to Cloudflare R2, return signed URL"


7.2 Next.js Dashboard
Cursor prompt:

"Build the PFAM dashboard in Next.js 14 App Router. Use shadcn/ui components and Tailwind CSS. Use Recharts for all charts. Pages needed:

/dashboard — KPI cards (Net Profit, Spend, ROAS, Paused Today), Platform tiles, Campaign health heatmap (color by profit status), Automation activity feed
/campaigns — Sortable table with columns: Platform, Campaign, Spend, Revenue, COGS, Returns, Net Profit ($), Net Profit (%), ROAS, Confidence, Status. Color code Net Profit: green if >0, amber if -10% to 0, red if <-10%. Default sort by net profit ascending.
/automation — Rules list with ON/OFF toggle. Rule builder form with plain-English sentence: IF [metric] [operator] [value] THEN [action]
/settings/connectors — Connected platforms with sync status and manual sync button
All pages fetch from FastAPI backend. Use Clerk useAuth() for the JWT token in API calls."


7.3 Notifications
Cursor prompt:

"Create a Celery task send_notification(org_id, trigger_type, payload). It checks the org's notification settings and: 1) sends email via Resend SDK if email enabled, 2) posts to Slack webhook URL if configured, 3) sends HTTP webhook with HMAC-SHA256 signature if configured. Insert into notifications table with delivery status. Retry on failure up to 3 times. Trigger this task from the action executor after successful/failed rule actions, and from sync jobs on failure."

✅ Phase 7 done when: You can see real campaign profit data in the UI, toggle a rule on/off, and receive a Slack/email notification when it fires.














Phase 8 — Tier 5 ML Attribution (Weeks 21–24)
Goal: Train XGBoost model on your Tier 1/2 ground truth data to improve Tier 3/4 accuracy.
Prerequisite: You need at least 30 days of real data with Tier 1/2 matches before this is useful.
Cursor prompt:

"Create app/services/attribution/tier5_ml.py.
Training function train_attribution_model(org_id):

Query attributed_orders WHERE attribution_tier IN (1,2) — these are ground truth labels
For each order build feature vector: hour_of_day, day_of_week, days_since_last_order, product_category, order_value_cents, customer_is_returning, geo_country, recency_of_last_ad_interaction_hours
Label = ad_set_id (multi-class classification)
Train XGBoost XGBClassifier with 80/20 train/test split
Log accuracy, feature importance to a json file
Save model as model.pkl to Cloudflare R2 under org_id/attribution_model.pkl
Only train if >= 500 Tier 1/2 matched orders exist

Inference function predict_attribution(org_id, unattributed_orders):

Load model.pkl from R2
Build feature vectors for unattributed orders
Predict ad_set_id + get probability score as confidence
Insert attributed_orders with tier=5, confidence=probability_score
Fall back to Tier 4 if model not trained or confidence < 0.50

Schedule training as a weekly Celery Beat task."

✅ Phase 8 done when: Your attribution coverage improves vs Tiers 1-4 alone and the model file exists in R2.
















Phase 9 — Billing, RBAC, Polish (Weeks 25–27)
Goal: Real subscriptions, proper permissions, production-ready.
9.1 Stripe Billing
Cursor prompt:

"Implement Stripe billing in FastAPI. 1) POST /billing/checkout — create Stripe Checkout session for selected plan, return URL. 2) POST /billing/portal — create Stripe Customer Portal session. 3) POST /webhooks/stripe — handle events: customer.subscription.created → update org.billing_plan, customer.subscription.deleted → downgrade to free, invoice.payment_failed → send notification + set grace_period_ends. 4) Middleware that checks billing_plan on every API request and returns 402 if plan limit exceeded (e.g. Starter plan: block hourly sync, enforce 1 user limit). Store Stripe customer_id + subscription_id on organizations table."

9.2 RBAC Enforcement
Cursor prompt:

"Create a permissions system. Roles: owner, admin, analyst, readonly. Permissions matrix:

readonly: GET endpoints only
analyst: GET + POST/PUT on rules
admin: all except billing and ownership transfer
owner: all permissions
Create a FastAPI dependency require_permission(permission) that checks current_user.role against this matrix. Apply to every endpoint. Return 403 with message 'Insufficient permissions' if check fails. Never rely only on UI to enforce permissions — every API endpoint must check."


9.3 Production Checklist
Cursor prompt:

"Add these production hardening items: 1) Rate limiting on all public API endpoints using slowapi (100 req/min per IP, 60 req/min for auth endpoints), 2) CORS configuration allowing only the Vercel frontend domain, 3) Structured JSON logging on all services using Python logging + json formatter, 4) Sentry SDK integration in both FastAPI and Next.js with error capturing, 5) Database connection pooling via SQLAlchemy pool_size=10, max_overflow=20, 6) All secrets loaded from environment variables — no hardcoded values, 7) Add GET /health endpoint that checks DB connectivity and returns 200/503."

✅ Phase 9 done when: A test user can subscribe via Stripe, their plan limits are enforced, and Sentry captures real errors.









Manual Steps (Cannot Be Vibecoded — Do These Early)
StepWhenTimeCreate Shopify Partner account + custom appWeek 130 minApply for Meta ads_management App ReviewWeek 11 hr (wait 2–6 weeks)Apply for Google Ads developer tokenWeek 120 min (auto-approved basic)Create Stripe account + products for all 5 pricing tiersWeek 245 minClaim GitHub Student PackDay 15 minClaim AWS Educate + GCP creditsDay 115 minSet up Neon, Upstash, Cloudflare R2, Clerk accountsWeek 11 hr total    




Debugging Cheat Sheet
Sync job not running? Check Railway logs for the celery-worker service. Check Upstash Redis for queue depth.
Attribution coverage < 20%? Your Shopify orders don't have UTM params. Check if the Shopify store has UTM tracking set up in ad campaigns.
Meta API 190 error (token expired)? Implement token refresh: call GET /oauth/access_token?grant_type=fb_exchange_token with your app credentials.
Profit numbers look wrong? Check: are monetary values consistently in cents? Run SELECT unit_cogs_cents, unit_price_cents FROM line_items LIMIT 10 — if values look like dollars (e.g. 29 instead of 2900), you have a cents conversion bug.
Celery tasks not idempotent? Add a Redis lock: with redis_client.lock(f"sync:{org_id}:{window}", timeout=600): at the top of every sync task.
RLS / tenant leak? Run this test: create two orgs, query campaigns with Org A's token, verify zero Org B rows appear. If any Org B rows appear, you have a missing WHERE org_id = somewhere.

Build Order Summary
Phase 1  → Foundation (auth + DB schema)            Weeks 1-2
Phase 2  → Shopify connector + COGS                  Weeks 3-4
Phase 3  → Meta + Google connectors + scheduler      Weeks 5-7
Phase 4  → Attribution engine Tiers 1-4              Weeks 8-11
Phase 5  → Profit calculation engine                 Weeks 12-13
Phase 6  → Automation rules + execution + audit log  Weeks 14-16
Phase 7  → API layer + full dashboard UI             Weeks 17-20
Phase 8  → Tier 5 ML attribution model               Weeks 21-24
Phase 9  → Billing + RBAC + production hardening     Weeks 25-27
Data before UI. Schema before code. Tests before moving to next phase.
Total: ~6-7 months of serious focused work.