-- KAP "Yeni Is Iliskisi" data model (DuckDB)

-- 1) Structured data from Matriks new-business-api
CREATE TABLE IF NOT EXISTS new_business (
    url          VARCHAR PRIMARY KEY,  -- KAP disclosure link, unique per disclosure
    sym          VARCHAR,              -- ticker, e.g. ASELS
    date         DATE,
    cur          VARCHAR,              -- currency: TRY, USD, EUR...
    amount       DOUBLE,
    description  VARCHAR,              -- 'desc' in the API (reserved word in SQL)
    per          INTEGER,              -- balance-sheet period, e.g. 202506
    rt           DOUBLE,               -- deal value (TRY) / shifted revenue
    shf_ret      DOUBLE,               -- shifted revenue of that period
    tcmb_ex_rt   DOUBLE,               -- central bank FX rate used
    cum_rt       DOUBLE,               -- all deals in period (TRY) / shifted revenue
    mar_val_rt   DOUBLE,               -- deal value / market cap
    fetched_at   TIMESTAMP DEFAULT current_timestamp
);

-- 2) Full disclosure texts from Matriks news service (source:KAP tag:NewBusiness)
CREATE TABLE IF NOT EXISTS disclosures (
    news_id        VARCHAR PRIMARY KEY, -- Matriks news id
    kap_url        VARCHAR,             -- 'Orjinal Link' in content, joins to new_business.url
    headline       VARCHAR,
    symbol         VARCHAR,             -- may be empty in API, filled from headline
    published_at   TIMESTAMP,
    is_update      BOOLEAN,             -- 'Yapilan Aciklama Guncelleme mi?'
    is_correction  BOOLEAN,             -- 'Yapilan Aciklama Duzeltme mi?'
    form_json      VARCHAR,             -- parse_form() output as JSON text
    aciklama       VARCHAR,             -- free-text 'Aciklama' field, input for the LLM
    fetched_at     TIMESTAMP DEFAULT current_timestamp
);

CREATE INDEX IF NOT EXISTS idx_disclosures_kap_url ON disclosures(kap_url);
CREATE INDEX IF NOT EXISTS idx_new_business_sym_date ON new_business(sym,date);