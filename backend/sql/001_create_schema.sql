create table if not exists users (
    id            serial primary key,
    username      varchar(32) unique not null,
    password_hash text,
    api_key_hash  text,
    preferences   jsonb not null default '{}'
);

create table if not exists user_tickers (
    user_id    integer not null references users(id) on delete cascade,
    ticker     varchar(10) not null,
    sort_order integer not null default 0,
    primary key (user_id, ticker)
);

create table if not exists positions (
    id         serial primary key,
    user_id    integer not null references users(id) on delete cascade,
    ticker     varchar(10) not null,
    shares     numeric not null,
    cost_basis numeric not null,
    opened_at  timestamptz not null default now()
);
